from copy import deepcopy
from datetime import date
import numpy as np
import pandas as pd
import pytest
from moex_intelligence.advisor import evaluate, validate_profile, render_investment_report
from moex_intelligence.risk import assess, portfolio_impact
from moex_intelligence.decision import decide
from moex_intelligence.persistence import ResearchStore
from time_machine_core.moex_data import demo_daily
from time_machine_core.simulator import simulate


def profile(**changes):return {'amount':5000.,'horizon_months':12,'max_drawdown_pct':50.,'risk_preference':'high','needs_money_early':False,**changes}
def dataset():return demo_daily(days=756)


def test_scenario_1_risk_limit_overrides_positive_returns():
    frame,meta=dataset()
    result=evaluate(frame,meta,profile=profile(max_drawdown_pct=5),runs=100)
    assert result['verdict']['category']=='unsuitable'
    assert any(x['id']=='drawdown' for x in result['risk']['hard_conflicts'])
    assert result['verdict']['score']<=40


def test_scenario_2_insufficient_history_no_score():
    frame,meta=demo_daily(days=65)
    r=evaluate(frame,meta,profile=profile(max_drawdown_pct=100),runs=100)
    assert r['verdict']['category']=='insufficient' and r['verdict']['score'] is None


def test_scenario_3_concentration_blocks_favorable_verdict():
    frame,meta=dataset()
    r=evaluate(frame,meta,profile=profile(max_drawdown_pct=100),portfolio={'equity':10000,'asset_value':7000,'cash':0,'funding':'new_money'},runs=100)
    assert r['portfolio_impact']['after_weight_pct']>70
    assert r['verdict']['category']=='unsuitable'
    assert any(x['id']=='concentration' for x in r['risk']['hard_conflicts'])


def test_scenario_4_model_disagreement_is_explicit():
    frame,meta=dataset()
    quality={'critical_gaps':[],'warnings':[],'historical_drawdown_pct':5.,'volatility_pct':10.}
    stats=[{'p05_strategy_max_drawdown':-.05,'es95_loss':.05,'p05_return':-.04},
           {'p05_strategy_max_drawdown':-.15,'es95_loss':.15,'p05_return':-.15}]
    risk=assess(frame,meta,None,profile(max_drawdown_pct=90),quality,stats,{},None)
    assert any(x['id']=='model_disagreement' for x in risk['uncertainties'])
    assert decide(risk,True)['category']=='study'


async def test_scenario_5_network_error_no_demo_fallback(monkeypatch):
    from moex_intelligence.advisor import investigate
    from moex_intelligence.data import get_engine
    async def fail(*args):raise ValueError('MOEX unavailable')
    monkeypatch.setattr(get_engine(),'frame',fail)
    with pytest.raises(ValueError,match='unavailable'):await investigate('SBER',profile(),runs=100)


def test_scenario_6_profile_missing_no_personal_fit():
    frame,meta=dataset()
    r=evaluate(frame,meta,profile=None,runs=100)
    assert r['verdict']['category']=='insufficient' and r['verdict']['fit']=='Невозможно оценить'
    assert r['verdict']['score'] is None and r['historical']


def test_scenario_7_historical_growth_not_fundamental_value():
    frame,meta=dataset();frame['CLOSE']=np.linspace(100,300,len(frame))
    r=evaluate(frame,meta,profile=profile(max_drawdown_pct=100),runs=100)
    assert r['historical']['252']['return_pct']>0
    assert r['verdict']['category']=='study'
    assert any(x['id']=='fundamentals' for x in r['risk']['uncertainties'])


def test_no_shortening_long_horizon():
    frame,meta=dataset();r=evaluate(frame,meta,profile=profile(horizon_months=24,max_drawdown_pct=100),runs=100)
    assert r['parameters']['horizon_trading_days']==504 and not r['models']
    assert r['verdict']['category']=='insufficient'


def test_short_horizon_and_cash_need_override_model():
    frame,meta=dataset();r=evaluate(frame,meta,profile=profile(horizon_months=2,needs_money_early=True),runs=100)
    assert r['verdict']['category']=='unsuitable'
    assert any(x['id']=='horizon' for x in r['risk']['hard_conflicts'])


def test_stale_real_data_and_unsupported_bonds():
    frame,meta=dataset()
    for changes in [{'demo_data':False},{'asset_type':'bond'}]:
        r=evaluate(frame,{**meta,**changes},quote={'security':{'LOTSIZE':1}},profile=profile(max_drawdown_pct=100),runs=100,as_of='2026-10-25')
        assert r['verdict']['category']=='insufficient' and r['verdict']['score'] is None


