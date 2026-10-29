import asyncio
import copy
from datetime import datetime,timezone
import json
import numpy as np
import pytest
from moex_intelligence.data import market_today
from moex_intelligence.portfolio import analyze_portfolio
from moex_intelligence.portfolio_service import opening_event
from moex_intelligence.laboratory import (asset_from_quote,manual_asset,order_cost,preview_trade,
 stress_selected,scenario_envelope,model_position,capital_goal,liquidity_check)
from moex_intelligence.lab_data import QuoteSnapshots,load_asset
from time_machine_core.moex_data import demo_daily


def quote(bond=False):
 return {'instrument':{'symbol':'BOND' if bond else 'SBER','name':'Test','asset_type':'bond' if bond else 'equity','currency':'SUR','board':'TQOB' if bond else 'TQBR'},
 'security':{'LOTSIZE':1 if bond else 10,'FACEUNIT':'SUR','FACEVALUE':1000,'ACCRUEDINT':12},'currency':'SUR',
 'marketdata':{'BID':284.9,'OFFER':285.1,'VOLTODAY':100000,'LASTTRADEDATE':str(market_today())},
 'last_price':95 if bond else 285,'source':'MOEX fixture','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}


def portfolio():
 day=str(market_today());events=[opening_event(day,[{'symbol':'SBER','quantity':20,'price':285},{'symbol':'FUND','quantity':100,'price':16},{'symbol':'BOND','quantity':3,'price':962}],4000)]
 marks={s:{'price':p,'as_of':day,'source':'test'} for s,p in [('SBER',285),('FUND',16),('BOND',962)]}
 return events,marks


def test_cash_buy_sale_rounding_and_read_only_replay():
 events,marks=portfolio();original=copy.deepcopy((events,marks));a=asset_from_quote(quote())
 r=preview_trade(events,marks,a,10,fee_pct=.05)
 assert r['order']['fee']==1.43 and r['after']['cash']==pytest.approx(1148.57)
 assert r['after']['equity']==pytest.approx(14184.57) and not r['events_changed']
 sale=preview_trade(events,marks,a,10,side='sell',fee_pct=.05)
 assert sale['after']['cash']==pytest.approx(6848.57)
 assert sale['after']['equity']==pytest.approx(r['after']['equity'])
 assert (events,marks)==original


def test_insufficient_cash_topup_is_capital_not_profit_and_oversell():
 e,m=portfolio();a=asset_from_quote(quote())
 bad=preview_trade(e,m,a,20,fee_pct=.05)
 assert bad['after'] is None and any('Недостаточно' in x for x in bad['errors'])
 good=preview_trade(e,m,a,20,fee_pct=.05,funding='topup')
 assert good['topup']==pytest.approx(1702.85) and good['after']['cash']==0
 assert good['after']['equity']==pytest.approx(good['before']['equity']+good['topup']-good['order']['fee'])
 assert preview_trade(e,m,a,30,side='sell',fee_pct=.05)['after'] is None


def test_unknown_fee_does_not_become_zero_and_noop_costs_nothing():
 e,m=portfolio();a=asset_from_quote(quote())
 r=preview_trade(e,m,a,10)
 assert r['order']['fee'] is None and r['order']['buy_total'] is None and r['after'] is None
 assert order_cost(a,0,.3,minimum_fee=50)['fee']==0
 assert order_cost(a,0)['buy_total']==0
 assert order_cost(a,10,0)['buy_total']==2850
 assert order_cost(a,10,.01,minimum_fee=3)['fee']==3


@pytest.mark.parametrize('qty',[1,7,11,-1,1.5,True])
def test_invalid_quantity_never_rounded(qty):
 with pytest.raises(ValueError):order_cost(asset_from_quote(quote()),qty,.05)


def test_bond_dirty_cost_and_clean_price_stress():
 e,m=portfolio();a=asset_from_quote(quote(True));assert a['unit_price']==962 and a['clean_price']==950
 r=preview_trade(e,m,a,1,fee_pct=.05)
 assert r['order']['gross']==962 and r['order']['fee']==.48
 stress=stress_selected(r['after'],a,50)
 assert stress['unit_price']==1437 and stress['position_value']==5748
 assert stress['change_rub']==1900
 assert stress['equity_after']==pytest.approx(16085.52)


@pytest.mark.parametrize('field,value',[('LOTSIZE',None),('LOTSIZE',0),('LOTSIZE',True),('ACCRUEDINT',None),('FACEVALUE',None),('FACEUNIT','USD')])
def test_unknown_bond_metadata_cannot_generate_cost(field,value):
 q=quote(True);q['security'][field]=value
 with pytest.raises(ValueError):asset_from_quote(q)


def test_currency_also_validated_when_a_mark_is_supplied():
 q=quote();mark={'price':285,'source':'test','retrieved_at_utc':'x'};q['currency']='USD'
 with pytest.raises(ValueError):asset_from_quote(q,mark)


def test_incomplete_marks_cannot_fabricate_total():
 e,m=portfolio();del m['FUND']
 r=preview_trade(e,m,asset_from_quote(quote()),10,fee_pct=.05)
 assert r['before'] is None and r['after'] is None
 assert r['order']['buy_total']==2851.43
 assert r['cash_after']==pytest.approx(1148.57)


def test_empty_portfolio_can_experiment_only_with_explicit_funding():
 a=asset_from_quote(quote())
 assert preview_trade([],{},a,10,fee_pct=0)['after'] is None
 r=preview_trade([],{},a,10,fee_pct=0,funding='topup')
 assert r['topup']==2850 and r['after']['equity']==2850


def test_manual_price_requires_source_lot_and_units():
 a=manual_asset('BOND','bond',95,1,'Statement 25 Oct',face=1000,accrued=12)
 assert a['manual'] and a['unit_price']==962 and a['quoted_pct']==95
 for lot,source in [(0,'statement'),(1,'')]:
  with pytest.raises(ValueError):manual_asset('SBER','equity',285,lot,source)


def test_liquidity_never_claims_executability():
 a=asset_from_quote(quote());r=liquidity_check(a,10000)
 assert not r['execution_confirmed'] and r['spread_pct']>0
 assert r['order_share_of_reported_volume_pct']==10
 a['liquidity']={};assert liquidity_check(a,10)['spread_pct'] is None


def test_existing_model_is_reproducible_and_separate_from_hypothetical_stress():
 frame,meta=demo_daily(days=756)
 envelope=scenario_envelope(frame,meta,horizon=63,runs=100)
 assert envelope==scenario_envelope(frame,meta,horizon=63,runs=100)
 assert len(envelope['mid'])==64 and envelope['mid'][0]==1
 a=asset_from_quote(quote());e,m=portfolio();s=analyze_portfolio(e,m)
 model=model_position(envelope,a,20,21,s)
 assert model['position']['mid'][0]==5700
 assert model['conditional_portfolio']['mid'][0]==14186
 assert all(x<=y<=z for x,y,z in zip(envelope['lo'],envelope['mid'],envelope['hi']))
 before=copy.deepcopy(envelope);stress_selected(s,a,-50)
 assert envelope==before
 with pytest.raises(ValueError):scenario_envelope(frame,{**meta,'asset_type':'bond'},horizon=21,runs=100)


def test_goal_contributions_timing_inflation_and_sensitivity():
 r=capital_goal(5000,1000,12,0,0)
 assert r.nominal.iloc[-1]==17000 and r.real.iloc[-1]==17000
 r=capital_goal(10000,0,12,10,5)
 assert r.nominal.iloc[-1]==pytest.approx(11000)
 assert r.real.iloc[-1]==pytest.approx(11000/1.05)
 up=capital_goal(10000,1000,12,12,0)
 monthly=1.12**(1/12)
 assert up.nominal.iloc[-1]==pytest.approx(10000*1.12+1000*(1.12-1)/(monthly-1))


async def test_market_snapshot_fallback_preserves_timestamp_and_does_not_invent_prices(tmp_path):
 class Live:
  async def research_quote(self,s):return quote()
 class Offline:
  async def research_quote(self,s):raise ValueError('offline')
 store=QuoteSnapshots(tmp_path)
 live=await load_asset('SBER',store,Live())
 cached=await load_asset('SBER',store,Offline())
 assert cached['asset']['saved_snapshot'] and cached['error']=='offline'
 assert cached['asset']['retrieved_at_utc']==live['asset']['retrieved_at_utc']
 assert cached['asset']['unit_price']==285
 missing=await load_asset('UNKNOWN',store,Offline())
 assert missing['asset'] is None
 (tmp_path/'SBER.json').write_text('{}')
 assert store.load('SBER') is None


def test_upgrade_backup_preserves_both_databases_and_never_overwrites(tmp_path):
 import sqlite3
 from moex_intelligence.upgrades import ensure_v06_backup
 for name in ['portfolio.sqlite3','research.sqlite3']:
  with sqlite3.connect(tmp_path/name) as db:
   db.execute('CREATE TABLE original (id TEXT)');db.execute('INSERT INTO original VALUES (?)',('original-record',))
 dest=ensure_v06_backup(tmp_path)
 with sqlite3.connect(tmp_path/'research.sqlite3') as db:db.execute('INSERT INTO original VALUES (?)',('new-study',))
 assert ensure_v06_backup(tmp_path)==dest
 for name in ['portfolio.sqlite3','research.sqlite3']:
  with sqlite3.connect(dest/name) as db:assert db.execute('SELECT id FROM original').fetchall()==[('original-record',)]


def test_snapshot_tampering_is_not_used_as_real_quote(tmp_path):
 store=QuoteSnapshots(tmp_path);store.save(asset_from_quote(quote()))
 p=tmp_path/'SBER.json';body=json.loads(p.read_text());body['asset']['unit_price']=1;p.write_text(json.dumps(body))
 assert store.load('SBER') is None


def test_tariff_preferences_keep_only_numeric_settings(tmp_path):
 from moex_intelligence.persistence import ResearchStore
 db=ResearchStore(tmp_path/'r.sqlite3')
 db.save_preferences({'commission':{'pct':.05,'minimum':0,'api_key':'must-not-be-saved'}})
 assert db.preferences()['commission']=={'pct':.05,'minimum':0}
