"""Tests for single-owner local Paper background execution."""
import os
from pathlib import Path
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
