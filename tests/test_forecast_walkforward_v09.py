"""Causal multi-fold walk-forward with sealed final holdout (synthetic only)."""
from dataclasses import replace
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import pytest

from moex_intelligence.crypto.forecast_walkforward import evaluate_purged_walkforward
from moex_intelligence.crypto.forecast_evaluation import evaluate_historical_baseline
from moex_intelligence.crypto.market import Candle

STEP=900


def rows(n=1600):
    base=int(time.time()//STEP)*STEP-(n+10)*STEP
    return [
        Candle(base+i*STEP,100+i*.015,100+i*.015+.4,
               100+i*.015-.4,100+i*.015,4.2,True)
        for i in range(n)]


def csv_file(path, candles):
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.writer(f)
        w.writerow(("open_time_ms","open","high","low","close","volume"))
        for c in candles:
            w.writerow((c.time*1000,c.open,c.high,c.low,c.close,c.volume))
    return path


def test_check_1_sealed_holdout_and_fold_boundaries():
    data=rows()
    report=evaluate_purged_walkforward(data,"BTCUSDT","15")
    assert report.mode=="PURGED_WALKFORWARD_RESEARCH_SEALED_FINAL"
    assert report.status=="EVALUATED_DEVELOPMENT_ONLY"
    assert report.folds_requested==report.folds_evaluated==3
    assert report.sealed_final.evaluated is False
    assert report.sealed_final.start_index==1280
    assert report.sealed_final.end_exclusive==1600
    assert report.sealed_final.closed_bars==320
    assert report.sealed_final.first_open_utc_seconds==data[1280].time
    assert report.sealed_final.last_close_utc_seconds==data[-1].time+STEP
    assert len(report.sealed_final.sha256)==64
    assert report.folds[0].validation_start_index==128
    assert report.folds[-1].validation_end_exclusive==1280
    assert all(f.result.status=="EVALUATED" for f in report.folds)
    assert all(f.result.origins>=30 for f in report.folds)
    assert all(f.validation_end_exclusive<=report.sealed_final.start_index
               for f in report.folds)
    assert "NOT scored" in report.note


def test_check_2_purged_boundary_and_fold_outcome_disjointness():
    report=evaluate_purged_walkforward(rows(),"BTCUSDT","15")
    outcome_times=set()
    for f in report.folds:
        assert f.purged_training_end_exclusive+f.purge_bars==f.validation_start_index
        assert f.purge_bars==8
        start,end=f.validation_start_index,f.validation_end_exclusive
        # Every score target lies within the current fold; none appears twice.
        for origin in range(start-1,end-8,8):
            for h in (1,2,4,8):
                future=origin+h
                assert start<=future<end
                key=(h,future)
                assert key not in outcome_times
                outcome_times.add(key)
        for score in f.result.horizons:
            assert score.observations==f.result.origins
    assert report.folds[0].purged_training_end_exclusive==120


def test_check_3_change_sealed_future_but_never_change_dev_scores():
    data=rows()
    before=evaluate_purged_walkforward(data,"ETHUSDT","15")
    final_index=before.sealed_final.start_index
    mutated=data[:final_index]+[
        replace(c,open=c.open*2,high=c.high*2,low=c.low*2,close=c.close*2)
        for c in data[final_index:]]
    after=evaluate_purged_walkforward(mutated,"ETHUSDT","15")
    assert before.folds==after.folds
    assert before.status==after.status
    assert before.sealed_final.sha256 != after.sealed_final.sha256
    assert before.sealed_final.start_index == after.sealed_final.start_index
    assert before.sealed_final.evaluated is False and after.sealed_final.evaluated is False


def test_check_3_open_trailing_candle_is_ignored_without_touching_seal():
    data=rows()
    r1=evaluate_purged_walkforward(data,"SOLUSDT","15")
    partial=Candle(data[-1].time+STEP,9999,10000,9998,9999,3,False)
    r2=evaluate_purged_walkforward(data+[partial],"SOLUSDT","15")
    assert r1==r2


def test_check_3_original_single_holdout_semantics_unchanged():
    data=rows()
    default=evaluate_historical_baseline(data,"BTCUSDT","15")
    start=max(120,math.floor(len(data)*(1-.30)))
    explicit=evaluate_historical_baseline(
        data,"BTCUSDT","15",evaluation_window=(start,len(data)))
    assert default==explicit


@pytest.mark.parametrize("window",[(119,1000),(120,2000),(130,130),
                                   (500,200),(120.,800),[120,800],
                                   (True,800),(130,),None])
def test_check_3_invalid_explicit_windows_rejected(window):
    if window is None:
        assert evaluate_historical_baseline(rows(),"BTCUSDT","15").status=="EVALUATED"
    else:
        with pytest.raises(ValueError,match="Evaluation window"):
            evaluate_historical_baseline(rows(),"BTCUSDT","15",evaluation_window=window)


@pytest.mark.parametrize("kwargs",[
    {"folds":1},{"folds":7},{"folds":True},
    {"final_fraction":.05},{"final_fraction":.51},{"final_fraction":float("nan")},
    {"final_fraction":10**400},
    {"embargo_bars":0},{"embargo_bars":7},{"embargo_bars":65},
    {"stride":1},{"stride":True},
    {"min_required_origins":0},
])
def test_check_4_reject_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        evaluate_purged_walkforward(rows(),"BTCUSDT","15",**kwargs)


def test_check_4_small_dataset_has_explicit_insufficient_status():
    r=evaluate_purged_walkforward(rows(1000),"BTCUSDT","15")
    assert r.status=="INSUFFICIENT"
    assert r.folds_evaluated<r.folds_requested
    assert r.sealed_final.evaluated is False


def test_check_4_too_short_history_rejected_without_false_statistics():
    with pytest.raises(ValueError,match="Not enough chronology"):
        evaluate_purged_walkforward(rows(180),"BTCUSDT","15")


def test_check_4_custom_embargo_and_fold_count():
    report=evaluate_purged_walkforward(rows(2200),"BTCUSDT","15",
                                       folds=5,embargo_bars=16,stride=8)
    assert report.folds_requested==5
    assert all(f.purge_bars==16 for f in report.folds)
    assert all(f.validation_start_index-f.purged_training_end_exclusive==16
               for f in report.folds)
    assert all(f.validation_end_exclusive<=report.sealed_final.start_index
               for f in report.folds)


def test_check_5_readonly_cli_shows_seal_and_never_changes_input(tmp_path):
    src=csv_file(tmp_path/"dataset.csv",rows())
    initial_hash=hashlib.sha256(src.read_bytes()).hexdigest()
    output=tmp_path/"walkforward.json"
    root=Path(__file__).resolve().parents[1]
    cmd=[sys.executable,str(root/"scripts/evaluate_walkforward_csv_v09.py"),
         "--input",str(src),"--symbol","BTCUSDT","--timeframe","15",
         "--output",str(output)]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=35)
    assert result.returncode==0,result.stderr
    payload=json.loads(result.stdout)
    assert json.loads(output.read_text(encoding="utf8"))==payload
    assert payload["source"]=="USER_SUPPLIED_CSV_UNVERIFIED"
    assert payload["final_status"]=="SEALED_UNSCORED"
    assert payload["development"]["sealed_final"]["evaluated"] is False
    assert payload["development"]["status"]=="EVALUATED_DEVELOPMENT_ONLY"
    assert payload["market"]["file_sha256"]==initial_hash
    assert hashlib.sha256(src.read_bytes()).hexdigest()==initial_hash
    # Existing report may never be overwritten or used as an input destination.
    report_hash=hashlib.sha256(output.read_bytes()).hexdigest()
    assert subprocess.run(cmd,capture_output=True,timeout=35).returncode==2
    assert hashlib.sha256(output.read_bytes()).hexdigest()==report_hash
    cmd[-1]=str(src)
    assert subprocess.run(cmd,capture_output=True,timeout=35).returncode==2
    assert hashlib.sha256(src.read_bytes()).hexdigest()==initial_hash


def test_check_5_deterministic_json_and_no_market_credentials():
    report=evaluate_purged_walkforward(rows(),"BTCUSDT","15").as_dict()
    dump=json.dumps(report,allow_nan=False,sort_keys=True)
    assert json.loads(dump)["sealed_final"]["evaluated"] is False
    assert "api_key" not in dump and "secret" not in dump.lower()
    assert "EVALUATED_DEVELOPMENT_ONLY" in dump
