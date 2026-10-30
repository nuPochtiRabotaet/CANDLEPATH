# CandlePath v0.9 — Safe local OHLCV historical replay

**Status: experimental, no live trading or orders.** This is a fallback for legally obtained historical candle files when public exchange REST is unavailable. It does NOT verify exchange authenticity.

## Required input (strict CSV)

A UTF-8 CSV file with exactly these six columns, in this order:

```csv
open_time_ms,open,high,low,close,volume
1793304000000,100,101,99,100.5,4.5
1793304900000,100.5,102,100,101,4.2
```

The two example lines only demonstrate the format and are **not sufficient for a meaningful evaluation**. Timestamps must represent UTC candle **opening** times as epoch milliseconds. Rows must be strictly increasing, consecutive, on a supported timeframe grid and already completely closed as of the time of evaluation. Price/volume must be finite and internally consistent. No partial candles, gaps, duplicates, NaN/Infinity or malformed timestamps are accepted. It is not a flexible automatic format detector, intentionally: ambiguous data would silently corrupt forecast statistics.

Supported spot-like symbols: BTCUSDT, ETHUSDT, SOLUSDT. Intervals: 1, 5, 15, 30, 60, 240, D.

## Run from the repository root

```bash
python scripts/evaluate_ohlcv_csv_v09.py --input ~/Downloads/candles.csv --symbol BTCUSDT --timeframe 15
```

To create a **new** report file (existing reports are never overwritten):

```bash
python scripts/evaluate_ohlcv_csv_v09.py --input ~/Downloads/candles.csv --symbol BTCUSDT --timeframe 15 --output ~/Downloads/candlepath-evaluation.json
```

The script reads input only, does not initialize Store or open the user SQLite database, does not access an exchange or API key, and never publishes retroactive "live predictions". It displays the existing causal chronological 30% holdout metrics (coverage, MAE/MAPE, interval score, upper/lower misses, origin count). Small files may produce INSUFFICIENT status: do not mistake that for evaluation success.

The report explicitly contains:
- `verification: LOCAL_FILE_FORMAT_VALIDATED_NOT_MARKET_VERIFIED`
- `market.source: USER_SUPPLIED_CSV_UNVERIFIED`
- `market.verified_bybit_http: false`
- source file SHA256 and normalized OHLCV SHA256, first/last UTC timestamps and row count

These digests establish input reproducibility but **cannot prove who created the CSV or whether the prices came from Bybit**. No pretense of real exchange access, model skill, calibrated probability or trading profitability.

## Five independent verification gates

1. **Ingestion:** strict headers, UTF-8, UTC epoch milliseconds, bounded file size/rows, OHLCV validation.
2. **Time and causality:** closed candles only, consecutive timestamps, reject gaps/future/partial/corrupted data.
3. **Mathematics/provenance:** the same pure Random Walk+EWMA evaluation from v0.9, strict finite JSON, raw and normalized SHA256; unverified source label always retained.
4. **Nonmutation:** SHA of input unchanged, no portfolio database initialization or writes, report output is create-only, even when a user accidentally sets output equal to input.
5. **Full GitHub CI:** all Python, Node geometry, JS syntax and Chromium on the exact PR head must pass. Local fixtures are synthetic and **not** claimed as verified live market data.

## Remaining roadmap

Next: purged chronological multi-fold walk-forward and truly untouched final evaluation, then compare model candidates against Random Walk, with proper calibration analysis. Separate release gates: Mac/Safari, actual Bybit network access where authorized, real-time transport and full Paper runtime resilience. Real orders stay disabled; changes remain stacked on open v0.9 PRs, not main.
