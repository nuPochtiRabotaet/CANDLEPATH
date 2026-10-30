#!/usr/bin/env python3
"""Compare a research momentum median against flat Random Walk on local CSV.

Offline only; source is unverified, final holdout sealed, no exchange, no
SQLite/Store access, no live BUY/SELL and no publication of past forecasts.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from moex_intelligence.crypto.momentum_evaluation import compare_momentum_to_rw
from moex_intelligence.crypto.offline_ohlcv import read_local_ohlcv
from moex_intelligence.crypto.market import INTERVALS,SYMBOLS,MarketError


def main(argv=None):
    parser=argparse.ArgumentParser(description="RESEARCH ONLY: causal candidate vs Random Walk")
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--symbol",choices=SYMBOLS,required=True)
    parser.add_argument("--timeframe",choices=tuple(INTERVALS.values()),required=True)
    parser.add_argument("--folds",type=int,default=3)
    parser.add_argument("--final-fraction",type=float,default=.20)
    parser.add_argument("--output",type=Path,
                        help="Creates a NEW JSON report; never overwrites any file")
    args=parser.parse_args(argv)
    history=read_local_ohlcv(args.input,args.symbol,args.timeframe)
    evaluation=compare_momentum_to_rw(
        history.candles,args.symbol,args.timeframe,
        folds=args.folds,final_fraction=args.final_fraction)
    report={
        "verification":"RESEARCH_ON_UNVERIFIED_USER_CSV",
        "source":"USER_SUPPLIED_CSV_UNVERIFIED",
        "market":{"symbol":args.symbol,"timeframe":args.timeframe,
                  "file_sha256":history.file_sha256,
                  "normalized_sha256":history.normalized_sha256,
                  "candles":history.row_count},
        "comparison":evaluation.as_dict(),
        "live_model_changed":False,
        "live_trading_enabled":False,
    }
    rendered=json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)
    if args.output:
        with args.output.open("x",encoding="utf-8") as stream:
            stream.write(rendered+"\n")
    print(rendered)
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (MarketError,ValueError,OSError) as exc:
        print("DIRECTIONAL RESEARCH UNAVAILABLE: "+str(exc),file=sys.stderr)
        raise SystemExit(2) from None
