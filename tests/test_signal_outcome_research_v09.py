"""Sealed, causal research on CandlePath's actual confirmed signal rules."""
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

from moex_intelligence.crypto.costs import CostModel
from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.signal_outcome_research import (
    HORIZONS, STRATEGIES, _cash_return, audit_buy_signal_outcomes)

STEP = 60


def candles(n=1600, *, flat=False):
    t0 = int(time.time() // STEP) * STEP - (n + 10) * STEP
    result = []
    for i in range(n):
        opening = 100.0 if flat else 100 + i * .01
        close = opening if flat else opening + .005
        result.append(Candle(t0+i*STEP,opening,opening+.5,
                             opening-.5,close,2.0,True))
    return result


def fake_signals(rows, symbol, timeframe):
    """Stable, fully causal mocked signal source to isolate replay semantics."""
    signals = []
    for i in range(135, len(rows), 16):
        kind = "BUY" if i % 5 else "EXIT"
        strategy = STRATEGIES[(i//16) % len(STRATEGIES)]
        signals.append({
            "status":"confirmed","strategy":strategy,"type":kind,
            "candle_time":rows[i]["time"],"timestamp":rows[i]["time"]+STEP,
            "reference_price":rows[i]["close"]})
    return {"signals":signals,"regime":"Uncertain","overlay":[]}


def test_fixed_horizon_uses_next_open_not_signal_close(monkeypatch):
    import moex_intelligence.crypto.signal_outcome_research as module
    data=candles()
    monkeypatch.setattr(module,"analyze",fake_signals)
    report=audit_buy_signal_outcomes(data,"BTCUSDT","1")
    assert report.mode=="PAST_ONLY_SIGNAL_OUTCOME_AUDIT_NOT_TRADING"
    assert report.final_holdout_evaluated is False
    assert report.assumed_full_spread_bps==0
    assert report.cost_model["fees"]["taker"]=="0.001"
    assert report.cost_model["execution"]["slippage_bps"]=="5"
    assert report.status=="INSUFFICIENT_SIGNAL_SAMPLE"
    assert sum(f.scored_buy_signals for f in report.folds)>0
    for f in report.folds:
        assert f.end_exclusive<=int(len(data)*.8)
        assert sum(s.observations for s in f.outcomes)>0
        for s in f.outcomes:
            assert s.horizon_candles in HORIZONS
            assert s.strategy in STRATEGIES
            assert s.observations <= f.confirmed_buy_signals
            if s.observations:
                assert s.mean_net_return_pct < s.mean_gross_return_pct
                assert s.positive_net <= s.positive_gross
                assert s.min_net_return_pct<=s.median_net_return_pct<=s.max_net_return_pct
    payload=json.dumps(report.as_dict(),allow_nan=False)
    assert "NOT_TRADING" in payload
    assert "SEALED" not in payload or not report.final_holdout_evaluated


def test_same_open_prices_are_unprofitable_after_bid_ask_fee_slippage():
    net=_cash_return(100,100,0,CostModel())
    assert float(net)==pytest.approx(-0.2995008,abs=.005)
    wide=_cash_return(100,100,12,CostModel())
    assert wide<net
    assert -0.5 < float(wide) < -0.3


def test_cash_return_invalid_quotes_and_spread_fail_closed():
    with pytest.raises((ValueError, ArithmeticError)):
        _cash_return(100,100,30000,CostModel())
    with pytest.raises((ValueError, ArithmeticError)):
        _cash_return(100,0,0,CostModel())


def test_sealed_last_twenty_percent_never_reach_rules_or_scoring(monkeypatch):
    import moex_intelligence.crypto.signal_outcome_research as module
    seen=[]
    def capture(rows,symbol,timeframe):
        seen.append(rows[-1]["time"])
        return fake_signals(rows,symbol,timeframe)
    monkeypatch.setattr(module,"analyze",capture)
    original=candles()
    before=audit_buy_signal_outcomes(original,"BTCUSDT","1")
    assert len(seen)==3
    assert max(seen)<original[1280].time
    changed=original[:1280]+[
        replace(c,open=c.open*1.04, high=c.high*1.04,
                low=c.low*1.04,close=c.close*1.04) for c in original[1280:]]
    seen.clear()
    after=audit_buy_signal_outcomes(changed,"BTCUSDT","1")
    assert before.folds==after.folds
    assert before.final_holdout_sha256!=after.final_holdout_sha256
    assert not after.final_holdout_evaluated


def test_exit_is_counted_never_scored_as_short(monkeypatch):
    import moex_intelligence.crypto.signal_outcome_research as module
    def only_exit(rows,symbol,timeframe):
        sig=fake_signals(rows,symbol,timeframe)["signals"]
        return {"signals":[{**s,"type":"EXIT"} for s in sig]}
    monkeypatch.setattr(module,"analyze",only_exit)
    audit=audit_buy_signal_outcomes(candles(),"BTCUSDT","1")
    assert sum(f.confirmed_exit_signals for f in audit.folds)>0
    assert sum(f.confirmed_buy_signals for f in audit.folds)==0
    assert all(s.observations==0 and s.mean_net_return_pct is None
               for f in audit.folds for s in f.outcomes)
    assert audit.status=="INSUFFICIENT_SIGNAL_SAMPLE"


@pytest.mark.parametrize("spread",[-1,101,float("nan"),float("inf"),True,"5"])
def test_invalid_spread_fails_closed(spread):
    with pytest.raises(ValueError):
        audit_buy_signal_outcomes(candles(200),"BTCUSDT","1",
                                  assumed_spread_bps=spread)


def test_corrupt_generated_future_signal_is_rejected(monkeypatch):
    import moex_intelligence.crypto.signal_outcome_research as module
    def broken(rows,symbol,timeframe):
        sig=fake_signals(rows,symbol,timeframe)["signals"]
        if sig: sig[0]["timestamp"]+=STEP
        return {"signals":sig}
    monkeypatch.setattr(module,"analyze",broken)
    with pytest.raises(ValueError,match="timestamp/reference"):
        audit_buy_signal_outcomes(candles(),"BTCUSDT","1")


def test_native_real_rule_engine_can_process_fixture_without_publishing():
    audit=audit_buy_signal_outcomes(candles(),"BTCUSDT","1")
    assert audit.final_holdout_evaluated is False
    assert audit.status in ("DESCRIPTIVE_DEV_ONLY","INSUFFICIENT_SIGNAL_SAMPLE")
    assert all(s.observations>=0 for f in audit.folds for s in f.outcomes)
    assert all(s.strategy in STRATEGIES for f in audit.folds for s in f.outcomes)


def test_trade_csv_cli_signals_are_readonly_and_final_sealed(tmp_path):
    path=tmp_path/"BTCUSDT_2026-10-25.csv"
    n=1600
    # The fixture must match its filename's UTC day. Use a deterministic day
    # rather than the current clock; keeps the test runnable any month/year.
    day=int(__import__("datetime").datetime(2026,10,25,tzinfo=__import__("datetime").timezone.utc).timestamp()*1000)
    with path.open("w",encoding="utf8",newline="") as f:
        w=csv.writer(f);w.writerow(["id","timestamp","price","volume","side","rpi"])
        for i in range(n):
            # Split into two daily files to keep timestamps inside named UTC days.
            if i>=1440:break
            w.writerow([i+1,day+i*60000,str(100+i*.01),".02","buy","0"])
    second=tmp_path/"BTCUSDT_2026-10-26.csv"
    with second.open("w",encoding="utf8",newline="") as f:
        w=csv.writer(f);w.writerow(["id","timestamp","price","volume","side","rpi"])
        for i in range(160):
            w.writerow([i+500,day+86400000+i*60000,str(114.4+i*.01),".02","sell","0"])
    initial=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,second)]
    root=Path(__file__).resolve().parents[1]
    out=tmp_path/"signal-audit"
    cmd=[sys.executable,str(root/"scripts/evaluate_spot_trades_csv_v09.py"),
         "--input",str(path),str(second),"--symbol","BTCUSDT",
         "--timeframes","1","--output-dir",str(out),
         "--evaluate","--audit-signals","--assumed-spread-bps","4"]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr
    payload=json.loads(result.stdout)
    record=payload["outputs"][0]
    assert record["candles"]==n
    assert record["signal_outcome_status"]=="INSUFFICIENT_SIGNAL_SAMPLE"
    audit=record["signal_outcome_research"]
    assert audit["final_holdout_evaluated"] is False
    assert audit["assumed_full_spread_bps"]==4
    assert audit["final_holdout_sha256"]==record["development"]["sealed_final"]["sha256"]
    assert payload["signal_audit_is_execution_backtest"] is False
    assert payload["trading_edge_verified"] is False
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,second)]==initial
    again=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    assert again.returncode==2  # no overwrite allowed


