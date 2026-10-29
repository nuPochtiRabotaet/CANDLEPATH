import json,time,uuid
from decimal import Decimal as D
import pytest
from moex_intelligence.crypto.costs import CostModel,FeeSchedule,ExecutionAssumptions,estimate,budget_quantity,basis
from moex_intelligence.crypto.orders import OrderPreview
from moex_intelligence.crypto.paper import Paper
from moex_intelligence.crypto.storage import Store
from moex_intelligence.crypto.risk import plan,metrics,RiskError
from moex_intelligence.crypto.quality import assess,QualityPolicy

def setup(tmp_path,currency='quote'):
 s=Store(tmp_path/'crypto.sqlite3');p=Paper(s);g=OrderPreview(s)
 model=CostModel(FeeSchedule(version='test-v1',maker='.0001',taker='.001',buy_currency=currency),ExecutionAssumptions('5'));p.configure_costs(model)
 q={'BTCUSDT':{'price':100,'bid':99.99,'ask':100.01,'ts':time.time(),'fresh':True}}
 r={'BTCUSDT':{'step':'.000001','tick':'.01','minimum':'5','maximum':'100','retrieved':time.time()}}
 req={'id':str(uuid.uuid4()),'symbol':'BTCUSDT','side':'BUY','quantity':'.125','stop':'97','target':'106','risk_pct':.75}
 return s,p,g,q,r,req,model

def check_identity(p,q):
 s=p.state();m=metrics(s,q)
 assert D(s['cash'])+sum((basis(x) for x in s['positions'].values()),D(0))==D(s['initial'])+D(s['realized'])
 assert D(m['equity_decimal'])==D(s['initial'])+D(s['realized'])+D(m['unrealized_decimal'])

@pytest.mark.parametrize('currency',['quote','base'])
def test_buy_partial_full_accounting(tmp_path,currency):
 s,p,g,q,r,req,model=setup(tmp_path,currency);i=g.prepare(req,q,r,'owner');out=g.confirm(i['id'],'owner',q,r,True)
 a=estimate('BUY',req['quantity'],q['BTCUSDT'],model);pos=p.state()['positions']['BTCUSDT']
 assert D(pos['qty'])==a.net_base and D(pos['cost_basis'])==-a.cash_delta
 assert D(out['net_received'])==a.net_base and D(p.state()['cash'])==D(10000)+a.cash_delta
 if currency=='base':assert D(req['quantity'])-D(pos['qty'])==a.fee_quantity
 assert i['estimate']['fill']==out['execution']['values']
 assert D(i['estimate']['costs']['loss'])==-a.cash_delta-estimate('SELL',a.net_base,{'bid':97},model).cash_delta
 check_identity(p,q)
 sell={**req,'id':str(uuid.uuid4()),'side':'SELL','quantity':'.06'}
 o=g.confirm(g.prepare(sell,q,r,'owner')['id'],'owner',q,r,True)
 assert D(o['allocated_basis'])==-a.cash_delta*D('.06')/a.net_base
 check_identity(p,q)
 sell.update(id=str(uuid.uuid4()),quantity=p.state()['positions']['BTCUSDT']['qty'])
 final=g.confirm(g.prepare(sell,q,r,'owner')['id'],'owner',q,r,True)
 assert final['status']=='Filled' and not p.state()['positions'];check_identity(p,q)
 assert D(p.state()['realized'])==sum(D(x.get('realized','0')) for x in s.orders())
 assert g.confirm(i['id'],'owner',q,r,True)==out

@pytest.mark.parametrize('currency',['base','quote'])
@pytest.mark.parametrize('budget_mode',['notional','total'])
def test_budget_25(tmp_path,currency,budget_mode):
 s,p,g,q,r,req,model=setup(tmp_path,currency);req.update(input_mode='amount',budget='25',budget_mode=budget_mode)
 i=g.prepare(req,q,r,'o');a=estimate('BUY',i['request']['quantity'],q['BTCUSDT'],model)
 assert (a.notional if budget_mode=='notional' else -a.cash_delta)<=25
 plus=estimate('BUY',a.quantity+D(r['BTCUSDT']['step']),q['BTCUSDT'],model)
 assert (plus.notional if budget_mode=='notional' else -plus.cash_delta)>25
 out=g.confirm(i['id'],'o',q,r,True);assert out['status']=='Filled' and D(out['cash_delta'])==a.cash_delta
 if budget_mode=='total':assert D(10000)-D(p.state()['cash'])<=25

