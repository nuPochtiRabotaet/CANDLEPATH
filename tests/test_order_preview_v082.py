import json,time,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from moex_intelligence.crypto.storage import Store
from moex_intelligence.crypto.paper import Paper
from moex_intelligence.crypto.orders import OrderPreview
from moex_intelligence.crypto.risk import RiskError,D,PROFILE

def fixture(tmp_path):
 s=Store(tmp_path/'ledger.sqlite3');p=Paper(s);g=OrderPreview(s)
 q={'BTCUSDT':{'price':100,'bid':99.99,'ask':100.01,'ts':time.time(),'fresh':True}}
 r={'BTCUSDT':{'step':'.001','tick':'.01','minimum':'5','maximum':'100','retrieved':time.time()}}
 req={'id':str(uuid.uuid4()),'symbol':'BTCUSDT','side':'BUY','quantity':'1','stop':'97','target':'106','risk_pct':.75}
 return s,p,g,q,r,req

def test_prepare_cancel_no_order(tmp_path):
 s,p,g,q,r,req=fixture(tmp_path);before=p.state();i=g.prepare(req,q,r,'owner')
 assert i['status']=='Prepared' and p.state()==before and not s.orders()
 g.cancel(i['id'],'owner')
 with pytest.raises(RiskError):g.confirm(i['id'],'owner',q,r,True)
 assert not s.orders() and p.state()==before

def test_concurrent_confirmation_restart(tmp_path):
 s,p,g,q,r,req=fixture(tmp_path);i=g.prepare(req,q,r,'owner')
 with ThreadPoolExecutor(2) as pool:out=list(pool.map(lambda _:g.confirm(i['id'],'owner',q,r,True),range(2)))
 assert all(x['status']=='Filled' for x in out) and len(s.orders())==1
 assert D(p.state()['positions']['BTCUSDT']['qty'])==1
 assert OrderPreview(Store(s.path)).confirm(i['id'],'owner',q,r,True)==out[0]
 assert g.get(i['id'])['status']=='Filled'
 assert [x['status'] for x in g.get(i['id'])['history']]==['Prepared','Confirmed','Submitted','Accepted','Filled']

@pytest.mark.parametrize('case',['ack','owner','expired','price','spread','quote','rules','cash','position','profile'])
def test_revalidation(tmp_path,case,monkeypatch):
 s,p,g,q,r,req=fixture(tmp_path);i=g.prepare(req,q,r,'owner');owner='owner';ack=True
 if case=='ack':ack=False
 if case=='owner':owner='another'
 if case=='expired':
  with s.connect() as db:i['expires']=0;db.execute('UPDATE intents SET body=? WHERE id=?',(json.dumps(i),i['id']))
 if case=='price':q['BTCUSDT'].update(price=102,bid=101.99,ask=102.01)
 if case=='spread':q['BTCUSDT']['bid']=99.8
 if case=='quote':q['BTCUSDT']['bid']=0
 if case=='rules':r['BTCUSDT']['step']='.1'
 if case in ('cash','position'):
  state=p.state()
  if case=='cash':state['cash']='9999'
  else:state['positions']['BTCUSDT']={'qty':'1','entry':'100','entry_fee':'0','stop':'97','target':'106','opened':time.time()}
  with s.connect() as db:db.execute('UPDATE paper SET body=? WHERE id=1',(json.dumps(state),))
 if case=='profile':monkeypatch.setitem(PROFILE,'positions',2)
 with pytest.raises(RiskError):g.confirm(i['id'],owner,q,r,ack)
 assert not s.orders()

@pytest.mark.parametrize('quantity',['0','-1','NaN','Infinity','.0001','10000'])
def test_invalid_quantity(tmp_path,quantity):
 s,p,g,q,r,req=fixture(tmp_path);req['quantity']=quantity
 with pytest.raises((RiskError,ArithmeticError)):g.prepare(req,q,r,'o')
 assert not s.orders()

