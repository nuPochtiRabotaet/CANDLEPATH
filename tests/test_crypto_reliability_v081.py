import json,time,threading,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from moex_intelligence.crypto.paper import Paper,position_key
from moex_intelligence.crypto.storage import Store
from moex_intelligence.crypto.market import Feed
from moex_intelligence.crypto.risk import quote_ok,D
from .MOEX_v08_regression_tests import setup,order,quote


def test_retry_throttle_restart_and_no_duplicate_success(tmp_path):
    s,p,q,r=setup(tmp_path);p.execute(order('BUY','.055','90','130'),q,r);q['BTCUSDT']=quote(89,89,89.1)
    p.protect(q,r);n=len(s.orders());p=Paper(Store(s.path));p.protect(q,r);assert len(s.orders())==n
    r['BTCUSDT']['minimum']='1';p.protect(q,r);p.protect(q,r)
    assert not p.state()['positions'];assert len([o for o in s.orders() if o['side']=='SELL' and o['status']=='Filled'])==1


def test_concurrent_sells_and_exact_accounting(tmp_path):
    s,p,q,r=setup(tmp_path);p.execute(order('BUY','1'),q,r)
    with ThreadPoolExecutor(2) as pool:out=list(pool.map(lambda _:p.execute(order('SELL','1'),q,r),range(2)))
    assert sorted(x['status'] for x in out)==['Filled','Rejected'];assert not p.state()['positions']
    assert D(p.state()['cash'])==D('1000')+D(p.state()['realized'])


def test_no_partial_dust_and_explicit_writeoff(tmp_path):
    s,p,q,r=setup(tmp_path);p.execute(order('BUY','.1'),q,r);before=p.state();o=p.execute(order('SELL','.06'),q,r)
    assert o['status']=='Rejected' and 'DUST' in o['error'];assert p.state()['cash']==before['cash']
    r['BTCUSDT']['minimum']='100';assert p.execute(order('SELL','.1'),q,r)['status']=='Rejected'
    rid=str(uuid.uuid4());cash=p.state()['cash']
    with pytest.raises(ValueError):p.write_off_dust('BTCUSDT',rid)
    result=p.write_off_dust('BTCUSDT',rid,True);assert result['status']=='Written Off';assert p.state()['cash']==cash;assert not p.state()['positions']
    assert p.write_off_dust('BTCUSDT',rid,True)==result


def test_stale_sides_with_fresh_last_price():
    q=quote();q.update(price_ts=time.time(),bid_ts=time.time()-100,ask_ts=time.time()-100)
    assert not quote_ok(q)
    q.update(bid_ts=time.time(),ask_ts=time.time());assert quote_ok(q)
    q['bid']=101;assert not quote_ok(q)


def test_snapshot_missing_sides_does_not_reuse_old_values(tmp_path):
    f=object.__new__(Feed);f.symbol='BTCUSDT';f.interval='15';f.lock=threading.RLock();f.quote=quote();f.last_ws=0;f.rows=[];f.rules={};f.events=[];f.version=0;f.error='';f.status='Live'
    f.receive({'topic':'tickers.BTCUSDT','type':'snapshot','ts':time.time()*1000,'data':{'lastPrice':'101'}})
    assert not f.snapshot()['fresh'];assert f.snapshot()['readiness']['last_price_fresh'];assert not f.snapshot()['readiness']['bid_ask_valid']


def test_pending_attempt_restart_reuses_id(tmp_path):
    s,p,q,r=setup(tmp_path);p.execute(order('BUY','1'),q,r);pos=p.state()['positions']['BTCUSDT'];key=position_key('BTCUSDT',pos);rid=str(uuid.uuid4())
    with s.connect() as db:db.execute('INSERT INTO protective VALUES(?,?)',(key,json.dumps({'attempt':1,'status':'pending','order_id':rid,'next_at':0,'fingerprint':'old'})))
    q['BTCUSDT']=quote(97,97,97.1);p.protect(q,r);assert s.orders()[0]['id']==rid;assert not p.state()['positions']


