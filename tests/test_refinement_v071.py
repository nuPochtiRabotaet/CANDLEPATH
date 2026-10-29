import asyncio,copy,json,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from moex_intelligence.data import market_today
from moex_intelligence.laboratory import asset_from_quote
from moex_intelligence.lab_data import QuoteSnapshots,load_asset
from moex_intelligence.portfolio import PortfolioStore
from moex_intelligence.portfolio_service import value_portfolio
from moex_intelligence.sandbox import calculate,default_state,quote_status,validate_state
from moex_intelligence.provenance import asset_mark,describe_price
from moex_intelligence.formatting import money,price,percent,quantity
from moex_intelligence.design import TOKENS


def asset():
    return asset_from_quote({'instrument':{'symbol':'SBER','name':'Fixture','asset_type':'equity','currency':'RUB','board':'TQBR'},'security':{'LOTSIZE':10},'currency':'RUB','marketdata':{'LASTTRADEDATE':str(market_today())},'last_price':300,'source':'test fixture, not market data','retrieved_at_utc':datetime.now(timezone.utc).isoformat()})


def setup(tmp_path):
    a=asset();store=PortfolioStore(tmp_path/'portfolio.sqlite3');store.append_many([{'kind':'deposit','date':str(market_today()),'amount':10000}]);b=store.bundle();marks={'SBER':a['mark']}
    s=default_state(a);s.update(quantity=20,fee_known=True,fee_pct=.05,profile_known=True)
    return a,store,b,marks,s


def test_three_distinct_outcomes_are_scenario_only(tmp_path):
    a,store,b,m,s=setup(tmp_path)
    clear=calculate(a,b,m,s)['constraints'];assert clear['status']=='no_conflicts'
    assert clear['investment_assessment']=='not_assessed' and clear['scope']=='scenario_only'
    assert clear['coverage']['unknown']==0
    s['shock']=-20;conflict=calculate(a,b,m,s)['constraints'];assert conflict['status']=='conflict'
    s.update(shock=0,fee_known=False);unknown=calculate(a,b,m,s)['constraints'];assert unknown['status']=='insufficient_data'
    assert any(x['kind']=='fee' for x in unknown['actions'])
    assert len({x['id'] for x in unknown['checks']})==len(unknown['checks'])


def test_concentration_unknown_liquidity_and_incomplete_profile(tmp_path):
    a,store,b,m,s=setup(tmp_path);s.update(concentration_known=True,concentration_limit=40)
    result=calculate(a,b,m,s)['constraints'];assert result['status']=='conflict'
    assert any(x['kind']=='quantity' for x in result['actions'])
    s.update(concentration_known=False,early=True)
    result=calculate(a,b,m,s)['constraints'];assert result['status']=='insufficient_data'
    assert any(c['id']=='liquidity' and c['status']=='unknown' for c in result['checks'])
    for profile in [{'horizon_months':12},{'horizon_months':'oops','max_drawdown_pct':None},[],{'horizon_months':12,'max_drawdown_pct':10,'needs_money_early':None}]:
        d=default_state(a,{'profile':profile});assert not d['profile_known'];validate_state(d,a,d)


def test_snapshot_all_dates_immutable_across_reads_and_failures(tmp_path,monkeypatch):
    a=asset();a['observed_at']='2026-10-01';a['retrieved_at_utc']='2026-10-02T10:00:00+00:00';a['mark'].update(as_of='2026-10-02',valuation_as_of='2026-10-02',market_observed_at='2026-10-01',retrieved_at_utc=a['retrieved_at_utc'])
    original=copy.deepcopy(a);cache=QuoteSnapshots(tmp_path);cache.save(a);assert a==original
    first=cache.load('SBER');stamp=first['snapshot_saved_at_utc']
    import moex_intelligence.lab_data as module
    monkeypatch.setattr(module,'market_today',lambda:market_today()+timedelta(days=10))
    second=cache.load('SBER')
    assert second['mark']['as_of']==first['mark']['as_of']=='2026-10-02'
    assert second['observed_at']==first['observed_at']=='2026-10-01'
    assert second['retrieved_at_utc']==a['retrieved_at_utc']
    assert second['snapshot_saved_at_utc']==stamp
    assert quote_status(second)['state']=='saved'
    assert describe_price(asset_mark(second))['observed_at']=='2026-10-01'


