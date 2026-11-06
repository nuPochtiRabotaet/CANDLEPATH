from pathlib import Path
from streamlit.testing.v1 import AppTest
from moex_intelligence.crypto.coliseum_jobs import register_csv,registered_folders,start,pause,status
import pytest
import csv
import io
import hashlib


def valid_csv():
    stream=io.StringIO()
    writer=csv.DictWriter(stream,fieldnames=['timestamp_ms','open','high','low','close','volume'])
    writer.writeheader()
    start_ms=1600000000000//300000*300000
    for i in range(420):
        writer.writerow(dict(timestamp_ms=start_ms+i*300000,open=100,high=101,low=99,close=100,volume=25))
    return stream.getvalue().encode()


def test_rejected_csv_is_not_runnable_or_listed(tmp_path,monkeypatch):
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
    invalid=b'timestamp_ms,open,high,low,close,volume\nbroken\n'
    with pytest.raises(ValueError):
        register_csv(invalid)
    assert registered_folders()==[]
    identity=hashlib.sha256(invalid).hexdigest()
    with pytest.raises(ValueError,match='Unvalidated'):
        start(tmp_path/'coliseum-research'/identity)
    assert not list(tmp_path.rglob('source.csv'))


def test_valid_registration_is_immutable_and_tamper_evident(tmp_path,monkeypatch):
    monkeypatch.setenv('MOEX_DATA_DIR',str(tmp_path))
    source=valid_csv()
    folder,quality=register_csv(source)
    assert folder.name==hashlib.sha256(source).hexdigest()
    assert quality['source']=='USER_SUPPLIED_CSV_UNVERIFIED'
    assert quality['sealed_evaluated'] is False
    assert registered_folders()==[folder]
    assert register_csv(source)[0]==folder
    assert not list(folder.glob('.upload-*'))
    with pytest.raises(ValueError,match='not started'):
        pause(folder)
    (folder/'source.csv').write_bytes(source+b'\n')
    assert registered_folders()==[]
    with pytest.raises(ValueError,match='changed'):
        start(folder)
    with pytest.raises(ValueError,match='changed'):
        status(folder)


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

def test_compressed_saved_report_preserves_financial_results(tmp_path):
    import gzip
    from moex_intelligence.crypto.coliseum_ui import load_report
    root=Path(__file__).resolve().parents[1]/'docs/research/coliseum_v02'
    (tmp_path/'manifest.json').write_bytes((root/'manifest.json').read_bytes())
    (tmp_path/'result.json.gz').write_bytes(gzip.compress((root/'result.json').read_bytes(),mtime=0))
    assert load_report(tmp_path)==load_report(root)
