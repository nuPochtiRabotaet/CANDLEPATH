import csv,fcntl,json,subprocess,sys,time
from pathlib import Path
import pytest
from moex_intelligence.crypto.coliseum_data import load_history
from moex_intelligence.crypto.coliseum_jobs import pause,register_csv,start,status
ROOT=Path(__file__).resolve().parents[1]

def source(path):
    with path.open('w') as f:
        w=csv.writer(f);w.writerow(['timestamp_ms','open','high','low','close','volume'])
        for i in range(450):w.writerow([1500000000000//300000*300000+i*300000,100,101,99,100,10])

def test_import_guard_and_duplicates(tmp_path):
    p=tmp_path/'a.csv';source(p);rows,q=load_history(p)
    assert q['development_end']==360 and not q['sealed_evaluated']
    with pytest.raises(ValueError,match='original sealed'):load_history(p,protected_interval=[rows[100]['time'],rows[120]['time']])
    with p.open('a') as f:f.write(p.read_text().splitlines()[-1]+'\n')
    with pytest.raises(ValueError):load_history(p)

def test_process_lock_kill_resume(tmp_path):
    p=tmp_path/'a.csv';source(p);out=tmp_path/'out'
    cmd=[sys.executable,str(ROOT/'scripts/run_coliseum_v02.py'),str(p),str(out)]
    log=(tmp_path/'log').open('w');first=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=log)
    try:
        deadline=time.monotonic()+30
        while not list(out.glob('????????????????????????????????????????????????????????????????.json')):
            assert first.poll() is None
            if time.monotonic()>deadline:pytest.fail('No trial checkpoint')
            time.sleep(.02)
        second=subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=30)
        assert second.returncode!=0 and b'BlockingIOError' in second.stderr
        first.terminate();first.wait(timeout=10)
        cached={p.name:p.read_bytes() for p in out.glob('*.json')}
        resumed=subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=60);assert resumed.returncode==0,resumed.stderr
        for name,content in cached.items():assert (out/name).read_bytes()==content
        before=(out/'result.json').read_bytes()
        again=subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=30);assert again.returncode==0,again.stderr
        assert (out/'result.json').read_bytes()==before
    finally:
        if first.poll() is None:first.terminate();first.wait(timeout=10)
        log.close()

def test_start_does_not_clear_another_process_pause(tmp_path, monkeypatch):
    monkeypatch.setenv('MOEX_DATA_DIR', str(tmp_path))
    csv_path = tmp_path/'upload.csv'
    source(csv_path)
    folder, _ = register_csv(csv_path.read_bytes())
    study = folder/'study'
    study.mkdir()
    with (study/'.writer.lock').open('a') as worker_lock:
        fcntl.flock(worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert status(folder)['running']
        pause(folder)
        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Worker already active'))
        start(folder)
        assert (study/'cancel.requested').exists()


def test_worker_rejects_csv_replaced_after_start_validation(tmp_path, monkeypatch):
    from moex_intelligence.crypto import coliseum_jobs

    monkeypatch.setenv('MOEX_DATA_DIR', str(tmp_path))
    csv_path = tmp_path/'upload.csv'
    source(csv_path)
    folder, _ = register_csv(csv_path.read_bytes())
    real_popen = subprocess.Popen

    def substitute_then_launch(*args, **kwargs):
        (folder/'source.csv').write_bytes(csv_path.read_bytes() + b'\n')
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', substitute_then_launch)
    start(folder)
    child = coliseum_jobs._CHILDREN.pop(str(folder))
    try:
        assert child.wait(timeout=30) != 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
    assert 'Research source changed after validation' in (folder/'worker.log').read_text()
    assert not (folder/'study'/'manifest.json').exists()
