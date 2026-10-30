"""Causal baseline tests. All prices are synthetic and must never appear as live quotes."""
import math
import time
from dataclasses import replace
import pytest

from moex_intelligence.crypto.forecast_baseline import HistoricalVolatilityBaseline
from moex_intelligence.crypto.intelligence import validate
from moex_intelligence.crypto.market import Candle

STEP = 900
BASE = 1760000400  # aligned to a 15-minute boundary


def candles(n=90, *, low_variance=False):
    rows = []
    for i in range(n):
        price = 100.0 if low_variance else 100 + i * .03 + math.sin(i / 4) * .2
        rows.append(Candle(BASE + i*STEP, price, price+.1, price-.1, price, 2., True))
    return rows


def clock(monkeypatch, rows, delta=50):
    now=rows[-1].time + STEP + delta
    monkeypatch.setattr('moex_intelligence.crypto.forecast_baseline.time.time',lambda: now)
    return now


def test_calculates_aligned_future_only_and_keeps_experimental_status(monkeypatch):
    rows=candles();now=clock(monkeypatch, rows)
    f=HistoricalVolatilityBaseline().forecast(rows,'BTCUSDT','15',now)
    assert f.status=='EXPERIMENTAL' and f.interval_coverage==.8
    assert f.validation_reference is None
    assert f.model_version.startswith('rw-ewma')
    assert f.data_as_of == rows[-1].time+STEP
    assert f.created_at==now
    assert [p.target_time for p in f.points]==[f.data_as_of + x*STEP for x in (1,2,4,8)]
    assert all(0<float(p.lower)<=float(p.median)<=float(p.upper) for p in f.points)
    validate(f, now)


def test_unclosed_huge_spike_never_changes_predicted_range(monkeypatch):
    rows=candles();now=clock(monkeypatch,rows)
    engine=HistoricalVolatilityBaseline()
    before=engine.forecast(rows,'BTCUSDT','15',now)
    partial=Candle(rows[-1].time+STEP,99999,100001,99998,99999,50,False)
    after=engine.forecast(rows+[partial],'BTCUSDT','15',now)
    assert after.points==before.points and after.id==before.id


def test_older_history_cannot_modify_trailing_window(monkeypatch):
    rows=candles(140);now=clock(monkeypatch,rows)
    oldrows=rows[:-120]
    mutated=[replace(c,open=99,high=110,low=90,close=99) for c in oldrows]+rows[-120:]
    engine=HistoricalVolatilityBaseline()
    assert engine.forecast(rows,'BTCUSDT','15',now).points==engine.forecast(mutated,'BTCUSDT','15',now).points


def test_rejects_future_candle_even_when_marked_closed(monkeypatch):
    rows=candles();now=clock(monkeypatch,rows)
    future=Candle(rows[-1].time+STEP,100,101,99,100,1.,True)
    assert HistoricalVolatilityBaseline().forecast(rows+[future],'BTCUSDT','15',now).status=='UNAVAILABLE'


def test_rejects_gapped_or_reordered_or_duplicate_data(monkeypatch):
    rows=candles();now=clock(monkeypatch,rows)
    e=HistoricalVolatilityBaseline()
    for altered in (rows[:20]+rows[21:], rows[:-2]+list(reversed(rows[-2:])), rows[:-1]+[rows[-2],rows[-1]]):
        assert e.forecast(altered,'BTCUSDT','15',now).status=='UNAVAILABLE'


def test_no_data_and_stale_data_have_no_prediction(monkeypatch):
    rows=candles();now=clock(monkeypatch,rows,delta=STEP+12)
    for subset in ([], rows[:12], rows):
        f=HistoricalVolatilityBaseline().forecast(subset,'BTCUSDT','15',now)
        assert f.status=='UNAVAILABLE' and not f.points


def test_flat_market_does_not_invent_trend(monkeypatch):
    rows=candles(low_variance=True);now=clock(monkeypatch,rows)
    f=HistoricalVolatilityBaseline().forecast(rows,'ETHUSDT','15',now)
    assert f.status=='EXPERIMENTAL'
    assert all(p.lower==p.median==p.upper=='100.0' for p in f.points)


def test_forecast_identity_is_stable_with_same_closed_inputs(monkeypatch):
    rows=candles();now=clock(monkeypatch,rows)
    e=HistoricalVolatilityBaseline()
    assert e.forecast(rows,'SOLUSDT','15',now)==e.forecast(rows,'SOLUSDT','15',now)


def test_invalid_cutoff_never_emits_a_forecast(monkeypatch):
    rows=candles();now=clock(monkeypatch,rows)
    e=HistoricalVolatilityBaseline()
    assert e.forecast(rows,'SOLUSDT','15',now+10).status=='UNAVAILABLE'
    assert e.forecast(rows,'SOLUSDT','15',now-100).status=='UNAVAILABLE'
