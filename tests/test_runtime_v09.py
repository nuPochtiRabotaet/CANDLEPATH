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