def test_amount_rounding_and_fee(tmp_path):
 s,p,g,q,r,req=fixture(tmp_path);req.update(input_mode='amount',budget='25')
 i=g.prepare(req,q,r,'o');e=i['estimate'];assert e['amount']<=25 and e['total']==e['amount']+e['fee']
 before=D(p.state()['cash']);o=g.confirm(i['id'],'o',q,r,True)
 assert before-D(p.state()['cash'])==D(o['fill'])*D(o['quantity'])+D(o['fee'])
 assert e['quantity']==o['quantity']

def test_sell_dust_full_preview(tmp_path):
 s,p,g,q,r,req=fixture(tmp_path);req['quantity']='.1';g.confirm(g.prepare(req,q,r,'o')['id'],'o',q,r,True)
 sell={**req,'id':str(uuid.uuid4()),'side':'SELL','quantity':'.06'}
 with pytest.raises(RiskError,match='DUST'):g.prepare(sell,q,r,'o')
 sell.update(id=str(uuid.uuid4()),quantity='.1');i=g.prepare(sell,q,r,'o');assert p.state()['positions']
 assert g.confirm(i['id'],'o',q,r,True)['status']=='Filled';assert not p.state()['positions']
 assert D(p.state()['cash'])==D(p.state()['initial'])+D(p.state()['realized'])

def test_immutable_payload_and_idempotent_prepare(tmp_path):
 s,p,g,q,r,req=fixture(tmp_path);i=g.prepare(req,q,r,'o');req['quantity']='2'
 assert g.prepare(req,q,r,'o')['request']['quantity']=='1'
 i['request']['quantity']='1000'
 assert g.confirm(i['id'],'o',q,r,True)['quantity']=='1'

def test_v2_migration_preserves_state(tmp_path):
 s,p,g,q,r,req=fixture(tmp_path);before=p.state()
 with s.connect() as db:db.execute('DROP TABLE intents');db.execute('PRAGMA user_version=2')
 s2=Store(s.path);assert Paper(s2).state()==before
 assert s.path.with_name(s.path.name+'.before-v082').exists()
 with s2.connect() as db:assert db.execute('PRAGMA user_version').fetchone()[0]==5

def test_small_price_drift_uses_current_quote(tmp_path):
 s,p,g,q,r,req=fixture(tmp_path);i=g.prepare(req,q,r,'o');q['BTCUSDT'].update(price=100.02,bid=100.01,ask=100.03)
 o=g.confirm(i['id'],'o',q,r,True)
 assert o['status']=='Filled' and D(o['fill'])==D('100.03')*D('1.0005')
 assert float(o['fill'])!=i['estimate']['entry']

def test_rejections_audited(tmp_path):
 s,p,g,q,r,req=fixture(tmp_path);req['quantity']='10000'
 with pytest.raises(RiskError):g.prepare(req,q,r,'o')
 assert any('Preview blocked' in x['message'] for x in s.events())

def test_monitor_reports_stale_and_rule_recovery(tmp_path):
 from moex_intelligence.crypto.monitor import PaperMonitor
 s,p,g,q,r,req=fixture(tmp_path);g.confirm(g.prepare(req,q,r,'o')['id'],'o',q,r,True)
 class Feed:
  def snapshot(self):return {'quote':q['BTCUSDT'],'fresh':q['BTCUSDT']['fresh'],'rules':r['BTCUSDT']}
 class Hub:
  def retain(self,*args):pass
  def get(self,*args):return Feed()
 class Thread:
  alive=True
  def is_alive(self):return self.alive
 m=object.__new__(PaperMonitor);m.store=s;m.hub=Hub();m.owner='test';m.thread=Thread();m.heartbeat=0;m.ready=False;m.last_success=0;m.error='';m.health='Recovering'
 assert m.status()['state']=='Recovering'
 m.tick();assert m.status()['active'] and m.status()['state']=='Running'
 q['BTCUSDT']['fresh']=False;m.tick();assert m.status()['state']=='Stale Market Data' and not m.status()['active']
 q['BTCUSDT']['fresh']=True;r['BTCUSDT']['retrieved']=0;m.tick();assert m.status()['state']=='Degraded'
 r['BTCUSDT']['retrieved']=time.time();m.tick();assert m.status()['state']=='Running'
 m.thread.alive=False;assert m.status()['state']=='Not Monitoring' and not m.status()['active']
