"""Integration contract for the Mac/Linux QA launcher.

Run a copied launcher with fake Python/Node binaries, never real pytest,
a real browser, user market data, or user portfolio directories.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "verify_v09_local.command"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="Bash unavailable")


def run_launcher(tmp_path, *, browser=True, strict=False, fail_node=False):
    root = tmp_path / "isolated-checkout"
    (root / "scripts").mkdir(parents=True)
    (root / ".venv" / "bin").mkdir(parents=True)
    launcher = root / "scripts" / "verify_v09_local.command"
    shutil.copyfile(SOURCE, launcher)

    mock_log = tmp_path / "commands.log"
    py = root / ".venv" / "bin" / "python"
    py.write_text(
        "#!/bin/sh\n"
        "printf 'PY %s | DATA=%s\\n' \"$*\" \"$MOEX_DATA_DIR\" >> \"$MOCK_LOG\"\n"
        "if [ \"$1\" = \"-c\" ]; then\n"
        "  [ \"$MOCK_BROWSER_AVAILABLE\" = \"1\" ]\n"
        "  exit $?\n"
        "fi\n"
        "exit 0\n"
    )
    py.chmod(0o755)

    bin_dir = tmp_path / "mock-bin"
    bin_dir.mkdir()
    node = bin_dir / "node"
    node.write_text(
        "#!/bin/sh\n"
        "printf 'NODE %s | DATA=%s\\n' \"$*\" \"$MOEX_DATA_DIR\" >> \"$MOCK_LOG\"\n"
        "if [ \"$MOCK_NODE_FAIL\" = \"1\" ] && "
        "[ \"$1\" = \"scripts/verify_v09_chart_updates.js\" ]; then exit 7; fi\n"
        "exit 0\n"
    )
    node.chmod(0o755)

    env = dict(os.environ)
    env.update(
        PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        TMPDIR=str(tmp_path),
        MOCK_LOG=str(mock_log),
        MOCK_BROWSER_AVAILABLE="1" if browser else "0",
        MOCK_NODE_FAIL="1" if fail_node else "0",
        MOEX_DATA_DIR="/should/not/be/reused",
    )
    proc = subprocess.run(
        ["bash", str(launcher), *(["--strict"] if strict else [])],
        cwd=root, env=env, text=True, capture_output=True, check=False,
    )
    return proc, mock_log.read_text() if mock_log.exists() else ""


def test_local_qa_runs_all_ci_contracts_and_cleans_temporary_data(tmp_path):
    result, log = run_launcher(tmp_path, strict=True)
    assert result.returncode == 0, result.stderr
    for expected in (
        "PY -m compileall -q moex_intelligence tests scripts",
        "NODE --check moex_intelligence/components/trade.js",
        "NODE scripts/verify_v09_forecast_geometry.js",
        "NODE scripts/verify_v09_chart_updates.js",
        "PY -m pytest -q",
        "PY scripts/verify_v09_forecast_browser.py",
    ):
        assert expected in log
    assert "PASS: local Python, JS and synthetic Chromium checks completed" in result.stdout
    data_dir = next(line.split("DATA=", 1)[1] for line in log.splitlines() if "DATA=" in line)
    assert data_dir.startswith(str(tmp_path) + os.sep)
    assert not Path(data_dir).exists(), "Temporary test DB must be removed"


@pytest.mark.parametrize("strict,expected", [(False, 0), (True, 2)])
def test_missing_browser_is_explicit_partial_coverage(tmp_path, strict, expected):
    result, log = run_launcher(tmp_path, browser=False, strict=strict)
    assert result.returncode == expected, result.stderr
    assert "PY -m pytest -q" in log
    assert "SKIP: Playwright missing" in result.stderr
    assert "PARTIAL COVERAGE" in result.stderr
    assert "PASS: local Python, JS" not in result.stdout


def test_failing_js_contract_stops_qa_before_python_suite(tmp_path):
    result, log = run_launcher(tmp_path, fail_node=True)
    assert result.returncode == 7
    assert "NODE scripts/verify_v09_chart_updates.js" in log
    assert "PY -m pytest -q" not in log


def test_bad_cli_flag_stops_before_any_commands(tmp_path):
    result, log = run_launcher(tmp_path, strict=False)
    assert result.returncode == 0
    assert "PY -m pytest -q" in log
