#!/usr/bin/env python3
"""Convert locally downloaded SPOT trade history and optionally run v0.9 research.

No API access, orders, credential use, SQLite writes or live forecasts.
The original user-provided trade files are never modified or committed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from moex_intelligence.crypto.market import MarketError, SYMBOLS, INTERVALS
from moex_intelligence.crypto.offline_ohlcv import read_local_ohlcv
from moex_intelligence.crypto.spot_trade_import import (
    read_spot_trade_minutes, segment_spot_trade_minutes, write_spot_candle_segments)
from moex_intelligence.crypto.forecast_walkforward import evaluate_purged_walkforward


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline SPOT trade CSV -> validated candles -> optional sealed research")
    parser.add_argument("--input", type=Path, nargs="+", required=True,
                        help="Daily SYMBOL_YYYY-MM-DD.csv exports (can omit calendar days)")
    parser.add_argument("--symbol", choices=SYMBOLS, required=True)
    parser.add_argument("--timeframes", nargs="+", default=["1", "15"],
                        choices=tuple(INTERVALS.values()))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evaluate", action="store_true",
                        help="Run the actual CandlePath purged walk-forward; final holdout stays SEALED")
    parser.add_argument("--min-origins", type=int, default=30)
    args = parser.parse_args(argv)
    if len(set(args.timeframes)) != len(args.timeframes):
        raise ValueError("Duplicate requested timeframe")
    # Avoid reading millions of source rows a second time for each timeframe.
    minutes, sources = read_spot_trade_minutes(args.input, args.symbol)
    outputs = []
    for timeframe in args.timeframes:
        groups = segment_spot_trade_minutes(minutes, args.symbol, timeframe)
        for output in write_spot_candle_segments(groups, args.output_dir,
                                                  args.symbol, timeframe):
            # Reuse the strict existing v0.9 research importer; reject any
            # invalid timestamp, unclosed candle, float or gap.
            dataset = read_local_ohlcv(output, args.symbol, timeframe)
            result = {
                "file": str(output), "timeframe": timeframe,
                "candles": dataset.row_count,
                "raw_csv_sha256": dataset.file_sha256,
                "normalized_sha256": dataset.normalized_sha256,
                "research_status": "NOT_REQUESTED",
            }
            if args.evaluate:
                try:
                    evaluation = evaluate_purged_walkforward(
                        dataset.candles, args.symbol, timeframe,
                        min_required_origins=args.min_origins)
                except ValueError as exc:
                    result["research_status"] = "INSUFFICIENT_HISTORY"
                    result["reason"] = str(exc)
                else:
                    result["research_status"] = evaluation.status
                    result["development"] = evaluation.as_dict()
                    result["final_status"] = "SEALED_UNSCORED"
            outputs.append(result)
    report = {
        "verification": "USER_SUPPLIED_TRADE_CSV_FORMAT_VALIDATED_NOT_EXCHANGE_VERIFIED",
        "market": "SPOT", "symbol": args.symbol,
        "source": "USER_SUPPLIED_TRADE_CSV_UNVERIFIED",
        "no_api_calls": True, "no_orders": True, "no_live_forecasts": True,
        "missing_minutes": "SPLIT_SEGMENTS_NO_BACKFILL",
        "final_holdout": "UNSCORED_WHEN_EVALUATED",
        "sources": sources, "outputs": outputs,
    }
    # Exclusive create: avoid silent overwrite of an earlier experiment.
    target = args.output_dir / f"{args.symbol}_spot_trade_research.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (MarketError, ValueError, OSError) as exc:
        print("OFFLINE TRADE HISTORY RESEARCH UNAVAILABLE: " + str(exc), file=sys.stderr)
        raise SystemExit(2) from None
