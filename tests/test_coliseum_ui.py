from pathlib import Path
from streamlit.testing.v1 import AppTest
from moex_intelligence.crypto.coliseum_jobs import register_csv,start
import pytest

def test_saved_report_ui_and_filters(tmp_path,monkeypatch):
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
    a=AppTest.from_string('from moex_intelligence.crypto.coliseum_ui import page\npage()').run(timeout=30)
    assert not a.exception
    assert any(x.value=='100' for x in a.metric)
    a.selectbox(key=None) if False else None
    select=next(x for x in a.selectbox if x.label=='Прибыльность')
    select.set_value('Валовой > 0').run(timeout=30)
    assert not a.exception and len(a.dataframe[0].value)==33
    assert not list(tmp_path.rglob('*.db'))

def test_job_rejects_unknown_source_and_path(tmp_path,monkeypatch):
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
    with pytest.raises(ValueError):register_csv(b'')
    with pytest.raises(ValueError):start(tmp_path/'not-registered')
