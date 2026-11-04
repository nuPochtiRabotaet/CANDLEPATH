#!/bin/bash
set -eu
cd "$(dirname "$0")"

pause_if_interactive() {
  if [ -t 0 ]; then
    read -r -p 'Нажмите Enter для закрытия.' _unused || true
  fi
}

if [ ! -x .venv/bin/python ]; then
  echo 'Сначала запустите setup.command' >&2
  pause_if_interactive
  exit 1
fi

if .venv/bin/python scripts/diagnose_bybit.py; then
  status=0
else
  status=$?
  echo "Диагностика Bybit завершилась с кодом $status." >&2
fi
pause_if_interactive
exit "$status"
