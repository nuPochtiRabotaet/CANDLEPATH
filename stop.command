#!/bin/bash
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo 'Виртуальное окружение не найдено.'; exit 0; fi
.venv/bin/python -m moex_intelligence.launcher stop
