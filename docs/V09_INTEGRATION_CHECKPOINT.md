# CandlePath v0.9 — working-branch integration checkpoint

**Status: DEVELOPMENT ONLY. Not a release. Do not merge into `main` yet.**

**Integration date:** 2026-11-02 (UTC). **Working branch:** `develop/v0.9`.
**Stable base:** `main` at `f421d2123b62e8e03a4aa767ad1fd0243842f34e`
at the time of integration inspection. Baseline: MOEX Intelligence v0.8.2-rc3.

## What is already integrated

The `develop/v0.9` history includes the code heads of the **stacked
PRs #2–#20**, including reliability, chart forecast overlays, sealed offline
evaluation, imported user-supplied OHLCV and Spot trade data, paired momentum
and past-volatility research. Further development commits on this branch
introduce research-only causal signal outcome scoring, single-long Paper path
replay, stop/target / time exit, cost assumptions, UTC mark-to-liquidation
risk diagnostics, assumed Spot symbol-rule constraints, and spread/slippage
stress scenarios. These are **offline simulations**, not exchange/live
executions and not verified directional alpha.

The original **PR #1 was not a Git ancestor of develop** even though its
product vision was required. Its unchanged `CANDLE_VISION.md` content has
now been copied into `develop/v0.9` explicitly. This does **not** mark
PR #1 as GitHub-merged; it preserves the content without rewriting history.
Keep historical PRs for review/audit; do not re-merge their code in an
arbitrary order. New work starts from **develop/v0.9**, in short, isolated
branches and integrates back into **develop/v0.9**, not into the middle of
the old PR stack.

## Observed integration checks (prior to this documentation update)