def test_legacy_cache_without_save_time_remains_honest(tmp_path):
    a=asset();payload=json.dumps(a,ensure_ascii=False,allow_nan=False,sort_keys=True)
    import hashlib
    (tmp_path/'SBER.json').write_text(json.dumps({'asset':a,'sha256':hashlib.sha256(payload.encode()).hexdigest()}))
    restored=QuoteSnapshots(tmp_path).load('SBER');assert restored
    assert describe_price(restored)['saved_at'] is None
    assert restored['mark']['as_of']==a['mark']['as_of']


def test_mismatched_dates_do_not_escape_as_unhandled_error(tmp_path):
    store=PortfolioStore(tmp_path/'p.sqlite3');store.append_many([{'kind':'opening','date':'2026-10-01','amount':100,'holdings':[{'symbol':'SBER','quantity':1,'price':300},{'symbol':'SBMX','quantity':1,'price':16}]}])
    r=value_portfolio(store.load(),{'marks':{'SBER':{'price':300,'as_of':'2026-10-02','source':'fixture'},'SBMX':{'price':16,'as_of':'2026-10-03','source':'fixture'}},'errors':{}})
    assert r['snapshot'] is None and r['state']['cash']==100 and r['errors']


def test_manual_stale_and_unknown_sources_cannot_gain_positive_fit(tmp_path):
    a,store,b,m,s=setup(tmp_path)
    for patch in [{'manual':True},{'saved_snapshot':True},{'observed_at':None},{'observed_at':'2020-01-01'}]:
        candidate={**a,**patch};r=calculate(candidate,b,m,s)['constraints']
        assert r['status']=='insufficient_data' and r['investment_assessment']=='not_assessed'


@pytest.mark.parametrize('value,expected',[(551.1700000000001,'551,17 ₽'),(285,'285,00 ₽'),(16.369,'16,369 ₽'),(.00001234,'0,00001234 ₽'),(None,'—')])
def test_price_precision_is_only_added_when_needed(value,expected):assert price(value)==expected


def test_display_does_not_mutate_number_and_handles_missing():
    x=16.369;assert money(x)=='16,37 ₽' and x==16.369
    assert percent(20.1,signed=True,points=True)=='+20,1 п.п.'
    assert quantity(100)=='100' and money(None)==percent(None)=='—'


def test_semantic_contrast_meets_aa():
    def lum(hex):
        c=[int(hex[i:i+2],16)/255 for i in [1,3,5]];c=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in c]
        return sum(v*w for v,w in zip(c,[.2126,.7152,.0722]))
    def ratio(a,b):
        hi,lo=sorted([lum(a),lum(b)],reverse=True);return (hi+.05)/(lo+.05)
    for fg in ['text','muted','accent','gain','loss','warn']:
        for bg in ['bg','panel']:assert ratio(TOKENS[fg],TOKENS[bg])>=4.5,(fg,bg)
    assert ratio('#ffffff',TOKENS['accent_strong'])>=4.5
    assert ratio(TOKENS['bg'],TOKENS['accent'])>=4.5


def test_market_batch_deadline_includes_semaphore_queue(tmp_path,monkeypatch):
    import moex_intelligence.portfolio_ui as ui
    import moex_intelligence.lab_data as source
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path));monkeypatch.setattr(ui,'MARKET_TIMEOUT_SECONDS',.03)
    active=0;maximum=0
    async def slow(*args):
        nonlocal active,maximum
        active+=1;maximum=max(maximum,active)
        try:await asyncio.sleep(1)
        finally:active-=1
    monkeypatch.setattr(source,'load_asset',slow);ui.market_marks.clear()
    started=time.monotonic();r=ui.market_marks(tuple('X'+str(i) for i in range(30)))
    assert time.monotonic()-started<1 and maximum<=4 and len(r['errors'])==30 and not r['marks']


