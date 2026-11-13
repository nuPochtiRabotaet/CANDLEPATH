"""Synthetic causal intrabar replay. No market access, user DB, or profitability claim."""
import copy
import json
from dataclasses import asdict

import pytest

from .test_crypto_v08 import candles
from .test_market_feed_atomic_v09 import new_feed
from moex_intelligence.crypto.analysis import analyze
from moex_intelligence.crypto.lifecycle import SignalLifecycle, provisional
from moex_intelligence.crypto.market import Candle, MarketError
from moex_intelligence.crypto.storage import Store


def fixture(kind='BUY'):
    rows=candles()
    sig=next(s for s in analyze(rows,'BTCUSDT','15')['signals'] if s['type']==kind)
    i=next(i for i,r in enumerate(rows) if r['time']==sig['candle_time'])
    return rows[:i]+[{**rows[i],'closed':False}],sig


def message(rows,now):
    return {'topic':'kline.15.BTCUSDT','ts':int(now*1000),
            'data':[{'start':r['time']*1000,'confirm':r['closed'],
                     **{k:str(r[k]) for k in ('open','high','low','close','volume')}} for r in rows]}


def records(store):
    with store.connect() as db:
        return {i:json.loads(b) for i,b in db.execute('SELECT id,body FROM lifecycle')}


def replay(tmp_path,monkeypatch,kind='BUY'):
    rows,sig=fixture(kind);clock=[rows[-1]['time']+30.25]
    monkeypatch.setattr('time.time',lambda:clock[0])
    f=new_feed(tmp_path);f.rows=[Candle(**r) for r in rows[:-1]]
    f.store.save_candles(f.symbol,f.interval,f.rows)
    f.receive(message([rows[-1]],clock[0]))
    return f,rows,sig,clock


@pytest.mark.parametrize('kind',['BUY','EXIT'])
def test_feed_detects_before_ui_and_confirms_at_real_receipt(tmp_path,monkeypatch,kind):
    def forbidden(*a,**kw):raise AssertionError('Observation cannot evaluate a portfolio')
    monkeypatch.setattr('moex_intelligence.crypto.lifecycle.plan',forbidden)
    monkeypatch.setattr('moex_intelligence.crypto.lifecycle.sell_preview',forbidden)
    f,rows,sig,clock=replay(tmp_path,monkeypatch,kind)
    r=records(f.store)[sig['id']]
    assert r['state']=='POTENTIAL' and r['confirmed_at'] is None
    assert r['potential_detected_at']==clock[0]<sig['timestamp']
    assert f.store.signals('BTCUSDT','15')==[]
    assert f.snapshot()['readiness']['forecast_feed_ready']
    # Exact boundary: unconfirmed final OHLC still cannot confirm itself.
    clock[0]=sig['timestamp'];f.receive(message([rows[-1]],clock[0]))
    assert records(f.store)[sig['id']]['confirmed_at'] is None
    clock[0]+=2.5;rows[-1]['closed']=True
    f.receive(message([rows[-1]],clock[0]))
    r=records(f.store)[sig['id']]
    assert r['confirmed_at']==clock[0] and r['available_at']==clock[0]
    assert r['potential_detected_at']==rows[-1]['time']+30.25
    assert r['state']=='CONFIRMED' and r['source']=='Bybit public WebSocket'
    published=next(s for s in f.store.signals('BTCUSDT','15') if s['id']==sig['id'])
    assert published['detected_at']==clock[0]
    assert published['potential_detected_at']==r['potential_detected_at']
    assert published['confirmed_at']==clock[0]
    assert f.signal_timing['processing_ms']>=f.signal_timing['indicators_ms']>=0