@pytest.mark.parametrize('currency',['base','quote'])
def test_total_cap_not_exceeded_after_drift(tmp_path,currency):
 s,p,g,q,r,req,model=setup(tmp_path,currency);req.update(input_mode='amount',budget='25',budget_mode='total')
 i=g.prepare(req,q,r,'o');q['BTCUSDT'].update(price=100.04,bid=100.03,ask=100.05)
 with pytest.raises(RiskError,match='maximum spend'):g.confirm(i['id'],'o',q,r,True)
 assert not s.orders()

def test_schedule_change_invalidates_and_history_immutable(tmp_path):
 s,p,g,q,r,req,model=setup(tmp_path);i=g.prepare(req,q,r,'o');new=CostModel(FeeSchedule(version='v2',taker='.002'));p.configure_costs(new)
 with pytest.raises(RiskError):g.confirm(i['id'],'o',q,r,True)
 req['id']=str(uuid.uuid4());out=g.confirm(g.prepare(req,q,r,'o')['id'],'o',q,r,True)
 before=json.dumps(s.orders(),sort_keys=True);p.configure_costs(model)
 assert json.dumps(s.orders(),sort_keys=True)==before and out['execution']['model']['fees']['taker']=='.002'
 assert D(out['fee'])==D(out['fill'])*D(out['quantity'])*D('.002')

@pytest.mark.parametrize('qty',['0.00000001','0.00037','0.125','12.12345678'])
def test_small_base_no_invented_units(qty):
 model=CostModel(FeeSchedule(buy_currency='base',taker='.0013'));f=estimate('BUY',qty,{'bid':'67234.11','ask':'67235.22'},model)
 assert f.net_base+f.fee_quantity==D(qty) and -f.cash_delta==f.notional
 assert f.fee_quote_value==f.fee_quantity*f.price and f.price==D('67235.22')*D('1.0005')

def test_sell_base_blocked():
 with pytest.raises(ValueError):FeeSchedule(sell_currency='base')

def test_taker_and_spread_once():
 model=CostModel(FeeSchedule(maker='0',taker='.002'),ExecutionAssumptions('0'))
 buy=estimate('BUY','2',{'ask':101,'bid':99},model);sell=estimate('SELL','2',{'ask':101,'bid':99},model)
 assert buy.price==101 and sell.price==99 and buy.fee_quantity==D('.404')
 assert -buy.cash_delta-sell.cash_delta==D(4)+buy.fee_quantity+sell.fee_quantity

def test_fractional_base_dust_never_fake_sell(tmp_path):
 s,p,g,q,r,req,model=setup(tmp_path,'base');r['BTCUSDT']['step']='.001'
 i=g.prepare(req,q,r,'o');assert not i['estimate']['exit_closeable']
 g.confirm(i['id'],'o',q,r,True);before=p.state()
 sell={**req,'id':str(uuid.uuid4()),'side':'SELL','quantity':before['positions']['BTCUSDT']['qty']}
 with pytest.raises(RiskError):g.prepare(sell,q,r,'o')
 assert p.state()==before
 p.write_off_dust('BTCUSDT',str(uuid.uuid4()),True);assert p.state()['cash']==before['cash'];check_identity(p,q)

def test_legacy_migration_unchanged(tmp_path):
 s,p,g,q,r,req,model=setup(tmp_path);legacy={'qty':'1','entry':'100','entry_fee':'.1','stop':'97','target':'106','opened':time.time()}
 st=p.state();st.pop('cost_model',None);st['positions']={'BTCUSDT':legacy};st['cash']='9899.9'
 with s.connect() as db:db.execute('UPDATE paper SET body=? WHERE id=1',(json.dumps(st),));db.execute('PRAGMA user_version=3')
 s=Store(s.path);assert Paper(s).state()==st and s.path.with_name(s.path.name+'.before-rc2').exists()
 assert basis(legacy)==D('100.1')

