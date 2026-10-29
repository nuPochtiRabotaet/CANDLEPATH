#!/bin/bash
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo 'Сначала запустите setup.command'; exit 1; fi
.venv/bin/python scripts/diagnose_bybit.py || true
read -r -p 'Нажмите Enter для закрытия.' _unused
