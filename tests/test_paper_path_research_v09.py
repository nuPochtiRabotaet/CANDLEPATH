"""Causal single-long historical path research, not actual Paper execution."""
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.paper_path_research import (
    simulate_paper_paths, _buy_for_cash, _quote_at)
from moex_intelligence.crypto.costs import CostModel, estimate

STEP=60
START=1792900000//STEP*STEP  # October 2026; historical fully closed


def history(n=1600, patches=None):
    patches=patches or {}
    out=[]
    for i in range(n):
        op,hi,lo,close=patches.get(i,(100.,100.2,99.8,100.))
        out.append(Candle(START+i*STEP,op,hi,lo,close,10.,True))
    return out


def signal(rows, index, side="BUY", strategy="Trend Following", stop=99., target=101.):
    return {"strategy":strategy, "status":"confirmed", "type":side,
            "candle_time":rows[index]["time"],
            "timestamp":rows[index]["time"]+STEP,
            "reference_price":rows[index]["close"],
            "risk_estimates":{"stop":stop, "target":target}}


def plug(monkeypatch, events):
    from moex_intelligence.crypto import paper_path_research as module
    calls=[]
    def fake(rows,symbol,tf):
        calls.append(len(rows))
        return {"signals":[signal(rows,idx,**options)
                           for idx,options in events
                           if idx < len(rows)]}
    monkeypatch.setattr(module,"analyze",fake)
    return calls


def trades_of(report):
    return [t for f in report["folds"] for t in f["trades"]]


def test_stop_and_target_same_candle_chooses_worst_case(monkeypatch):
    calls=plug(monkeypatch,[(140,{})])
    bars=history(patches={141:(100.,102.,98.,100.)})
    report=simulate_paper_paths(bars,"BTCUSDT","1")
    trades=trades_of(report)
    assert len(trades)==1
    assert trades[0]["reason"]=="STOP_FIRST_AMBIGUOUS"
    assert trades[0]["entry_open_time"]==bars[141].time
    assert trades[0]["exit_reference_price"]=="99.0"
    assert Decimal(trades[0]["net_pnl_quote"])<0
    assert report["folds"][0]["events"]["ambiguous_stop_first"]==1
    assert calls==[512,896,1280]
    assert report["final_holdout_evaluated"] is False


def test_downward_stop_gap_fills_next_open_not_stale_stop(monkeypatch):
    plug(monkeypatch,[(140,{})])
    bars=history(patches={142:(97.,98.,96.,97.)})
    report=simulate_paper_paths(bars,"BTCUSDT","1")
    t=trades_of(report)[0]
    assert t["reason"]=="STOP_GAP"
    assert t["exit_reference_price"]=="97.0"
    assert t["exit_open_time"]==bars[142].time


def test_target_gap_is_not_filled_at_stale_target(monkeypatch):
    plug(monkeypatch,[(140,{})])
    bars=history(patches={142:(104.,105.,103.,104.)})
    t=trades_of(simulate_paper_paths(bars,"BTCUSDT","1"))[0]
    assert t["reason"]=="TARGET_GAP"
    assert t["exit_reference_price"]=="104.0"
    assert Decimal(t["net_pnl_quote"])>0


def test_matching_rule_exit_after_entry_uses_next_open(monkeypatch):
    plug(monkeypatch,[(140,{}),(141,{"side":"EXIT"})])
    bars=history()
    t=trades_of(simulate_paper_paths(bars,"BTCUSDT","1"))[0]
    assert t["reason"]=="RULE_EXIT"
    assert t["exit_open_time"]==bars[142].time


def test_unrelated_exit_never_closes_position(monkeypatch):
    plug(monkeypatch,[(140,{}),(141,{"side":"EXIT","strategy":"Mean Reversion"})])
    t=trades_of(simulate_paper_paths(history(),"BTCUSDT","1",
                                      max_hold_bars=2))[0]
    assert t["reason"]=="MAX_HOLD"


def test_single_position_risk_allocation_and_never_reenter_same_open(monkeypatch):
    # Two independent BUY strategies at the SAME origin never open two positions.
    plug(monkeypatch,[(140,{}),(140,{"strategy":"Mean Reversion"})])
    bars=history(patches={141:(100.,102.,98.,100.)})
    report=simulate_paper_paths(bars,"BTCUSDT","1")
    assert report["folds"][0]["events"]["buys"]==1
    t=trades_of(report)[0]
    assert Decimal(t["entry_total_debit"])<=Decimal("2500")
    assert Decimal(t["base_quantity"])>0
    assert report["safety_limits"]["maximum_initial_stop_risk_fraction"]=="0.0075"
    assert report["safety_limits"]["max_open_positions"]==1
    quote=_quote_at(100,4)
    buy=_buy_for_cash(Decimal(10000),Decimal(100),Decimal(99),4,CostModel())
    sell=estimate("SELL",buy.net_base,_quote_at(99,4),CostModel())
    assert -buy.cash_delta-sell.cash_delta<=Decimal("75")


