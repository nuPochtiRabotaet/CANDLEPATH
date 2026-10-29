"""Financial/UI-contract regression; browser behavior is exercised separately."""
import copy
import pytest
from moex_intelligence.sandbox import presentation_data,default_state,validate_state,calculate,required_return,context_id
from moex_intelligence.laboratory import manual_asset,capital_goal
from moex_intelligence.portfolio import PortfolioStore
from moex_intelligence.data import market_today


def inputs(tmp_path,kind='equity'):
    a=manual_asset('BONDTEST' if kind=='bond' else 'SBER',kind,95 if kind=='bond' else 300,1 if kind=='bond' else 10,'test only',face=1000,accrued=20)
    store=PortfolioStore(tmp_path/'portfolio.sqlite3');store.append_many([{'kind':'deposit','date':str(market_today()),'amount':10000}])
    return a,store,store.bundle(),{a['symbol']:a['mark']}


def test_spec_stock_2_then_3_lots(tmp_path):
    a,store,b,m=inputs(tmp_path);original=store.bundle();s=default_state(a);s.update(quantity=20,fee_known=True,fee_pct=.05)
    r=calculate(a,b,m,s);assert r['order']['gross']==6000 and r['order']['buy_total']==6003
    assert r['after']['cash']==3997 and r['after']['equity']==9997
    s['quantity']=30;r=calculate(a,b,m,s);assert r['order']['buy_total']==9004.5
    assert store.bundle()==original


def test_spec_dirty_bond_minimum10(tmp_path):
    a,store,b,m=inputs(tmp_path,'bond');s=default_state(a);s.update(quantity=1,fee_known=True,minimum_fee=10)
    r=calculate(a,b,m,s);assert r['order']['gross']==970 and r['order']['buy_total']==980
    assert r['after']['cash']==9020
    assert r['asset']['clean_price']==950 and r['asset']['accrued_interest']==20


def test_invalid_lot_unknown_fee_and_topup(tmp_path):
    a,store,b,m=inputs(tmp_path);s=default_state(a)
    r=calculate(a,b,m,s);assert r['after'] is None and r['order']['fee'] is None
    s.update(fee_known=True,quantity=7);r=calculate(a,b,m,s);assert r['after'] is None and 'не кратны' in r['errors'][0]
    s.update(quantity=100,fee_pct=.05);assert calculate(a,b,m,s)['after'] is None
    s['funding']='topup';r=calculate(a,b,m,s);assert r['topup']==20015 and r['after']['cash']==0
    assert r['after']['equity']==30000
    s['side']='sell';assert calculate(a,b,m,s)['after'] is None


def test_context_tracks_revision_asset_and_marks(tmp_path):
    a,store,b,m=inputs(tmp_path);base=context_id(a,b,m)
    c=copy.deepcopy(a);c['unit_price']=301;assert base!=context_id(c,b,m)
    assert base!=context_id(a,{**b,'revision':'different'},m)
    d=presentation_data(a,b,m,existing=True);assert d['initial']['quantity']==0 and d['held']==0


def test_conflicts_cannot_be_overridden_by_modeled_return(tmp_path):
    a,store,b,m=inputs(tmp_path);s=default_state(a);s.update(quantity=20,fee_known=True,profile_known=True,max_loss=10,shock=-20)
    r=calculate(a,b,m,s);assert r['constraints']['status']=='conflict'
    assert '20,0%' in r['constraints']['why'][0]
    s['shock']=50;assert calculate(a,b,m,s)['constraints']['status']=='insufficient_data'
    s['early']=True;assert calculate(a,b,m,s)['constraints']['status']=='insufficient_data'
    assert any(c['id']=='liquidity' and c['status']=='unknown' for c in calculate(a,b,m,s)['constraints']['checks'])
    s.update(early=False,concentration_known=True,concentration_limit=50)
    assert calculate(a,b,m,s)['constraints']['status']=='conflict'


def test_validation_and_goal_inverse(tmp_path):
    a,store,b,m=inputs(tmp_path);d=default_state(a)
    for patch in [{'quantity':True},{'quantity':1.5},{'side':'execute'},{'shock':51},{'fee_pct':float('nan')},{'show_model':'yes'},{'horizon':60}]:
        with pytest.raises(ValueError):validate_state({**d,**patch},a,d)
    target=capital_goal(5000,1000,60,10,5).nominal.iloc[-1]
    assert required_return(5000,1000,60,target)==pytest.approx(10,abs=1e-7)
    assert required_return(0,0,12,1e6) is None


def test_model_loss_conflict_is_distinct_from_price_stress(tmp_path):
    from moex_intelligence.sandbox import evaluate_constraints
    a,store,b,m=inputs(tmp_path);s=default_state(a);s.update(quantity=10,fee_known=True,profile_known=True,max_loss=10,shock=0)
    r=calculate(a,b,m,s);env={'horizon':21,'lo':[1]+[.8]*21}
    v=evaluate_constraints(r,a,s,env)
    assert v['status']=='conflict' and '5-м процентиле' in v['why'][0]
    assert r['constraints']['status']=='insufficient_data'


def test_stale_and_unknown_quote_status_are_not_live(tmp_path):
    from moex_intelligence.sandbox import quote_status
    a,store,b,m=inputs(tmp_path);a['manual']=False
    a['observed_at']='2020-01-01';assert quote_status(a)['state']=='stale'
    a['observed_at']=None;assert quote_status(a)['state']=='unknown_age'
    a['observed_at']=str(market_today());a['price_type']='daily_close'
    assert quote_status(a)['state']=='historical'


def test_v07_backup_does_not_overwrite_original_data(tmp_path):
    from moex_intelligence.upgrades import ensure_v07_backup
    import sqlite3
    a,store,b,m=inputs(tmp_path);dest=ensure_v07_backup(tmp_path)
    first=(dest/'portfolio.sqlite3').read_bytes()
    store.append_many([{'kind':'deposit','date':str(market_today()),'amount':100}])
    assert ensure_v07_backup(tmp_path)==dest and (dest/'portfolio.sqlite3').read_bytes()==first
    assert len(PortfolioStore(dest/'portfolio.sqlite3').load())==1
    assert len(store.load())==2