def test_model_never_uses_retrieval_time_as_trade_time():
    from moex_intelligence.interactive_lab import prepare_model
    a=asset();a['observed_at']=None
    result=prepare_model(a);assert result.get('error') and 'lo' not in result


@pytest.mark.asyncio
async def test_exchange_snapshot_time_is_labeled_separately_from_trade_date(tmp_path):
    from moex_intelligence.portfolio_service import quote_mark
    from moex_intelligence.lab_data import load_asset
    q={'instrument':{'symbol':'SBER','name':'Fixture','asset_type':'equity','currency':'RUB','board':'TQBR'},'security':{'LOTSIZE':1},'currency':'RUB','marketdata':{'SYSTIME':'2026-10-27 13:48:14','TIME':'13:33:14'},'last_price':300,'source':'fixture','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    mark=quote_mark(q);assert mark['market_trade_at'] is None and mark['observation_kind']=='snapshot'
    class Engine:
        async def research_quote(self,s):return q
    r=await load_asset('SBER',QuoteSnapshots(tmp_path),Engine());a=r['asset']
    assert a['observed_at']=='2026-10-27 13:48:14' and a['observation_kind']=='snapshot'
    p=describe_price(a);assert p['trade_at'] is None and p['trade_clock']=='13:33:14'
    restored=QuoteSnapshots(tmp_path).load('SBER');assert restored['observed_at']==a['observed_at']


def test_changed_board_is_new_context_and_mismatched_history_is_refused(monkeypatch):
    from moex_intelligence.interactive_lab import prepare_model
    from moex_intelligence.sandbox import context_id
    from moex_intelligence import lab_ui
    from time_machine_core.moex_data import demo_daily
    a=asset();b={**a,'board':'TQTF'};bundle={'revision':'fixture'}
    assert context_id(a,bundle,{})!=context_id(b,bundle,{})
    frame,meta=demo_daily(days=756,end=market_today()-timedelta(days=1));meta={**meta,'demo_data':False,'board':'TQTF'}
    monkeypatch.setattr(lab_ui,'cached_history',lambda *args:{'data':(frame,meta),'error':None})
    assert 'Режим торгов' in prepare_model(a)['error']


def test_partial_profile_is_never_preconfirmed_in_detailed_ui():
    from moex_intelligence.workbench import profile_preferences
    p,complete=profile_preferences({'amount':5000,'horizon_months':None})
    assert p=={'amount':5000} and not complete
    p,complete=profile_preferences([]);assert p=={} and not complete
    p,complete=profile_preferences({'risk_preference':[]});assert p=={} and not complete


@pytest.mark.parametrize('patch,message',[
    ({'fee_known':False},'неизвестная комиссия'),
    ({'fee_pct':5},'до 3%'),
    ({'minimum_fee':10},'минимальную комиссию'),
    ({'side':'sell'},'а не продажу'),
    ({'months':61},'до 60 месяцев')])
def test_advisor_bridge_rejects_unrepresentable_assumptions(tmp_path,patch,message):
    from moex_intelligence.interactive_lab import advisor_transfer
    a,store,b,m,s=setup(tmp_path);s.update(patch)
    with pytest.raises(ValueError,match=message):advisor_transfer(a,b,m,s)
    assert store.bundle()==b


def test_existing_position_advisor_bridge_never_adds_it_again(tmp_path):
    from moex_intelligence.interactive_lab import advisor_transfer
    a,store,b,m,s=setup(tmp_path)
    store.append_many([{'kind':'buy','date':str(market_today()),'symbol':'SBER','quantity':20,'price':300}]);b=store.bundle()
    s.update(quantity=0,funding='cash')
    request=advisor_transfer(a,b,m,s)
    assert request['fields']['adv_amount']==6000 and not request['fields']['advisor_use_saved']
    assert not request['fields']['adv_portfolio_known'] and not request['fields']['adv_filled']
    assert 'повторно' in request['notice'] and store.bundle()==b
