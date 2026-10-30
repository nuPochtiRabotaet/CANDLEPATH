# CandlePath v0.9 — Forecast math-to-chart alignment

Status: experimental development, not a finished release or profitable trading strategy.

## Confirmed issue

ForecastPoint.target_time is the predicted future candle CLOSE boundary (epoch seconds). Candlesticks are drawn at their OPEN times. The old chart anchored the line at the last real candle's OPEN and shifted predicted targets to target_time-minus-interval, making the entire projected price curve appear **one candle earlier** than its actual meaning. This was a presentation bug, not proof that the Python prediction formula was wrong.

Correct geometry:

- Last real closed bar opens at T and ends at data_as_of = T + STEP.
- The actual observed anchor on the projection is at data_as_of (and at the last closed price).
- The +1/+2/+4/+8 predictions are at data_as_of + horizon * STEP, with no subtract-one-step shift.
- Lightweight Charts has an ordinal time axis. Add a whitespace-only hidden series for the intervening future timestamps so sparse forecast horizons occupy **1:1:2:4** proportional horizontal gaps. That series contains *no prices*: it never fabricates observations.
- The shaded fan and median line must share one strictly validated projection, not independently parse or shift forecast points.

## Safety/fail-closed contract

Accept EXPERIMENTAL projections only when the symbol, timeframe, data_as_of, current closed-candle anchor and fresh candle stream agree; all future times must be integer, increasing, UTC interval-aligned and bounded; all quantiles must be positive finite numbers with lower <= median <= upper. Otherwise hide BOTH median and fan, clear prior future timestamps, and explain why. On an empty candle feed, clear the whole projection. No autonomous decisions, real orders, data migrations, investment ledger modifications or live-model version changes.

## Five independent verification passes

1. Python→JavaScript: actual Python Forecast values must survive JSON/JS without altered quantile prices or target timestamps (BTC, ETH, SOL).
2. Numerical validation: Node pure-geometry tests reject mismatched markets, stale data, invalid prices, inverted bounds, duplicate and unaligned horizon times, and excessive projection length.
3. Chromium visual geometry: end-boundary positions exactly match the model; +1, +2, +4, +8 points have correct horizontal spacing with the vendored Lightweight Charts; a trailing open candle cannot shift the prediction.
4. Browser failure/recovery: invalidity, toggle, no candles and same-version data restoration must not leave stale forecast, band or volume on screen or cause JavaScript errors.
5. Exact GitHub head: the entire existing Python suite, Python compilation, Node math tests, JS syntax check, and Chromium smoke must all pass. Do not claim completion based on earlier heads or a selected local subset.

## Unverified release gates

Real Bybit network data, actual Mac/Safari, interval calibration, directional predictive skill and actual market outcomes remain separate tasks. Do not merge this stacked PR to main until prior v0.9 PRs are reviewed in sequence.
