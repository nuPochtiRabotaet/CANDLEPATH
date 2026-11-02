"""Regression gates for public-market feed atomicity and Bybit depth-1 deltas.

All messages/sources are synthetic; never connect to Bybit or place orders.
"""
import threading
import time

import pytest

from moex_intelligence.crypto.market import Candle, Feed, MarketError
from moex_intelligence.crypto.risk import quote_ok
from moex_intelligence.crypto.storage import Store


def new_feed(tmp_path):
    f = object.__new__(Feed)
    f.symbol = "BTCUSDT"
    f.interval = "15"
    f.lock = threading.RLock()
    f.store = Store(tmp_path / "feed-atomic.sqlite3")
    f.rows = []
    f.quote = {}
    f.rules = None
    f.status = "Connecting"
    f.error = ""
    f.events = []
    f.version = 0
    f.last_ws = 0
    f.stop = threading.Event()
    f.touched = time.monotonic()
    return f


def ticker(now, *, last="100", bid="99", ask="101", typ="snapshot"):
    return {"topic": "tickers.BTCUSDT", "type": typ, "ts": int(now*1000),
            "data": {"lastPrice":last,"bid1Price":bid,"ask1Price":ask}}


def book(now, bids=None, asks=None, typ="delta"):
    data = {}
    if bids is not None:
        data["b"] = bids
    if asks is not None:
        data["a"] = asks
    return {"topic":"orderbook.1.BTCUSDT","type":typ,"ts":int(now*1000),
            "data":data}


def test_one_sided_book_deltas_preserve_opposite_side_and_fresh_quote(tmp_path):
    f = new_feed(tmp_path)
    now = time.time()
    f.receive(ticker(now))
    f.receive(book(now, [["99.5", "1"]], [["100.5","2"]], "snapshot"))
    assert f.quote["bid"] == 99.5
    assert f.quote["ask"] == 100.5
    assert quote_ok({**f.quote,"fresh":True},now)
    f.receive(book(now+0.1, [["99.7","1"]], None))
    assert f.quote["bid"] == 99.7
    assert f.quote["ask"] == 100.5, "Unmentioned ask is not an empty book side"
    assert quote_ok({**f.quote,"fresh":True},now)
    f.receive(book(now+0.2, None, [["100.3","1"]]))
    assert f.quote["bid"] == 99.7
    assert f.quote["ask"] == 100.3
    assert quote_ok({**f.quote,"fresh":True},now)


def test_empty_delta_keeps_book_and_does_not_refresh_side_timestamp(tmp_path):
    f = new_feed(tmp_path)
    now = time.time()
    f.receive(ticker(now))
    f.receive(book(now, [["99.5","1"]], [["100.5","1"]], "snapshot"))
    old_bid_ts = f.quote["bid_ts"]
    old_ask_ts = f.quote["ask_ts"]
    f.receive(book(now+1, [], [], "delta"))
    assert (f.quote["bid"], f.quote["ask"]) == (99.5, 100.5)
    assert f.quote["bid_ts"] == old_bid_ts
    assert f.quote["ask_ts"] == old_ask_ts
    # Explicit 0 quantity is a real book removal, never a false positive quote.
    f.receive(book(now+2,[["99.5","0"]], None,"delta"))
    assert f.quote["bid"] == 0
    assert not quote_ok({**f.quote,"fresh":True},now+2)


def test_fresh_ticker_does_not_get_overwritten_by_older_orderbook(tmp_path):
    f = new_feed(tmp_path)
    now = time.time()
    f.receive(ticker(now))
    f.receive(book(now, [["99.5","1"]],[["100.5","1"]],"snapshot"))
    f.receive(ticker(now+2, last="100.7", bid="100.1", ask="100.9", typ="delta"))
    assert f.quote["bid"] == 100.1
    assert f.quote["ask"] == 100.9
    # A stale book message must not roll back a more recent bid/ask.
    f.receive(book(now+1,[["98","1"]],[["102","1"]]))
    assert f.quote["bid"] == 100.1
    assert f.quote["ask"] == 100.9
    assert quote_ok({**f.quote,"fresh":True},now+2)


def test_gap_rejects_candle_update_without_modifying_memory_or_store(tmp_path):
    f=new_feed(tmp_path)
    first = Candle(0,100,101,99,100,2,True)
    second = Candle(900,100,101,99,100,2,True)
    f.rows=[first,second]
    f.store.save_candles("BTCUSDT","15",[first,second])
    before=f.rows[:]
    msg={"topic":"kline.15.BTCUSDT","ts":int(time.time()*1000),
         "data":[{"start":2700000,"open":"100","high":"101","low":"99",
                  "close":"100","volume":"2","confirm":True}]}
    with pytest.raises(MarketError,match="пропуск"):
        f.receive(msg)
    assert f.rows == before
    assert f.version == 0
    assert f.store.candles("BTCUSDT","15") == before


def test_missing_close_confirmation_does_not_publish_new_future_bar(tmp_path):
    f=new_feed(tmp_path)
    original=Candle(0,100,101,99,100,2,False)
    f.rows=[original]
    f.store.save_candles("BTCUSDT","15",[original])
    msg={"topic":"kline.15.BTCUSDT","ts":int(time.time()*1000),
         "data":[{"start":900000,"open":"100","high":"101","low":"99",
                  "close":"100","volume":"2","confirm":True}]}
    with pytest.raises(MarketError,match="подтверждение"):
        f.receive(msg)
    assert f.rows == [original]
    assert f.version == 0
    assert f.store.candles("BTCUSDT","15") == [original]


@pytest.mark.asyncio
async def test_sync_store_failure_does_not_publish_uncommitted_memory(tmp_path,monkeypatch):
    f=new_feed(tmp_path)
    first=Candle(0,100,101,99,100,1,True)
    second=Candle(900,100,101,99,100,1,True)
    f.rows=[first]
    f.store.save_candles("BTCUSDT","15",[first])

    class FakeAPI:
        async def rules(self,symbol):
            return {"step":".001"}
        async def history(self,symbol,interval,end=None):
            return [first,second]
        async def ticker(self,symbol):
            return {"price":100,"bid":99,"ask":101,"ts":time.time()}
    f.api=FakeAPI()
    f.backfills=0
    f.quote={"price":90,"bid":89,"ask":91,"ts":time.time()}
    f.rules={"step":".01"}
    def fail(*args,**kwargs):
        raise OSError("test-only persistence failure")
    monkeypatch.setattr(f.store,"save_candles",fail)
    with pytest.raises(OSError,match="persistence failure"):
        await f.sync()
    assert f.rows == [first]
    assert f.rules == {"step":".01"}
    assert f.quote["price"] == 90
    assert f.version == 0
    assert f.backfills == 0
