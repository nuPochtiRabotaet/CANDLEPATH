import numpy as np
import pandas as pd
import pytest
from time_machine_core.simulator import simulate, compare_scenarios
from time_machine_core.moex_data import demo_daily
from moex_intelligence.backtest import backtest, signals, rsi, compare_backtest


@pytest.mark.parametrize('kwargs',[
 {'runs':True},{'runs':100.5},{'horizon':float('nan')},{'runs':50000,'horizon':120},
 {'seed':-1},{'stop_pct':float('nan')},{'commission_pct':float('inf')},{'volatility_scale':0}
])
def test_simulation_parameter_limits(kwargs):
    with pytest.raises(ValueError): simulate(pd.Series([100.]*100),**kwargs)


@pytest.mark.parametrize('bad',[None,0,-1,float('nan'),float('inf')])
def test_no_dropping_bad_prices(bad):
    x=pd.Series([100.]*100); x.iloc[20]=bad
    with pytest.raises(ValueError): simulate(x,runs=100)


def test_flat_prices_exact_roundtrip_cost_var_es():
    r=simulate(pd.Series([100.]*100),runs=100,horizon=5,commission_pct=.5,slippage_pct=.5)
    expected=.99/1.01-1
    np.testing.assert_allclose(r.net_returns,expected)
    assert r.stats['var95_loss']==pytest.approx(-expected)
    assert r.stats['es95_loss']==pytest.approx(-expected)
    assert r.stats['median_strategy_max_drawdown']==pytest.approx(expected)
    assert r.stats['p_open']==1
    np.testing.assert_allclose(r.wealth_paths[:,-1],1+r.net_returns)


def test_daily_close_gap_exits_at_close_not_stop_level():
    prices=pd.Series(100.*.9**np.arange(100))
    r=simulate(prices,runs=100,horizon=3,stop_pct=5,commission_pct=0,slippage_pct=0)
    np.testing.assert_allclose(r.net_returns,-.1,atol=1e-12)
    assert r.hit_stop.all() and (r.exit_steps==1).all()
    np.testing.assert_allclose(r.wealth_paths[:,1:],.9)


def test_scenario_assumptions_same_seed_and_order():
    data,_=demo_daily()
    comparison=compare_scenarios(data.CLOSE,runs=100,horizon=10)
    assert len(comparison)==3 and comparison[1]['volatility_scale']==1.5
    assert comparison[2]['drift_shift_pct']==20


def bars(opens,closes):
    return pd.DataFrame({'OPEN':opens,'CLOSE':closes},index=pd.date_range('2026-01-01',periods=len(opens)))


def test_next_open_execution_and_whole_lots_hand_calculation():
    data=bars([100,120,130],[110,125,140])
    r=backtest(data,initial_cash=1000,commission_pct=0,slippage_pct=0,lot_size=2)
    # No first-day fill; 8 units bought on second OPEN=120, sold final CLOSE=140.
    assert r.trades.iloc[0]['date']=='2026-01-02'
    assert r.trades.iloc[0]['signal_date']=='2026-01-01'
    assert r.trades.iloc[0]['quantity']==8
    assert r.stats['final_equity']==pytest.approx(1160)


def test_costs_flat_price_exact():
    r=backtest(bars([100]*3,[100]*3),initial_cash=1010,commission_pct=1,slippage_pct=0)
    assert r.stats['final_equity']==990 and r.stats['fees']==20
    assert r.stats['max_drawdown_pct']==pytest.approx((990/1010-1)*100)


@pytest.mark.parametrize('strategy',['buy_hold','ma_cross','ema_cross','rsi'])
def test_future_changes_cannot_change_past_signals(strategy):
    data,_=demo_daily()
    changed=data.copy(); changed.iloc[200:,changed.columns.get_loc('CLOSE')]*=5
    a=signals(data,strategy); b=signals(changed,strategy)
    pd.testing.assert_series_equal(a.iloc[:200],b.iloc[:200])


def test_custom_receives_only_prefixes():
    data,_=demo_daily(days=65)
    lengths=[]
    def custom(history): lengths.append(len(history)); return int(len(history)>10)
    r=backtest(data,custom=custom)
    assert lengths==list(range(1,66)) and r.trades.iloc[0]['date']==str(data.index[11].date())


def test_rsi_monotonic_and_flat():
    assert rsi(pd.Series(range(1,51))).iloc[-1]==100
    assert rsi(pd.Series([100]*50)).iloc[-1]==50
    assert rsi(pd.Series(range(50,0,-1))).iloc[-1]==0


def test_holdout_dates_cash_and_benchmark():
    data,_=demo_daily()
    r=compare_backtest(data,'ma_cross',.7)
    assert r['train'].curve.index[-1]<r['test'].curve.index[0]
    assert r['test'].curve.index.equals(r['benchmark'].curve.index)
    assert r['test'].stats['initial_cash']==r['benchmark'].stats['initial_cash']==100000


def test_missing_open_is_rejected():
    with pytest.raises(ValueError): backtest(bars([100,None,100],[100]*3))
