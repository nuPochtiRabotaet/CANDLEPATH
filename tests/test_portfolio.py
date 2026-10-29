import pandas as pd
import pytest
from moex_intelligence.portfolio import analyze_portfolio, ledger_state, portfolio_curve, PortfolioStore, stress_test


def deposit(day='2026-01-01',amount=1000):return {'date':day,'kind':'deposit','amount':amount}
def buy(day='2026-01-01',quantity=5,price=100): return {'date':day,'kind':'buy','symbol':'SBER','quantity':quantity,'price':price,'fee':1}
def mark(price=120,day='2026-01-03'):return {'SBER':{'price':price,'as_of':day,'source':'test statement'}}


def test_ledger_pnl_income_and_cost_basis():
    events=[deposit(),buy(),{'date':'2026-01-02','kind':'dividend','symbol':'SBER','amount':20,'source':'issuer notice'},
            {'date':'2026-01-03','kind':'sell','symbol':'SBER','quantity':2,'price':120,'fee':1}]
    r=analyze_portfolio(events,mark())
    assert r['cash']==758 and r['equity']==1118 and r['total_pnl']==118
    assert r['income']==20 and r['positions'][0]['cost_basis']==pytest.approx(300.6)
    assert r['realized_pnl']==pytest.approx(38.6)
    stress=stress_test(r,{'SBER':-20})
    assert stress['change_rub']==-72


@pytest.mark.parametrize('events',[
 [buy()], [deposit(),{'date':'2026-01-01','kind':'sell','symbol':'SBER','quantity':1,'price':100}],
 [deposit(),{'date':'2026-01-02','kind':'coupon','symbol':'BOND','amount':10}],
 [{'date':'2026-01-01','kind':'deposit','amount':float('nan')}],
 [{'date':'2026-01-01','kind':'deposit','amount':1000,'currency':'USD'}],
])
def test_invalid_ledger(events):
    with pytest.raises(ValueError): ledger_state(events)


def test_store_rolls_back_invalid_batch(tmp_path):
    store=PortfolioStore(tmp_path/'portfolio.sqlite3')
    store.append_many([deposit()])
    with pytest.raises(ValueError): store.append_many([buy(),buy(quantity=100)])
    assert len(store.load())==1


def test_external_deposit_does_not_create_return():
    events=[deposit(),{'date':'2026-01-01','kind':'buy','symbol':'SBER','quantity':10,'price':100},deposit('2026-01-02',1000)]
    prices=pd.DataFrame({'SBER':[100.,100.,90.]},index=pd.date_range('2026-01-01',periods=3))
    curve,stats=portfolio_curve(events,prices)
    assert curve.daily_return.iloc[1]==0
    assert stats['time_weighted_return_pct']==pytest.approx(-5)
    assert stats['max_drawdown_pct']==pytest.approx(-5)


def test_marks_missing_or_older_than_ledger_rejected():
    for marks in [{},mark(day='2025-12-31')]:
        with pytest.raises(ValueError): analyze_portfolio([deposit(),buy()],marks)
