#!/bin/bash
set -eu
cd "$(dirname "$0")"
PYTHON_BIN=""
for candidate in python3.12 python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if (3,12) <= sys.version_info[:2] < (3,14) else 1)' 2>/dev/null; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo 'Нужен Python 3.12 или 3.13. Установите его с python.org, затем повторите setup.command.'
  read -r -p 'Нажмите Enter для закрытия.' _unused
  exit 1
fi
if [ ! -x .venv/bin/python ]; then "$PYTHON_BIN" -m venv .venv; fi
.venv/bin/python -c 'import sys; assert (3,12) <= sys.version_info[:2] < (3,14), "Пересоздайте .venv с Python 3.12/3.13"'
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -c 'import numpy, pandas, streamlit, mcp, websockets; print("Зависимости готовы.")'
echo 'Настройка завершена. Откройте start.command.'
# Finder/Terminal keeps its confirmation; non-interactive QA can exit cleanly.
if [ -t 0 ]; then read -r -p 'Нажмите Enter для закрытия.' _unused || true; fi
