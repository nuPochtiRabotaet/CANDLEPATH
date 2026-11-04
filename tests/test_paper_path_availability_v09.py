from .test_paper_path_research_v09 import history, plug, trades_of, STEP
from moex_intelligence.crypto.paper_path_research import simulate_paper_paths
import pytest

@pytest.mark.parametrize('high,low,reason', [(102.,98.,'STOP_FIRST_AMBIGUOUS'),(100.2,98.,'STOP'),(102.,99.8,'TARGET')])
def test_intrabar_exit_not_known_at_open(monkeypatch, high, low, reason):
    plug(monkeypatch,[(140,{})])
    bars=history(patches={141:(100.,high,low,100.)})
    trade=trades_of(simulate_paper_paths(bars,'BTCUSDT','1'))[0]
    assert trade['reason']==reason
    assert trade['exit_event_time']==bars[141].time+STEP
    assert trade['exit_time_precision']=='BAR_CLOSE_AVAILABILITY'

def test_strategy_filter_preserves_matching_exit(monkeypatch):
    plug(monkeypatch,[(140,{}),(141,{'side':'EXIT'}),(145,{'strategy':'Mean Reversion'}),(146,{'side':'EXIT','strategy':'Mean Reversion'})])
    r=simulate_paper_paths(history(),'BTCUSDT','1',strategy='Mean Reversion')
    trades=trades_of(r)
    assert len(trades)==1 and trades[0]['strategy']=='Mean Reversion'
    assert trades[0]['reason']=='RULE_EXIT'
    assert trades[0]['exit_time_precision']=='NEXT_OPEN'
    with pytest.raises(ValueError):simulate_paper_paths(history(),'BTCUSDT','1',strategy='typo')

def test_sqlite_failure_rolls_back_confirm_and_fill(tmp_path):
    import sqlite3
    from .test_order_preview_v082 import fixture
    s,p,g,q,r,req=fixture(tmp_path)
    intent=g.prepare(req,q,r,'owner');before=p.state()
    with s.connect() as db:
        db.execute("CREATE TRIGGER reject_fill BEFORE INSERT ON orders BEGIN SELECT RAISE(ABORT,'injected disk failure'); END")
    with pytest.raises(sqlite3.IntegrityError):g.confirm(intent['id'],'owner',q,r,True)
    assert p.state()==before and not s.orders()
    assert g.get(intent['id'])['status']=='Prepared'
    with s.connect() as db:db.execute('DROP TRIGGER reject_fill')
    assert g.confirm(intent['id'],'owner',q,r,True)['status']=='Filled'
    assert len(s.orders())==1

def test_concurrent_exits_cannot_oversell_and_basis_reconciles(tmp_path):
    import uuid
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal as D
    from .test_order_preview_v082 import fixture
    s,p,g,q,r,req=fixture(tmp_path)
    g.confirm(g.prepare(req,q,r,'owner')['id'],'owner',q,r,True)
    requests=[dict(req,id=str(uuid.uuid4()),side='SELL',quantity='.75') for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:out=list(pool.map(lambda req:p.execute(req,q,r),requests))
    assert sorted(o['status'] for o in out)==['Filled','Rejected']
    assert D(p.state()['positions']['BTCUSDT']['qty'])==D('.25')
    final=p.execute(dict(req,id=str(uuid.uuid4()),side='SELL',quantity='.25'),q,r)
    assert final['status']=='Filled'
    state=p.state()
    assert not state['positions']
    assert D(state['cash'])==D(state['initial'])+D(state['realized'])
