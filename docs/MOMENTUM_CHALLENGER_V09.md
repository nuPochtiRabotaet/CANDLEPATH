# CandlePath v0.9 — causal momentum challenger (RESEARCH ONLY)

**This is NOT a live predictive model, validated directional alpha, BUY/SELL generator, or trading system.** It adds one deliberately simple *fixed-parameter candidate* and an honest, matched comparison against the existing flat Random Walk + EWMA baseline on development folds. The previously sealed final holdout is not scored.

## Mathematical definition

At each origin, use only the preceding 60–120 **fully closed** prices. For each historical pair calculate its log return (r_t=\log(P_t)-\log(P_{t-1})). Reject nonpositive/nonfinite inputs, returns of magnitude at least 0.7, malformed or unordered horizons, and any nonfinite projected price.

Set EWMA decay to 0.94 (same as the current Random Walk volatility baseline). Let (\bar r_t) be the exponentially weighted mean return and (\sigma_t=\sqrt{EWMA(r_t^2)}). The candidate's per-candle drift is **fixed** in code:

`mu = clamp(0.25 * EWMA_mean_return, -0.25 * sigma, +0.25 * sigma)`

For a future horizon of h closed candles:

- Median = (P_t \exp(h \mu))
- Lower = median × (\exp(-1.2815515655\,\sigma\sqrt h))
- Upper = median × (\exp(+1.2815515655\,\sigma\sqrt h))

The 80% interval is purely **nominal and uncalibrated**. The model can be wrong about direction; its shrinkage factor is not optimized or advertised as an edge. No hyperparameters are selected using evaluation data.

## Paired comparison

The evaluator first obtains the existing three-fold *purged chronological development split* from `forecast_walkforward.py`. For every origin, it passes **the exact same past closes** to the flat Random Walk model and the momentum candidate, and scores **the exact same future price** for both on +1/+2/+4/+8 horizons.

Reported per-fold and per-horizon:
- Number of paired observations and skipped origins
- Random Walk and challenger median MAE
- Candidate MAE gain % (may be negative; null when Random Walk error is zero)
- Random Walk and challenger normalized 80% interval scores (penalty for both width and misses)
- Empirical interval coverage for both
- Candidate direction hit rate on *all nonflat realized moves*. Flat candidate calls count as misses and participation count is reported separately.

**No model is fitted or updated by future labels**. The final 20% is fingerprinted but **never used as model input or scored**. Changing all prices in that final block must leave every development score unchanged. Apparent gain on synthetic trends is only a unit test, never proof of future profits.

## Usage with locally supplied candles

The same strict, *unverified source* CSV schema applies, documented in `docs/OFFLINE_OHLCV_CSV_V09.md`.

```bash
python scripts/evaluate_momentum_candidate_v09.py --input ~/Downloads/candles.csv --symbol BTCUSDT --timeframe 15
```

Optional `--output ~/Downloads/momentum.json` creates a **new** report only and never overwrites a file. The program never opens Store/SQLite, connects to Bybit, publishes historical "live" forecasts, places any Paper/Live trade or changes any live Forecast Overlay. Source identity is always `USER_SUPPLIED_CSV_UNVERIFIED`.

## Five verification gates

1. **Mathematics:** flat series yields a flat prediction, trending series a correctly bounded finite drift, invalid inputs fail closed.
2. **Matched comparison:** candidate and Random Walk use identical origins, closed inputs, future outcomes and compatible error/interval-score formulas. No optimistic missing-outcome filtering.
3. **Causal isolation:** mutating the entire sealed final segment cannot change any development comparison; first origin's input excludes the next actual candle.
4. **Nonmutation and reporting:** strict finite JSON, unverified-source label, new-only report output, no SQLite/credentials/real orders; exact version and negative as well as positive gains must be representable.
5. **Full exact-HEAD CI:** pytest, Python compilation, Node math/geometry, JS syntax, Chromium smoke. A region-blocked Bybit probe remains explicitly **unverified**.

## Next research gate

Use provenance-checked market history when available. Compare metrics in trending, flat and high-volatility regimes and record actual prospective forecast outcomes. Only consider model promotion after independent, untouched final evaluation plus separate trading-cost-aware backtesting. Do **not** promote this candidate into live chart, Paper decisions or real execution based on synthetic data.
