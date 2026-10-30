"""Five verification gates for locally supplied v0.9 OHLCV history.

All files in these tests are synthetic. Success DOES NOT validate exchange
provenance or prove profits from historical forecasts.
"""
import csv
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from moex_intelligence.crypto.offline_ohlcv import (
    read_local_ohlcv, evaluate_local_ohlcv, _MAX_BYTES)
from moex_intelligence.crypto.market import seconds

STEP=900
FIELDS=("open_time_ms","open","high","low","close","volume")


def bars(count=1100, *, interval="15"):
    step=seconds(interval)
    start=int(time.time()//step)*step - (count+10)*step
    return [
        dict(open_time_ms=str((start+i*step)*1000), open=f"{100+i*.02:.5f}",
             high=f"{101+i*.02:.5f}", low=f"{99+i*.02:.5f}",
             close=f"{100+i*.02:.5f}", volume="4.5")
        for i in range(count)]


def csv_file(tmp_path, dataset=None, name="valid.csv"):
    target=tmp_path/name
    with target.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(bars() if dataset is None else dataset)
    return target


def test_check_1_valid_utc_ohlcv_and_reproducible_hash(tmp_path):
    source=csv_file(tmp_path)
    info=read_local_ohlcv(source, "BTCUSDT", "15")
    assert info.row_count==1100 and len(info.candles)==1100
    assert info.first_open_ms == int(bars()[0]["open_time_ms"])
    assert all(b.time-a.time==STEP for a,b in zip(info.candles,info.candles[1:]))
    assert all(c.closed for c in info.candles)
    assert info.file_sha256==hashlib.sha256(source.read_bytes()).hexdigest()
    assert info == read_local_ohlcv(source,"BTCUSDT","15")
    assert len(info.normalized_sha256)==64


def test_check_2_mathematics_provenance_and_json(tmp_path):
    src=csv_file(tmp_path)
    data=evaluate_local_ohlcv(src,"ETHUSDT","15")
    assert data["verification"]=="LOCAL_FILE_FORMAT_VALIDATED_NOT_MARKET_VERIFIED"
    assert data["market"]["verified_bybit_http"] is False
    assert data["market"]["source"]=="USER_SUPPLIED_CSV_UNVERIFIED"
    assert data["historical_replay_only"] is True
    assert data["evaluation"]["mode"]=="HISTORICAL_REPLAY_NOT_LIVE"
    assert data["evaluation"]["status"]=="EVALUATED"
    assert data["evaluation"]["origins"]>=30
    assert [r["horizon_candles"] for r in data["evaluation"]["horizons"]]==[1,2,4,8]
    assert all(r["mean_absolute_error"]==r["random_walk_mae"]
               for r in data["evaluation"]["horizons"])
    assert "NOT" in data["market"]["note"]
    json.dumps(data, allow_nan=False)


@pytest.mark.parametrize("change,expected",[
    (lambda x: x.__setitem__(7,{**x[7],"open_time_ms":"tomorrow"}),"integer"),
    (lambda x: x.__setitem__(7,{**x[7],"open_time_ms":str(int(x[7]["open_time_ms"])+1)}),"aligned"),
    (lambda x: x.__setitem__(7,{**x[7],"open_time_ms":x[6]["open_time_ms"]}),"duplicate"),
    (lambda x: x.pop(7),"missing or reordered"),
    (lambda x: x.__setitem__(7,{**x[7],"open":"-0.2"}),"nonpositive"),
    (lambda x: x.__setitem__(7,{**x[7],"close":"inf"}),"nonfinite"),
    (lambda x: x.__setitem__(7,{**x[7],"volume":"-2"}),"negative volume"),
    (lambda x: x.__setitem__(7,{**x[7],"high":"0.1"}),"inconsistent OHLCV"),
    (lambda x: x.__setitem__(7,{**x[7],"low":"nan"}),"nonfinite"),
])
def test_check_3_bad_data_must_fail_closed(tmp_path,change,expected):
    inputs=bars()
    change(inputs)
    src=csv_file(tmp_path,inputs)
    with pytest.raises(ValueError,match=expected):
        evaluate_local_ohlcv(src,"BTCUSDT","15")


def test_check_3_partial_or_future_candle_is_rejected(tmp_path):
    rows=bars()
    now=time.time()
    step=seconds("15")
    current_open=int(now//step)*step
    rows[-1]["open_time_ms"]=str(current_open*1000)
    with pytest.raises(ValueError,match="unclosed/future"):
        read_local_ohlcv(csv_file(tmp_path,rows),"BTCUSDT","15")


def test_check_3_wrong_header_and_extra_data_are_rejected(tmp_path):
    source=tmp_path/"wrong.csv"
    source.write_text("time,open,high,low,close,volume\n0,1,2,1,1,2\n",encoding="utf8")
    with pytest.raises(ValueError,match="columns must exactly"):
        read_local_ohlcv(source,"BTCUSDT","15")
    source.write_text(",".join(FIELDS)+"\n"+"1,1,2,1,1,5,extra\n",encoding="utf8")
    with pytest.raises(ValueError,match="column count"):
        read_local_ohlcv(source,"BTCUSDT","15")


def test_check_3_invalid_format_and_size_bounds(tmp_path):
    bad=tmp_path/"bad.csv"
    bad.write_bytes(b"\xff\xfe\x00\x03")
    with pytest.raises(ValueError,match="UTF-8"):
        read_local_ohlcv(bad,"BTCUSDT","15")
    bad.write_bytes(b"x"*(_MAX_BYTES+1))
    with pytest.raises(ValueError,match="12 MiB"):
        read_local_ohlcv(bad,"BTCUSDT","15")
    bad.unlink()
    with pytest.raises(ValueError,match="does not exist"):
        read_local_ohlcv(bad,"BTCUSDT","15")


def test_check_4_no_portfolio_or_store_import(monkeypatch,tmp_path):
    import moex_intelligence.crypto.storage as storage
    def forbidden(*args,**kwargs):
        raise AssertionError("Never initialize or migrate a portfolio SQLite database")
    monkeypatch.setattr(storage.Store,"__init__",forbidden)
    data=evaluate_local_ohlcv(csv_file(tmp_path),"SOLUSDT","15")
    assert data["market"]["row_count"]==1100


def test_check_4_cli_read_only_and_create_only_report(tmp_path):
    source=csv_file(tmp_path)
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    output=tmp_path/"report.json"
    base=Path(__file__).resolve().parents[1]
    command=[sys.executable,str(base/"scripts/evaluate_ohlcv_csv_v09.py"),
             "--input",str(source),"--symbol","BTCUSDT","--timeframe","15",
             "--output",str(output)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert json.loads(output.read_text(encoding="utf8"))==report
    assert report["market"]["file_sha256"]==original
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    # No accidental replacement of user-owned reports.
    existing=hashlib.sha256(output.read_bytes()).hexdigest()
    collision=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert collision.returncode==2
    assert hashlib.sha256(output.read_bytes()).hexdigest()==existing
    # Even a malicious destination equal to the input cannot truncate the input.
    command[-1]=str(source)
    collision=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert collision.returncode==2
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original


def test_check_5_benchmark_and_different_timeframes(tmp_path):
    for interval in ("1","60","D"):
        src=csv_file(tmp_path,bars(1100,interval=interval),f"{interval}.csv")
        result=evaluate_local_ohlcv(src,"BTCUSDT",interval)
        assert result["market"]["row_count"]==1100
        assert result["evaluation"]["status"]=="EVALUATED"
        assert all(h["observations"]==result["evaluation"]["origins"]
                   for h in result["evaluation"]["horizons"])


@pytest.mark.parametrize("now",[None,float("inf"),float("nan"),"2026",True,10**400])
def test_check_5_invalid_cutoff_fails_closed(tmp_path,now):
    source=csv_file(tmp_path)
    if now is None:
        # A valid absent explicit cutoff is permitted.
        assert read_local_ohlcv(source,"BTCUSDT","15").row_count==1100
    else:
        with pytest.raises(ValueError,match="Invalid UTC observation cutoff"):
            read_local_ohlcv(source,"BTCUSDT","15",now=now)
