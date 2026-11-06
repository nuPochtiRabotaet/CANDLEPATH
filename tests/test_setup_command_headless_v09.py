"""Ensure macOS setup.command works in a non-interactive shell.

Uses only a stub interpreter; does not create a real venv or install packages.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "setup.command"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="Bash unavailable")


def test_successful_setup_exits_zero_without_interactive_stdin(tmp_path):
    root = tmp_path / "separate-install"
    root.mkdir()
    launcher = root / "setup.command"
    shutil.copyfile(SOURCE, launcher)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake = fake_bin / "python3.12"
    fake.write_text(
        "#!/bin/sh\n"
        "printf 'PY %s\\n' \"$*\" >> \"$MOCK_LOG\"\n"
        "if [ \"$1\" = \"-m\" ] && [ \"$2\" = \"venv\" ]; then\n"
        "  mkdir -p \"$3/bin\"\n"
        "  cp \"$0\" \"$3/bin/python\"\n"
        "  chmod +x \"$3/bin/python\"\n"
        "fi\n"
        "exit 0\n"
    )
    fake.chmod(0o755)
    log = tmp_path / "fake-python.log"
    env = dict(os.environ)
    env["PATH"] = str(fake_bin) + os.pathsep + os.environ.get("PATH", "")
    env["MOCK_LOG"] = str(log)

    result = subprocess.run(
        [shutil.which("bash"), str(launcher)], cwd=root, env=env,
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Настройка завершена" in result.stdout
    assert (root / ".venv" / "bin" / "python").is_file()
    recorded = log.read_text()
    assert "PY -m venv .venv" in recorded
    assert "PY -m pip install --require-hashes -r requirements.txt" in recorded
    assert "import numpy, pandas, streamlit" in recorded
