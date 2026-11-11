"""Sizing explanations must describe the existing Decimal gate, never authorize it."""
import copy
import time
import pytest
from moex_intelligence.crypto.paper import new_state
from moex_intelligence.crypto.risk import D, plan, RiskError
from moex_intelligence.crypto.costs import CostModel, FeeSchedule, ExecutionAssumptions


def inputs():
    state = new_state('10000')
    quotes = {'BTCUSDT': {'price':100,'bid':99.99,'ask':100.01,'ts':time.time(),'fresh':True}}
    rules = {'step':'.001','tick':'.01','minimum':'5','maximum':'100','retrieved':time.time()}
    return state, quotes, rules


def planned(state, quotes, rules, quantity='1'):
    return plan(state, quotes, 'BTCUSDT', quantity, '97', '106', rules)


def test_limits_explain_existing_recommendation_without_mutating_inputs():
    s,q,r=inputs(); before=copy.deepcopy((s,q,r)); result=planned(s,q,r)
    details=result['sizing_diagnostics']
    assert {x['code'] for x in details['limits']} == {'trade_risk','portfolio_risk','cash','symbol_notional','occupied_notional','exchange_quantity'}
    caps={x['code']:D(x['quantity_cap']) for x in details['limits']}
    assert D(result['recommended']) == min(caps.values())
    assert details['binding_limits'] == [x['code'] for x in details['limits'] if D(x['quantity_cap'])==D(result['recommended'])]
    assert all(type(x['quantity_cap']) is str for x in details['limits'])
    assert details['authorization'] == 'USE_NEW_PREVIEW'
    assert (s,q,r)==before


@pytest.mark.parametrize('kind',['cash','exchange_quantity','trade_risk','symbol_notional','portfolio_risk','occupied_notional'])
def test_each_binding_limit_and_ties(kind):
    s,q,r=inputs()
    if kind=='cash':
        s['cash']='0'
        s['positions']['ETHUSDT']={'qty':'50','entry':'100','entry_fee':'0','stop':'99.99','target':'200','opened':time.time()}
        q['ETHUSDT']={'price':100,'bid':100,'ask':100.01,'ts':time.time(),'fresh':True}
    elif kind=='exchange_quantity': r['maximum']='.1'
    elif kind=='trade_risk': stop='80'
    elif kind=='symbol_notional': stop='99.98'
    else:
        s['positions']['ETHUSDT']={'qty':'74' if kind=='occupied_notional' else '2','entry':'100','entry_fee':'0','stop':'99.99' if kind=='occupied_notional' else '1','target':'200','opened':time.time()}
        q['ETHUSDT']={'price':100,'bid':100,'ask':100.01,'ts':time.time(),'fresh':True}
        s['cash']='2600' if kind=='occupied_notional' else '9900'
        result=plan(s,q,'BTCUSDT','1','99.98','106',r,portfolio_rules={'ETHUSDT':{**r,'minimum':'0'}})
        assert kind in result['sizing_diagnostics']['binding_limits'];return
    result=plan(s,q,'BTCUSDT','.1' if kind=='exchange_quantity' else '1',locals().get('stop','97'),'106',r)
    assert kind in result['sizing_diagnostics']['binding_limits']


def test_exchange_maximum_caps_recommendation_even_when_current_request_allowed():
    s,q,r=inputs();r['maximum']='2'
    result=planned(s,q,r)
    assert result['allowed']
    assert D(result['recommended']) <= D(r['maximum'])


def test_expenses_and_rules_are_backend_snapshots():
    s,q,r=inputs()
    s['cost_model']=CostModel(FeeSchedule(buy_currency='base'),ExecutionAssumptions('20')).snapshot()
    result=planned(s,q,r);d=result['sizing_diagnostics']
    assert d['rules']=={'minimum_notional':'5','quantity_step':'.001','price_tick':'.01','maximum_quantity':'100'}
    assert d['costs']==result['costs']
    assert d['market_data_fresh'] is True


def test_stale_quote_and_off_step_still_fail_closed():
    s,q,r=inputs();q['BTCUSDT']['fresh']=False
    with pytest.raises(RiskError):planned(s,q,r)
    q['BTCUSDT']['fresh']=True
    with pytest.raises(RiskError):planned(s,q,r,quantity='.0001')
