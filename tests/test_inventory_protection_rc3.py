import copy,json,time,uuid
from decimal import Decimal as D
from concurrent.futures import ThreadPoolExecutor
import pytest
from moex_intelligence.crypto.storage import Store
from moex_intelligence.crypto.paper import Paper,position_key
from moex_intelligence.crypto.orders import OrderPreview
from moex_intelligence.crypto.protection import ProtectionPreview
from moex_intelligence.crypto.inventory import inventory,position_revision
from moex_intelligence.crypto.costs import CostModel,FeeSchedule,basis,SimulatedFill
from moex_intelligence.crypto.risk import RiskError


def fixture(tmp_path,base=True):
 s=Store(tmp_path/'paper.sqlite3');p=Paper(s);p.configure_costs(CostModel(FeeSchedule(buy_currency='base' if base else 'quote',taker='.0013')))
 q={'BTCUSDT':{'price':100,'bid':99.99,'ask':100.01,'ts':time.time(),'fresh':True}}
 r={'BTCUSDT':{'step':'.001','tick':'.01','minimum':'5','maximum':'100','retrieved':time.time()}}
 g=OrderPreview(s);req={'id':str(uuid.uuid4()),'symbol':'BTCUSDT','side':'BUY','quantity':'1','stop':'97','target':'106'}
 assert g.confirm(g.prepare(req,q,r,'owner')['id'],'owner',q,r,True)['status']=='Filled'
 return s,p,g,q,r


def invariant(p):
 s=p.state()
 assert D(s['cash'])+sum((basis(x) for x in s['positions'].values()),D(0))==D(s['initial'])+D(s['realized'])


def sell(g,q,r,qty,dispose=False):
 req={'id':str(uuid.uuid4()),'symbol':'BTCUSDT','side':'SELL','quantity':qty,'dispose_sellable':dispose}
 i=g.prepare(req,q,r,'owner')
 return i,g.confirm(i['id'],'owner',q,r,True)


def test_base_decomposition_and_partial(tmp_path):
 s,p,g,q,r=fixture(tmp_path);pos=p.state()['positions']['BTCUSDT'];a=inventory(pos['qty'],q['BTCUSDT'],r['BTCUSDT'],CostModel.from_state(p.state()),basis(pos))
 assert a['net_holdings']=='0.9987' and a['sellable_quantity']=='0.998' and a['non_sellable_residue']=='0.0007'
 assert not a['fully_sellable'] and D(a['residue_value'])-D(a['residue_basis'])==D(a['residue_unrealized'])
 _,out=sell(g,q,r,'.5')
 assert out['status']=='Filled' and p.state()['positions']['BTCUSDT']['qty']=='0.4987';invariant(p)


def test_sell_available_preserves_residue_basis_and_writeoff(tmp_path):
 s,p,g,q,r=fixture(tmp_path);old=p.state()['positions']['BTCUSDT']
 i,out=sell(g,q,r,'.998',True);res=p.state()['positions']['BTCUSDT']
 assert i['estimate']['remaining_quantity']=='0.0007' and out['status']=='Filled' and res['qty']=='0.0007'
 assert basis(res)==basis(old)-D(out['allocated_basis']);invariant(p)
 assert g.confirm(i['id'],'owner',q,r,True)==out
 cash=p.state()['cash'];rid=str(uuid.uuid4())
 written=p.write_off_dust('BTCUSDT',rid,True,expected_position=position_revision(res),quotes=q,rules=r)
 assert written['status']=='Written Off' and written['cash_delta']=='0' and p.state()['cash']==cash
 assert p.write_off_dust('BTCUSDT',rid,True)==written;invariant(p)


def test_no_new_unconfirmed_dust_or_oversell(tmp_path):
 s,p,g,q,r=fixture(tmp_path,False);before=p.state()
 for qty in ['.99','1.001','1.0001']:
  with pytest.raises((RiskError,ValueError)):sell(g,q,r,qty)
 assert p.state()==before
 with pytest.raises(RiskError):p.write_off_dust('BTCUSDT',str(uuid.uuid4()),True,expected_position=position_revision(before['positions']['BTCUSDT']),quotes=q,rules=r)


