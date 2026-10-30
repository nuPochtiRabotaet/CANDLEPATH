# CandlePath v0.9 — Interval quality (five-check protocol)

Status: EXPERIMENTAL offline research. No trading advice, no validated directional model, no auto-orders.

## Why raw coverage can mislead

A nominal 80% prediction interval could achieve 100% historical coverage simply by expanding its boundaries until it includes every observed price. Measuring only coverage rewards overwide, uninformative ranges. This iteration adds a **proper prediction-interval (Winkler) score** to the offline historical replay. It does NOT change the existing live Random Walk + EWMA model.

For a central nominal 80% interval [L, U], observed future price Y, alpha = 0.2:

    interval_score = (U-L) + 10 * max(L-Y,0) + 10 * max(Y-U,0)

Reported mean_interval_score_pct normalizes each interval score by the **forecast median (anchor price)**, then multiplies by 100. Smaller is preferable when evaluated on the same outcomes and horizons. The score penalizes both excessive interval width and misses. It is not a profit estimate or evidence of model superiority.

New metrics per evaluated horizon:
- below_interval: number of future closes below L
- above_interval: number of future closes above U
- calibration_gap_percentage_points: 100 × (observed coverage - nominal 0.8), descriptive and signed
- mean_interval_score_pct: average price-normalized interval score, or JSON null if unrepresentable as finite float

Existing immutable ForecastHistory and database schema remain untouched. Only offline replay results receive new fields. Decimal accumulation avoids JSON Infinity/NaN.

## Five independent verification layers

1. **Mathematical formula.** With bounds [99, 101] and median 100, a future close of 100 scores 2%; a future close of 103 or 97 scores 22% (width 2 plus 10 times the miss of 2). Check tail classifications and coverage identity.
2. **Boundary and numeric safety.** Constant-price data has zero score and width; high observed coverage alone does NOT mean calibrated probabilities. Extreme prices cannot cause NaN/Infinity in strict JSON.
3. **Causal replay.** Mutating future candles must not alter the model inputs at the first historical origin. Strict existing gap/closed-candle/chronology/OHLCV validation is preserved.
4. **Read-only and compatibility.** The CLI exposes all new fields. A temporary SQLite database has the same SHA256 before and after evaluation and no new historical "live" forecasts. The live model and version are unchanged.
5. **Complete CI gate.** Full branch pytest with installed dependencies, Python compilation, JS syntax, and real Chromium synthetic forecast-overlay smoke must all pass on the actual PR head. Partial local tests alone are insufficient.

## Remaining limitations

The results are descriptive historical statistics, not validation of a winning crypto strategy. We still need actual Bybit data, prospective saved forecasts, regime-specific calibration, a genuine untouched holdout, and physical macOS/Safari acceptance. No real orders are activated. Review this stacked branch after PR #7 before merging.