def test_invalid_history_not_simulated():
    frame,meta=dataset();frame.iloc[0,frame.columns.get_loc('CLOSE')]=float('nan')
    r=evaluate(frame,meta,profile=profile(max_drawdown_pct=100),runs=100)
    assert not r['models'] and r['verdict']['category']=='insufficient'


def test_numeric_results_and_verdict_reproducible():
    frame,meta=dataset();a=evaluate(frame,meta,profile=profile(),runs=100);b=evaluate(frame,meta,profile=profile(),runs=100)
    assert a['models']==b['models'] and a['verdict']==b['verdict'] and a['scenarios']==b['scenarios']


def test_lots_and_cash_residual():
    frame,meta=dataset()
    r=evaluate(frame,meta,{'security':{'LOTSIZE':10}},profile=profile(),runs=100)
    s=r['sizing'];assert s['quantity']%10==0 and 0<=s['cash_remaining']<s['indicative_price']*10*1.001
    assert s['allocated_cash']+s['cash_remaining']==pytest.approx(5000)
    for scenario,stat in zip(r['scenarios'],['p05_return','median_return','p95_return']):
        assert scenario['final_capital_rub']==pytest.approx(5000+s['allocated_cash']*r['models'][0][stat])


def test_portfolio_existing_cash_not_new_capital():
    r=portfolio_impact({'equity':10000,'asset_value':1000,'cash':5000,'funding':'existing_cash'},3000,2990,3)
    assert r['equity_after_costs']==9997 and r['after_weight_pct']==pytest.approx(3990/9997*100)
    with pytest.raises(ValueError):portfolio_impact({'equity':10000,'asset_value':1000,'cash':100,'funding':'existing_cash'},3000,2990,3)


def test_immutable_research_and_profile_storage(tmp_path):
    frame,meta=dataset();r=evaluate(frame,meta,profile=profile(),runs=100)
    db=ResearchStore(tmp_path/'research.sqlite3');key=db.save(r,frame)
    saved=db.load(key);r['verdict']['label']='tampered';frame.iloc[0,0]=0
    assert db.load(key)==saved
    db.save_preferences({'profile':profile(),'api_key':'must_not_save','onboarding_done':True})
    assert 'api_key' not in db.preferences()
    assert '## Вердикт:' in render_investment_report(saved['result'])
    with db.connect() as connection:connection.execute('UPDATE studies SET body=? WHERE id=?',('{}',key))
    with pytest.raises(ValueError,match='integrity'):db.load(key)


@pytest.mark.parametrize('model',['block_bootstrap','historical_bootstrap','gbm'])
def test_models_deterministic_and_flat_cost(model):
    x=pd.Series([100.]*100)
    a=simulate(x,runs=100,model=model,exit_policy='horizon')
    b=simulate(x,runs=100,model=model,exit_policy='horizon')
    np.testing.assert_array_equal(a.paths,b.paths)
    np.testing.assert_allclose(a.net_returns,.999/1.001-1)
    assert a.stats['p_open']==1


def test_gbm_log_calibration_without_double_drift_correction():
    x=pd.Series(np.exp(np.arange(100)*.01))
    a=simulate(x,runs=100,horizon=10,model='gbm',exit_policy='horizon',commission_pct=0,slippage_pct=0)
    np.testing.assert_allclose(a.net_returns,np.exp(.1)-1,atol=1e-12)


def test_missing_profile_dominates_detected_conflict():
    risk={'hard_conflicts':[{'id':'drawdown','reason':'risk'}],'critical_gaps':[], 'uncertainties':[]}
    r=decide(risk,False)
    assert r['category']=='insufficient' and r['score'] is None and r['fit']=='Невозможно оценить'


def test_observed_conflict_not_hidden_by_missing_data():
    risk={'hard_conflicts':[{'id':'drawdown','reason':'risk'}],'critical_gaps':['missing data'], 'uncertainties':[]}
    r=decide(risk,True)
    assert r['category']=='unsuitable' and r['score'] is None


def test_score_never_overrides_hard_lot_constraint():
    risk={'hard_conflicts':[{'id':'lot','reason':'budget below one lot'}],'critical_gaps':[], 'uncertainties':[]}
    r=decide(risk,True)
    assert r['category']=='unsuitable' and r['score']==40
