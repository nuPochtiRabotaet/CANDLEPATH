#!/usr/bin/env python3
"""CandlePath v0.9: offline evaluation of a locally provided OHLCV CSV.

Read-only input and optional create-only JSON report. Source authenticity is
UNVERIFIED. No exchange access, API keys, Store, SQLite, Paper or live orders.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from moex_intelligence.crypto.offline_ohlcv import evaluate_local_ohlcv
from moex_intelligence.crypto.market import MarketError, SYMBOLS, INTERVALS


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only historical replay of USER-SUPPLIED CSV (source unverified)")
    parser.add_argument("--input", type=Path, required=True,
                        help="UTF-8 CSV: open_time_ms,open,high,low,close,volume")
    parser.add_argument("--symbol", choices=SYMBOLS, required=True)
    parser.add_argument("--timeframe", choices=tuple(INTERVALS.values()), required=True)
    parser.add_argument("--holdout-fraction", type=float, default=.30)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--min-origins", type=int, default=30)
    parser.add_argument("--output", type=Path,
                        help="Optional NEW JSON report; never overwrites existing files")
    args = parser.parse_args(argv)
    report = evaluate_local_ohlcv(
        args.input, args.symbol, args.timeframe,
        holdout_fraction=args.holdout_fraction, stride=args.stride,
        min_required_origins=args.min_origins)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        # "x" makes accidental overwriting of the user's files impossible.
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (MarketError, ValueError, OSError) as exc:
        print(f"OFFLINE CSV EVALUATION UNAVAILABLE: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