@pytest.mark.parametrize('stage',['POTENTIAL','CONFIRMED','ACTIONABLE','EXPIRED','INVALIDATED','NO_SIGNAL'])
def test_quality_independent(tmp_path,stage):
 s,p,g,q,r,req,model=setup(tmp_path);v=plan(p.state(),q,'BTCUSDT','.125','97','106',r['BTCUSDT'])
 a=assess('Bullish',{'state':stage,'first_seen':time.time()-10},v,q['BTCUSDT'])
 assert a['regime']=='Bullish' and a['signal']==stage and a['statistical_edge'] is None
 if stage in ('EXPIRED','INVALIDATED'):assert a['attention']=='No Trade'
 if stage=='POTENTIAL':assert a['attention']=='Wait'
 if stage=='CONFIRMED':assert a['attention']=='Review Setup'

def test_low_rr_stale_drift_no_data(tmp_path):
 s,p,g,q,r,req,model=setup(tmp_path);v=plan(p.state(),q,'BTCUSDT','.125','97','100.02',r['BTCUSDT']);sig={'state':'CONFIRMED'}
 a=assess('Bullish',sig,v,q['BTCUSDT']);assert a['attention']=='No Trade' and 'LOW_NET_RR' in a['codes']
 q['BTCUSDT']['bid']=0;assert 'STALE_QUOTE' in assess('Bullish',sig,v,q['BTCUSDT'])['codes']
 assert assess('Uncertain',{},None,{},'no candles')['attention']=='No Trade'
 sig['maximum_entry_price']=90;assert 'PRICE_DRIFT' in assess('Bullish',sig,v,q['BTCUSDT'])['codes']
 with pytest.raises(ValueError):QualityPolicy(min_net_rr=float('nan'))

@pytest.mark.parametrize('currency',['base','quote'])
def test_protection_net_inventory_current_costs(tmp_path,currency):
 s,p,g,q,r,req,model=setup(tmp_path,currency);g.confirm(g.prepare(req,q,r,'o')['id'],'o',q,r,True);held=p.state()['positions']['BTCUSDT']['qty']
 new=CostModel(FeeSchedule(version='exit-v2',taker='.002',buy_currency=currency),ExecutionAssumptions('12'));p.configure_costs(new)
 q['BTCUSDT'].update(price=96,bid=95.99,ask=96.01);p.protect(q,r);o=s.orders()[0]
 assert not p.state()['positions'] and o['status']=='Filled' and o['quantity']==held and o['execution']['model']==new.snapshot()
 check_identity(p,q);p.protect(q,r);assert len(s.orders())==2

def test_liquidation_equals_immediate_close(tmp_path):
 s,p,g,q,r,req,model=setup(tmp_path,'base');g.confirm(g.prepare(req,q,r,'o')['id'],'o',q,r,True)
 expected=D(metrics(p.state(),q)['liquidation_equity']);sell={**req,'id':str(uuid.uuid4()),'side':'SELL','quantity':p.state()['positions']['BTCUSDT']['qty']}
 g.confirm(g.prepare(sell,q,r,'o')['id'],'o',q,r,True);assert D(p.state()['cash'])==expected

def test_partial_basis_conservation(tmp_path):
 s,p,g,q,r,req,model=setup(tmp_path,'base');req['quantity']='.9';g.confirm(g.prepare(req,q,r,'o')['id'],'o',q,r,True)
 for _ in range(4):
  sell={**req,'id':str(uuid.uuid4()),'side':'SELL','quantity':'.111111'};g.confirm(g.prepare(sell,q,r,'o')['id'],'o',q,r,True);check_identity(p,q)
 sell.update(id=str(uuid.uuid4()),quantity=p.state()['positions']['BTCUSDT']['qty']);g.confirm(g.prepare(sell,q,r,'o')['id'],'o',q,r,True);check_identity(p,q)
