"""Tests for single-owner local Paper background execution."""
from contextlib import closing, contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
from select import select
import signal
import sqlite3
import subprocess
import sys

import pytest

from moex_intelligence.crypto import runtime


def test_runtime_starts_without_trade_and_is_singleton(tmp_path, monkeypatch):
    monkeypatch.setenv('MOEX_DATA_DIR', str(tmp_path))
    try:
        first = runtime.start()
        assert first.thread.is_alive()
        assert runtime.start() is first
        assert runtime.monitor(tmp_path / '.' / 'crypto-v08.sqlite3') is first
        first.tick()
        assert first.heartbeat > 0
    finally:
        runtime.shutdown()
    assert not first.thread.is_alive()


def test_runtime_can_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('MOEX_DATA_DIR', str(tmp_path))
    first = runtime.start()
    runtime.shutdown()
    try:
        second = runtime.start()
        assert second is not first
        assert second.thread.is_alive()
    finally:
        runtime.shutdown()


def _claim_in_subprocess(path):
    script = '''import fcntl,os,sys
fd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600)
try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: sys.exit(17)
else: sys.exit(0)
'''
    return subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True, timeout=5).returncode


def test_process_lock_blocks_second_process_until_shutdown(tmp_path):
    dbpath = tmp_path / 'positions.sqlite3'
    try:
        worker = runtime.monitor(dbpath)
        assert worker.thread.is_alive()
        assert _claim_in_subprocess(Path(str(dbpath) + '.monitor.lock')) == 17
        assert (tmp_path / 'positions.sqlite3.monitor.lock').stat().st_mode & 0o077 == 0
    finally:
        runtime.shutdown()
    assert _claim_in_subprocess(Path(str(dbpath) + '.monitor.lock')) == 0


def test_second_process_monitor_fails_closed_without_mutating_ledger(tmp_path):
    dbpath = tmp_path / 'one.sqlite3'
    try:
        worker = runtime.monitor(dbpath)
        script = '''import sys
from moex_intelligence.crypto import runtime
try: runtime.monitor(sys.argv[1])
except RuntimeError: sys.exit(17)
else: runtime.shutdown();sys.exit(1)
'''
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        result = subprocess.run([sys.executable, '-c', script, str(dbpath)], env=env, capture_output=True, timeout=8)
        assert result.returncode == 17, result.stderr.decode()
        assert worker.thread.is_alive()
    finally:
        runtime.shutdown()


def test_failed_monitor_startup_releases_process_ownership(tmp_path, monkeypatch):
    dbpath = tmp_path / 'failed.sqlite3'
    def broken(*_args):
        raise OSError('simulated constructor failure')
    monkeypatch.setattr(runtime, 'PaperMonitor', broken)
    with pytest.raises(OSError, match='constructor failure'):
        runtime.monitor(dbpath)
    assert _claim_in_subprocess(Path(str(dbpath) + '.monitor.lock')) == 0
    runtime.shutdown()


@contextmanager
def _paper_process(directory, role):
    script = Path(__file__).with_name('paper_crash_worker.py').resolve()
    # Allowlist the child environment; do not inherit credentials or user settings.
    env = {'MOEX_DATA_DIR': str(directory), 'MOEX_PAPER_CAPITAL': '10000',
           'PYTHONPATH': str(script.parents[1])}
    with subprocess.Popen([sys.executable, str(script), role], cwd=directory, env=env,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as child:
        try:
            yield child
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=15)


def _message(child):
    assert select([child.stdout], [], [], 15)[0], 'Paper child timed out before its checkpoint'
    line = child.stdout.readline()
    assert line, f'Paper child exited before its checkpoint (status {child.poll()})'
    return json.loads(line)


def _financial_snapshot(path):
    # One read-only snapshot of committed business records, independent of the worker.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        state = json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0])
        return {
            'account': {k: state[k] for k in ('initial', 'cash', 'realized', 'positions')},
            'orders': {k: json.loads(v) for k, v in db.execute('SELECT id,body FROM orders')},
            'intents': {k: json.loads(v) for k, v in db.execute('SELECT id,body FROM intents')},
            'events': db.execute('SELECT id,time,body FROM events ORDER BY id').fetchall(),
        }


def _check_committed_purchase(snapshot, fill):
    assert fill['status'] == 'Filled' and fill['source'] == 'LOCAL PAPER'
    assert snapshot['orders'] == {fill['id']: fill}
    intents = snapshot['intents']
    assert intents[fill['id']]['status'] == 'Filled'
    assert sorted(i['status'] for i in intents.values()) == ['Filled', 'Prepared']
    events = [json.loads(body) for _, _, body in snapshot['events']]
    assert [e['order'] for e in events if 'order' in e] == [fill['id']]

    account = snapshot['account']
    assert set(account['positions']) == {'BTCUSDT'}
    position = account['positions']['BTCUSDT']
    assert position['position_id'] == fill['id']
    assert Decimal(position['qty']) == Decimal(fill['filled_quantity']) == 1
    fee = Decimal(fill['fee'])
    assert fee == Decimal(position['entry_fee']) == Decimal(fill['execution']['values']['fee_quantity'])
    assert fee == Decimal(fill['fill']) * Decimal(fill['execution']['model']['fees']['taker']) > 0
    basis = Decimal(position['cost_basis'])
    assert basis == Decimal(fill['fill']) + fee == -Decimal(fill['cash_delta'])
    assert Decimal(account['realized']) == 0 and Decimal(account['cash']) > 0
    assert Decimal(account['cash']) + basis == Decimal(account['initial']) == 10000


def _crash(owner):
    owner.kill()
    assert owner.wait(timeout=15) == -signal.SIGKILL


def test_single_owner_recovers_committed_fill_after_sigkill(tmp_path):
    """Two abrupt handovers: an idle owner, then an owner inside a real SELL transaction."""
    db_path = tmp_path / 'crypto-v08.sqlite3'
    with _paper_process(tmp_path, 'initial') as owner:
        fill = _message(owner)
        original = _financial_snapshot(db_path)
        _check_committed_purchase(original, fill)
        with _paper_process(tmp_path, 'recover') as contender:
            assert _message(contender) == 'ownership denied'
            assert contender.wait(timeout=15) == 0
        assert owner.poll() is None
        assert _financial_snapshot(db_path) == original
        _crash(owner)
    assert _financial_snapshot(db_path) == original

    with _paper_process(tmp_path, 'recover') as successor:
        assert _message(successor) == fill  # replay the same confirmed UUID
        assert _financial_snapshot(db_path) == original
        print('stage sale', file=successor.stdin, flush=True)
        assert _message(successor) == 'sell staged before commit'
        assert _financial_snapshot(db_path) == original
        _crash(successor)
    assert _financial_snapshot(db_path) == original

    with _paper_process(tmp_path, 'recover') as successor:
        assert _message(successor) == fill
        print('shutdown', file=successor.stdin, flush=True)
        assert successor.wait(timeout=15) == 0
    assert _financial_snapshot(db_path) == original