@pytest.mark.parametrize('kind,reverse',[('BUY',80),('EXIT',120)])
def test_transient_cancellation_persists_without_ui_poll(tmp_path,monkeypatch,kind,reverse):
    f,rows,sig,clock=replay(tmp_path,monkeypatch,kind);bar=rows[-1]
    clock[0]+=.1
    altered={**bar,'close':reverse,'high':max(bar['high'],reverse),'low':min(bar['low'],reverse),'volume':bar['volume']+1}
    f.receive(message([altered],clock[0]))
    r=records(Store(f.store.path))[sig['id']]
    assert r['state']=='INVALIDATED' and r['confirmed_at'] is None
    assert r['preliminary_cancellations']==1
    assert [t['state'] for t in r['transitions']]==['POTENTIAL','INVALIDATED']
    assert r['transitions'][1]['at']-r['transitions'][0]['at']==pytest.approx(.1)
    assert f.store.signals('BTCUSDT','15')==[]


def test_duplicate_out_of_order_and_restart_preserve_detection(tmp_path,monkeypatch):
    f,rows,sig,clock=replay(tmp_path,monkeypatch);before=records(f.store);version=f.version
    msg=message([rows[-1]],clock[0]);clock[0]+=.2
    f.receive(msg)
    assert records(f.store)==before and f.version==version
    msg['ts']-=1;f.receive(msg)
    assert records(f.store)==before and f.version==version
    # New process re-observes the same candle without inventing earlier times.
    fresh=SignalLifecycle(Store(f.store.path))
    result=fresh.observe([],provisional(rows,'BTCUSDT','15'),'BTCUSDT','15',now=clock[0])
    assert result['active']['potential_detected_at']==before[sig['id']]['potential_detected_at']
    assert len([n for n in result['notifications'] if n['state']=='POTENTIAL'])==1


def test_closed_plus_new_partial_batch_confirms_previous(tmp_path,monkeypatch):
    f,rows,sig,clock=replay(tmp_path,monkeypatch)
    closed={**rows[-1],'closed':True};clock[0]=sig['timestamp']+1
    forming={**closed,'time':sig['timestamp'],'closed':False}
    f.receive(message([closed,forming],clock[0]))
    assert records(f.store)[sig['id']]['confirmed_at']==clock[0]
    assert any(s['id']==sig['id'] for s in f.store.signals('BTCUSDT','15'))


@pytest.mark.parametrize('failure',['stale','disconnect','future_clock','premature','gap','source_early'])
def test_unreliable_feed_never_exposes_current_potential(tmp_path,monkeypatch,failure):
    f,rows,sig,clock=replay(tmp_path,monkeypatch);bar=rows[-1]
    if failure=='stale':clock[0]+=66
    elif failure=='disconnect':f.transport_connected=False;f.status='Connection Lost'
    else:
        msg=message([bar],clock[0]+.1)
        if failure=='future_clock':msg['ts']+=10_000
        elif failure=='premature':msg['data'][0]['confirm']=True
        elif failure=='gap':
            clock[0]+=1800;msg['ts']=int(clock[0]*1000);msg['data'][0]['start']+=1800_000
        elif failure=='source_early':
            clock[0]=sig['timestamp']+1;msg['data'][0]['confirm']=True
        with pytest.raises(MarketError):f.receive(msg)
    snap=f.snapshot();assert not snap['readiness']['forecast_feed_ready']
    result=SignalLifecycle(f.store).update([],[],'BTCUSDT','15',{},'Uncertain',{},None,'0',
        now=clock[0],candle_fresh=snap['readiness']['forecast_feed_ready'],observe=False)
    assert result['active']['state']=='INVALIDATED'
    assert records(f.store)[sig['id']]['confirmed_at'] is None


