# CandlePath v0.9 — Ten-pass Hardening Report
Date: 2026-10-30. Branch: audit/v09-ten-pass-hardening (stacked on PR #4).

Status: development code reviewed, **NOT a completed v0.9 release**, validated prediction, or trading strategy.

## Ten repeatable review → repair → retest passes

| Pass | Check | Outcome and regression proof |
| --- | --- | --- |
| 1 | Reproducible testing | Added a clean-install CI workflow and local macOS verification command; GitHub Actions currently fails before scheduling jobs. |
| 2 | Temporal correctness | Rechecked closed-candle cutoffs and +1/+2/+4/+8 target boundaries; future data rejected, current partial candle ignored (test_06). |
| 3 | Input integrity | Reject malformed candle records, bogus closed flags, invalid prices, gaps (test_05 and prior baseline tests). |
| 4 | Numerical safety | Reproduced math.log(b/a) domain error for extreme positive prices and TypeError for nonnumeric observation time; now fail closed with UNAVAILABLE (tests_03/04). |
| 5 | Data readiness | Forecast now has a separate candle-stream readiness flag instead of depending on trading quote/bid-ask freshness; repaired three compatibility regressions discovered by full-suite run (tests_01/02). |
| 6 | Publication immutability | Same-ID repeat publication with new created_at returns the original immutable record, but changed forecast quantities are still rejected (tests_07/08). |
| 7 | Outcomes and explainability | Revalidated closed-candle settlement, restart safety and duplicate prevention; added an on-demand scorecard for empirical coverage and mean absolute percentage error (test_09). |
| 8 | SQLite scale | Reconciliation skips already settled horizons and history uses two SQL selects rather than N+1; exercised 40 forecasts in test_10 and 1000 in local benchmark. |
| 9 | Browser recovery | Fixed hidden r.version reset bug that prevented volume/indicator series recovering after an empty candle feed; Chromium synthetic render→empty→recover test passed with zero JS page errors. |
| 10 | Full regression disclosure | Local overlay 333 passed, 11 failed only because Streamlit/MCP are not installed, and 4 import-time collection errors. Full verification remains outstanding. |

## Observed verification evidence, precisely scoped

Tested on the v0.8.2-rc3 source archive with locally mirrored forecast, intelligence and market modifications; **not a pristine checkout of the complete stacked GitHub head**.

- Focused legacy-intelligence and ten-pass synthetic verification: **27 passed**.
- First broad pytest: 330 passed, 14 failed, 4 collection errors. Three failures exposed an actual regression in partially initialized Feed objects.
- Repeated broad pytest after repair: **333 passed, 11 dependency-import failures and 4 dependency collection errors**, not a full pass.
- Headless Chromium local synthetic integration: 120 real-shaped synthetic candle bars, 120 volume bars, 5 projection points; all empty on outage; all 120/120/5 returned on recovery, zero observed JavaScript page errors.
- Temporary SQLite benchmark: 1000 synthetic published forecasts; first settlement about 0.015s; already settled rerun about 0.004s; scorecard read about 0.010s. Hardware/fixture-specific measurement, not an SLA.
- GitHub Actions workflow was created but observed runs failed **before any jobs were scheduled** (no job/test logs). This is a BLOCKER, not a test pass. Validate repository Actions permissions/billing or YAML configuration.
- Live Bybit, actual Streamlit environment, user macOS/Safari, prolonged background Paper runtime and model calibration are **unverified**.

## What is still missing

1. Full verified suite on actual branch with all pinned dependencies; GitHub-hosted CI or local Mac logs.
2. Browser and Bybit REST+WebSocket acceptance on Mac/Safari, including reconnect and sleep/wake.
3. Independent chronological walk-forward/untouched holdout model evaluation and proper empirical calibration.
4. Baseline comparisons and costs/slippage-aware trading evaluation before forecast-driven BUY/SELL.
5. Robust background worker recovery before any further execution development.

The flat Random Walk median and nominal EWMA envelope **do not predict direction with a proven edge** and must remain EXPERIMENTAL. The empirical scorecard counts **observed** forecast outcomes; it is not a profitability claim. Real execution remains disabled.

Run full checks locally on an installed environment with:

    bash scripts/verify_v09_local.command

The script uses a temporary isolated database and clearly reports optional JavaScript/browser checks when unavailable.

**Ten hardening cycles were carried out. Perfection and final v0.9 acceptance are not claimed.**