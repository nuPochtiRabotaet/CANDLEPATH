from pathlib import Path
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]

def html(at):return ''.join(x.proto.body for x in at.get('html'))


def app(): return AppTest.from_file(str(ROOT/'app.py'),default_timeout=30)


def research(at,section):
    if section in {'AI Research','Investment Advisor'}:
        if at.session_state['page']!='Research':
            at.sidebar.button(key='nav_Research').click().run()
        at.button(key='deep_ai' if section=='AI Research' else 'deep_advisor').click().run()
        return at
    at.session_state['research_section']=section
    at.sidebar.button(key='nav_Research').click().run()
    return at


def test_six_pages_and_calculations(monkeypatch,tmp_path):
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
    at=app().run()
    assert not at.exception
    at.sidebar.radio(key='mode').set_value('Демо · искусственные данные').run()
    at.sidebar.button(key='load_history').click().run()
    assert not at.exception and 'dataset' in at.session_state
    from moex_intelligence import lab_ui
    monkeypatch.setattr(lab_ui,'cached_asset',lambda *a:{'asset':None,'error':'test offline'})
    research(at,'Market Explorer')
    assert not at.exception and len(at.dataframe)>0
    research(at,'Time Machine')
    at.selectbox(key='runs').set_value(1000)
    at.button(key='FormSubmitter:simulation_form-Рассчитать сценарии').click().run()
    assert not at.exception and not at.error and len(at.metric)>=6
    research(at,'Strategy Lab')
    at.button(key='FormSubmitter:backtest_form-Проверить стратегию').click().run()
    assert not at.exception and not at.error and len(at.dataframe)>0
    research(at,'AI Research')
    at.button(key='report').click().run()
    assert not at.exception and any('Исследование DEMO' in x.value for x in at.markdown)
    at.sidebar.button(key='nav_Portfolio').click().run()
    at.button(key='FormSubmitter:ledger_form-Сохранить запись').click().run()
    assert not at.exception and not at.error
    assert '19 000,00 ₽' in html(at)


def test_no_synthetic_fallback_on_live_error(monkeypatch,tmp_path):
    monkeypatch.setenv("MOEX_DATA_DIR",str(tmp_path))
    from moex_intelligence.data import get_engine
    def unavailable(*args): raise ValueError('network unavailable')
    monkeypatch.setattr(get_engine(),'frame_sync',unavailable)
    at=app().run()
    at.sidebar.button(key='load_history').click().run()
    assert not at.exception and len(at.error)==1 and 'network unavailable' in at.error[0].value
    assert 'dataset' not in at.session_state


def test_advisor_profile_history_and_mode_do_not_change_math(monkeypatch,tmp_path):
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
    at=app().run()
    at.sidebar.radio(key='mode').set_value('Демо · искусственные данные').run()
    at.sidebar.button(key='load_history').click().run()
    research(at,'Investment Advisor')
    at.checkbox(key='adv_filled').check()
    at.number_input(key='adv_loss').set_value(5.)
    at.selectbox(key='adv_runs').set_value(1000)
    at.button(key='FormSubmitter:advisor_form-Проанализировать инвестицию').click().run()
    assert not at.exception and not at.error
    result=at.session_state['advisor_result']
    assert result['verdict']['category']=='unsuitable'
    before=result['models']
    assert all(r.key != 'ui_mode' for r in at.sidebar.radio)
    at.run()
    assert at.session_state['advisor_result']['models']==before
    research(at,'History')
    assert not at.exception and any('Сохранённый снимок' in x.value for x in at.info)
    at.button(key='open_settings').click().run()
    assert not at.exception
