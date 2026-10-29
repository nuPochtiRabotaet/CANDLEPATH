import copy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from moex_intelligence import lab_ui,portfolio_ui
from moex_intelligence.data import market_today,get_engine
from moex_intelligence.portfolio_service import opening_event
from moex_intelligence.laboratory import asset_from_quote
from time_machine_core.moex_data import demo_daily

ROOT=Path(__file__).resolve().parents[1]


def quote():
 return {'instrument':{'symbol':'SBER','name':'Test Sber','asset_type':'equity','currency':'SUR','board':'TQBR'},
 'security':{'LOTSIZE':10},'currency':'SUR','marketdata':{'LASTTRADEDATE':str(market_today())},
 'last_price':285.,'source':'MOEX test fixture','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}


def fixture_market(monkeypatch,tmp_path):
 monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
 asset=asset_from_quote(quote())
 def fetch(*args):return {'asset':copy.deepcopy(asset),'error':None}
 fetch.clear=lambda:None
 monkeypatch.setattr(lab_ui,'cached_asset',fetch)
 def marks(symbols):return {'marks':{s:copy.deepcopy(asset['mark']) for s in symbols},'errors':{}}
 marks.clear=lambda:None
 monkeypatch.setattr(portfolio_ui,'market_marks',marks)
 store=portfolio_ui.portfolio_store()
 store.append_many([opening_event(str(market_today()),[{'symbol':'SBER','quantity':20,'price':285}],4000)])
 return store


def app_lab():
 # Retain regression coverage of the v0.6 fragment's financial behavior.
 # The default v0.7 component is covered by test_sandbox_v07 + browser checks.
 at=AppTest.from_string("""
import streamlit as st
from moex_intelligence import lab_ui,portfolio_ui
from moex_intelligence.config import Settings
from moex_intelligence.portfolio import ledger_state
asset=lab_ui.cached_asset('SBER',str(Settings.from_env().data_dir))['asset']
if asset:
 bundle=portfolio_ui.portfolio_store().bundle()
 symbols=tuple(sorted(ledger_state([r['event'] for r in bundle['records']])['positions']))
 if st.button('Сбросить эксперимент',key='lab_reset_button',on_click=lab_ui._reset):pass
 view=st.segmented_control('Эксперимент',['Покупка и цена','Финансовая цель'],default='Покупка и цена',key='lab_view')
 if view=='Финансовая цель':lab_ui.goal_panel()
 else:lab_ui.trade_panel(asset,bundle,portfolio_ui.market_marks(symbols)['marks'])
else:lab_ui._manual_quote('SBER')
""",default_timeout=30).run()
 assert not at.exception
 return at


def prefix(at):
 return next(x.key[:-3] for x in at.number_input if x.key and x.key.endswith('_qty') and x.key.startswith('lab_'))


def metric(at,label):return next(x.value for x in at.metric if x.label==label)


def test_automatic_buy_topup_stress_sale_and_reset_do_not_touch_ledger(monkeypatch,tmp_path):
 store=fixture_market(monkeypatch,tmp_path);original=copy.deepcopy(store.bundle())
 at=app_lab();p=prefix(at)
 assert not at.exception and not at.error
 assert metric(at,'Стоимость покупки с комиссией')=='Комиссия неизвестна'
 at.checkbox(key=p+'fee_known').check().run()
 at.number_input(key=p+'fee_rate').set_value(.05).run()
 assert metric(at,'Стоимость покупки с комиссией')=='2,851.43 ₽'
 at.number_input(key=p+'qty').set_value(20).run()
 assert any('Недостаточно денег' in x.value for x in at.warning)
 at.button(key=p+'try_topup').click().run()
 assert not at.exception and any('Гипотетическое пополнение' in x.value for x in at.info)
 at.slider(key=p+'shock').set_value(-20).run()
 assert metric(at,'Стоимость позиции при этой цене')=='9,120.00 ₽'
 # This fixture holds only SBER: after topping up, all NAV is 40 shares.
 assert metric(at,'Стоимость портфеля при этой цене')=='9,120.00 ₽'
 at.segmented_control(key=p+'side').set_value('sell').run()
 assert not at.exception and metric(at,'Выручка после комиссии')=='5,697.15 ₽'
 at.button(key='lab_reset_button').click().run()
 assert not at.exception and prefix(at)!=p
 assert store.bundle()==original


def test_lot_error_unknown_fee_and_empty_manual_price_are_clear(monkeypatch,tmp_path):
 fixture_market(monkeypatch,tmp_path);at=app_lab();p=prefix(at)
 at.number_input(key=p+'qty').set_value(7).run()
 assert not at.exception and any('не кратны лоту' in x.value for x in at.error)
 assert at.number_input(key=p+'qty').value==7
 monkeypatch.setattr(lab_ui,'cached_asset',lambda *args:{'asset':None,'error':'offline'})
 at.run()
 assert not at.exception and at.number_input(key='lab_manual_lot').value==0
 at.checkbox(key='lab_manual_ack').check()
 at.button(key='FormSubmitter:lab_manual_quote-Использовать ручную цену только в песочнице').click().run()
 assert not at.exception and at.error


def test_history_loaded_once_quantity_and_shock_do_not_recalibrate_model(monkeypatch,tmp_path):
 store=fixture_market(monkeypatch,tmp_path);engine=get_engine();counter={'history':0}
 frame,meta=demo_daily(days=756,end=market_today()-timedelta(days=1))
 # Deliberately synthetic and visibly labelled; this is not claimed as a live quote test.
 async def history(*args):counter['history']+=1;return frame,meta
 monkeypatch.setattr(engine,'frame',history)
 lab_ui.cached_history.clear();lab_ui.cached_envelope.clear()
 at=app_lab();p=prefix(at)
 at.checkbox(key=p+'model_enabled').check().run()
 assert not at.exception and counter['history']==1
 assert any('ИСКУССТВЕННАЯ' in x.value for x in at.warning)
 before=store.bundle()
 at.slider(key=p+'shock').set_value(-30).run()
 at.number_input(key=p+'qty').set_value(20).run()
 at.segmented_control(key=p+'model_horizon').set_value('Год').run()
 assert not at.exception and counter['history']==1
 at.button(key=p+'save_model').click().run()
 assert not at.exception and lab_ui.research_store().list()
 assert store.bundle()==before
 assert not at.exception


def test_financial_goal_recomputes_without_a_calculate_button(monkeypatch,tmp_path):
 fixture_market(monkeypatch,tmp_path);at=app_lab()
 at.segmented_control(key='lab_view').set_value('Финансовая цель').run()
 assert not at.exception
 first=metric(at,'Номинальный капитал')
 at.number_input(key='goal_monthly').set_value(10000.).run()
 assert not at.exception and metric(at,'Номинальный капитал')!=first
 assert all('Рассчитать' not in x.label for x in at.button)


def test_portfolio_one_click_opens_existing_quantity_and_structural_health(monkeypatch,tmp_path):
 store=fixture_market(monkeypatch,tmp_path)
 at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
 at.sidebar.button(key='nav_Portfolio').click().run()
 at.button(key='portfolio_health').click().run()
 assert not at.exception and any('Структура и стресс' in x.value for x in at.subheader)
 at.button(key='position_evaluate').click().run()
 assert not at.exception and at.session_state['page']=='Laboratory'
 assert at.session_state['sandbox_validated']['known_quantity']==20
 assert at.session_state['sandbox_validated']['order']['quantity']==0
 assert at.session_state['sandbox_validated']['constraints']['status']=='insufficient_data'


def test_odd_lot_existing_position_is_valued_without_a_new_order(monkeypatch,tmp_path):
 store=fixture_market(monkeypatch,tmp_path);record=store.bundle()['records'][0]
 replacement=copy.deepcopy(record['event']);replacement['holdings'][0]['quantity']=7
 store.correct(record['id'],replacement,expected_revision=store.bundle()['revision'])
 at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
 at.sidebar.button(key='nav_Portfolio').click().run();before=store.bundle()
 at.button(key='position_scenarios').click().run()
 assert not at.exception and not at.error
 r=at.session_state['sandbox_validated']
 assert r['known_quantity']==7 and r['order']['quantity']==0
 assert r['before']['positions'][0]['market_value']==1995
 assert store.bundle()==before


def test_fee_is_saved_explicitly_and_reused_after_reset(monkeypatch,tmp_path):
 fixture_market(monkeypatch,tmp_path);at=app_lab();p=prefix(at)
 at.checkbox(key=p+'fee_known').check().run()
 at.number_input(key=p+'fee_rate').set_value(.05).run()
 at.button(key=p+'save_fee').click().run()
 assert not at.exception and lab_ui.research_store().preferences()['commission']['pct']==.05
 at.button(key='lab_reset_button').click().run()
 assert not at.exception and metric(at,'Стоимость покупки с комиссией')=='2,851.43 ₽'
