"""SQLite write-amplification and immutable-history regression checks (v0.9).

Uses only temporary databases and synthetic candles. No market or user data.
"""
import sqlite3

import pytest

from moex_intelligence.crypto.market import Candle, MarketError
from moex_intelligence.crypto.storage import Store


STEP = 900


def candle(index, price=100.0, *, closed=True):
    return Candle(index * STEP, price, price + 1, price - 1, price, 2.0, closed)


def test_bulk_save_uses_bounded_lookups_not_n_selects(tmp_path, monkeypatch):
    store = Store(tmp_path / "bulk.sqlite")
    observed = []
    original_connect = store.connect

    def traced_connect():
        conn = original_connect()
        conn.set_trace_callback(observed.append)
        return conn

    monkeypatch.setattr(store, "connect", traced_connect)
    batch = [candle(i) for i in range(1200)]
    store.save_candles("BTCUSDT", "15", batch)

    selects = [stmt for stmt in observed
               if stmt.lstrip().upper().startswith("SELECT")
               and "FROM candles" in stmt]
    assert len(selects) == 3, "1200 records require 3 bounded reads, not 1200"
    assert store.candles("BTCUSDT", "15") == batch

    observed.clear()
    store.save_candles("BTCUSDT", "15", batch)
    assert len([stmt for stmt in observed
                if stmt.lstrip().upper().startswith("SELECT")
                and "FROM candles" in stmt]) == 3
    assert store.candles("BTCUSDT", "15") == batch


def test_open_to_closed_update_and_closed_to_open_is_ignored(tmp_path):
    store = Store(tmp_path / "updates.sqlite")
    initial = candle(10, closed=False)
    final = candle(10, price=101, closed=True)
    store.save_candles("BTCUSDT", "15", [initial])
    store.save_candles("BTCUSDT", "15", [final])
    store.save_candles("BTCUSDT", "15", [initial])
    assert store.candles("BTCUSDT", "15") == [final]


def test_conflicting_closed_candle_rolls_back_entire_batch(tmp_path):
    store = Store(tmp_path / "immutability.sqlite")
    old = candle(10)
    store.save_candles("BTCUSDT", "15", [old])
    with pytest.raises(MarketError, match="неизменяема"):
        store.save_candles("BTCUSDT", "15", [
            candle(11), candle(10, price=110), candle(12)])
    assert store.candles("BTCUSDT", "15") == [old]


def test_duplicate_times_within_batch_obey_first_closed_publication(tmp_path):
    store = Store(tmp_path / "duplicates.sqlite")
    first = candle(1, closed=False)
    final = candle(1, price=101, closed=True)
    # Open -> closed -> open must retain the first published closed candle.
    store.save_candles("BTCUSDT", "15", [first, final, first])
    assert store.candles("BTCUSDT", "15") == [final]

    with pytest.raises(MarketError, match="неизменяема"):
        store.save_candles("BTCUSDT", "15", [candle(2), candle(2, price=105)])
    assert store.candles("BTCUSDT", "15") == [final]


def test_batches_do_not_cross_market_or_interval(tmp_path):
    store = Store(tmp_path / "markets.sqlite")
    bitcoin = candle(1, price=100)
    ethereum = candle(1, price=200)
    store.save_candles("BTCUSDT", "15", [bitcoin])
    store.save_candles("ETHUSDT", "15", [ethereum])
    store.save_candles("BTCUSDT", "60", [ethereum])
    store.save_candles("BTCUSDT", "15", [candle(2)])
    assert store.candles("BTCUSDT", "15") == [bitcoin, candle(2)]
    assert store.candles("ETHUSDT", "15") == [ethereum]
    assert store.candles("BTCUSDT", "60") == [ethereum]


def test_empty_input_leaves_sqlite_unchanged(tmp_path):
    store = Store(tmp_path / "empty.sqlite")
    store.save_candles("BTCUSDT", "15", [])
    assert store.candles("BTCUSDT", "15") == []
