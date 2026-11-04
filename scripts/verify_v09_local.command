#!/bin/bash
# CandlePath v0.9 local verification on macOS / Linux.
# Runs entirely against a temporary data directory. Never touches saved portfolios.
set -euo pipefail

STRICT_QA=0
if [[ $# -gt 0 ]]; then
  if [[ $# -eq 1 && "$1" == "--strict" ]]; then
    STRICT_QA=1
  else
    echo "Usage: bash scripts/verify_v09_local.command [--strict]" >&2
    exit 2
  fi
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "Python missing. Run ./setup.command first." >&2
  exit 1
fi

TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/candlepath-v09-XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT
export MOEX_DATA_DIR="$TEST_DIR"
export PYTHONDONTWRITEBYTECODE=1
partial=0

echo "[1/4] Compile Python sources"
"$PYTHON" -m compileall -q moex_intelligence tests scripts

echo "[2/4] JavaScript syntax, Forecast geometry, chart contract"
if command -v node >/dev/null 2>&1; then
  node --check moex_intelligence/components/trade.js
  node scripts/verify_v09_forecast_geometry.js
  node scripts/verify_v09_chart_updates.js
else
  echo "SKIP: Node.js missing; JS syntax, Forecast and chart contracts NOT checked" >&2
  partial=1
fi

echo "[3/4] Full Python test suite"
"$PYTHON" -m pytest -q

echo "[4/4] Optional Chromium integration smoke (synthetic candles)"
if "$PYTHON" -c "import playwright" >/dev/null 2>&1; then
  if ! "$PYTHON" scripts/verify_v09_forecast_browser.py; then
    echo "FAIL: Chromium check failed. Install browsers with: $PYTHON -m playwright install chromium" >&2
    exit 1
  fi
else
  echo "SKIP: Playwright missing; install it and Chromium for browser QA" >&2
  partial=1
fi

if [[ "$partial" -ne 0 ]]; then
  echo "PARTIAL COVERAGE: at least one optional check was skipped" >&2
  if [[ "$STRICT_QA" -eq 1 ]]; then
    echo "FAIL: --strict requires Node.js and Playwright/Chromium checks" >&2
    exit 2
  fi
else
  echo "PASS: local Python, JS and synthetic Chromium checks completed"
fi
echo "LIMITS: real Bybit, macOS Safari and trading profitability remain unverified."