def test_reconnect_revalidates_and_closed_history_is_frozen(tmp_path,monkeypatch):
    f,rows,sig,clock=replay(tmp_path,monkeypatch)
    SignalLifecycle(f.store).observe([],[],'BTCUSDT','15',now=clock[0],fresh=False)
    clock[0]+=1;f.receive(message([rows[-1]],clock[0]))
    assert records(f.store)[sig['id']]['state']=='POTENTIAL'
    clock[0]=sig['timestamp'];rows[-1]['closed']=True;f.receive(message([rows[-1]],clock[0]))
    old=f.store.signals('BTCUSDT','15');r=records(f.store)[sig['id']]
    for i in range(1,4):
        clock[0]+=900;future={**rows[-1],'time':rows[-1]['time']+900*i}
        f.receive(message([future],clock[0]))
    assert f.store.signals('BTCUSDT','15')[:len(old)]==old
    after=records(f.store)[sig['id']]
    assert all(after[k]==r[k] for k in ('reference_price','confirmed_at','potential_detected_at','explanation','observed_at'))
    corrected={**rows[-1],'close':rows[-1]['close']+.01}
    with pytest.raises(MarketError):f.receive(message([corrected],clock[0]+.1))
    assert f.store.signals('BTCUSDT','15')[:len(old)]==old


@pytest.mark.parametrize('kind',['BUY','EXIT'])
def test_latest_only_equivalent_and_no_input_mutation(kind):
    rows,sig=fixture(kind);before=copy.deepcopy(rows)
    full=analyze(rows,'BTCUSDT','15',include_forming=True)
    tail=analyze(rows,'BTCUSDT','15',include_forming=True,latest_only=True)
    assert tail['signals']==[s for s in full['signals'] if s['candle_time']==rows[-1]['time']]
    assert tail['overlay']==full['overlay'][-1:]
    assert rows==before and sig['id'] in [s['id'] for s in provisional(rows,'BTCUSDT','15')]
    assert sig['id'] not in [s['id'] for s in analyze(rows,'BTCUSDT','15')['signals']]


def test_stale_observation_has_no_false_potential_notification(tmp_path,monkeypatch):
    rows,sig=fixture();f=new_feed(tmp_path);f.rows=[Candle(**r) for r in rows[:-1]]
    now=rows[-1]['time']+100;monkeypatch.setattr('time.time',lambda:now)
    f.receive(message([rows[-1]],now-70))
    assert sig['id'] not in records(f.store)
    assert not f.snapshot()['readiness']['forecast_feed_ready']


def test_watching_is_not_first_potential_and_clock_rollback_cannot_rewrite(tmp_path,monkeypatch):
    rows,sig=fixture();f=new_feed(tmp_path);engine=SignalLifecycle(f.store);now=rows[-1]['time']+10
    watching={**sig,'status':'WATCHING'};potential={**sig,'status':'POTENTIAL'}
    engine.observe([],[watching],'BTCUSDT','15',now=now)
    engine.observe([],[potential],'BTCUSDT','15',now=now+2)
    r=records(f.store)[sig['id']]
    assert r['first_seen']==now and r['potential_detected_at']==now+2
    engine.observe([],[],'BTCUSDT','15',now=now-1)
    assert records(f.store)[sig['id']]==r


def test_conflicting_timestamp_and_old_candle_cannot_refresh_current(tmp_path,monkeypatch):
    f,rows,sig,clock=replay(tmp_path,monkeypatch);old_stamp=f.last_candle_event
    clock[0]+=2
    f.receive(message([rows[-2]],clock[0]))
    assert f.last_candle_event==old_stamp
    msg=message([{**rows[-1],'volume':rows[-1]['volume']+1}],old_stamp)
    with pytest.raises(MarketError,match='одинаковым'):f.receive(msg)
    # Fresh ticker traffic cannot clear an unhealed candle validation error.
    from .test_market_feed_atomic_v09 import ticker
    f.receive(ticker(clock[0]))
    assert not f.snapshot()['readiness']['forecast_feed_ready']


def test_ui_snapshot_cannot_see_later_feed_observation(tmp_path,monkeypatch):
    f,rows,sig,clock=replay(tmp_path,monkeypatch);snapshot_at=clock[0]
    clock[0]+=1;f.receive(message([rows[-1]],clock[0]))
    result=SignalLifecycle(f.store).update([],[],'BTCUSDT','15',{},'Uncertain',{},None,'0',
        now=clock[0],candle_fresh=True,observe=False,as_of=snapshot_at)
    assert result['active']['state']=='NO_SIGNAL'
    assert records(f.store)[sig['id']]['state']=='POTENTIAL'
