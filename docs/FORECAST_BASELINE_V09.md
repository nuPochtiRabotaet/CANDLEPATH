# v0.9 Forecast Overlay — experimental statistical baseline

Status: **implemented in development branch, NOT a validated prediction system or 1.0 release**.

## What this iteration adds

- \`crypto/forecast_baseline.py\`: bounded (last 120) closed-candle Random Walk reference with EWMA(log-return²) volatility; model-implied nominal 80% lognormal intervals, horizons +1/+2/+4/+8 candles.
- \`crypto/ui.py\`: route the newest real closed-candle history to the baseline **only when live market snapshot is fresh**; if stale, keep the prior UNAVAILABLE state.
- \`components/trade.js\`: dashed reference-price projection and translucent fan **on the existing Lightweight Charts instance**, not a fake candle or a second graph; overlay toggle in \`trade.html\`.
- No API keys, order placement, investment-data deletions, new chart vendor licensing, or live execution.

## Causality & safeguards

- Only consecutive, unique, UTC-aligned, fully closed candles can contribute to the baseline; incomplete candles are ignored.
- A closed candle ending after the observation cutoff makes the forecast unavailable (not silently filtered).
- Last closed candle must be recent (within one interval). Missing data, extreme/invalid returns, insufficient history, stale data, nonfinite prices, incorrect ordering and unsupported markets return UNAVAILABLE with no forecast line.
- Published metadata distinguishes \`data_as_of\` (last used candle close) from creation time and future target boundaries.
- \`ForecastPoint.target_time\` represents the **end** of the future candle. The chart uses candle **opening** timestamps, so points are positioned at \`target_time - interval_seconds\`. Last factual closed candle anchors the overlay.
- The 80% band is a **model-implied nominal interval** and has NOT been empirically calibrated. \`EXPERIMENTAL\` is the only possible nonempty forecast status; this iteration does not claim predictive skill.
- The Random Walk median is constant, NOT a directional trading recommendation. Existing BUY/EXIT indicators are independent and do not use this forecast.

## Explicitly NOT included

- No directional alpha model; no probabilities of rise, fall or earning profit.
- No automatic BUY/SELL decisions from forecast.
- No forecast auto-publication into append-only history; no walk-forward/held-out performance report, and no measured empirical interval coverage.
- No historical replay, autonomous execution, exchange demo, or real orders.
- No real Bybit connection / physical Mac acceptance confirmed in this environment.

## Verification and next acceptance tasks

Local checks on extracted v0.8.2-rc3 source with exact v0.9 branch changes applied:
- 9 new numerical/causality tests passed (future closed candle blocked, unclosed price spike ignored, stale history rejected, duplicates/gaps rejected, stable identity, interval math, baseline constancy).
- 24 focused tests passed (includes prior research and Paper runtime).
- 302 available regression tests passed; **not the complete test suite**, because \`streamlit\` and \`mcp\` are absent in this execution environment.
- \`python -m compileall\` and \`node --check moex_intelligence/components/trade.js\` passed.

Before considering the graphical forecast acceptance complete: install project dependencies, run full pytest, open the terminal on macOS/Safari, check zoom/pan + partial current candle + changing BTC/ETH/SOL / timeframes, reconnect behavior, stale status hiding and consistent interval placement, then begin independent walk-forward evaluation. Do not upgrade to VALIDATED without actual documented calibration evidence.
