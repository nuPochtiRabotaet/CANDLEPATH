# v0.9 Forecast Engine — integrity audit and repair pass

Date: 2026-10-30. Branch: fix/v09-forecast-integrity-audit (stacked on Forecast Overlay PR #3).

**Not a completed v0.9 release, not validated forecasting, not a trading strategy.**

## Ten review dimensions

| # | Review | Finding | Action/status |
|---|---|---|---|
| 1 | Forecast mathematics | Random Walk median is constant by design; EWMA estimates dispersion, not directional alpha | Keep as baseline, clearly labelled EXPERIMENTAL |
| 2 | Time and look-ahead | Only closed candles, future-close cutoff, stale feed checks; synthetic future leakage tests exist | Retain causal guards |
| 3 | Data quality | Gap/duplicate/reordered/invalid and extreme returns fail closed | Retain reject behavior and tests |
| 4 | Data readiness | snapshot.fresh describes quote/trading readiness, not independent kline readiness | **Fixed**: require market_stream_active and candle_data_fresh, independent of spread/quote |
| 5 | Forecast identity | Same symbol/timeframe/last closed candle produces same logical ID but a new created_at on rerun | **Fixed**: idempotent publication preserves original immutable record and timestamp; content mismatches still raise |
| 6 | Persistent outcome journal | Existing schema and ForecastHistory were unused by v0.9 UI | **Integrated**: publish only when experimental baseline ready; reconcile outcomes after new closed-candle cutoff; suppress visible forecast when publication fails |
| 7 | Chart: normal rendering | Vendor Lightweight Charts renders projected median and nominal interval fan, and can toggle visibility | Verified in synthetic Chromium harness; real macOS/Safari pending |
| 8 | Chart: network/empty state | A retained quote with empty candles called timeToCoordinate(undefined), throwing in vendor JS; prior forecast remained drawn | **Reproduced and fixed**; clear all chart/forecast series on empty feed |
| 9 | Regression suite | New targeted publication/readiness tests and independent browser smoke script | Tested below; full regression remains dependency-limited |
| 10 | Empirical usefulness | No held-out calibration, no directional forecast accuracy / backtest after fees, no profitability evidence | **Unresolved by design**; top priority for remaining v0.9 work |

## Verification evidence and limits

- Direct local reproduction before fix: repeated baseline publication with same candle ID and new created_at raised ValueError: Published forecast is immutable. After fix: same record returned unchanged; altered median rejected.
- Direct real Chromium reproduction before JS fix: empty candle feed while quote retained raised a vendor JS TypeError from timeToCoordinate(undefined), and retained the old forecast. After fix: zero forecast/candle points and no page errors in the synthetic test.
- 26 targeted Python tests passed (legacy intelligence + forecast baseline + runtime); Python compileall and JS syntax check passed.
- Local available suite: **332 passed, 11 failed** solely due to missing Streamlit/MCP imports; four additional collection errors from missing Streamlit/MCP. This is not a full-suite pass.
- Standalone synthetic Chromium script (scripts/verify_v09_forecast_browser.py): PASS (initial line, toggle, stale forecast disappearance, empty-data clearing, JS errors). This does not test Streamlit, Bybit network, Safari or physical Mac.
- No actual market price prediction benefit or trading profit has been measured. Treat nominal 80% envelope as **uncalibrated**.
- The local browser run used a locally overlaid source tree; the GitHub changes and their PR still require CI/browser checks after integration.

## Important remaining gaps

1. Full requirements environment, macOS/Safari acceptance, live Bybit REST/WS and reconnection.
2. Robust per-symbol/per-timeframe forecast history/outcome UI and empirical calibration report (coverage, MAE/pinball, Random Walk comparator).
3. Walk-forward / untouched holdout evaluation with reproducible datasets and causal publication timestamps.
4. Test and optimize ledger reconciliation with a large number of historical forecasts.
5. Investigate whether any directional ML model improves held-out outcomes, **before** forecasting BUY/SELL or describing confidence of profit.
6. Complete v0.9 Paper runtime restart/ownership checks and only then move toward v1.0.

## Safety invariant

A stale quote is not automatically stale market candles; an active quote is not proof of current candles. Neither forecast nor chart may hide a data outage behind an outdated projection. Immutable published forecasts must not be overwritten, and their outcomes may be added only from subsequent closed candles. Real trading remains disabled.
