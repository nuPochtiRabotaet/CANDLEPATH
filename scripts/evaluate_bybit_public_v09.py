#!/usr/bin/env python3
"""Public Bybit spot historical forecast audit. NO keys, Store or live trading.

Requires working, unblocked public REST access to https://api.bybit.com.
No pretend/synthetic fallback: if Bybit cannot be reached, exit 2.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from moex_intelligence.crypto.bybit_history_evaluation import evaluate_public_spot_history
from moex_intelligence.crypto.market import MarketError, SYMBOLS, INTERVALS


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="READ-ONLY Bybit SPOT historical replay; not a live forecast or trade")
    parser.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    parser.add_argument("--timeframe", choices=tuple(INTERVALS.values()), default="15")
    parser.add_argument("--bars", type=int, default=1600)
    parser.add_argument("--output", type=Path,
                        help="Optional JSON report path (created ONLY after real-data verification)")
    args = parser.parse_args(argv)

    result = asyncio.run(evaluate_public_spot_history(
        args.symbol, args.timeframe, bars=args.bars))
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output is not None:
        # A named output is intentional; no SQLite/private portfolio writes.
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (MarketError, ValueError, OSError) as exc:
        print("REAL BYBIT HISTORY NOT VERIFIED: " + str(exc), file=sys.stderr)
        raise SystemExit(2) from None
