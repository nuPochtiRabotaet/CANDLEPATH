#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Сначала запустите setup.command в этой папке."
  exit 1
fi
.venv/bin/python -m scripts.diagnose_moex --quotes --output .runtime/moex-diagnostic.json
