"""Test-only controlled market adapter. Never imported by the production app."""
import os,sys,copy
from pathlib import Path
ROOT=Path(os.environ.get('MOEX_QA_ROOT',Path(__file__).resolve().parents[1]));sys.path.insert(0,str(ROOT))
assert os.environ.get('MOEX_DATA_DIR'), 'QA requires an isolated MOEX_DATA_DIR'
from moex_intelligence import lab_ui,portfolio_ui
from moex_intelligence.data import market_today
from moex_intelligence.laboratory import asset_from_quote
from moex_intelligence.portfolio_service import opening_event
from time_machine_core.moex_data import demo_daily
from datetime import datetime,timezone,timedelta
import streamlit as st

def fixture_asset(symbol,*args):
    bond=symbol=='OFZTEST';fund=symbol=='SBMX';penny=symbol=='PENNY'
    q={'instrument':{'symbol':symbol,'name':'ТЕСТОВАЯ ОБЛИГАЦИЯ' if bond else 'Тестовый фонд' if fund else 'Тестовый Сбербанк','asset_type':'bond' if bond else 'fund' if fund else 'equity','currency':'SUR','board':'TQOB' if bond else 'TQTF' if fund else 'TQBR'},'security':{'LOTSIZE':1 if bond or penny else 100 if fund else 10},'currency':'SUR','marketdata':{'LASTTRADEDATE':str(market_today()),'BID':284.9,'OFFER':285.1,'VOLTODAY':1000000},'last_price':95 if bond else 16 if fund else .29 if penny else 285.,'source':'MOEX TEST FIXTURE · НЕ РЫНОЧНЫЕ ДАННЫЕ','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    if bond:q['security'].update(FACEUNIT='SUR',FACEVALUE=1000,ACCRUEDINT=20)
    asset=asset_from_quote(q);asset['demo_data']=True
    return {'asset':asset,'error':None}
def fake_asset(symbol,*args):
    if symbol=='NOQUOTE':return {'asset':None,'error':'QA: подходящая котировка отсутствует'}
    if symbol=='OLDTEST':
        import asyncio
        from moex_intelligence.lab_data import QuoteSnapshots,load_asset
        a=fixture_asset(symbol)['asset'];a['demo_data']=False;a['observed_at']='2026-10-01';a['retrieved_at_utc']='2026-10-01T10:00:00+00:00'
        a['mark'].update(as_of='2026-10-01',valuation_as_of='2026-10-01',market_observed_at='2026-10-01',retrieved_at_utc=a['retrieved_at_utc'],demo_data=False)
        cache=QuoteSnapshots(Path(os.environ['MOEX_DATA_DIR'])/'market_snapshots')
        if not (cache.directory/'OLDTEST.json').exists():cache.save(a)
        class Offline:
            async def research_quote(self,*args):raise ValueError('QA: сеть недоступна')
        return asyncio.run(load_asset(symbol,cache,Offline()))
    return fixture_asset(symbol)
fake_asset.clear=lambda:None
lab_ui.cached_asset=fake_asset

def marks(symbols):
    try:from moex_intelligence.provenance import asset_mark
    except ImportError:asset_mark=lambda a:{**a['mark'],'demo_data':True}
    return {'marks':{s:asset_mark(fake_asset(s)['asset']) for s in symbols},'errors':{}}
marks.clear=lambda:None
portfolio_ui.market_marks=marks
@st.cache_data(show_spinner=False)
def hist(symbol,end):
    if symbol=='NOHISTORY':return {'data':None,'error':'QA: недостаточно истории'}
    counter=Path(os.environ['MOEX_DATA_DIR'])/'history-calls.txt'
    if not counter.exists():
        import time
        time.sleep(.5)  # QA-only: provoke a late model response during rapid input.
    counter.write_text(str(int(counter.read_text())+1 if counter.exists() else 1))
    frame,meta=demo_daily(days=756,end=market_today()-timedelta(days=1));return {'data':(frame,meta),'error':None}
lab_ui.cached_history=hist
store=portfolio_ui.portfolio_store()
if not store.load():store.append_many([opening_event(str(market_today()),[{'symbol':'SBER','quantity':20,'price':285},{'symbol':'SBMX','quantity':100,'price':16},{'symbol':'OFZTEST','quantity':3,'price':970}],4000)])
from moex_intelligence.workbench import main
main()
