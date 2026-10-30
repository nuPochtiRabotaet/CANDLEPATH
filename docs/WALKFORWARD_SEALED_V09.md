# CandlePath v0.9 — Purged walk-forward with sealed final holdout

Status: **research-only**, no live orders, no trained directional model, no claims of profitable forecasting.

## Why the original replay is not enough

A single final-30%-of-history replay can look acceptable while the model behaves differently across market periods. Repeating model selection on the same final block would contaminate its usefulness as a true untouched holdout.

The new tool evaluates a **fixed Random Walk/EWMA baseline** on multiple chronological development folds and reserves a separate, unscored final segment. It reuses the exact existing quantile and interval-scoring maths from `forecast_evaluation.py`; it does not invent or fit an ML model.

## Split contract (default parameters)

- Require strictly validated, complete chronological OHLCV candles (a trailing open candle may be ignored). Local CSV origin is `USER_SUPPLIED_CSV_UNVERIFIED`, even after a pass.
- **20%** of the final closed data is sealed and never passed to any development evaluation. A SHA256 of its normalized OHLCV bytes allows later integrity comparisons. The checksum **does not authenticate exchange provenance**.
- Score **3** sequential development folds, each with independent outcomes contained entirely inside its test interval.
- Use a **purge/embargo boundary of 8 bars** before every fold's first target (the longest forecast horizon). The current fixed EWMA model has **no fitting step**, so this is a documented cutoff for future supervised model development, not pretend training.
- Origins are spaced by **8 candles** so that forward outcome windows do not overlap among consecutive scored origins. Every +1/+2/+4/+8 target must fall inside its own fold.
- Each fold requires at least **30** successful origin points for the `EVALUATED` diagnostic status; smaller folds say `INSUFFICIENT`, not `VALIDATED`.
- The last 20% gets **NO forecast outcomes, coverage, MAE, interval score or trading metric** in this report. No automatic access or hidden option to unseal it.

### Run with authorized historical file

```bash
python scripts/evaluate_walkforward_csv_v09.py --input ~/Downloads/candles.csv --symbol BTCUSDT --timeframe 15
```

Optional *new* report:

```bash
python scripts/evaluate_walkforward_csv_v09.py --input ~/Downloads/candles.csv --symbol BTCUSDT --timeframe 15 --output ~/Downloads/walkforward.json
```

The CLI imports exactly the OHLCV schema documented in `docs/OFFLINE_OHLCV_CSV_V09.md`. Input is read-only, output is create-only, SQLite and live Bybit are never opened, and no retroactive forecasts are published.

The output includes per-fold `train_end_exclusive` (purged boundary), observed validation time interval, actual completed-origin count, normalized interval score, observed interval coverage and below/above misses, plus the sealed final segment's SHA256. No final-holdout model scores.

## Five verification gates

1. **Split math:** exact chronological boundaries, 20% seal, period counts, 8-bar purge cutoff and 8-bar prediction horizons.
2. **Causal separation:** no fold's outcomes overlap another fold's; no fold receives final-holdout candles. Changing every price in the sealed final segment changes only its SHA256, not development scores.
3. **Legacy regression:** original single-holdout results remain bit-for-bit identical when an equivalent explicit window is supplied; invalid ranges are rejected.
4. **No mutation and strict JSON:** CSV is unchanged, existing report/CSV cannot be overwritten, final results never printed, JSON excludes NaN/Infinity and exchange credentials.
5. **Exact-HEAD GitHub CI:** complete Python suite with dependencies, independent Node geometry checks, JavaScript syntax and browser Chromium smoke. A public Bybit probe remains a **separate diagnostic** and does not certify any user-provided CSV.

## Limitations

"Purged" here means a **recorded training-boundary discipline for future learned models** and horizon-contained development scoring. It does not mean our fixed Random Walk model has undergone train/test fitting. Sequential results are descriptive; they do not demonstrate a profitable strategy, calibrated probabilities or valid future BUY/SELL alpha. No real orders or portfolio changes. Actual data provenance, Mac/Safari, Bybit transport and independently decided one-time final assessment remain unresolved release gates.
