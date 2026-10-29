import asyncio,copy,json,math,time,uuid,threading
from dataclasses import asdict
import httpx,numpy as np,pytest
from moex_intelligence.crypto.market import Bybit,Candle,MarketError,merge_candles,Feed
from moex_intelligence.crypto.analysis import indicators,ema,wilder,analyze
from moex_intelligence.crypto.storage import Store
from moex_intelligence.crypto.risk import D,floor_step,plan,metrics,RiskError
from moex_intelligence.crypto.paper import Paper,transition,LiveExecutionDisabled

def candles(n=220):
    out=[];base=1700000100//900*900
    for i in range(n):
        c=100+12*math.sin(i/18)+i*.025;o=100+12*math.sin((i-1)/18)+(i-1)*.025
        out.append(dict(time=base+i*900,open=o,high=max(o,c)+.5,low=min(o,c)-.5,close=c,volume=100+50*(i%7),closed=True))
    return out

def setup(tmp_path):
    store=Store(tmp_path/'crypto.sqlite3');paper=Paper(store);q={'BTCUSDT':{'price':100,'bid':99.99,'ask':100.01,'ts':time.time(),'fresh':True}}
    rules={'BTCUSDT':{'step':'.01','tick':'.01','minimum':'5','maximum':'100','retrieved':time.time()}}
    return store,paper,q,rules

def order(side='BUY',quantity='10',**extra):return {'id':str(uuid.uuid4()),'symbol':'BTCUSDT','side':side,'quantity':quantity,'stop':'98','target':'105',**extra}

def test_ema_wilder_vectors():
    assert ema([1,2,3,4],3)==pytest.approx([1,1.5,2.25,3.125])
    assert np.isnan(wilder([1,2,3,4],3)[0]);assert wilder([1,2,3,4],3)[2:]==pytest.approx([2,8/3])

def test_atr_rsi_supertrend():
    rows=[dict(time=i*900,open=100+i,high=101+i,low=99+i,close=100+i,volume=1,closed=True) for i in range(100)]
    f=indicators(rows);assert f.atr.iloc[-1]==pytest.approx(2);assert f.rsi.iloc[-1]==100;assert f.direction.iloc[-1]==1;assert f.supertrend.iloc[-1]<f.close.iloc[-1]
    for r in rows:r.update(open=100,high=101,low=99,close=100)
    assert indicators(rows).rsi.iloc[-1]==50

def test_causal_prefix_stream_restart(tmp_path):
    rows=candles();full=analyze(rows,'BTCUSDT','15');assert full['signals'];assert {s['type'] for s in full['signals']}=={'BUY','EXIT'}
    prior=[]
    for i in range(56,len(rows)+1):
        prefix=analyze(rows[:i],'BTCUSDT','15')['signals']
        assert prefix==[s for s in full['signals'] if s['candle_time']<=rows[i-1]['time']]
        assert prefix[:len(prior)]==prior;prior=prefix
    store=Store(tmp_path/'s.db');store.publish(full['signals']);one=store.signals('BTCUSDT','15');store=Store(tmp_path/'s.db');store.publish(full['signals']);assert store.signals('BTCUSDT','15')==one
    assert all(s['timestamp']==s['candle_time']+900 for s in one)

def test_open_candle_no_confirmation():
    rows=candles();signal=analyze(rows,'BTCUSDT','15')['signals'][-1];end=next(i+1 for i,r in enumerate(rows) if r['time']==signal['candle_time']);subset=rows[:end]
    subset[-1]['closed']=False;result=analyze(subset,'BTCUSDT','15');assert signal['id'] not in [s['id'] for s in result['signals']]
    subset[-1]['close']*=1.1;assert result['signals']==analyze(subset,'BTCUSDT','15')['signals']

def test_merge_dedupe_gap_immutability(tmp_path):
    a=Candle(0,100,101,99,100,1,False);b=Candle(900,100,102,99,101,2,True)
    rows,gaps=merge_candles([b],[a,b],'15');assert [x.time for x in rows]==[0,900];assert not gaps
    assert merge_candles([a],[Candle(1800,100,101,99,100,1,True)],'15')[1]==[(900,1800)]
    with pytest.raises(MarketError):merge_candles([b],[Candle(900,100,102,99,101,3,True)],'15')
    store=Store(tmp_path/'s.db');store.save_candles('BTCUSDT','15',[b]);
    with pytest.raises(MarketError):store.save_candles('BTCUSDT','15',[Candle(900,100,102,99,101,3,True)])

