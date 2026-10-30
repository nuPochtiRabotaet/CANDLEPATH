#!/usr/bin/env python3
"""Evaluate CandlePath's EXPERIMENTAL Random Walk envelope on stored candles.

This is read-only historical replay and does NOT create 'live' forecasts.
Run from the repository root:
    python scripts/evaluate_forecast_v09.py --symbol BTCUSDT --timeframe 15
Optionally supply --database PATH, otherwise uses the configured crypto ledger.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

# Running as 'python scripts/...' puts scripts/, not repo root, on sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from moex_intelligence.config import Settings
from moex_intelligence.crypto.forecast_evaluation import evaluate_historical_baseline
from moex_intelligence.crypto.market import INTERVALS, SYMBOLS


def load_candles_readonly(dbpath: Path, symbol: str, timeframe: str):
    """Access an existing DB using SQLite mode=ro; never create or migrate."""
    path = dbpath.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Crypto database does not exist: {path}')
    uri = path.as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True, timeout=5) as conn:
        conn.execute('PRAGMA query_only=ON')
        items = conn.execute(
            'SELECT body FROM candles WHERE symbol=? AND interval=? ORDER BY time',
            (symbol, timeframe)).fetchall()
    return [json.loads(item[0]) for item in items]


def main(argv=None):
    parser = argparse.ArgumentParser(description='OFFLINE experimental baseline replay; NEVER live forecast publication')
    parser.add_argument('--symbol', choices=SYMBOLS, required=True)
    parser.add_argument('--timeframe', choices=tuple(INTERVALS.values()), required=True)
    parser.add_argument('--database', type=Path, default=None,
                        help='Existing crypto-v08.sqlite3 (read-only); defaults to MOEX_DATA_DIR')
    parser.add_argument('--holdout-fraction', type=float, default=0.30)
    parser.add_argument('--stride', type=int, default=8)
    parser.add_argument('--min-origins', type=int, default=30)
    args = parser.parse_args(argv)
    dbpath = args.database or Settings.from_env().data_dir / 'crypto-v08.sqlite3'
    rows = load_candles_readonly(dbpath, args.symbol, args.timeframe)
    report = evaluate_historical_baseline(rows, args.symbol, args.timeframe,
                                           holdout_fraction=args.holdout_fraction,
                                           stride=args.stride,
                                           min_required_origins=args.min_origins)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        print(f'Forecast evaluation unavailable: {exc}', file=sys.stderr)
        raise SystemExit(2) from None
