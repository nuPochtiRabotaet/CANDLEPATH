#!/usr/bin/env python3
"""Multi-fold development evaluation with sealed final holdout.

User-provided CSV provenance is not exchange authenticated. No SQLite, Store,
API calls, credentials, retrospective live forecast publication or orders.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from moex_intelligence.crypto.forecast_walkforward import evaluate_purged_walkforward
from moex_intelligence.crypto.offline_ohlcv import read_local_ohlcv
from moex_intelligence.crypto.market import MarketError, SYMBOLS, INTERVALS


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sealed-final multi-fold walk-forward, LOCAL UNVERIFIED CSV only")
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--symbol",choices=SYMBOLS,required=True)
    parser.add_argument("--timeframe",choices=tuple(INTERVALS.values()),required=True)
    parser.add_argument("--folds",type=int,default=3)
    parser.add_argument("--final-fraction",type=float,default=.20)
    parser.add_argument("--embargo-bars",type=int,default=8)
    parser.add_argument("--stride",type=int,default=8)
    parser.add_argument("--min-origins",type=int,default=30)
    parser.add_argument("--output",type=Path,
                        help="Create a NEW JSON report; existing files are never overwritten")
    args=parser.parse_args(argv)

    dataset=read_local_ohlcv(args.input,args.symbol,args.timeframe)
    evaluation=evaluate_purged_walkforward(
        dataset.candles,args.symbol,args.timeframe,folds=args.folds,
        final_fraction=args.final_fraction,embargo_bars=args.embargo_bars,
        stride=args.stride,min_required_origins=args.min_origins)
    result={
        "verification":"LOCAL_CSV_FORMAT_VALIDATED_NOT_EXCHANGE_VERIFIED",
        "source":"USER_SUPPLIED_CSV_UNVERIFIED",
        "market":{"symbol":dataset.symbol,"timeframe":dataset.interval,
                  "file_sha256":dataset.file_sha256,
                  "normalized_sha256":dataset.normalized_sha256,
                  "closed_candles":dataset.row_count},
        "development":evaluation.as_dict(),
        "final_status":"SEALED_UNSCORED",
        "limitations":"Final holdout is not evaluated; research folds are retrospective. "
                      "Model is fixed, untrained and not a proven trading strategy."
    }
    encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    if args.output is not None:
        with args.output.open("x",encoding="utf-8") as stream:
            stream.write(encoded+"\n")
    print(encoded)
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (MarketError,ValueError,OSError) as exc:
        print("WALK-FORWARD RESEARCH UNAVAILABLE: "+str(exc),file=sys.stderr)
        raise SystemExit(2) from None
