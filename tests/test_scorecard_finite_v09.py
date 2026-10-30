"""Five-review audit for actual published forecast scorecard safety.

All candles are synthetic LOCAL test data. They are not verified Bybit prices
and make no claim about trading returns.
"""
from dataclasses import replace
import json
import math

import pytest

from moex_intelligence.crypto.intelligence import (
    Forecast, ForecastPoint, ForecastHistory, format_forecast_scorecard_pct)
from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.storage import Store


def sample(ident="fixed",median="100"):
    return Forecast(ident,"BTCUSDT","15",1800,1799,"test-v1","EXPERIMENTAL",
        (ForecastPoint(2700,"90",median,"110"),),.8)


def create_outcome(tmp_path, actual=105, ident="fixed"):
    store=Store(tmp_path/"ledger.sqlite")
    history=ForecastHistory(store)
    history.publish(sample(ident),now=1800)
    candle=Candle(1800,actual,actual,actual,actual,1.0,True)
    store.save_candles("BTCUSDT","15",[candle])
    assert history.reconcile(now=2700)==1
    return store,history


def test_check_1_normal_math_and_existing_contract(tmp_path):
    store,history=create_outcome(tmp_path,105)
    report=history.scorecard("BTCUSDT","15")
    assert report["forecasts"]==1
    h=report["horizons"][1]
    assert h["observations"]==1
    assert h["empirical_coverage"]==1.0
    assert h["mean_absolute_pct_error"]==pytest.approx(100*5/105)
    assert h["unrepresentable_percentage_errors"]==0
    assert h["sufficient_sample"] is False
    assert format_forecast_scorecard_pct(h["mean_absolute_pct_error"])=="4.76%"
    assert history.scorecard("ETHUSDT","15")=={"forecasts":0,"horizons":{}}


def test_check_2_extreme_valid_price_returns_null_not_infinity(tmp_path):
    store,history=create_outcome(tmp_path,1e-320)
    report=history.scorecard("BTCUSDT","15")
    h=report["horizons"][1]
    assert h["observations"]==1
    assert h["empirical_coverage"]==0.0
    assert h["mean_absolute_pct_error"] is None
    assert h["unrepresentable_percentage_errors"]==1
    assert "недоступно" in format_forecast_scorecard_pct(h["mean_absolute_pct_error"])
    # Must be valid strict JSON even on extreme market moves.
    json.dumps(report,allow_nan=False)


@pytest.mark.parametrize("bad",[
    {"actual":"NaN","covered":True},
    {"actual":"Infinity","covered":True},
    {"actual":"0","covered":False},
    {"actual":"-5","covered":False},
    {"actual":"not-a-number","covered":False},
    {"actual":"101","covered":1},
    {"actual":None,"covered":True},
])
def test_check_3_corrupted_immutable_outcome_fails_closed(tmp_path,bad):
    store=Store(tmp_path/"ledger.sqlite")
    history=ForecastHistory(store)
    history.publish(sample(),now=1800)
    row={"target_time":2700,"recorded_at":2700,"source":"injected test only",**bad}
    with store.connect() as db:
        db.execute("INSERT INTO forecast_outcomes VALUES(?,?,?)",
                   ("fixed",2700,json.dumps(row)))
    with pytest.raises(ValueError,match="Corrupt immutable forecast outcome journal"):
        history.scorecard("BTCUSDT","15")


def test_check_4_formatter_never_emits_nan_or_infinity():
    for number in (None,float("nan"),float("inf"),-float("inf"),"Infinity",
                   True,{},[]):
        result=format_forecast_scorecard_pct(number)
        assert result.startswith("недоступно")
        assert not ("nan" in result.lower() or "infinity" in result.lower())
    assert format_forecast_scorecard_pct(0.)=="0.00%"
    assert format_forecast_scorecard_pct(100.123)=="100.12%"


def test_check_4_idempotent_history_and_score_are_not_modified(tmp_path):
    store,history=create_outcome(tmp_path,101)
    before=history.records()
    report=history.scorecard()
    assert history.scorecard()==report
    assert history.reconcile(now=3600)==0
    assert history.records()==before
    assert report["horizons"][1]["unrepresentable_percentage_errors"]==0


def test_check_5_multiple_extreme_outcomes_are_counted_per_horizon(tmp_path):
    store=Store(tmp_path/"ledger.sqlite")
    history=ForecastHistory(store)
    for i in range(35):
        history.publish(sample(f"forecast-{i}"),now=1800)
    store.save_candles("BTCUSDT","15",[Candle(1800,1e-320,1e-320,1e-320,1e-320,1,True)])
    assert history.reconcile(now=2700)==35
    report=history.scorecard("BTCUSDT","15")
    h=report["horizons"][1]
    assert h["observations"]==35
    assert h["unrepresentable_percentage_errors"]==35
    assert h["mean_absolute_pct_error"] is None
    assert h["sufficient_sample"] is True   # a count, not evidence of success
    assert h["empirical_coverage"]==0.0
