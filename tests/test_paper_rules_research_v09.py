"""Fail-closed offline symbol-rule assumptions and no fabricated execution."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.costs import CostModel, FeeSchedule
from moex_intelligence.crypto.paper_path_research import (
    simulate_paper_paths, _quote_at, _buy_for_cash)
from moex_intelligence.crypto.paper_risk_research import liquidation_equity
from moex_intelligence.crypto.paper_rules_research import (
    load_research_rules, PROVENANCE, MAX_FILE_BYTES)

STEP=60
START=int(datetime(2026,10,25,tzinfo=timezone.utc).timestamp())


def assume(tmp_path, **changes):
    data={
        "symbol":"BTCUSDT","step":"0.001","tick":"0.01",
        "minimum":"10","maximum":"100",
        "as_of_utc_seconds":int(datetime(2026,10,31,tzinfo=timezone.utc).timestamp()),
        "note":"Locally chosen scenario; actual historical Bybit rule unverified",
    }
    data.update(changes)
    path=tmp_path/"spot_rules_scenario.json"
    path.write_text(json.dumps(data),encoding="utf8")
    return path


def bars(n=1600, patches=None):
    patches=patches or {}
    return [Candle(START+i*STEP,*patches.get(i,(100.,100.3,99.7,100.)),
                   1.,True) for i in range(n)]


def fake(monkeypatch, indices=(140,)):
    import moex_intelligence.crypto.paper_path_research as m
    def rules(rows,symbol,tf):
        return {"signals":[{
            "strategy":"Trend Following","status":"confirmed","type":"BUY",
            "candle_time":rows[i]["time"],
            "timestamp":rows[i]["time"]+STEP,
            "reference_price":rows[i]["close"],
            "risk_estimates":{"stop":99., "target":101.},
        } for i in indices if i < len(rows)]}
    monkeypatch.setattr(m,"analyze",rules)


def test_assumed_rules_are_never_presented_as_verified(tmp_path):
    f=assume(tmp_path)
    digest=hashlib.sha256(f.read_bytes()).hexdigest()
    r=load_research_rules(f,"BTCUSDT")
    assert r.step==Decimal("0.001")
    assert r.snapshot()["original_sha256"]==digest
    assert r.snapshot()["provenance"]==PROVENANCE
    assert r.snapshot()["historically_verified"] is False
    assert r.snapshot()["exchange_accepted_fills_verified"] is False
    assert f.read_bytes()


@pytest.mark.parametrize("invalid", [
    {"step":"0"},{"tick":"NaN"},{"minimum":"-2"},
    {"maximum":"Infinity"},{"maximum":"0.0001"},
    {"as_of_utc_seconds":False},{"as_of_utc_seconds":"2026-10-31"},
    {"symbol":"ETHUSDT"},{"note":""},{"note":"hi"},{"step":1},
])
def test_bad_rules_rejected(tmp_path,invalid):
    f=assume(tmp_path,**invalid)
    with pytest.raises(ValueError):
        load_research_rules(f,"BTCUSDT")


def test_duplicate_keys_missing_field_and_nonfinite_json_fail(tmp_path):
    f=assume(tmp_path)
    raw=f.read_text()
    f.write_text(raw.replace('"step": "0.001"', '"step": "0.001", "step": "0.001"'))
    with pytest.raises(ValueError,match="Duplicate field"):
        load_research_rules(f,"BTCUSDT")
    f=assume(tmp_path)
    f.write_text(f.read_text().replace('"step": "0.001", ',''))
    with pytest.raises(ValueError,match="seven fields"):
        load_research_rules(f,"BTCUSDT")
    f=assume(tmp_path)
    f.write_text(f.read_text().replace('"step": "0.001"','"step": NaN'))
    with pytest.raises(ValueError):
        load_research_rules(f,"BTCUSDT")


def test_huge_rule_json_rejected_before_parsing(tmp_path):
    f=assume(tmp_path)
    f.write_bytes(f.read_bytes()+b" "*MAX_FILE_BYTES)
    with pytest.raises(ValueError,match="too large"):
        load_research_rules(f,"BTCUSDT")


def test_synthetic_rule_scenario_has_one_valid_full_exit(monkeypatch,tmp_path):
    fake(monkeypatch)
    r=load_research_rules(assume(tmp_path),"BTCUSDT")
    path=simulate_paper_paths(bars(),"BTCUSDT","1",assumed_rules=r)
    trades=path["folds"][0]["trades"]
    assert len(trades)==1
    assert Decimal(trades[0]["base_quantity"])%r.step==0
    assert path["folds"][0]["events"]["rejected_rules"]==0
    assert path["assumed_spot_rules"]["historically_verified"] is False
    assert path["trading_edge_verified"] is False
    assert path["final_holdout_evaluated"] is False
    json.dumps(path,allow_nan=False)


def test_notional_and_tick_reject_without_fictitious_fill(monkeypatch,tmp_path):
    fake(monkeypatch)
    highmin=load_research_rules(assume(tmp_path,minimum="5000"),"BTCUSDT")
    p=simulate_paper_paths(bars(),"BTCUSDT","1",assumed_rules=highmin)
    assert p["folds"][0]["events"]["rejected_rules"]==1
    assert p["folds"][0]["trade_count"]==0
    bad_tick=load_research_rules(assume(tmp_path,tick="0.07"),"BTCUSDT")
    q=simulate_paper_paths(bars(),"BTCUSDT","1",assumed_rules=bad_tick)
    assert q["folds"][0]["events"]["rejected_rules"]==1
    assert q["folds"][0]["events"]["buys"]==0


def test_base_fee_creates_uncloseable_dust_rejected_upfront(monkeypatch,tmp_path):
    fake(monkeypatch)
    rules=load_research_rules(assume(tmp_path),"BTCUSDT")
    model=CostModel(fees=FeeSchedule(buy_currency="base"))
    p=simulate_paper_paths(bars(),"BTCUSDT","1",assumed_rules=rules,cost_model=model)
    assert p["folds"][0]["events"]["rejected_rules"]==1
    assert p["folds"][0]["events"]["buys"]==0


def test_later_gap_below_minimum_fails_closed_not_fake_profit(monkeypatch,tmp_path):
    fake(monkeypatch)
    r=load_research_rules(assume(tmp_path,minimum="2000"),"BTCUSDT")
    data=bars(patches={142:(40.,41.,39.,40.)})
    with pytest.raises(ValueError,match="UNEXECUTABLE_RESEARCH_EXIT"):
        simulate_paper_paths(data,"BTCUSDT","1",assumed_rules=r)


def test_illiquid_mark_values_uncloseable_base_at_zero_recovery(tmp_path):
    r=load_research_rules(assume(tmp_path,minimum="2000"),"BTCUSDT")
    pos={"base":Decimal("24")}
    eq=liquidation_equity(Decimal("7600"),pos,10,4,CostModel(),r)
    assert eq==Decimal("7600")


def test_sealed_final_mutation_invariance_with_rules(monkeypatch,tmp_path):
    fake(monkeypatch)
    rules=load_research_rules(assume(tmp_path),"BTCUSDT")
    history=bars()
    before=simulate_paper_paths(history,"BTCUSDT","1",assumed_rules=rules)
    history_changed=history[:1280]+[
        replace(x,open=x.open*2,high=x.high*2,
                low=x.low*2,close=x.close*2) for x in history[1280:]]
    after=simulate_paper_paths(history_changed,"BTCUSDT","1",assumed_rules=rules)
    assert before["folds"]==after["folds"]
    assert before["final_holdout_sha256"]!=after["final_holdout_sha256"]
    assert not after["final_holdout_evaluated"]


def test_cli_rejects_implicit_rule_mode_before_reading_trade_data(tmp_path):
    file=assume(tmp_path)
    root=Path(__file__).resolve().parents[1]
    proc=subprocess.run([
        sys.executable,str(root/"scripts/evaluate_spot_trades_csv_v09.py"),
        "--input","not-a-trade-file.csv","--symbol","BTCUSDT",
        "--output-dir",str(tmp_path/"out"),"--paper-rules-file",str(file)],
        capture_output=True,text=True,timeout=25)
    assert proc.returncode==2
    assert "--paper-rules-file requires --simulate-paper-paths" in proc.stderr
    assert not (tmp_path/"out").exists()
