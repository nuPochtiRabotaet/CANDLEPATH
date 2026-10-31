# CandlePath v0.9: causal volatility regime diagnostics

**Research only. Not a live signal or permission to trade.**

## Why

A momentum candidate may seem better in aggregate but fail badly whenever
the market's recent volatility expands. This report adds an extra *descriptive*
breakdown of the existing paired Random Walk vs shrunk-momentum test on the
same dev-fold origins, with zero additional predictions, fitted parameters,
threshold optimization or access to final sealed outcomes.

## Strict origin-only labels

The label is computed from the **same 120 closed historical prices** already
supplied to both models at each forecast origin:

- Calculate 119 backward log returns.
- Use the RMS of the 20 **most recent** returns divided by RMS of the **99
  preceding** returns. The thresholds are predetermined: **EXPANDING** if
  ratio >=1.25, **CONTRACTING** if ratio <=0.80, otherwise **STABLE**.
- If historical RMS is zero and recent RMS positive, label EXPANDING; if both
  are zero, STABLE.
- No future price, future volatility, event-time outcome or final holdout is
  used to select the regime. Labels describe observed past volatility change,
  not an ability to forecast future volatility.

## Report and integrity

Each `comparison.folds[i].volatility_regimes` item (in the existing
`scripts/evaluate_momentum_candidate_v09.py` or the direct trade CLI) contains
a regime, horizon, observation count, reference/challenger MAE, candidate MAE
gain %, empirical coverage, directional hit fraction and a
`sample_sufficient` flag. This flag is true only when at least 30 scored
origins **and** 30 nonflat future moves are in that particular stratum. Even
then, these are descriptive sample counts, not statistically independent
observations or evidence of market edge.

**Regime totals must exactly reconcile** to each fold's existing horizon
observations and scores. Each scored origin belongs to exactly one category.
Tests change the sealed last 20% prices and require *all* development
regime scores to remain identical. A short or missing segment stays explicitly
insufficient; it is never padded, extrapolated, or counted as an evaluated fold.

## How to interpret results

A positive gain in EXPANDING and a negative gain in CONTRACTING is a
hypothesis worth testing on **new** days; it is *not* an invitation to choose
model/threshold parameters after seeing the same scores. Do not select the
best-performing regime or model on these folds and then call the same period
out-of-sample. Preserve the sealed final 20%, collect new independent
periods, and only after freezing a decision rule evaluate execution costs,
spread, slippage and strategy drawdowns.

To run the direct offline trade CLI with additional regime fields:

```bash
python scripts/evaluate_spot_trades_csv_v09.py \
  --input ~/Downloads/BTCUSDT_2026-10-25.csv \
          ~/Downloads/BTCUSDT_2026-10-26.csv \
          ~/Downloads/BTCUSDT_2026-10-27.csv \
          ~/Downloads/BTCUSDT_2026-10-29.csv \
  --symbol BTCUSDT --timeframes 1 15 \
  --output-dir ~/Desktop/candlepath-regimes-new \
  --evaluate --compare-momentum
```

Source labels remain **USER_SUPPLIED_TRADE_CSV_UNVERIFIED**. No live API,
SQLite account data, credentials, user trading or automatic model promotion.
The source CSVs themselves are not committed to GitHub.
