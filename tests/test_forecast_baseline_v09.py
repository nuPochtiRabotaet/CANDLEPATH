"""Causal baseline tests. All prices are synthetic and must never appear as live quotes."""
import math
import time
from dataclasses import replace
import pytest

from moex_intelligence.crypto.forecast_baseline import HistoricalVolatilityBaseline, candle_stream_ready
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


def test_candle_stream_readiness_independent_of_trade_quote():
    from moex_intelligence.crypto.forecast_baseline import candle_stream_ready
    snapshot={'fresh': False, 'candles': [{'closed': False}], 'readiness': {
        'forecast_feed_ready': True,'market_stream_active': False,'candle_data_fresh': True,
        'trade_execution_ready': False,'bid_ask_valid': False}}
    assert candle_stream_ready(snapshot)
    snapshot['fresh']=True
    snapshot['readiness']['candle_data_fresh']=False
    assert not candle_stream_ready(snapshot)
    snapshot['readiness']['candle_data_fresh']=True
    snapshot['readiness']['forecast_feed_ready']=False
    assert not candle_stream_ready(snapshot)
    assert not candle_stream_ready({'fresh': True,'candles': [],'readiness': {}})


def test_baseline_publication_is_idempotent_on_successive_reruns(tmp_path,monkeypatch):
    from moex_intelligence.crypto.storage import Store
    from moex_intelligence.crypto.intelligence import ForecastHistory
    rows=candles()
    now=clock(monkeypatch,rows)
    engine=HistoricalVolatilityBaseline()
    history=ForecastHistory(Store(tmp_path/'forecast.sqlite'))
    first=engine.forecast(rows,'BTCUSDT','15',now)
    original=history.publish(first,now=now)
    monkeypatch.setattr('moex_intelligence.crypto.forecast_baseline.time.time',lambda: now+30)
    later=engine.forecast(rows,'BTCUSDT','15',now+30)
    assert later.id==first.id
    assert later.created_at>first.created_at
    assert history.publish(later,now=now+30)==original
    assert len(history.records())==1
    with pytest.raises(ValueError,match='immutable'):
        history.publish(replace(later,points=(replace(later.points[0],median='9999'),)+later.points[1:]),now=now+30)
    assert history.records()[0]['forecast']==original


def test_snapshot_candle_readiness_without_any_executable_quote():
    import threading
    from moex_intelligence.crypto.market import Feed
    step=900
    now=time.time()
    open_time=int(now//step)*step
    feed=object.__new__(Feed)
    feed.symbol='BTCUSDT'
    feed.interval='15'
    feed.lock=threading.RLock()
    feed.rows=[Candle(open_time,100,101,99,100,5,False)]
    feed.rules=None
    feed.quote={}
    feed.status='Synchronizing'
    feed.last_ws=now
    feed.last_candle_event=now
    feed.transport_connected=True
    feed.stop=threading.Event()
    feed.error=''
    feed.events=[]
    feed.version=1
    snap=feed.snapshot()
    assert not snap['fresh'] and not snap['readiness']['market_stream_active']
    assert snap['readiness']['forecast_feed_ready']
    assert candle_stream_ready(snap)
    feed.last_candle_event=now-200
    snap=feed.snapshot()
    assert not snap['readiness']['forecast_feed_ready']
    feed.last_candle_event=time.time()
    feed.transport_connected=False
    assert not feed.snapshot()['readiness']['forecast_feed_ready']


def test_snapshot_fresh_trade_quote_does_not_override_stale_candles():
    import threading
    from moex_intelligence.crypto.market import Feed
    now=time.time()
    feed=object.__new__(Feed)
    feed.symbol='SOLUSDT'
    feed.interval='1'
    feed.lock=threading.RLock()
    feed.rows=[Candle(int(now//60)*60,100,101,99,100,5,False)]
    feed.rules=None
    feed.quote={'price':100,'bid':99.9,'ask':100.1,'ts':now}
    feed.status='Live'
    feed.last_ws=now
    feed.last_candle_event=now-100
    feed.transport_connected=True
    feed.stop=threading.Event()
    feed.error=''
    feed.events=[]
    feed.version=1
    snap=feed.snapshot()
    assert not snap['readiness']['forecast_feed_ready']
    assert not candle_stream_ready(snap)