@pytest.mark.asyncio
async def test_rest_adapter_sort_closed_errors():
    async def handler(req):return httpx.Response(200,json={'retCode':0,'time':1800000,'result':{'list':[['1800000','100','101','99','100','2','200'],['900000','100','101','99','100','1','100']]}})
    api=Bybit(httpx.MockTransport(handler));rows=await api.history('BTCUSDT','15');assert [x.time for x in rows]==[900,1800];assert rows[0].closed and not rows[1].closed
    for response in [httpx.Response(200,text='<h1>Site Unavailable</h1>'),httpx.Response(403),httpx.Response(200,json={'retCode':10001})]:
        api=Bybit(httpx.MockTransport(lambda _:response))
        with pytest.raises(MarketError):await api.history('BTCUSDT','15')

@pytest.mark.asyncio
async def test_actual_local_websocket_protocol():
    from websockets.asyncio.server import serve
    received=[];stop=threading.Event()
    async def server(ws):
        sub=json.loads(await ws.recv());assert sub['args']==['kline.15.BTCUSDT','tickers.BTCUSDT']
        await ws.send(json.dumps({'topic':'kline.15.BTCUSDT','ts':1800000,'data':[{'start':900000,'open':'100','high':'101','low':'99','close':'100','volume':'5','confirm':True}]}))
        await asyncio.sleep(.05)
    async with serve(server,'127.0.0.1',0) as srv:
        api=Bybit();api.ws='ws://127.0.0.1:'+str(srv.sockets[0].getsockname()[1])
        def handler(b):received.append(b);stop.set()
        await api.stream('BTCUSDT','15',handler,stop)
    assert received[0]['data'][0]['confirm']

def test_feed_receive_duplicate_closed_and_stale(tmp_path):
    f=object.__new__(Feed);f.symbol='BTCUSDT';f.interval='15';f.lock=threading.RLock();f.rows=[];f.store=Store(tmp_path/'s.db');f.quote={};f.version=0;f.status='Connecting';f.rules={};f.error='';f.events=[];f.last_ws=0
    now=time.time();c={'start':900000,'open':'100','high':'101','low':'99','close':'100','volume':'5','confirm':True}
    f.receive({'topic':'kline.15.BTCUSDT','ts':now*1000,'data':[c]});f.receive({'topic':'kline.15.BTCUSDT','ts':now*1000,'data':[c]});assert len(f.rows)==1
    f.receive({'topic':'tickers.BTCUSDT','ts':now*1000,'data':{'lastPrice':'100','bid1Price':'99','ask1Price':'101'}});assert f.snapshot()['fresh']
    f.quote['ts']=now-60;assert not f.snapshot()['fresh'];assert f.snapshot()['status']=='Stale Data'
    c={**c,'start':2700000}
    with pytest.raises(MarketError,match='пропуск'):f.receive({'topic':'kline.15.BTCUSDT','ts':now*1000,'data':[c]})

@pytest.mark.asyncio
async def test_reconnect_backfill(tmp_path):
    rows=[Candle(**x) for x in candles(6)];store=Store(tmp_path/'s.db');store.save_candles('BTCUSDT','15',rows[:2])
    class Mock:
        async def rules(self,s):return {'step':'.01'}
        async def history(self,s,i,end=None):return rows[4:] if end is None else rows[:4]
        async def ticker(self,s):return {'price':100,'ts':time.time()}
    f=object.__new__(Feed);f.symbol='BTCUSDT';f.interval='15';f.api=Mock();f.rows=store.candles('BTCUSDT','15');f.store=store;f.lock=threading.RLock();f.events=[];f.version=0;f.backfills=0
    await f.sync();assert f.rows==rows;assert len(store.candles('BTCUSDT','15'))==6;assert f.backfills==1

