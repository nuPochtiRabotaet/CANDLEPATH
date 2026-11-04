#!/bin/bash
set -eu
cd "$(dirname "$0")"

pause_if_interactive() {
  if [ -t 0 ]; then
    read -r -p "$1" _unused || true
  fi
}

if [ ! -x .venv/bin/python ]; then
  echo 'Сначала запустите setup.command.' >&2
  pause_if_interactive 'Нажмите Enter для закрытия.'
  exit 1
fi

if .venv/bin/python -m moex_intelligence.launcher start; then
  exit 0
else
  status=$?
  echo "Ошибка запуска CandlePath (код $status)." >&2
  pause_if_interactive 'Нажмите Enter для закрытия.'
  exit "$status"
fi
