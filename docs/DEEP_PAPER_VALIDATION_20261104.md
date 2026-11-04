# Deep Paper validation — v0.9, 2026-11-04

Verdict: **NOT READY for unqualified full manual Paper acceptance**. The ledger
checks below pass, but physical Mac/Safari/outage acceptance remains missing;
reviewed draft improvements are not yet in develop. No profitable edge found.

Base: develop `c6ae68a`. Reviewed Issue #31 and PRs #33–37; #36 is a closed,
unmerged integration QA tree, not the production baseline. No merges performed.
UI work and Issue #38 intentionally excluded.

## Confirmed and corrected

`_closed_exit` timestamped intrabar STOP/TARGET outcomes at the bar OPEN, before
their high/low range was available. Three new regressions failed on original
code. These exits now report bar-close availability and explicit precision,
with the bar-open time retained separately. NEXT_OPEN exits retain their time.
This repairs temporal reporting, not evidence of future leakage into entry
decisions: fills, prices, costs and P&L are unchanged. Research version is 4.
No published records or user ledger are rewritten.

Optional fixed strategy filtering in the existing `simulate_paper_paths` permits
independent single-long runs; default mixed-priority behavior remains unchanged.
No new execution simulator or optimized trading parameters.

## Reproducible data study

`scripts/deep_paper_validation_v09.py INPUT OUTPUT` reads the uploaded
BTCUSDT_spot_5m.csv copy, **8640** rows (not the claimed Mac 8641).
SHA256 and complete aggregate results: `research/deep_paper_20261104.json`.
Source remains USER_SUPPLIED_CSV_UNVERIFIED. Six-column Mac format is also
accepted. Raw CSV is not committed. Final 1728 rows are not scored; existing
sealed walk-forward only evaluates development folds ending before row 6912.
There are three independently capitalized 10000-USDT folds per strategy.
Sum of fold P&L is not a compounded portfolio return. Max DD is worst fold's
sampled OPEN/CLOSE liquidation drawdown, not continuous intrabar drawdown.

| Strategy | Trades | Net USDT | Win rate | Expectancy USDT | PF | Max DD % |
|---|---:|---:|---:|---:|---:|---:|
| Trend Following |58|-554.56|6.90%|-9.56|0.019|2.29|
| Mean Reversion |15|-105.57|6.67%|-7.04|0.003|0.49|
| Breakout Detection |109|-1035.98|10.09%|-9.50|0.042|4.15|

Standard assumptions: fee 10 bps + slippage 5 bps per side, full spread 4 bps;
25% allocation cap, .75% initial risk, existing 16-bar timeout and UTC guards.
Even LOW costs (5/2 bps) remain negative: -326.59/-45.81/-613.04 USDT.
STRESS (20/10 bps): -976.42/-217.09/-1811.30. No parameter selection based
on these outcomes. Exit reasons and individual-fold returns are in JSON.
Cash benchmark: zero. Passive 25%-allocation buy/hold with identical folds and
standard costs: -160.86 USDT total; it has no stop and is **not risk-matched**.
Mean Reversion loses less than passive here, but 15 trades establish no edge.
These are descriptive outcomes, not calibrated confidence or independent samples.
One instrument/month, optimistic threshold fills, assumed spread and missing
historical lot rules preclude economic certification or extrapolation.

## Verification / remaining gates

- Targeted lifecycle/ledger scope: 117 tests passed, including six new tests.
- Adversarial SQLite trigger failure rolls back Confirm, order and balance;
  retry after repair posts once. Concurrent .75 + .75 SELL against 1 unit
  gives one Filled/one Rejected; final close reconciles cash and realized P&L.
- Existing protective retry, dust, cost, process-lock and Paper-path tests pass.
- JS syntax, 32 geometry checks, chart contract and synthetic Chromium pass.
- Full local Python: **705 passed, 0 failed, 0 skipped** (49.55 s).
  Final-head CI results are recorded in the PR after execution.
- No physical Mac/Safari, sleep/resume or real WebSocket acceptance executed.
  Linux/Chromium does not substitute for them. No live or autonomous operations.

Top risks: (1) local protective worker unavailable during sleep/outage,
(2) unmerged/incomplete physical integration acceptance,
(3) negative sampled economics plus uncertain fills/costs and insufficient data.