def test_paper_round_trip_fees_partial_persistence(tmp_path):
    store,paper,q,rules=setup(tmp_path);req=order();buy=paper.execute(req,q,rules);assert buy['status']=='Filled';assert float(buy['fee'])>1
    assert paper.execute(req,q,rules)==buy;assert len(store.orders())==1
    sell=paper.execute(order('SELL','4'),q,rules);assert sell['status']=='Filled';assert float(sell['realized'])<0
    assert paper.state()['positions']['BTCUSDT']['qty']=='6';paper=Paper(Store(store.path));assert paper.state()['positions']['BTCUSDT']['qty']=='6'
    sell2=paper.execute(order('SELL','6'),q,rules);assert sell2['status']=='Filled';assert not paper.state()['positions'];assert float(paper.state()['cash'])==pytest.approx(10000+float(sell['realized'])+float(sell2['realized']))
    assert len(store.events())==3

def test_risk_gate_steps_cash_and_capital(tmp_path):
    _,p,q,r=setup(tmp_path);s=p.state();assert floor_step('1.23456','.001')==D('1.234')
    assert plan(s,q,'BTCUSDT','10','98','105',r['BTCUSDT'])['allowed']
    for kwargs in [{'quantity':'10.001'},{'stop':'98.001'},{'quantity':'.01'}]:
        vals=dict(quantity='10',stop='98',target='105');vals.update(kwargs)
        with pytest.raises(RiskError):plan(s,q,'BTCUSDT',rules=r['BTCUSDT'],**vals)
    assert not plan(s,q,'BTCUSDT','30','98','105',r['BTCUSDT'])['allowed']
    assert not plan(s,q,'BTCUSDT','10','90','105',r['BTCUSDT'])['allowed']
    q['BTCUSDT']['ts']-=30
    with pytest.raises(RiskError):plan(s,q,'BTCUSDT','10','98','105',r['BTCUSDT'])

def test_risk_drawdown_daily_weekly_and_aggregate(tmp_path):
    _,p,q,r=setup(tmp_path);s=p.state();s['peak']='11500';x=plan(s,q,'BTCUSDT','10','98','105',r['BTCUSDT']);assert any('12%' in e for e in x['errors'])
    s=p.state();s['day_equity']='10500';assert any('день' in e for e in plan(s,q,'BTCUSDT','10','98','105',r['BTCUSDT'])['errors'])
    s=p.state();s['week_equity']='11000';assert any('неделя' in e for e in plan(s,q,'BTCUSDT','10','98','105',r['BTCUSDT'])['errors'])
    s=p.state();s['peak']='11000';assert plan(s,q,'BTCUSDT','20','98','105',r['BTCUSDT'])['recommended']<plan(p.state(),q,'BTCUSDT','20','98','105',r['BTCUSDT'])['recommended']
    s=p.state();s['positions']={'ETHUSDT':{'qty':'10','entry':'100','entry_fee':'1','stop':'85'}};q['ETHUSDT']=q['BTCUSDT'];assert any('1,5%' in e for e in plan(s,q,'BTCUSDT','10','98','105',r['BTCUSDT'])['errors'])

def test_no_short_averaging_stale_or_live(tmp_path):
    _,p,q,r=setup(tmp_path);assert p.execute(order('SELL'),q,r)['status']=='Rejected';assert p.execute(order(),q,r)['status']=='Filled';assert p.execute(order(),q,r)['status']=='Rejected'
    assert p.execute(order('SELL','11'),q,r)['status']=='Rejected';q['BTCUSDT']['fresh']=False;assert p.execute(order('SELL'),q,r)['status']=='Rejected'
    with pytest.raises(RiskError):LiveExecutionDisabled().submit({})

def test_virtual_stop_gap_fill(tmp_path):
    store,p,q,r=setup(tmp_path);p.execute(order(),q,r);q['BTCUSDT'].update(price=95,bid=94.99,ask=95.01);p.protect(q,r);assert not p.state()['positions'];assert float(store.orders()[0]['fill'])<95

def test_order_state_machine():
    o={'status':'Created','history':[]}
    for state in ['Submitted','Accepted','Partially Filled','Filled']:transition(o,state)
    with pytest.raises(ValueError):transition(o,'Accepted')

def test_reconciler_ack_partial_duplicate_terminal():
    from moex_intelligence.crypto.paper import reconcile_order
    o={'id':'a','quantity':'10','filled_quantity':'0','status':'Submitted','history':[]}
    o=reconcile_order(o,{'order_id':'a','event_id':'ack','status':'Accepted'});assert o['filled_quantity']=='0'
    event={'order_id':'a','event_id':'partial','status':'Partially Filled','filled_quantity':'4'}
    o=reconcile_order(o,event);assert reconcile_order(o,event)==o
    with pytest.raises(RiskError):reconcile_order(o,{'order_id':'a','event_id':'bad','status':'Filled','filled_quantity':'6'})
    o=reconcile_order(o,{'order_id':'a','event_id':'fill','status':'Filled','filled_quantity':'10'})
    with pytest.raises((RiskError,ValueError)):reconcile_order(o,{'order_id':'a','event_id':'late','status':'Accepted','filled_quantity':'0'})