def test_protect_sells_available_then_rules_recovery(tmp_path):
 s,p,g,q,r=fixture(tmp_path);q['BTCUSDT'].update(price=96,bid=95.99,ask=96.01)
 p.protect(q,r);assert p.state()['positions']['BTCUSDT']['qty']=='0.0007';invariant(p)
 assert s.orders()[0]['quantity']=='0.998' and s.orders()[0]['status']=='Filled'
 p.protect(q,r);count=len(s.orders());assert s.orders()[0]['status']=='Rejected'
 p.protect(q,r);assert len(s.orders())==count
 r['BTCUSDT'].update(step='.0001',minimum='.01');p.protect(q,r)
 assert not p.state()['positions'];invariant(p)
 p.protect(q,r);assert len(s.orders())==count+1


def test_maximum_preserves_tradeable_remainder(tmp_path):
 s,p,g,q,r=fixture(tmp_path);r['BTCUSDT']['maximum']='.5'
 pos=p.state()['positions']['BTCUSDT'];a=inventory(pos['qty'],q['BTCUSDT'],r['BTCUSDT'],CostModel.from_state(p.state()),basis(pos))
 assert a['sellable_quantity']=='0.5' and a['non_sellable_residue']=='0.0007' and a['remaining_after_sale']=='0.4987'
 sell(g,q,r,'.5',True);invariant(p)


@pytest.mark.parametrize('step,minimum,expected',[('.001','5','.998'),('.01','5','.99'),('1','5','0'),('.001','1000','0')])
def test_rule_changes(step,minimum,expected):
 a=inventory('.9987',{'bid':'100'},{'step':step,'minimum':minimum,'maximum':'100'},CostModel())
 assert D(a['sellable_quantity'])==D(expected)
 assert D(a['net_holdings'])==D(a['sellable_quantity'])+D(a['remaining_after_sale'])


def prepare_protection(s,q,r):
 g=ProtectionPreview(s);i=g.prepare({'id':str(uuid.uuid4()),'symbol':'BTCUSDT','stop':'98','target':'107'},q,r,'owner');return g,i


def test_protection_edit_cancel_idempotence_restart(tmp_path):
 s,p,_,q,r=fixture(tmp_path);before=p.state();g,i=prepare_protection(s,q,r)
 assert p.state()==before and i['estimate']['old_stop']=='97' and D(i['estimate']['risk_delta'])<0
 g.cancel(i['id'],'owner')
 with pytest.raises(RiskError):g.confirm(i['id'],'owner',q,r,True)
 g,i=prepare_protection(s,q,r)
 with ThreadPoolExecutor(2) as pool:outputs=list(pool.map(lambda _:g.confirm(i['id'],'owner',q,r,True),range(2)))
 assert outputs[0]==outputs[1] and outputs[0]['status']=='Applied'
 assert len(s.orders())==1 and p.state()['cash']==before['cash']
 assert p.state()['positions']['BTCUSDT']['stop']=='98'
 assert ProtectionPreview(Store(s.path)).confirm(i['id'],'owner',{}, {}, True)==outputs[0]
 assert sum(e['message']=='LOCAL PAPER protection updated' for e in s.events())==1


@pytest.mark.parametrize('change',['owner','ack','stale','price','spread','rules','costs','partial','closed','expired','levels'])
def test_protection_conflicts_no_posting(tmp_path,change):
 s,p,orders,q,r=fixture(tmp_path,False);g,i=prepare_protection(s,q,r);owner='owner';ack=True
 if change=='owner':owner='other'
 if change=='ack':ack=False
 if change=='stale':q['BTCUSDT']['fresh']=False
 if change=='price':q['BTCUSDT'].update(price=101,bid=100.99,ask=101.01)
 if change=='spread':q['BTCUSDT']['ask']=101
 if change=='rules':r['BTCUSDT']['step']='.01'
 if change=='costs':p.configure_costs(CostModel(FeeSchedule(taker='.002')))
 if change in ('partial','closed'):sell(orders,q,r,'.5' if change=='partial' else '1')
 if change=='expired':
  with s.connect() as db:i['expires']=0;db.execute('UPDATE intents SET body=? WHERE id=?',(json.dumps(i),i['id']))
 if change=='levels':
  other=g.prepare({'id':str(uuid.uuid4()),'symbol':'BTCUSDT','stop':'97.5','target':'106.5'},q,r,'owner');g.confirm(other['id'],'owner',q,r,True)
 before=p.state();old_orders=s.orders()
 with pytest.raises(RiskError):g.confirm(i['id'],owner,q,r,ack)
 assert p.state()==before and s.orders()==old_orders


