from dataclasses import asdict
from decimal import Decimal as D
import pytest
from .test_paper_path_research_v09 import history,plug
from moex_intelligence.crypto.paper_path_research import simulate_paper_paths
from moex_intelligence.crypto.coliseum_diagnostics import trade_diagnostics
from moex_intelligence.crypto.costs import CostModel

def test_trace_preserves_fills_and_reconciles(monkeypatch):
    plug(monkeypatch,[(140,{}),(145,{'side':'EXIT'})]);bars=history()
    old=simulate_paper_paths(bars,'BTCUSDT','1');new=simulate_paper_paths(bars,'BTCUSDT','1',record_equity=True)
    for a,b in zip(old['folds'],new['folds']):assert a['trades']==b['trades'] and a['ending_cash']==b['ending_cash']
    d=trade_diagnostics(new,[asdict(x) for x in bars[:1280]],CostModel(),4)
    assert d['trades']
    for t in d['trades']:
        assert abs(D(t['gross_pnl'])-D(t['fee_cost'])-D(t['spread_cost'])-D(t['slippage_cost'])-D(t['net_pnl']))<D('1e-8')
    new['folds'][0]['trades'][0]['entry_total_debit']='1'
    with pytest.raises(ValueError,match='mismatch'):trade_diagnostics(new,[asdict(x) for x in bars[:1280]],CostModel(),4)
