import json,time,uuid
from decimal import Decimal as D
from moex_intelligence.crypto.performance import report,build_report,statistics,record_equity
from moex_intelligence.crypto.orders import OrderPreview
from moex_intelligence.crypto.paper import Paper
from moex_intelligence.crypto.storage import Store
from tests.test_inventory_protection_rc3 import fixture,sell


def test_real_ledger_fees_partial_writeoff_restart(tmp_path):
 s,p,g,q,r=fixture(tmp_path);sell(g,q,r,'.5')
 partial=report(s);assert partial['summary']['closed_positions']==0 and partial['partial_positions']==1
 sell(g,q,r,'.498',True);p.write_off_dust('BTCUSDT',str(uuid.uuid4()),True,quotes=q,rules=r)
 out=report(Store(s.path));assert out['summary']['closed_positions']==1
 assert out['realized_reconciles'] and out['cash_reconciles'];t=out['trades'][0]
 assert t['contains_writeoff'] and t['exit_orders']==3 and t['initial_risk'] is not None
 assert D(t['net_pnl'])==D(p.state()['realized'])
 assert D(t['gross_pnl'])==D(t['net_pnl'])+D(out['fees_in_period'])
 assert t['strategy']=='Manual / no signal';assert len(out['observed_equity'])==4


def test_full_history_not_last_200_and_window():
 orders=[];cash=D('1000');realized=D(0)
 for i in range(120):
  orders.append({'id':str(i),'symbol':'BTCUSDT','side':'BUY','status':'Filled','time':i*3,'quantity':'1','fill':'100','fee':'0.1','cash_delta':'-100.1'});cash-=D('100.1')
  for j in (1,2):
   profit=D('.95') if i%2==0 else D('-.55');proceeds=D('50.05')+profit;cash+=proceeds;realized+=profit
   orders.append({'id':f'{i}-{j}','symbol':'BTCUSDT','position_id':'BTCUSDT:'+str(i),'side':'SELL','status':'Filled','time':i*3+j,'quantity':'.5','fill':'100','fee':'.05','cash_delta':str(proceeds),'realized':str(profit)})
 state={'initial':'1000','cash':str(cash),'realized':str(realized),'positions':{}}
 out=build_report(state,orders,[]);assert out['total_order_count']==360 and out['summary']['closed_positions']==120
 assert out['realized_reconciles'] and out['cash_reconciles'];assert D(out['summary']['net_pnl'])==48
 assert D(out['summary']['win_rate'])==D('.5')
 filtered=build_report(state,orders,[],start=300,end=330);assert filtered['summary']['closed_positions']==10
 assert all(t['initial_risk'] is None for t in filtered['trades'])


def test_no_infinity_or_invented_legacy_metadata():
 assert statistics([])['profit_factor'] is None
 assert statistics([{'net_pnl':'1','duration_seconds':4}])['profit_factor'] is None
 out=build_report({'initial':'100','cash':'100','realized':'0','positions':{}},[{'id':'old','symbol':'X','side':'SELL','status':'Filled','time':1,'realized':'1','quantity':'1'}],[])
 assert out['orphan_exit_orders']==['old'] and not out['realized_reconciles'] and out['cash_reconciles'] is None


def test_signal_metadata_immutable_and_explicit(tmp_path):
 s=Store(tmp_path/'x.db');p=Paper(s);g=OrderPreview(s);now=time.time()
 q={'BTCUSDT':{'bid':100,'ask':100.01,'price':100,'ts':now,'fresh':True}};rules={'BTCUSDT':{'retrieved':now,'step':'.001','tick':'.01','minimum':'5'}}
 signal={'id':'chosen','symbol':'BTCUSDT','type':'BUY','state':'POTENTIAL','strategy':'Trend Following','timeframe':'15'}
 with s.connect() as db:db.execute('INSERT INTO lifecycle VALUES(?,?)',('chosen',json.dumps(signal)))
 request={'id':str(uuid.uuid4()),'symbol':'BTCUSDT','side':'BUY','quantity':'1','stop':'97','target':'106','signal_id':'chosen','timeframe':'15','notes':'Manual hypothesis'}
 intent=g.prepare(request,q,rules,'owner');signal['state']='INVALIDATED'
 with s.connect() as db:db.execute('UPDATE lifecycle SET body=?',(json.dumps(signal),))
 o=g.confirm(intent['id'],'owner',q,rules,True)
 assert o['trade_metadata']['signal_state']=='INVALIDATED' and o['trade_metadata']['signal_state_at_preview']=='POTENTIAL'
 assert o['trade_metadata']['notes']=='Manual hypothesis' and o['status']=='Filled'
 with s.connect() as db:db.execute('DELETE FROM lifecycle')
 assert g.confirm(intent['id'],'owner',q,rules,True)==o


def test_mtm_observations_gaps_and_stale(tmp_path):
 s,p,g,q,r=fixture(tmp_path,False)
 with s.connect() as db:record_equity(db,p.state(),q,now=time.time()+300)
 out=report(s);assert out['observed_equity'][-1]['complete'] is False
 assert out['mtm_history_start'] is not None