@pytest.mark.asyncio
async def test_private_readonly_permissions_and_redaction(monkeypatch):
    from moex_intelligence.crypto.private import ReadOnly
    monkeypatch.setenv('BYBIT_READONLY_KEY','sensitive-key');monkeypatch.setenv('BYBIT_READONLY_SECRET','sensitive-secret')
    client=ReadOnly();calls=[]
    async def denied(path,params=None):calls.append(path);return {'readOnly':0,'permissions':{}}
    client.get=denied
    with pytest.raises(MarketError):await client.snapshot()
    assert calls==['/v5/user/query-api']
    async def allowed(path,params=None):
        if path.endswith('query-api'):return {'readOnly':1,'apiKey':'sensitive-key','permissions':{'Wallet':[]}}
        return {'list':[{'apiKey':'sensitive-key','secret':'sensitive-secret','totalEquity':'10','symbol':'BTCUSDT','coin':[{'coin':'USDT','walletBalance':'10','secret':'sensitive-secret'}]}]}
    client.get=allowed;view=await client.snapshot();assert 'sensitive' not in json.dumps(view);assert view['balances'][0]['equity']=='10'

def test_risk_occupied_positions_missing_quote_and_sell_unchanged(tmp_path):
    _,p,q,r=setup(tmp_path);state=p.state()
    for sym in ('ETHUSDT','SOLUSDT','TEST'):
        state['positions'][sym]={'qty':'25','entry':'100','entry_fee':'2.5','stop':'99.5'};q[sym]=q['BTCUSDT']
    state['cash']='2500';result=plan(state,q,'BTCUSDT','10','98','105',r['BTCUSDT']);assert any('3 позиции' in e for e in result['errors']);assert any('75%' in e for e in result['errors'])
    del q['ETHUSDT'];assert any('свежие' in e for e in plan(state,q,'BTCUSDT','10','98','105',r['BTCUSDT'])['errors'])
    assert p.execute(order(),q,r)['status']=='Filled';before=copy.deepcopy(p.state());assert p.execute(order('SELL','100'),q,r)['status']=='Rejected';assert p.state()['cash']==before['cash'];assert p.state()['positions']==before['positions']

def test_insufficient_cash_and_future_timestamp(tmp_path):
    _,p,q,r=setup(tmp_path);s=p.state();s['cash']='500';result=plan(s,q,'BTCUSDT','10','98','105',r['BTCUSDT']);assert any('баланса' in e for e in result['errors'])
    q['BTCUSDT']['ts']=time.time()+120
    with pytest.raises(RiskError):plan(s,q,'BTCUSDT','1','98','105',r['BTCUSDT'])

def test_critical_drawdown_and_day_roll_preserves_gap(tmp_path):
    _,p,q,r=setup(tmp_path);s=p.state();s['peak']='12000';result=plan(s,q,'BTCUSDT','10','98','105',r['BTCUSDT']);assert any('15%' in e for e in result['errors'])
    s=p.state();s.update(day='2000-01-01',last_equity='10000',cash='9600');p.refresh(s,q);assert s['day_equity']=='10000';assert any('день' in e for e in plan(s,q,'BTCUSDT','1','98','105',r['BTCUSDT'])['errors'])

def test_multiple_timeframes_isolated_and_store_future_version(tmp_path):
    store=Store(tmp_path/'s.db');store.save_candles('BTCUSDT','15',[Candle(0,100,101,99,100,1,True)]);store.save_candles('BTCUSDT','60',[Candle(0,200,201,199,200,1,True)]);assert store.candles('BTCUSDT','15')[0].close==100;assert store.candles('BTCUSDT','60')[0].close==200
    with store.connect() as db:db.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError):Store(store.path)

def test_future_scorer_and_no_execution_dependency():
    from pathlib import Path
    source=Path('moex_intelligence/crypto/analysis.py').read_text();assert 'ExecutionAdapter' not in source;assert 'httpx' not in source;assert 'random' not in source
