"""Five independent gates for causal directional challenger research.

Synthetic fixtures only. Positive performance on synthetic trends is NOT a
prediction of real Bybit gains, calibrated confidence, or safe order execution.
"""
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

from moex_intelligence.crypto.momentum_candidate import (
    CANDIDATE_VERSION, momentum_envelope)
from moex_intelligence.crypto.momentum_evaluation import compare_momentum_to_rw
from moex_intelligence.crypto.forecast_walkforward import evaluate_purged_walkforward
from moex_intelligence.crypto.market import Candle

STEP=900


def series(n=1600,mode="trend"):
    base=int(time.time()//STEP)*STEP-(n+10)*STEP
    result=[]
    for i in range(n):
        if mode=="flat":
            p=100.
        elif mode=="zigzag":
            p=100+(.7 if i%2 else -.7)+i*.0001
        else:
            p=100+i*.12
        result.append(Candle(base+i*STEP,p,p+.4,p-.4,p,5.,True))
    return result


def save_csv(filepath,items):
    with filepath.open("w",newline="",encoding="utf8") as stream:
        w=csv.writer(stream)
        w.writerow(("open_time_ms","open","high","low","close","volume"))
        for c in items:
            w.writerow((c.time*1000,c.open,c.high,c.low,c.close,c.volume))
    return filepath


def test_check_1_trending_series_candidate_is_nonflat_and_math_is_finite():
    closes=[c.close for c in series()[-120:]]
    projection=momentum_envelope(closes)
    assert len(projection)==4
    for h,(lower,median,upper) in zip((1,2,4,8),projection):
        assert 0<lower<=median<=upper
        assert median>closes[-1],h
        assert all(math.isfinite(v) for v in (lower,median,upper))
    assert CANDIDATE_VERSION.startswith("shrunk-log-momentum")


def test_check_1_flat_price_is_not_artificially_predicted_up_or_down():
    prediction=momentum_envelope([100.]*120)
    assert prediction==((100.,100.,100.),)*4
    report=compare_momentum_to_rw(series(mode="flat"),"BTCUSDT","15")
    assert report.status=="EVALUATED_DEVELOPMENT_ONLY"
    for fold in report.folds:
        for h in fold.horizons:
            assert h.candidate_mae==h.rw_mae==0
            assert h.candidate_mae_gain_pct is None
            assert h.nonflat_actuals==h.candidate_nonflat_predictions==0
            assert h.candidate_direction_hit_rate is None
            assert h.rw_coverage==h.candidate_coverage==1
    json.dumps(report.as_dict(),allow_nan=False)


def test_check_2_paired_scoring_same_origins_as_flat_baseline():
    data=series()
    baseline=evaluate_purged_walkforward(data,"BTCUSDT","15")
    challenger=compare_momentum_to_rw(data,"BTCUSDT","15")
    assert challenger.status=="EVALUATED_DEVELOPMENT_ONLY"
    assert challenger.final_holdout_evaluated is False
    assert challenger.final_holdout_sha256==baseline.sealed_final.sha256
    for f,c in zip(baseline.folds,challenger.folds):
        assert c.origins==f.result.origins>=30
        assert c.skipped_origins==f.result.skipped_origins
        assert c.validation_start_index==f.validation_start_index
        assert c.validation_end_exclusive==f.validation_end_exclusive
        for old,new in zip(f.result.horizons,c.horizons):
            assert new.observations==old.observations
            assert new.rw_mae==pytest.approx(old.mean_absolute_error)
            assert new.rw_coverage==pytest.approx(old.empirical_coverage)
            assert new.rw_interval_score_pct==pytest.approx(old.mean_interval_score_pct)


def test_check_2_trend_gain_is_observed_not_mislabelled_validated():
    report=compare_momentum_to_rw(series(),"ETHUSDT","15")
    assert report.status=="EVALUATED_DEVELOPMENT_ONLY"
    assert "not verified predictive alpha" in report.note
    for fold in report.folds:
        for horizon in fold.horizons:
            assert horizon.candidate_mae_gain_pct>0
            assert horizon.candidate_mae < horizon.rw_mae
            assert horizon.candidate_direction_hit_rate==1.
            assert horizon.candidate_nonflat_predictions==horizon.nonflat_actuals


def test_check_2_zigzag_can_produce_negative_or_mixed_gain():
    report=compare_momentum_to_rw(series(mode="zigzag"),"SOLUSDT","15")
    assert report.status=="EVALUATED_DEVELOPMENT_ONLY"
    # No test assumes or forces candidate superiority on volatile data.
    assert all(h.observations>0 for f in report.folds for h in f.horizons)
    json.dumps(report.as_dict(),allow_nan=False)


def test_check_3_sealed_final_mutation_cannot_change_candidate_results():
    initial=series()
    before=compare_momentum_to_rw(initial,"BTCUSDT","15")
    final_start=math.floor(len(initial)*.8)
    modified=initial[:final_start]+[
        replace(c,open=c.open*1.05,high=c.high*1.05,
                low=c.low*1.05,close=c.close*1.05)
        for c in initial[final_start:]]
    after=compare_momentum_to_rw(modified,"BTCUSDT","15")
    assert before.folds==after.folds
    assert before.final_holdout_sha256!=after.final_holdout_sha256
    assert not before.final_holdout_evaluated and not after.final_holdout_evaluated


def test_check_3_first_origin_sees_only_past_closes(monkeypatch):
    from moex_intelligence.crypto import momentum_evaluation as module
    items=series()
    seen=[]
    original=module.momentum_envelope
    def capture(closes,horizons):
        if not seen:
            seen.append(tuple(closes))
        return original(closes,horizons)
    monkeypatch.setattr(module,"momentum_envelope",capture)
    before=module.compare_momentum_to_rw(items,"BTCUSDT","15")
    first_origin=before.folds[0].validation_start_index-1
    assert seen[0]==tuple(x.close for x in items[first_origin-119:first_origin+1])
    assert seen[0][-1]==items[first_origin].close
    assert items[first_origin+1].close not in seen[0]


@pytest.mark.parametrize("prices,horizons",[
    ([100.]*5,(1,2,4,8)),
    ([100.]*121,(1,2,4,8)),
    ([100.]*119+[float("nan")],(1,)),
    ([100.]*119+[0.],(1,)),
    ([100.]*119+[10**400],(1,)),
    ([100.]*119+[10000.],(1,)),
    ([100.]*120,(0,1)),
    ([100.]*120,(1,1)),
    ([100.]*120,(2,1)),
    ([100.]*120,(1,65)),
])
def test_check_4_malformed_inputs_fail_closed(prices,horizons):
    with pytest.raises(ValueError):
        momentum_envelope(prices,horizons)


def test_check_4_extra_unclosed_candle_does_not_affect_model():
    rows=series()
    before=compare_momentum_to_rw(rows,"BTCUSDT","15")
    partial=Candle(rows[-1].time+STEP,900,901,899,900,2.,False)
    after=compare_momentum_to_rw(rows+[partial],"BTCUSDT","15")
    assert before==after


def test_check_5_cli_readonly_report_and_market_label(tmp_path):
    source=save_csv(tmp_path/"history.csv",series())
    original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    target=tmp_path/"candidate.json"
    root=Path(__file__).resolve().parents[1]
    command=[sys.executable,str(root/"scripts/evaluate_momentum_candidate_v09.py"),
        "--input",str(source),"--symbol","BTCUSDT","--timeframe","15",
        "--output",str(target)]
    run=subprocess.run(command,capture_output=True,text=True,timeout=35)
    assert run.returncode==0,run.stderr
    result=json.loads(run.stdout)
    assert json.loads(target.read_text(encoding="utf8"))==result
    assert result["source"]=="USER_SUPPLIED_CSV_UNVERIFIED"
    assert result["live_trading_enabled"] is False
    assert result["live_model_changed"] is False
    assert result["comparison"]["final_holdout_evaluated"] is False
    assert result["market"]["file_sha256"]==original_hash
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
    report_hash=hashlib.sha256(target.read_bytes()).hexdigest()
    assert subprocess.run(command,capture_output=True,timeout=35).returncode==2
    assert hashlib.sha256(target.read_bytes()).hexdigest()==report_hash


def test_check_5_never_touches_user_portfolio_store(monkeypatch):
    import moex_intelligence.crypto.storage as storage
    def forbidden(*a,**kw):
        raise AssertionError("Candidate research must never initialize SQLite")
    monkeypatch.setattr(storage.Store,"__init__",forbidden)
    report=compare_momentum_to_rw(series(),"BTCUSDT","15")
    assert report.final_holdout_evaluated is False
