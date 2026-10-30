"""Five-layer verification of PUBLIC Bybit SPOT historical replay.

Fixtures mimic the documented V5 response but are ALWAYS SYNTHETIC. A passing
fixture test does not establish that real Bybit network calls are accessible.
"""
import asyncio
from dataclasses import replace
import copy
import json
import math
import time

import pytest

from moex_intelligence.crypto.bybit_history_evaluation import (
    collect_public_spot_history, evaluate_public_spot_history)
from moex_intelligence.crypto.market import MarketError, seconds

STEP = 900


def api_time():
    return (int(time.time() // STEP) * STEP + 120) * 1000


class FakeBybit:
    def __init__(self, count=1700, *, now_ms=None):
        self.now_ms = now_ms if now_ms is not None else api_time()
        cutoff = self.now_ms // (STEP * 1000) * STEP * 1000
        self.calls = []
        self.hooks = {}
        self.rows = []
        for j in range(count, 0, -1):
            start_ms = cutoff - j * STEP * 1000
            close = 100 + (count - j) * .015 + math.sin(j / 9) * .1
            self.rows.append([str(start_ms),str(close-.03),str(close+.4),
                              str(close-.4),str(close),"5.5","550"])
        self.rows.reverse()

    async def get(self, path, params=None):
        self.calls.append((path, copy.deepcopy(params)))
        if path in self.hooks and callable(self.hooks[path]):
            return self.hooks[path](path, params)
        if path == "/v5/market/time":
            return {"retCode":0, "time": str(self.now_ms), "result":{}}
        if path != "/v5/market/kline":
            raise AssertionError("Unexpected endpoint")
        assert params["category"] == "spot"
        assert params["limit"] <= 1000
        items = [r for r in self.rows if int(r[0]) <= params["end"]]
        return {
            "retCode":0,"time":str(self.now_ms),
            "result":{"category":"spot","symbol":params["symbol"],
                      "list":items[:params["limit"]]},
        }


def run(coro):
    return asyncio.run(coro)


def test_check_1_real_shaped_pagination_is_descending_and_becomes_causal_ascending():
    api=FakeBybit()
    result=run(collect_public_spot_history("BTCUSDT","15",bars=1600,
                                           connector=api,pause_seconds=0))
    assert result.returned_bars == result.requested_bars == 1600
    assert result.pages == 2
    assert len(result.sha256) == 64
    assert result.last_closed_at_ms == api.now_ms // (STEP*1000) * STEP*1000
    assert all(c.closed for c in result.candles)
    assert all((b.time-a.time)==STEP for a,b in zip(result.candles,result.candles[1:]))
    assert result.candles[0].time < result.candles[-1].time
    times=[p for p, _ in api.calls]
    assert times==["/v5/market/time","/v5/market/kline","/v5/market/kline"]
    calls=[parameters for path,parameters in api.calls if path=="/v5/market/kline"]
    assert calls[0]["limit"]==1000 and calls[1]["limit"]==600
    assert calls[0]["end"] == result.last_closed_at_ms-1
    assert calls[1]["end"] < calls[0]["end"]
    assert all("api_key" not in p and "recv_window" not in p for p in calls)


def test_check_2_provenance_and_causality_of_evaluated_report():
    api=FakeBybit()
    response=run(evaluate_public_spot_history("ETHUSDT","15",bars=1600,
                                              connector=api,pause_seconds=0))
    assert response["verification"]=="PUBLIC_REST_HISTORY_VERIFIED"
    assert response["historical_replay_only"] is True
    assert response["market"]["source"] == "BYBIT_V5_SPOT_PUBLIC_REST"
    assert response["market"]["requested_bars"]==1600
    assert response["evaluation"]["mode"]=="HISTORICAL_REPLAY_NOT_LIVE"
    assert response["evaluation"]["status"]=="EVALUATED"
    assert response["evaluation"]["origins"] >= 30
    assert [h["horizon_candles"] for h in response["evaluation"]["horizons"]]==[1,2,4,8]
    assert len(response["market"]["sha256"])==64
    json.dumps(response, allow_nan=False)


@pytest.mark.parametrize("count", [0, 99, 300, 1199])
def test_check_3_insufficient_remote_history_does_not_fake_success(count):
    api=FakeBybit(count)
    with pytest.raises(MarketError,match="Incomplete Bybit history"):
        run(collect_public_spot_history("BTCUSDT","15",bars=1200,
                                        connector=api,pause_seconds=0))


def test_check_3_missing_middle_candle_is_reported_as_error():
    api=FakeBybit()
    api.rows.pop(900)
    with pytest.raises(MarketError,match="gaps|Missing"):
        run(collect_public_spot_history("BTCUSDT","15",bars=1600,
                                        connector=api,pause_seconds=0))


def test_check_3_missing_page_boundary_candle_is_reported():
    api=FakeBybit()
    api.rows.pop(1000)
    with pytest.raises(MarketError,match="Missing|gaps"):
        run(collect_public_spot_history("BTCUSDT","15",bars=1600,
                                        connector=api,pause_seconds=0))


def test_check_3_invalid_close_or_volume_are_rejected():
    for field,value in ((4,"NaN"), (5,"-2"),(2,"1"),(0,"not_a_timestamp")):
        api=FakeBybit()
        api.rows[0][field]=value
        with pytest.raises(MarketError):
            run(collect_public_spot_history("BTCUSDT","15",bars=1600,
                                            connector=api,pause_seconds=0))


def test_check_3_wrong_market_category_is_not_silently_coerced():
    api=FakeBybit()
    def bad(_p,params):
        return {"retCode":0,"result":{"category":"linear",
                "symbol":params["symbol"],"list":api.rows[:params["limit"]]}}
    api.hooks["/v5/market/kline"]=bad
    with pytest.raises(MarketError,match="different market"):
        run(collect_public_spot_history("BTCUSDT","15",bars=1600,
                                        connector=api,pause_seconds=0))


def test_check_3_oldest_first_page_is_rejected():
    api=FakeBybit()
    def bad(_p,params):
        matches=[x for x in api.rows if int(x[0])<=params["end"]][:params["limit"]]
        return {"retCode":0,"result":{"category":"spot","symbol":params["symbol"],
               "list":list(reversed(matches))}}
    api.hooks["/v5/market/kline"]=bad
    with pytest.raises(MarketError,match="newest-first"):
        run(collect_public_spot_history("BTCUSDT","15",bars=1600,
                                        connector=api,pause_seconds=0))


def test_check_3_current_partial_candle_in_payload_is_rejected():
    api=FakeBybit()
    def bad(_p,params):
        current=api.now_ms//(STEP*1000)*(STEP*1000)
        return {"retCode":0,"result":{"category":"spot","symbol":params["symbol"],
               "list":[[str(current),"100","101","99","100","10","10"]]}}
    api.hooks["/v5/market/kline"]=bad
    with pytest.raises(MarketError,match="Future|partial"):
        run(collect_public_spot_history("BTCUSDT","15",bars=1600,
                                        connector=api,pause_seconds=0))


def test_check_3_api_server_clock_skew_and_bad_retcode_fail_closed():
    api=FakeBybit(now_ms=api_time()+3600*1000)
    with pytest.raises(MarketError,match="clock"):
        run(collect_public_spot_history("BTCUSDT","15",bars=1200,connector=api))
    api=FakeBybit()
    api.hooks["/v5/market/time"]=lambda *_:{"retCode":10003, "time":str(api.now_ms)}
    with pytest.raises(MarketError,match="server time request failed"):
        run(collect_public_spot_history("BTCUSDT","15",bars=1200,connector=api))


def test_check_4_bybit_geoblock_propagates_and_never_falls_back_to_synthetic():
    api=FakeBybit()
    def blocked(*_):
        raise MarketError("Доступ Bybit ограничен платформой или регионом; обход не выполняется")
    api.hooks["/v5/market/kline"]=blocked
    with pytest.raises(MarketError,match="ограничен"):
        run(evaluate_public_spot_history("BTCUSDT","15",bars=1200,
                                          connector=api,pause_seconds=0))


@pytest.mark.parametrize("bars,pages", [(399,2),(5001,10),(1500,1),(1200,0),(True,5)])
def test_check_4_limits_are_enforced_before_network(bars,pages):
    api=FakeBybit()
    with pytest.raises(MarketError):
        run(collect_public_spot_history("BTCUSDT","15",bars=bars,
                                        max_pages=pages,connector=api,pause_seconds=0))
    assert not api.calls


def test_check_4_real_history_verification_never_initializes_user_store(monkeypatch):
    import moex_intelligence.crypto.storage as storage
    def bomb(*_a,**_kw):
        raise AssertionError("Evaluation must never open local portfolio DB")
    monkeypatch.setattr(storage.Store,"__init__",bomb)
    api=FakeBybit()
    response=run(evaluate_public_spot_history("SOLUSDT","15",bars=1200,
                                              connector=api,pause_seconds=0))
    assert response["verification"]=="PUBLIC_REST_HISTORY_VERIFIED"
