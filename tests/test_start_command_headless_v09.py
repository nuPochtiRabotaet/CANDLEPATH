"""Check start.command returns honest status without interactive prompts.

All subprocesses use a temporary fake Python launcher; Streamlit never starts.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "start.command"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="Bash missing")


@pytest.mark.parametrize("status", [0, 7])
def test_start_command_propagates_launcher_exit_code(tmp_path, status):
    root = tmp_path / "isolated-app"
    (root / ".venv" / "bin").mkdir(parents=True)
    shutil.copyfile(SOURCE, root / "start.command")

    mock_python = root / ".venv" / "bin" / "python"
    mock_python.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$MOCK_LOG\"\n"
        "exit \"$MOCK_EXIT\"\n"
    )
    mock_python.chmod(0o755)
    log = tmp_path / "launch.log"
    env = dict(os.environ, MOCK_EXIT=str(status), MOCK_LOG=str(log))
    result = subprocess.run(
        [shutil.which("bash"), str(root / "start.command")],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env,
        cwd=root, timeout=10, check=False,
    )
    assert result.returncode == status, (result.stdout, result.stderr)
    assert log.read_text().splitlines() == ["-m moex_intelligence.launcher start"]
    if status == 0:
        assert "Ошибка запуска" not in result.stderr
    else:
        assert f"код {status}" in result.stderr
    assert "Нажмите Enter" not in result.stderr + result.stdout


def test_start_command_missing_environment_fails_without_prompt(tmp_path):
    root = tmp_path / "isolated-app"
    root.mkdir()
    shutil.copyfile(SOURCE, root / "start.command")
    result = subprocess.run(
        [shutil.which("bash"), str(root / "start.command")],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        cwd=root, timeout=10, check=False,
    )
    assert result.returncode == 1
    assert "Сначала запустите setup.command." in result.stderr
    assert "Нажмите Enter" not in result.stderr + result.stdout