def test_final_unclosed_position_forced_flat_inside_fold(monkeypatch):
    plug(monkeypatch,[(150,{})])
    report=simulate_paper_paths(history(),"BTCUSDT","1",max_hold_bars=64)
    t=trades_of(report)[0]
    assert t["reason"]=="MAX_HOLD"
    assert report["folds"][0]["trade_count"]==1
    assert report["folds"][0]["events"]["buys"]==report["folds"][0]["events"]["exits"]


def test_real_rules_supported_and_undersampled_not_profitable_claim():
    report=simulate_paper_paths(history(),"BTCUSDT","1")
    assert report["status"]=="INSUFFICIENT_TRADE_SAMPLE"
    assert report["trading_edge_verified"] is False
    assert report["live_trading_enabled"] is False
    assert report["final_holdout_evaluated"] is False
    json.dumps(report,allow_nan=False)


def test_sealed_future_poisoning_cannot_change_development(monkeypatch):
    seen=plug(monkeypatch,[(140,{})])
    before=history()
    first=simulate_paper_paths(before,"BTCUSDT","1")
    mutated=before[:1280]+[
        replace(b,open=b.open*2,high=b.high*2,low=b.low*2,close=b.close*2)
        for b in before[1280:]]
    second=simulate_paper_paths(mutated,"BTCUSDT","1")
    assert first["folds"]==second["folds"]
    assert first["final_holdout_sha256"]!=second["final_holdout_sha256"]
    assert max(seen)<=1280
    assert first["final_holdout_evaluated"] is False


def test_malformed_future_signal_rejected(monkeypatch):
    from moex_intelligence.crypto import paper_path_research as m
    def forged(rows,symbol,tf):
        i=len(rows)
        return {"signals":[{
            "strategy":"Trend Following","status":"confirmed","type":"BUY",
            "candle_time":rows[-1]["time"]+STEP,
            "timestamp":rows[-1]["time"]+2*STEP,
            "reference_price":100.,
            "risk_estimates":{"stop":99.,"target":101.}}]}
    monkeypatch.setattr(m,"analyze",forged)
    with pytest.raises(ValueError,match="exceeds available fold history"):
        simulate_paper_paths(history(),"BTCUSDT","1")


@pytest.mark.parametrize("kwargs",[
    {"assumed_spread_bps":-1},{"assumed_spread_bps":101},
    {"assumed_spread_bps":float("nan")},
    {"assumed_spread_bps":True},
    {"initial_cash":"nan"},{"initial_cash":"0"},{"initial_cash":"99"},
    {"initial_cash":"10000000000"},
    {"max_hold_bars":0},{"max_hold_bars":True},
    {"max_hold_bars":65},
])
def test_bad_configs_fail_closed(kwargs):
    with pytest.raises(ValueError):
        simulate_paper_paths(history(200),"BTCUSDT","1",**kwargs)


def test_gap_in_source_history_rejected(monkeypatch):
    plug(monkeypatch,[])
    broken=history()
    with pytest.raises(ValueError,match="missing candles|Reordered"):
        simulate_paper_paths(broken[:250]+broken[251:],"BTCUSDT","1")


def test_readonly_cli_integration_on_two_offline_daily_files(tmp_path):
    import csv
    from datetime import datetime,timezone
    root=Path(__file__).resolve().parents[1]
    start=int(datetime(2026,10,25,tzinfo=timezone.utc).timestamp()*1000)
    files=[]
    for day,count in [(0,1440),(1,160)]:
        p=tmp_path/f"BTCUSDT_2026-10-{25+day:02d}.csv"
        with p.open("w",newline="",encoding="utf8") as f:
            w=csv.writer(f)
            w.writerow(["id","timestamp","price","volume","side","rpi"])
            for i in range(count):
                w.writerow([i+1,start+day*86400000+i*60000,
                           str(100+i*.001),".03","Buy","0"])
        files.append(p)
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
    dest=tmp_path/"results"
    command=[sys.executable,str(root/"scripts/evaluate_spot_trades_csv_v09.py"),
             "--input",*(str(p) for p in files),"--symbol","BTCUSDT",
             "--timeframes","1","--output-dir",str(dest),
             "--evaluate","--simulate-paper-paths","--assumed-spread-bps","4"]
    result=subprocess.run(command,text=True,capture_output=True,timeout=120)
    assert result.returncode==0,result.stderr
    payload=json.loads(result.stdout)
    out=payload["outputs"][0]
    assert out["candles"]==1600
    assert out["paper_path_research"]["final_holdout_evaluated"] is False
    assert out["paper_path_research"]["final_holdout_sha256"]==out["development"]["sealed_final"]["sha256"]
    assert payload["paper_path_is_live_or_production_paper"] is False
    assert payload["trading_edge_verified"] is False
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in files]==hashes
    assert subprocess.run(command,capture_output=True,timeout=120).returncode==2


def test_simulator_requires_explicit_research_opt_in(tmp_path):
    root=Path(__file__).resolve().parents[1]
    cmd=[sys.executable,str(root/"scripts/evaluate_spot_trades_csv_v09.py"),
         "--input","dummy.csv","--symbol","BTCUSDT",
         "--output-dir",str(tmp_path/"results"),"--simulate-paper-paths"]
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=20)
    assert p.returncode==2
    assert "--simulate-paper-paths requires --evaluate" in p.stderr
    assert not (tmp_path/"results").exists()