def test_signal_cli_requires_explicit_eval_mode(tmp_path):
    root=Path(__file__).resolve().parents[1]
    cmd=[sys.executable,str(root/"scripts/evaluate_spot_trades_csv_v09.py"),
         "--input","any.csv","--symbol","BTCUSDT",
         "--output-dir",str(tmp_path/"out"),"--audit-signals"]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
    assert result.returncode==2
    assert "--audit-signals requires --evaluate" in result.stderr
    assert not (tmp_path/"out").exists()


def test_exact_hypothetical_entry_exit_prices_are_future_opens(monkeypatch):
    import moex_intelligence.crypto.signal_outcome_research as module
    data=candles()
    origin=128
    def one(rows,symbol,timeframe):
        bar=rows[origin]
        return {"signals":[{
            "status":"confirmed","strategy":"Trend Following","type":"BUY",
            "candle_time":bar["time"],"timestamp":bar["time"]+STEP,
            "reference_price":bar["close"]}]}
    monkeypatch.setattr(module,"analyze",one)
    report=audit_buy_signal_outcomes(data,"BTCUSDT","1")
    f=report.folds[0]
    s=next(x for x in f.outcomes if
           x.strategy=="Trend Following" and x.horizon_candles==1)
    assert s.observations==1
    expected_gross=(data[origin+2].open/data[origin+1].open-1)*100
    assert s.mean_gross_return_pct==pytest.approx(expected_gross)
    assert s.mean_net_return_pct==pytest.approx(
        float(_cash_return(data[origin+1].open,data[origin+2].open,0,
                           CostModel())))
    assert f.confirmed_buy_signals==1
    assert all(x.observations==0 for x in report.folds[1].outcomes)


