"""Predeclared offline execution-cost sensitivity, no promotion of trading."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.costs import CostModel
from moex_intelligence.crypto.paper_cost_stress_research import (
    SCENARIOS, run_paper_cost_stress)

STEP=60
START=int(datetime(2026,10,25,tzinfo=timezone.utc).timestamp())


def history(n=1600):
    return [Candle(START+i*STEP,100.,100.3,99.7,100.,10.,True)
            for i in range(n)]


def one_buy(monkeypatch):
    from moex_intelligence.crypto import paper_path_research as module
    def source(rows, sym, tf):
        index=140
        if index>=len(rows):
            return {"signals":[]}
        return {"signals":[{
            "strategy":"Trend Following","status":"confirmed","type":"BUY",
            "candle_time":rows[index]["time"],
            "timestamp":rows[index]["time"]+STEP,
            "reference_price":rows[index]["close"],
            "risk_estimates":{"stop":99.,"target":101.}}]}
    monkeypatch.setattr(module,"analyze",source)


def test_three_cost_scenarios_are_predefined_not_optimized(monkeypatch):
    one_buy(monkeypatch)
    report=run_paper_cost_stress(history(),"BTCUSDT","1")
    assert report["scenario_count"]==3
    assert report["scenario_defs_fixed_in_source"] is True
    assert tuple(s["scenario"] for s in report["cost_scenarios"])==tuple(x[0] for x in SCENARIOS)
    assert report["trading_edge_verified"] is False
    assert report["live_trading_enabled"] is False
    assert report["final_holdout_evaluated"] is False
    assert all(s["folds"][0]["trade_count"]==1 for s in report["cost_scenarios"])
    # One flat-price trade at the same signal should lose progressively more
    # under wider assumed bid/ask and larger modeled slippage.
    ending=[Decimal(s["folds"][0]["ending_cash"]) for s in report["cost_scenarios"]]
    assert ending[0]>ending[1]>ending[2]
    assert all(s["status"]=="INSUFFICIENT_TRADE_SAMPLE"
               for s in report["cost_scenarios"])
    assert all(len(s["folds"])==3 for s in report["cost_scenarios"])
    json.dumps(report,allow_nan=False)


def test_sealed_history_is_untouched_by_any_cost_scenario(monkeypatch):
    one_buy(monkeypatch)
    data=history()
    before=run_paper_cost_stress(data,"BTCUSDT","1")
    changed=data[:1280]+[
        replace(x,open=x.open*1.5,high=x.high*1.5,
                low=x.low*1.5,close=x.close*1.5)
        for x in data[1280:]]
    after=run_paper_cost_stress(changed,"BTCUSDT","1")
    assert before["cost_scenarios"]==after["cost_scenarios"]
    assert before["final_holdout_sha256"]!=after["final_holdout_sha256"]
    assert not before["final_holdout_evaluated"]
    assert not after["final_holdout_evaluated"]


def test_cost_models_are_local_assumptions_not_account_verified(monkeypatch):
    one_buy(monkeypatch)
    out=run_paper_cost_stress(history(),"BTCUSDT","1",
                              base_fee_model=CostModel())
    assert all(s["taker_fee_assumed"]=="0.001" for s in out["cost_scenarios"])
    assert [s["spread_assumed_bps"] for s in out["cost_scenarios"]]==["0","4","15"]
    assert [s["slippage_assumed_bps_per_side"] for s in out["cost_scenarios"]]==["2","5","15"]


def test_bad_cost_model_fails_closed():
    with pytest.raises(ValueError,match="CostModel"):
        run_paper_cost_stress(history(200),"BTCUSDT","1",
                              base_fee_model=object())


def test_rules_symbol_mismatch_is_rejected():
    from moex_intelligence.crypto.paper_rules_research import ResearchSpotRules
    r=ResearchSpotRules("ETHUSDT",Decimal(".001"),Decimal(".01"),
                        Decimal("10"),Decimal("100"),1793404800,
                        "Unverified research note", "f"*64)
    with pytest.raises(ValueError,match="symbol mismatch"):
        run_paper_cost_stress(history(200),"BTCUSDT","1",assumed_rules=r)


def test_no_implicit_stress_without_paper_research(tmp_path):
    root=Path(__file__).resolve().parents[1]
    args=[sys.executable,str(root/"scripts/evaluate_spot_trades_csv_v09.py"),
          "--input","dummy.csv","--symbol","BTCUSDT",
          "--output-dir",str(tmp_path/"out"),"--stress-paper-costs"]
    p=subprocess.run(args,capture_output=True,text=True,timeout=20)
    assert p.returncode==2
    assert "--stress-paper-costs requires --simulate-paper-paths" in p.stderr
    assert not (tmp_path/"out").exists()


def test_native_offline_cli_stress_is_readonly_and_no_final_scoring(tmp_path):
    root=Path(__file__).resolve().parents[1]
    sources=[]
    for day,count in [(25,1440),(26,160)]:
        path=tmp_path/f"BTCUSDT_2026-10-{day}.csv"
        ts=int(datetime(2026,10,day,tzinfo=timezone.utc).timestamp()*1000)
        with path.open("w",newline="",encoding="utf8") as fd:
            writer=csv.writer(fd)
            writer.writerow(["id","timestamp","price","volume","side","rpi"])
            for i in range(count):
                writer.writerow([i+1,ts+i*60000,
                                 str(100+Decimal(i)*Decimal("0.001")),
                                 "0.02","buy","0"])
        sources.append(path)
    digest=[hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]
    dest=tmp_path/"research"
    cmd=[sys.executable,str(root/"scripts/evaluate_spot_trades_csv_v09.py"),
         "--input",*(str(p) for p in sources),
         "--symbol","BTCUSDT","--timeframes","1","--output-dir",str(dest),
         "--evaluate","--simulate-paper-paths","--stress-paper-costs"]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr
    payload=json.loads(result.stdout)
    main=payload["outputs"][0]
    stress=main["paper_cost_stress_research"]
    assert stress["scenario_count"]==3
    assert stress["final_holdout_sha256"]==main["development"]["sealed_final"]["sha256"]
    assert main["cost_scenarios_are_market_verified"] is False
    assert payload["cost_scenarios_are_market_verified"] is False
    assert not stress["trading_edge_verified"]
    assert not stress["final_holdout_evaluated"]
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]==digest
    assert subprocess.run(cmd,capture_output=True,timeout=120).returncode==2
