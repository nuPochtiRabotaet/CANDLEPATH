# CandlePath v0.9 — Offline Forecast Evaluation

**Status:** experimental research tool, not part of v1.0 and not an audited trading strategy.

## Why this exists

The Forecast Overlay draws a flat Random Walk median and an EWMA-volatility-derived **nominal 80%** band. It does **not** predict the direction of BTC, ETH or SOL. Before extending it with ML or forecast-driven BUY/SELL, we need measured historical diagnostics and clear separation between offline replay and real predictions published at the time they were made.

## New components

- `moex_intelligence/crypto/forecast_baseline.py`: a pure `ewma_price_envelope()` helper shared by the live baseline and offline replay. The live model version and numerical formula remain unchanged.
- `moex_intelligence/crypto/forecast_evaluation.py`: chronological holdout replay. It strictly validates a gap-free sequence of closed candles, ignores only a trailing incomplete candle, and calculates model values from candles at or before each replay origin.
- `scripts/evaluate_forecast_v09.py`: **read-only** SQLite CLI. It never calls the exchange, places a trade, opens `Store()`, migrates databases, or writes fake historical predictions into `ForecastHistory`.
- `tests/test_forecast_replay_v09.py`: numerical equivalence, chronological/casuality, missing-data, no-publishing and CLI read-only tests.

## How the evaluation works

1. Use an existing chronological sequence of saved BTCUSDT, ETHUSDT or SOLUSDT candles on one supported timeframe.
2. Reserve the final **30% of the sequence** for diagnostic replay; this is a chronological holdout, not a guarantee of an independent external dataset.
3. Start at the boundary immediately before the holdout. Each replay origin sees **only the previous 120 closes**; future candles are not passed to the model.
4. Move origins in steps of **8 candles** (the longest forecast horizon), reducing overlap of scoring windows.
5. For horizons +1, +2, +4, +8 candles, score observed range coverage, mean absolute price error, mean absolute percentage error and average predicted range width.
6. Report the flat Random Walk comparator explicitly. Since this model's median is the last close, **its median MAE equals Random Walk MAE by construction**.
7. Require at least **30 scored origins** for `EVALUATED` diagnostic status; otherwise `INSUFFICIENT` with explicit counts. Neither status means that forecast probabilities are calibrated or the strategy is profitable.

## Run it on your Mac

From the CandlePath repository root, with the project environment installed:

```bash
python scripts/evaluate_forecast_v09.py --symbol BTCUSDT --timeframe 15
```

The script uses the configured `MOEX_DATA_DIR/crypto-v08.sqlite3` by default. To point at an existing copy:

```bash
python scripts/evaluate_forecast_v09.py --database /path/to/crypto-v08.sqlite3 --symbol ETHUSDT --timeframe 60
```

Output: machine-readable JSON. Each result includes the evaluation period, number of origins, exact observed horizon count, empirical coverage, mean absolute error, mean absolute percentage error, width of the uncertainty interval, and nominal coverage. It **does not** turn simulated historical calculations into apparently live, timestamped predictions.

## Acceptance evidence from this development iteration

On the locally staged rc3 source + v0.9 code improvements:

- **43 targeted tests passed**: new replay, existing Forecast/Intelligence and v0.9 hardening tests.
- Broad test collection with unavailable optional dependencies: **348 passed, 11 failed due to absent Streamlit/MCP imports, 4 collection errors**. Not a complete pass.
- The CLI was exercised on a temporary database of 1000 **synthetic** BTCUSDT candles. It returned `HISTORICAL_REPLAY_NOT_LIVE`, 37 evaluated origins at +1/+2/+4/+8.
- Tests confirmed that the SQLite file remains unchanged and both forecast tables stay empty after offline analysis.
- The exact live statistical envelope formula and model version were preserved; the replay model uses the **same pure mathematical function**.

**Still required before release:** clean full test run on the complete GitHub head with dependencies, user Mac/Safari, real Bybit data, data-quality audit, comparison against additional baselines, independent walk-forward analysis on untouched data, and interval calibration. GitHub Actions was already failing before starting jobs in the previous iteration and is not claimed fixed here.

**No BUY/SELL predictions, live trading or autonomous agents were activated.**
