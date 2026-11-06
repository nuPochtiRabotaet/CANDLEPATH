"""Offline regression for the local public Bybit diagnostic shell wrapper.

A fake interpreter replaces the diagnostic; no network, keys, or trades.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "check_bybit.command"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="Bash unavailable")


@pytest.mark.parametrize("diagnostic_status", [0, 1, 7])
def test_headless_diagnostic_preserves_exact_status(tmp_path, diagnostic_status):
    root = tmp_path / "isolated-app"
    (root / ".venv" / "bin").mkdir(parents=True)
    shutil.copyfile(SOURCE, root / "check_bybit.command")

    fake_python = root / ".venv" / "bin" / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$MOCK_LOG\"\n"
        "exit \"$MOCK_EXIT\"\n"
    )
    fake_python.chmod(0o755)
    log = tmp_path / "diagnostic.log"
    env = dict(os.environ, MOCK_EXIT=str(diagnostic_status), MOCK_LOG=str(log))

    result = subprocess.run(
        [shutil.which("bash"), str(root / "check_bybit.command")],
        cwd=tmp_path, env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == diagnostic_status, result.stderr
    assert log.read_text().splitlines() == ["scripts/diagnose_bybit.py"]
    if diagnostic_status:
        assert f"кодом {diagnostic_status}" in result.stderr
    else:
        assert "Диагностика Bybit завершилась" not in result.stderr
    assert "Нажмите Enter" not in result.stdout + result.stderr


def test_missing_venv_fails_without_waiting_for_stdin(tmp_path):
    root = tmp_path / "isolated-app"
    root.mkdir()
    shutil.copyfile(SOURCE, root / "check_bybit.command")
    result = subprocess.run(
        [shutil.which("bash"), str(root / "check_bybit.command")],
        cwd=tmp_path, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 1
    assert "Сначала запустите setup.command" in result.stderr
    assert "Нажмите Enter" not in result.stdout + result.stderr