def test_monitor_rechecks_trigger_inside_transaction(tmp_path):
 s,p,_,q,r=fixture(tmp_path,False);pos=p.state()['positions']['BTCUSDT']
 request={'id':str(uuid.uuid4()),'symbol':'BTCUSDT','side':'SELL','quantity':'1','protective_position':position_key('BTCUSDT',pos)}
 out=p.execute(request,q,r);assert out['status']=='Rejected' and p.state()['positions']


def test_monitor_and_edit_serialized(tmp_path):
 s,p,_,q,r=fixture(tmp_path,False);g,i=prepare_protection(s,q,r)
 stopped=copy.deepcopy(q);stopped['BTCUSDT'].update(price=96,bid=95.99,ask=96.01)
 def edit():
  try:return g.confirm(i['id'],'owner',q,r,True)
  except RiskError:return None
 with ThreadPoolExecutor(2) as pool:
  a=pool.submit(edit);b=pool.submit(p.protect,stopped,r);a.result();b.result()
 assert not p.state()['positions'] and len([o for o in s.orders() if o['side']=='SELL' and o['status']=='Filled'])==1
 invariant(p)


def test_writeoff_revision_conflict(tmp_path):
 s,p,g,q,r=fixture(tmp_path);old=position_revision(p.state()['positions']['BTCUSDT'])
 sell(g,q,r,'.998',True);before=p.state()
 with pytest.raises(RiskError):p.write_off_dust('BTCUSDT',str(uuid.uuid4()),True,expected_position=old,quotes=q,rules=r)
 assert p.state()==before


def test_posting_failure_restores_state(tmp_path,monkeypatch):
 s,p,g,q,r=fixture(tmp_path);before=p.state()
 def broken(self):raise ValueError('injected snapshot failure')
 monkeypatch.setattr(SimulatedFill,'snapshot',broken)
 out=p.execute({'id':str(uuid.uuid4()),'symbol':'BTCUSDT','side':'SELL','quantity':'.5'},q,r)
 # refresh may update mark, but balances, basis and holdings must be identical.
 after=p.state()
 for key in ('cash','positions','realized'):assert after[key]==before[key]
 assert out['status']=='Rejected';invariant(p)


def test_v4_backup_and_no_data_rewrite(tmp_path):
 s,p,g,q,r=fixture(tmp_path);before=p.state()
 with s.connect() as db:db.execute('PRAGMA user_version=4')
 s=Store(s.path)
 assert s.path.with_name(s.path.name+'.before-rc3').exists() and Paper(s).state()==before
 with s.connect() as db:assert db.execute('PRAGMA user_version').fetchone()[0]==5


def test_protection_risk_increase_is_blocked(tmp_path):
 s,p,g,q,r=fixture(tmp_path,False)
 with pytest.raises(RiskError,match='Увеличение риска'):
  ProtectionPreview(s).prepare({'id':str(uuid.uuid4()),'symbol':'BTCUSDT','stop':'1','target':'107'},q,r,'owner')


def test_changed_protection_coverage_requires_confirmation(tmp_path):
 s,p,g,q,r=fixture(tmp_path)
 r['BTCUSDT']['step']='.01'
 stopped=copy.deepcopy(q);stopped['BTCUSDT'].update(price=96,bid=95.99,ask=96.01)
 p.protect(stopped,r)
 assert s.orders()[0]['status']=='Rejected' and p.state()['positions']['BTCUSDT']['qty']=='0.9987'
 edit,i=prepare_protection(s,q,r);edit.confirm(i['id'],'owner',q,r,True)
 assert p.state()['positions']['BTCUSDT']['protection_residue_limit']=='0.0087'
 p.protect(stopped,r)
 assert s.orders()[0]['status']=='Filled' and p.state()['positions']['BTCUSDT']['qty']=='0.0087'
 invariant(p)


def test_aggregate_risk_includes_non_executable_residue(tmp_path):
 from moex_intelligence.crypto.risk import metrics
 s,p,g,q,r=fixture(tmp_path);pos=p.state()['positions']['BTCUSDT']
 from moex_intelligence.crypto.inventory import liquidation_at
 _,proceeds=liquidation_at(pos,pos['stop'],r['BTCUSDT'],CostModel.from_state(p.state()))
 m=metrics(p.state(),q,rules=r)
 assert D(m['risk_decimal'])==D(pos['qty'])*D(str(q['BTCUSDT']['bid']))-proceeds
 unknown=metrics(p.state(),q,rules={})
 assert D(unknown['risk_decimal'])==D(pos['qty'])*D(str(q['BTCUSDT']['bid']))
 assert D(unknown['liquidation_equity'])==D(p.state()['cash'])
