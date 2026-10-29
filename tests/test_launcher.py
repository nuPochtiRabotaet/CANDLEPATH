from unittest.mock import patch
from moex_intelligence import launcher


def test_unrelated_pid_never_signalled(tmp_path, monkeypatch):
    path = tmp_path / 'launcher.json'
    path.write_text('{"pid":12345,"token":"12345678901234567890123456789012"}')
    monkeypatch.setattr(launcher, 'PIDFILE', path)
    with patch.object(launcher.os, 'kill') as kill, patch.object(launcher.os, 'killpg') as killpg:
        launcher.stop()
        kill.assert_not_called()
        killpg.assert_not_called()


def test_ownership_requires_authenticated_control(monkeypatch):
    monkeypatch.setattr(launcher, 'control', lambda info: {} if info.get('token') == '1' * 32 else None)
    assert launcher.process_owned({'token': '1' * 32})
    assert not launcher.process_owned({'token': '2' * 32})


def test_invalid_control_port_never_connects():
    for port in (True, 80, 65536, '8501', None):
        assert launcher.control({'control_port': port, 'token': '1' * 32}) is None
