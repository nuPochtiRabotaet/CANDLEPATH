"""Fail-closed numerical and completed-candle market ingress checks.

Synthetic malformed input only: no network access or real trades.
"""
import threading
import time

import pytest

from moex_intelligence.crypto.market import (
    Candle, Feed, MarketError, validate_quote)
from moex_intelligence.crypto.risk import quote_ok
from moex_intelligence.crypto.storage import Store


@pytest.mark.parametrize("time_value,close_value,closed", [
    (0, 100, "false"), (0, 100, 0), (0, 100, 1),
    (0, 100, None), (0, 100, "true"),
    (0.0, 100, True), (True, 100, True), (-900, 100, True),
    (0, 10**500, True), (0, float("inf"), True),
    (0, True, True),
])
def test_market_candle_fails_closed_on_invalid_types_and_nonfinite_inputs(
        time_value, close_value, closed):
    with pytest.raises(MarketError):
        Candle(time_value, 100, 101, 99, close_value, 1, closed)


def test_websocket_string_false_confirmation_not_promoted_to_closed(tmp_path):
    f = object.__new__(Feed)
    f.symbol="BTCUSDT";f.interval="15"
    f.lock=threading.RLock()
    f.rows=[]
    f.store=Store(tmp_path/"malformed-confirm.sqlite3")
    f.version=0
    f.last_candle_ts=0
    fake={"topic":"kline.15.BTCUSDT","ts":int(time.time()*1000),
          "data":[{"start":900000,"open":"100","high":"101",
                   "low":"99","close":"100","volume":"1",
                   "confirm":"false"}]}
    with pytest.raises(MarketError,match="confirm"):
        f.receive(fake)
    assert f.rows == []
    assert f.version == 0
    assert f.last_candle_ts == 0
    assert f.store.candles("BTCUSDT","15") == []


def test_quote_gate_rejects_enormous_int_without_overflow():
    now=time.time()
    invalid={"price":10**500,"bid":99.0,"ask":101.0,"ts":now,"fresh":True}
    assert quote_ok(invalid,now) is False
    with pytest.raises(MarketError):
        validate_quote({k:v for k,v in invalid.items() if k!="fresh"})


def test_quote_validation_rejects_malformed_price_fields():
    for q in (
        {"price":100,"bid":None,"ask":101,"ts":time.time()},
        {"price":100,"bid":"abc","ask":101,"ts":time.time()},
        {"price":100,"bid":105,"ask":101,"ts":time.time()},
        {"price":100,"bid":99,"ask":float("inf"),"ts":time.time()},
    ):
        with pytest.raises(MarketError):
            validate_quote(q)


def test_snapshot_survives_malformed_huge_numeric_quote_without_trading(tmp_path):
    f=object.__new__(Feed)
    f.symbol="BTCUSDT";f.interval="15"
    f.lock=threading.RLock()
    f.rows=[]
    f.quote={"price":10**500,"bid":99,"ask":101,"ts":time.time()}
    f.rules={"retrieved":time.time()}
    f.status="Live"
    f.events=[]
    f.error=""
    f.version=0
    f.stop=threading.Event()
    f.touched=time.monotonic()
    f.last_ws=time.time()
    snap=f.snapshot()
    assert snap["fresh"] is False
    assert snap["readiness"]["trade_execution_ready"] is False
    assert snap["readiness"]["forecast_feed_ready"] is False
    assert "price" not in snap["quote"]
