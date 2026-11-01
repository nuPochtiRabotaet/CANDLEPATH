"""Causal after-cost research equity guards; never production Paper state."""
from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

from moex_intelligence.crypto.costs import CostModel
from moex_intelligence.crypto.paper_risk_research import (
    ResearchEquityGuards, liquidation_equity, _periods)
from moex_intelligence.crypto.paper_path_research import simulate_paper_paths
from moex_intelligence.crypto.market import Candle

MODEL=CostModel()
STEP=60
START=int(datetime(2026,10,25,0,0,tzinfo=timezone.utc).timestamp())


def ts(y,m,d,h=0,minute=0):
    return int(datetime(y,m,d,h,minute,tzinfo=timezone.utc).timestamp())


def tick(ledger, t, cash, pos=None, op=100, close=100):
    gate=ledger.at_open(t,Decimal(cash),pos,op,4,MODEL)
    equity=ledger.at_close(t,Decimal(cash),pos,close,4,MODEL)
    return gate,equity


def test_marked_open_position_deducts_costs_and_open_loss():
    position={"base":Decimal("25")}
    mark=liquidation_equity(Decimal("7500"),position,100,4,MODEL)
    assert Decimal("9970")<mark<Decimal("10000")
    ledger=ResearchEquityGuards(10000)
    state=ledger.at_open(ts(2026,10,25,12),7500,position,100,4,MODEL)
    assert state is None
    ledger.at_close(ts(2026,10,25,12),7500,position,95,4,MODEL)
    snap=ledger.snapshot()
    assert Decimal(snap["max_marked_drawdown_pct"])>1
    assert snap["marking"].startswith("OPEN_BEFORE_ENTRY")
    assert snap["open_marks"]==snap["close_marks"]==1


def test_utc_day_rollover_uses_prior_close_not_post_gap_open():
    risk=ResearchEquityGuards(10000)
    gate,_=tick(risk,ts(2026,10,25,23,59),10000)
    assert gate is None
    gate=risk.at_open(ts(2026,10,26,0),9600,None,100,4,MODEL)
    assert gate=="blocked_day_loss"
    assert risk.day_anchor==Decimal("10000")
    assert risk.week_anchor==Decimal("10000")
    risk.at_close(ts(2026,10,26,0),9600,None,100,4,MODEL)
    assert Decimal(risk.snapshot()["max_marked_day_loss_pct"])==4


def test_weekly_cumulative_loss_blocks_even_without_daily_three_percent():
    risk=ResearchEquityGuards(10000)
    cash=Decimal("10000")
    # Start of ISO week, then three successive down days (~2% each).
    days=[(26,10000,9800),(27,9800,9600),(28,9600,9400)]
    for d,opening,closing in days:
        gate=risk.at_open(ts(2026,10,d,9),opening,None,100,4,MODEL)
        assert gate is None
        risk.at_close(ts(2026,10,d,9),closing,None,100,4,MODEL)
    assert risk.at_open(ts(2026,10,29,9),9400,None,100,4,MODEL)=="blocked_week_loss"
    assert risk.week_anchor==Decimal("10000")
    assert risk.day_anchor==Decimal("9400")
    assert Decimal(risk.snapshot()["max_marked_day_loss_pct"])<3
    assert Decimal(risk.snapshot()["max_marked_week_loss_pct"])>=6


def test_week_boundary_resets_week_anchor_after_previous_close():
    risk=ResearchEquityGuards(10000)
    tick(risk,ts(2026,10,25,23,59),9700)
    # Sunday loss 3%, new Monday is a new ISO week and should preserve the
    # prior Sunday close (9700) as the new weekly starting point.
    gate=risk.at_open(ts(2026,10,26),9700,None,100,4,MODEL)
    assert gate is None
    assert risk.week_anchor==Decimal("9700")
    assert risk.day_anchor==Decimal("9700")
    risk.at_close(ts(2026,10,26),9700,None,100,4,MODEL)


def test_marked_drawdown_has_priority_and_is_not_waiting_for_trade_close():
    risk=ResearchEquityGuards(10000)
    assert risk.at_open(ts(2026,10,25,12),8700,None,100,4,MODEL)=="blocked_drawdown"
    risk.at_close(ts(2026,10,25,12),8700,None,100,4,MODEL)
    assert Decimal(risk.snapshot()["max_marked_drawdown_pct"])==13


def test_chronological_open_close_order_is_enforced():
    r=ResearchEquityGuards(10000)
    t=ts(2026,10,25)
    with pytest.raises(ValueError,match="Close mark"):
        r.at_close(t,10000,None,100,4,MODEL)
    r.at_open(t,10000,None,100,4,MODEL)
    r.at_close(t,10000,None,100,4,MODEL)
    with pytest.raises(ValueError,match="chronological"):
        r.at_open(t,10000,None,100,4,MODEL)
    with pytest.raises(ValueError,match="Close mark"):
        r.at_close(t+60,10000,None,100,4,MODEL)


def _candles(n=1600,patches=None):
    patches=patches or {}
    return [Candle(START+i*STEP,
                   *(patches.get(i,(100.,100.2,99.8,100.))),2.0,True)
            for i in range(n)]


def _mock_signals(monkeypatch, events):
    import moex_intelligence.crypto.paper_path_research as engine
    def generate(rows,symbol,tf):
        return {"signals":[{
           "strategy":"Trend Following","status":"confirmed","type":"BUY",
           "candle_time":rows[i]["time"],"timestamp":rows[i]["time"]+STEP,
           "reference_price":rows[i]["close"],
           "risk_estimates":{"stop":99.,"target":101.}
        } for i in events if i<len(rows)]}
    monkeypatch.setattr(engine,"analyze",generate)


def test_after_gap_loss_next_buy_is_blocked_by_day_gate(monkeypatch):
    _mock_signals(monkeypatch,[140,143])
    # Gap down at i=142 makes the preceding position lose >3% of full
    # virtual capital, even though initial planned stop risk was <=0.75%.
    data=_candles(patches={142:(80.,81.,79.,80.)})
    report=simulate_paper_paths(data,"BTCUSDT","1")
    first=report["folds"][0]
    assert first["events"]["buys"]==1
    assert first["events"]["blocked_day_loss"]>=1
    assert first["events"]["blocked_week_loss"]==0
    assert first["events"]["blocked_drawdown"]==0
    assert first["trades"][0]["reason"]=="STOP_GAP"
    assert first["marked_equity_guards"]["open_marks"]==(
        first["end_exclusive"]-first["start_index"]-1)
    assert first["marked_equity_guards"]["close_marks"]==(
        first["end_exclusive"]-first["start_index"]-1)
    assert Decimal(first["marked_equity_guards"]["max_marked_day_loss_pct"])>=3
    assert report["trading_edge_verified"] is False
    json.dumps(report,allow_nan=False)


def test_default_path_marks_do_not_touch_final_holdout(monkeypatch):
    _mock_signals(monkeypatch,[140])
    data=_candles()
    result=simulate_paper_paths(data,"BTCUSDT","1")
    assert all(f["marked_equity_guards"]["open_marks"]==
               f["marked_equity_guards"]["close_marks"] for f in result["folds"])
    assert all(f["marked_equity_guards"]["period_timezone"]=="UTC" for f in result["folds"])
    assert result["final_holdout_evaluated"] is False
    assert result["status"]=="INSUFFICIENT_TRADE_SAMPLE"