def test_future_generated_signal_fails_closed(monkeypatch):
    import moex_intelligence.crypto.signal_outcome_research as module
    def future(rows,symbol,timeframe):
        future_time=rows[-1]["time"]+STEP
        return {"signals":[{
            "status":"confirmed","strategy":"Trend Following","type":"BUY",
            "candle_time":future_time,"timestamp":future_time+STEP,
            "reference_price":123.0}]}
    monkeypatch.setattr(module,"analyze",future)
    with pytest.raises(ValueError,match="outside the available historical prefix"):
        audit_buy_signal_outcomes(candles(),"BTCUSDT","1")


def test_extreme_finite_values_never_serialize_nonfinite_metrics():
    from decimal import Decimal
    from moex_intelligence.crypto.signal_outcome_research import _summary
    huge=Decimal("1e400")
    result=_summary("Breakout Detection",8,[huge],[-huge])
    assert result.mean_gross_return_pct is None
    assert result.mean_net_return_pct is None
    assert result.min_net_return_pct is None
    assert result.max_net_return_pct is None
    json.dumps(result.__dict__,allow_nan=False)


def test_missing_or_reordered_candles_cannot_be_scored():
    data=candles()
    with pytest.raises(ValueError,match="missing candles|Reordered|duplicate"):
        audit_buy_signal_outcomes(data[:200]+data[201:],
                                  "BTCUSDT","1")