- Commit `360a20e82826a5bce10e1b855d36d18b53471e8a` on
  `develop/v0.9` passed [CI workflow #41334155233](https://github.com/nuPochtiRabotaet/FUCKBINANCEANDMOEX/actions/runs/41334155233)
  on 2026-11-01 UTC: **664 Python tests passed**; Python compile,
  JavaScript syntax, geometry checks and synthetic Chromium browser smoke
  all passed.
- Git compare `main...develop/v0.9` reported **169 commits ahead, zero
  behind** at that checkpoint. The research PR #20 head was a strict Git
  ancestor, 35 commits behind develop.
- Public Bybit probe remained **NOT VERIFIED** (region/platform restriction).
  Successful synthetic CI does not validate real REST/WS or real fills.
- The `main` branch was **not updated** by this integration work.

**Re-check the current head's CI after every commit.** Do not treat the
older 664-test result as proof that new changes passed.

## Next development/release gates

1. **Keep v0.9 Alpha scope small:** one maintainable integration branch and
   short PRs; do not start v1.0 or enable live orders.
2. Run complete GitHub CI on every integrated commit, including browser QA.
   Do not hide failed tests behind selective skipping.
3. Acquire independently verifiable, continuous, multi-regime market history
   for the chosen timeframes; keep the sealed final evaluation holdout
   untouched and mark user-provided data provenance explicitly.
4. Score the exact strategy and execution rules on newly collected data:
   fees, spreads, slippage, gap fills, protective stops, liquidation basis,
   minimum notional/ticks and realistic drawdowns. Show uncertainty and
   insufficient samples instead of announcing profitability.
5. Complete **physical macOS/Safari acceptance**: clean install, launcher,
   graceful stop, data migrations/backups, old Invest isolation without data
   loss, recovery from Mac sleep, multiple-process protection, broker outage.
6. Manually review and test integration of Invest/Crypto behavior and schema;
   no automated migration or alteration of user's private portfolios.
7. Only after gates are recorded, prepare a release candidate and an
   explicitly reviewed PR from `develop/v0.9` to `main`. **Never automatically
   merge this branch because CI is green.**

## Workflow

```bash
git fetch origin
git switch develop/v0.9
git pull --ff-only origin develop/v0.9
python -m pip install -r requirements.in -r requirements-dev.in
python -m pytest -q
```

CI also runs syntax checks, forecast math and Chromium smoke. Real market
access, physical Mac acceptance and profitable strategies are **not**
provided by these tests. Existing raw market-data CSVs are not in Git.

## 2026-11-04 — stage 1: EXIT readiness / Paper parity

Base inspected: `c6ae68a59ab364a33f9f3311d53da1e637db6380` on
`develop/v0.9`. Read the instructions from draft PR #32 at `0987af1`;
did not merge it or the separate crypto-first UI PR #30. Work remains v0.9 Alpha.

**Confirmed P1:** `SignalLifecycle.update()` declared EXIT ACTIONABLE from
gross position notional alone. Fresh quotes with stale/future instrument rules,
off-step/zero/NaN quantity, overselling, a maximum-size violation, or a partial
sale creating dust could still produce ACTIONABLE. The existing Paper preview
already rejected these requests: this was false decision readiness, **not a
demonstrated invalid fill or loss of funds**. Missing rules/minimum failures
also now receive an explicit REJECTED_BY_RISK explanation.

**Bounded fix:** lifecycle reuses the existing read-only `orders.sell_preview`
for the selected quantity, including Decimal costs and inventory checks.
An optional evaluation clock keeps rule/quote age consistent with lifecycle.
No position means CONFIRMED; stale quotes/candles retain the existing waiting
gate. Restored rules can recover to ACTIONABLE without changing signal identity
or confirmation time. A signal never prepares, confirms or executes an order;
the readiness explanation explicitly requires manual Paper Preview → Confirm.
No schema, strategy thresholds, Invest, raw data or live execution changes.

**Audited path:** `Feed.receive/sync` → closed candles → `analysis.analyze`
→ `Store.publish` / `SignalLifecycle.update` (separate provisional path)
→ `ui.terminal` JSON → `trade.js` marker/assistant → explicit
`OrderPreview.prepare/confirm` → transactional `Paper.execute` → ledger;
`PaperMonitor.tick` → `Paper.protect` handles local protective exits.
Existing tests exercise causal prefixes, immutable publication, partial candles,
duplicate/restart events, gaps, preview drift/fees/rules, Decimal accounting,
dust, protective retries and process ownership. Passing tests do not certify
all market failure modes or physical Mac sleep behavior.

**Executed locally (Linux, Python 3.12.14, pytest 9.1.1):**

- Existing focused baseline: **109 passed**.
- New regression before the fix: **11 failed, 4 passed**. Failures include
  false ACTIONABLE cases and the explicit rejection/recovery contract.
- Final focused lifecycle/orders/costs/inventory/Paper-path run: **125 passed**,
  including **16 new tests** in `tests/test_exit_readiness_v09.py`.
- Final `MOEX_DATA_DIR=<temporary directory> python -m pytest -q
  --disable-warnings`: **715 passed, 0 failed, 0 skipped**, 52.41 seconds.
- `python -m compileall -q moex_intelligence tests scripts`: passed.
- Node 24.22.1: `node --check moex_intelligence/components/trade.js`,
  `node scripts/verify_v09_forecast_geometry.js` (**32 checks**), and
  `node scripts/verify_v09_chart_updates.js`: passed.
- `python scripts/verify_v09_forecast_browser.py`: passed with local Chromium
  and Playwright 1.64.1, **synthetic candles only**. Initial browser launch used
  an incorrect executable path; rerun with the actual binary passed.
- Source checkout used GitHub's authenticated file API because native clone
  lacked credentials. All **465 materialized files** were checked against
  the pinned Git blob hashes before edits; unrelated historical documents/images
  were not materialized. Remote commit uses the original tree, preserving them.
  CI results for the final PR SHA must be checked separately.

**Sequential research:** reused/reran the existing Paper-path tests, including
next-open matching-strategy EXIT, gap prices, stop-first ambiguity, costs,
allocation/UTC risk and sealed-holdout invariance. No second backtester or
threshold tuning. The user's 8641-bar OHLCV file is unavailable here; neither
the first 80% nor sealed 20% was examined or scored. The current CLI accepts
raw daily trade CSV, not `open_time_ms,open,high,low,close,volume` directly.
`read_local_ohlcv` and `simulate_paper_paths` can be reused in a later bounded
OHLCV entry-point change. The existing simulator mixes strategies with fixed
priority; attribution of those trades is not an independent per-strategy run.

| Strategy | Completed trades / net P&L / drawdown / win rate / exit reasons / baseline comparison |
| --- | --- |
| Trend Following | NOT EVALUATED — source history unavailable |
| Mean Reversion | NOT EVALUATED — source history unavailable |
| Breakout Detection | NOT EVALUATED — source history unavailable |

No actual Bybit REST/WS verification or profitable-strategy claim in this task.
Physical macOS/Safari, app sleep/resume and real-market acceptance remain open.
The chart still labels a technical EXIT as **SELL**; its tooltip says it is not
an executed trade. This is a confirmed semantic ambiguity, left as the **next
single task**: label technical markers EXIT, reserve Paper SELL for fills, and
verify hover/click/no-position behavior in Chromium without changing strategies.

**Mac reproduction:** fetch and switch to `fix/v09-paper-exit-readiness`, then
run `MOEX_DATA_DIR="$(mktemp -d)" .venv/bin/python -m pytest -q
tests/test_exit_readiness_v09.py` (expected 16 passes). For manual acceptance,
start the app with a separate temporary `MOEX_DATA_DIR`, use Paper only, inspect
a confirmed EXIT with an open position, vary quantity (valid / over balance /
dust), and verify the assistant agrees with Preview. Cancel must leave the
ledger unchanged; explicit confirm must post one fill, including after retry.
Also inspect stale-network status, stop/target and restart recovery separately;
none of these manual Mac steps is claimed as executed by this report.
