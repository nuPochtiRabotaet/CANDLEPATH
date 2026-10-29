from pathlib import Path
from streamlit.testing.v1 import AppTest
from moex_intelligence.portfolio import PortfolioStore
from moex_intelligence.portfolio_ui import portfolio_store
from moex_intelligence import portfolio_ui as ui
from moex_intelligence.data import market_today

ROOT=Path(__file__).resolve().parents[1]

def html(at):return ''.join(x.proto.body for x in at.get('html'))


def mocked_market(symbols):
    return {'marks':{s:{'price':150.,'as_of':market_today().isoformat(),'source':'test MOEX fixture',
            'name':'Test instrument','asset_type':'equity','retrieved_at_utc':'2026-10-25T12:00:00Z','exchange_time':'test'} for s in symbols},'errors':{}}


def start(monkeypatch,tmp_path):
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(ui,'market_marks',mocked_market)
    at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    at.sidebar.button(key='nav_Portfolio').click().run()
    assert not at.exception
    return at


def test_add_correct_delete_and_auto_revalue(monkeypatch,tmp_path):
    at=start(monkeypatch,tmp_path)
    at.number_input(key='event_amount').set_value(1000.)
    at.button(key='FormSubmitter:ledger_form-Сохранить запись').click().run()
    assert not at.exception and not at.error
    at.selectbox(key='event_kind').set_value('buy').run()
    assert not any(x.key=='event_amount' for x in at.number_input)
    at.number_input(key='event_qty').set_value(2)
    at.number_input(key='event_price').set_value(100.)
    at.button(key='FormSubmitter:ledger_form-Сохранить запись').click().run()
    assert not at.exception and not at.error and '1 100,00 ₽' in html(at)
    db=portfolio_store();record=db.bundle()['records'][1];eid=record['id']
    at.selectbox(key='edit_choice').set_value(eid).run()
    at.number_input(key='edit_'+eid+'_price').set_value(120.)
    at.button(key='FormSubmitter:edit_'+eid+'_form-Сохранить исправление').click().run()
    assert not at.exception and not at.error and len(db.load())==2
    assert '1 060,00 ₽' in html(at)
    # Delete a funding record: the UI must show the replay error and keep both rows.
    dep_id=db.bundle()['records'][0]['id']
    at.selectbox(key='edit_choice').set_value(dep_id).run()
    at.checkbox(key='edit_'+dep_id+'_confirm_delete').check().run()
    at.button(key='edit_'+dep_id+'_delete').click().run()
    assert not at.exception and at.error and len(db.load())==2
    at.selectbox(key='edit_choice').set_value(eid).run()
    at.checkbox(key='edit_'+eid+'_confirm_delete').check().run()
    at.button(key='edit_'+eid+'_delete').click().run()
    assert not at.exception and not at.error and len(db.load())==1
    assert '1 000,00 ₽' in html(at)


def test_quick_transfer_unknown_history_and_research_navigation(monkeypatch,tmp_path):
    at=start(monkeypatch,tmp_path)
    at.number_input(key='opening_qty').set_value(7)
    at.number_input(key='opening_price').set_value(100.)
    at.button(key='FormSubmitter:opening_position-Добавить в список переноса').click().run()
    at.number_input(key='opening_cash').set_value(300.)
    at.checkbox(key='opening_ack').check()
    at.button(key='FormSubmitter:opening_save-Сохранить начальные остатки').click().run()
    assert not at.exception and not at.error
    assert '1 350,00 ₽' in html(at) and 'недостаточно истории' in html(at)
    assert [e['kind'] for e in portfolio_store().load()]==['opening']
    from moex_intelligence import lab_ui
    monkeypatch.setattr(lab_ui,'cached_asset',lambda *args:{'asset':None,'error':'test offline'})
    at.button(key='position_evaluate').click().run()
    assert not at.exception and at.session_state['page']=='Laboratory'
    assert at.text_input(key='lab_picker_query').value=='SBER'
    # A normal manual portfolio edit invalidates a prior session research result.
    at.sidebar.button(key='nav_Overview').click().run()
    assert not at.exception and '300,00 ₽' in html(at)
    assert ui.current_portfolio()[2]['snapshot']['equity']==1350


def test_missing_quote_never_looks_like_zero_or_purchase_price(monkeypatch,tmp_path):
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
    db=portfolio_store();db.append_many([{'kind':'opening','date':'2026-01-01','amount':100,'holdings':[{'symbol':'SBER','quantity':7,'price':100}]}])
    monkeypatch.setattr(ui,'market_marks',lambda symbols:{'marks':{},'errors':{'SBER':'offline'}})
    at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    at.sidebar.button(key='nav_Portfolio').click().run()
    assert not at.exception and any('недоступна' in x.value for x in at.warning)
    assert all(x.label!='Стоимость портфеля' for x in at.metric)
    assert '100,00 ₽' in html(at)


def test_confirmed_operation_action_keeps_instrument_and_does_not_write(monkeypatch,tmp_path):
    at=start(monkeypatch,tmp_path)
    db=portfolio_store();db.append_many([{'kind':'opening','date':str(market_today()),'amount':300,'holdings':[{'symbol':'SBMX','quantity':7,'price':100}]}])
    at.run();before=db.bundle()
    at.button(key='position_actual').click().run()
    assert not at.exception and at.session_state['portfolio_active_tab']=='Операции'
    assert at.text_input(key='event_picker_query').value=='SBMX'
    assert db.bundle()==before
    at.run();assert at.session_state['portfolio_active_tab']=='Операции'
