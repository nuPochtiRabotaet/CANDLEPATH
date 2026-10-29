#!/bin/bash
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Сначала запустите setup.command.'
  read -r -p 'Нажмите Enter для закрытия.' _unused
  exit 1
fi
if ! .venv/bin/python -m moex_intelligence.launcher start; then
  read -r -p 'Ошибка запуска. Нажмите Enter для закрытия.' _unused
  exit 1
fi
