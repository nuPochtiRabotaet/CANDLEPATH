# CandlePath v0.9 — safe published-forecast scorecard

**Context.** Historical replay already uses finite-safe Decimal arithmetic. But the **actual prospective published forecast** scorecard used a raw float conversion for average percentage error and formatted it with a numeric format specifier in Streamlit. A perfectly valid extremely small future price could turn the mean into `Infinity`; a future null metric would crash the UI on `:.2f`. Malformed immutable SQLite outcomes could also crash Decimal math without a useful message.

This iteration does **not** change the forecast model or its immutable journal. It fixes the *reading and presentation layer*.

## Changes

- Compute outcome percentage errors in Decimal, preserve count/coverage and the original normal-range precision.
- An error that cannot be represented as a finite Python float becomes **JSON null / Python None**, not Infinity or fabricated zero.
- Include `unrepresentable_percentage_errors` count for transparency, while retaining existing `forecasts`, `horizons`, `observations`, `empirical_coverage`, `mean_absolute_pct_error`, `sufficient_sample` keys.
- Validate stored actual, median and covered flag when building the scorecard. Invalid/NaN/nonpositive/corrupt values raise a clear ValueError and suppress potentially misleading statistics. No records are overwritten.
- Streamlit uses `format_forecast_scorecard_pct()`: normal numeric values get two decimals and `%`; None/nonfinite values display **недоступно (слишком большая ошибка)** with an explicit count.

## Five rechecks

1. **Exact math:** 100 forecast median and observed 105 gives a 4.7619% error and the existing coverage result.
2. **Extreme numeric:** valid observed 1e-320 produces a very large finite Decimal error, converts to None rather than Infinity and preserves the observation in coverage.
3. **Integrity:** manually injected malformed/NaN/negative immutable outcomes fail closed. Earlier published records and existing outcome bytes stay unchanged.
4. **UI safety:** percentage formatter never raises on None, NaN, Infinity, strings or other unsupported values. Existing Streamlit scorecard cache remains compatible (new counter accessed via get()).
5. **Exact GitHub CI:** full pytest with installed dependencies, JS syntax, Node chart geometry and Chromium smoke must all pass on the final PR head. A blocked public Bybit probe remains **separate and unverified**.

**No change** to Invest, Paper order logic, exchange permissions, SQLite schema, live trading or actual Bybit connectivity. A scorecard is descriptive, not proof of valid predictive confidence or profitability. Review after PR #12 in the stacked v0.9 branch.