def test_position_identity_cannot_close_new_position(tmp_path):
    s,p,q,r=setup(tmp_path);p.execute(order('BUY','1'),q,r);old=position_key('BTCUSDT',p.state()['positions']['BTCUSDT']);p.execute(order('SELL','1'),q,r);p.execute(order('BUY','1'),q,r)
    o=p.execute({**order('SELL','1'),'protective_position':old},q,r);assert o['status']=='Rejected';assert p.state()['positions']


def test_step_and_max_refresh_recover(tmp_path):
    s,p,q,r=setup(tmp_path);p.execute(order('BUY','.11'),q,r);q['BTCUSDT']=quote(97,97,97.1)
    r['BTCUSDT']['step']='.1';p.protect(q,r);assert s.orders()[0]['status']=='Rejected'
    r['BTCUSDT'].update(step='.001',maximum='.1');p.protect(q,r);assert s.orders()[0]['status']=='Rejected'
    r['BTCUSDT'].update(maximum='1000',tick='.1');p.protect(q,r);assert not p.state()['positions']

def test_monitor_tick_without_ui(tmp_path):
    from moex_intelligence.crypto.monitor import PaperMonitor
    s,p,q,r=setup(tmp_path);p.execute(order('BUY','1'),q,r);q['BTCUSDT']=quote(97,97,97.1)
    class Hub:
        def retain(self,*args):pass
        def get(self,*args):return self
        def snapshot(self):return {'quote':q['BTCUSDT'],'fresh':True,'rules':r['BTCUSDT']}
    m=PaperMonitor(s,Hub())
    try:
        for _ in range(100):
            if not p.state()['positions']:break
            time.sleep(.02)
        assert not p.state()['positions']
    finally:m.stop.set();m.thread.join(timeout=3)

def test_spot_book_is_independently_fresh_and_out_of_order_safe(tmp_path):
    f=object.__new__(Feed);f.symbol='BTCUSDT';f.interval='15';f.lock=threading.RLock();f.quote={};f.last_ws=0;f.rows=[];f.rules={};f.events=[];f.version=0;f.error='';f.status='Live'
    now=time.time()
    ticker=lambda ts:{'topic':'tickers.BTCUSDT','type':'snapshot','ts':ts*1000,'data':{'lastPrice':'100'}}
    book=lambda ts,bid='99.9':{'topic':'orderbook.1.BTCUSDT','type':'snapshot','ts':ts*1000,'data':{'b':[[bid,'1']],'a':[['100.1','1']]}}
    f.receive(ticker(now));assert not f.snapshot()['fresh']
    f.receive(book(now));assert f.snapshot()['fresh'];f.receive(ticker(now+.1));assert f.snapshot()['fresh']
    f.receive(book(now-1,'90'));assert f.quote['bid']==99.9
    f.book.update(bid_ts=now-30,ask_ts=now-30);f.receive(ticker(now+.2));assert not f.snapshot()['fresh']

@pytest.mark.asyncio
async def test_spot_subscription_includes_book():
    import asyncio
    from websockets.asyncio.server import serve
    from moex_intelligence.crypto.market import Bybit
    stop=threading.Event()
    async def server(ws):
        payload=json.loads(await ws.recv());assert 'orderbook.1.BTCUSDT' in payload['args'];await ws.send(json.dumps({'success':True}));await asyncio.sleep(.1)
    async with serve(server,'127.0.0.1',0) as srv:
        api=Bybit();api.ws='ws://127.0.0.1:'+str(srv.sockets[0].getsockname()[1]);await api.stream('BTCUSDT','15',lambda b:stop.set(),stop,include_book=True)

def test_schema_backup_preserves_existing_ledger(tmp_path):
    import sqlite3
    s,p,q,r=setup(tmp_path);p.execute(order('BUY','1'),q,r);before=p.state()
    with s.connect() as db:db.execute('PRAGMA user_version=1')
    upgraded=Store(s.path);assert Paper(upgraded).state()==before
    backup=s.path.with_name(s.path.name+'.before-v081');assert backup.exists()
    with sqlite3.connect(backup) as db:assert json.loads(db.execute('SELECT body FROM paper').fetchone()[0])==before
