#!/bin/bash
# CandlePath v0.9 verification on macOS / Linux. Local isolated test database.
set -euo pipefail
ROOT="$(cd "$(dirname "\${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "Python missing. Run ./setup.command first." >&2
  exit 1
fi

TEST_DIR="$(mktemp -d "\${TMPDIR:-/tmp}/candlepath-v09-XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT
export MOEX_DATA_DIR="$TEST_DIR"
export PYTHONDONTWRITEBYTECODE=1

echo "[1/4] Compile Python sources"
"$PYTHON" -m compileall -q moex_intelligence tests scripts
echo "[2/4] Check JavaScript syntax"
if command -v node >/dev/null 2>&1; then
  node --check moex_intelligence/components/trade.js
else
  echo "SKIP: Node.js missing, JavaScript syntax not independently checked"
fi
echo "[3/4] Run full Python test suite"
"$PYTHON" -m pytest -q
echo "[4/4] Optional Chromium synthetic-browser smoke"
if "$PYTHON" -c "import playwright" >/dev/null 2>&1; then
  "$PYTHON" scripts/verify_v09_forecast_browser.py
else
  echo "SKIP: Playwright missing; macOS Safari / real Bybit remain manual acceptance"
fi
echo "DONE: these checks do not prove forecasting alpha or live exchange readiness."
