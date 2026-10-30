"""Regression tests for ten CandlePath v0.9 hardening passes.

All quotes and candles used here are SYNTHETIC; no trading is executed.
"""
from dataclasses import replace
import math
import threading
import time

import pytest

from moex_intelligence.crypto.forecast_baseline import HistoricalVolatilityBaseline, candle_stream_ready
from moex_intelligence.crypto.intelligence import Forecast, ForecastPoint, ForecastHistory, validate
from moex_intelligence.crypto.market import Candle, Feed
from moex_intelligence.crypto.storage import Store

STEP = 900


def candles(n=90):
    end=int(time.time()//STEP)*STEP
    return [Candle(end-(n-i)*STEP,100+i*.02,101+i*.02,99+i*.02,
                   100+i*.02,5.,True) for i in range(n)]


def sample(ident='f-a'):
    return Forecast(ident,'BTCUSDT','15',1800,1799,'test-v1','EXPERIMENTAL',
                    (ForecastPoint(2700,'90','100','110'),),.8)


def feed():
    f=object.__new__(Feed)
    now=time.time()
    f.symbol='BTCUSDT';f.interval='15';f.lock=threading.RLock()
    f.rows=[Candle(int(now//STEP)*STEP,100,101,99,100,5,False)]
    f.rules=None;f.quote={};f.status='Synchronizing'
    f.last_ws=now;f.last_candle_event=now;f.transport_connected=True
    f.stop=threading.Event();f.error='';f.events=[];f.version=1
    return f


def test_01_candle_readiness_does_not_require_trade_quote():
    snap=feed().snapshot()
    assert snap['readiness']['forecast_feed_ready']
    assert not snap['readiness']['trade_execution_ready']
    assert candle_stream_ready(snap)


def test_02_quote_cannot_rescue_stale_or_disconnected_candles():
    f=feed()
    f.status='Live';f.quote={'price':100,'bid':99.9,'ask':100.1,'ts':time.time()}
    f.last_candle_event=time.time()-200
    assert not candle_stream_ready(f.snapshot())
    f.last_candle_event=time.time();f.transport_connected=False
    assert not candle_stream_ready(f.snapshot())
    assert not candle_stream_ready({
        'readiness':{'forecast_feed_ready':True,'candle_data_fresh':True},'candles':[]})


@pytest.mark.parametrize('cutoff',['bad',None,float('nan'),float('inf'),True])
def test_03_bad_cutoff_is_unavailable_not_an_exception(cutoff):
    result=HistoricalVolatilityBaseline().forecast(candles(),'BTCUSDT','15',cutoff)
    assert result.status=='UNAVAILABLE' and not result.points
    assert math.isfinite(result.data_as_of)


def test_04_log_price_extremes_do_not_crash():
    rows=candles()
    extreme=[{'time':r.time,'close':1e-310 if i%2 else 1e308,'closed':True}
             for i,r in enumerate(rows)]
    assert HistoricalVolatilityBaseline().forecast(
        extreme,'BTCUSDT','15',time.time()).status=='UNAVAILABLE'


@pytest.mark.parametrize('row',[None,{'closed':'False','time':1,'close':100},
                                {'closed':True,'time':1,'close':True},
                                {'closed':True,'time':1,'close':0}])
def test_05_malformed_candles_fail_closed(row):
    rows=candles();rows[5]=row
    assert HistoricalVolatilityBaseline().forecast(
        rows,'BTCUSDT','15',time.time()).status=='UNAVAILABLE'


def test_06_horizons_use_only_closed_causal_data():
    rows=candles()
    e=HistoricalVolatilityBaseline()
    forecast=e.forecast(rows,'BTCUSDT','15',time.time())
    assert forecast.status=='EXPERIMENTAL'
    validate(forecast,time.time())
    assert [p.target_time-forecast.data_as_of for p in forecast.points]==[900,1800,3600,7200]
    future=rows+[Candle(rows[-1].time+STEP,100,101,99,100,5,True)]
    assert e.forecast(future,'BTCUSDT','15',time.time()).status=='UNAVAILABLE'
    partial=rows+[Candle(rows[-1].time+STEP,1000,1001,999,1000,5,False)]
    assert e.forecast(partial,'BTCUSDT','15',time.time()).points==forecast.points


def test_07_same_prediction_new_created_at_remains_immutable(tmp_path):
    h=ForecastHistory(Store(tmp_path/'f.sqlite'))
    a=sample()
    original=h.publish(a,now=1900)
    assert h.publish(replace(a,created_at=1850),now=2000)==original
    assert h.records()[0]['forecast']==original


def test_08_content_conflict_with_same_id_still_rejected(tmp_path):
    h=ForecastHistory(Store(tmp_path/'f.sqlite'))
    a=sample();h.publish(a,now=1900)
    with pytest.raises(ValueError,match='immutable'):
        h.publish(replace(a,points=(ForecastPoint(2700,'80','100','120'),)),now=1900)
    assert len(h.records())==1


def test_09_maturity_idempotence_and_honest_empirical_score(tmp_path):
    store=Store(tmp_path/'f.sqlite');h=ForecastHistory(store)
    h.publish(sample(),now=1800)
    store.save_candles('BTCUSDT','15',[Candle(1800,100,108,98,105,10,False)])
    assert h.reconcile(now=2699)==0
    assert h.reconcile(now=2700)==0
    store.save_candles('BTCUSDT','15',[Candle(1800,100,108,98,105,10,True)])
    assert h.reconcile(now=2700)==1
    assert h.reconcile(now=2701)==0
    assert ForecastHistory(Store(store.path)).reconcile(now=3000)==0
    score=h.scorecard('BTCUSDT','15')
    assert score['forecasts']==1
    assert score['horizons'][1]['observations']==1
    assert score['horizons'][1]['empirical_coverage']==1
    assert score['horizons'][1]['mean_absolute_pct_error']==pytest.approx(100*5/105)
    assert score['horizons'][1]['sufficient_sample'] is False
    assert h.scorecard('SOLUSDT','15')=={'forecasts':0,'horizons':{}}


def test_10_history_avoids_n_plus_one_sql_on_settled_outcomes(tmp_path,monkeypatch):
    store=Store(tmp_path/'f.sqlite');h=ForecastHistory(store)
    for i in range(40):
        h.publish(sample(f'f-{i}'),now=1800)
    store.save_candles('BTCUSDT','15',[Candle(1800,100,108,98,105,10,True)])
    assert h.reconcile(now=2700)==40
    trace=[];connect=store.connect
    def traced():
        db=connect();db.set_trace_callback(trace.append);return db
    monkeypatch.setattr(store,'connect',traced)
    assert h.reconcile(now=3000)==0
    assert not [sql for sql in trace if 'SELECT body FROM candles' in sql]
    trace.clear()
    assert len(h.records())==40
    assert sum('FROM forecast_outcomes' in sql for sql in trace)==1
