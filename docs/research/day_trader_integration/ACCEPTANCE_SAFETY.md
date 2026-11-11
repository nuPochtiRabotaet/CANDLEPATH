# Final acceptance — safety trace and evidence boundaries

Reviewed base: `a0ca13d26cee204bf152ee20ef5bc8b1e7969e42`.
Initial feature HEAD: `8071985230a08a53d5a8f1674a38bab6beabd9e6`.
Draft PR: https://github.com/nuPochtiRabotaet/CANDLEPATH/pull/51
Final candidate: the commit containing this document; resolve with `git rev-parse HEAD`.
The exact final SHA, CI run/job and readiness matrix are recorded in PR #51's
acceptance section after the run completes. Do not transfer a PASS to another SHA.

## Findings and fixes

1. First remote run `43073682338` on the initial feature SHA: Python 919 passed
   in 49.46s, compilation/JS/Forecast geometry/chart contracts and Forecast/Coliseum
   Chromium passed; Day Trader browser FAILED at the immediate dataframe count.
   The caption arrives before Streamlit finishes rendering the table. The browser
   regression now requires the table to become visible within its existing 30s
   timeout; missing/hidden tables still fail. No retry or assertion removal.
   Local browser reproduction was BLOCKED: Chromium's process-singleton socket
   failed with `Operation not permitted`; no sandbox policy was changed.
2. CI's default PR checkout tested a merge ref, not the requested head. Checkout
   now pins `github.event.pull_request.head.sha` and logs `git rev-parse HEAD`.
3. CI installed `.in` files, leaving transitive app dependencies unresolved across
   runs. It now installs the existing universal `requirements-dev.txt` with hashes;
   no dependency/lock versions changed. A JUnit gate rejects skipped/expected-fail,
   failure/error or empty reports and requires both risk/scan test modules.
   Full pytest has no selection filter; no old tests were removed or disabled.
4. Adversarial live-feed audit reproduced acceptance of a premature `closed=True`
   candle and future candle timestamps through WS, REST and saved cache. Before
   the fix: **7 failed, 1 passed** among eight new regression cases. Live-only
   time validation now runs before WS publication/persistence, REST publication,
   and starting a feed from cache. A closed bar must have ended locally; no bar
   may start in the future. Exact-boundary closure/current forming bars remain
   valid. Invalid persisted data is retained, not rewritten/deleted. An incorrect
   system clock/source fails closed and requires diagnosis. Pure historical
   analysis remains deterministic and uses its separate explicit cutoff.

## Critical chain

| Boundary / invariant | Source and regression evidence | Scope / remaining limitation |
|---|---|---|
| Public market data → closed candles | `market.py`: strict Boolean confirmation, immutable/gap validation, new live time gate, durable write before publish. `test_market_feed_atomic_v09.py`, `test_crypto_v08.py` | Public transport only; source availability and host clock still need physical acceptance. |
| Closed candles → analysis/signals | `analysis.py` skips forming bars for confirmed signals; indicator prefix invariance. `test_crypto_v08.py::test_open_candle_no_confirmation`, `::test_causal_prefix_stream_restart` | No proven predictive edge. A forming overlay is not confirmation. |
| Cutoff/availability → scan | `signal_scan.py` filters future/forming/not-yet-available bars before existing analyzer; validates continuity and stale/sample exclusions. `test_signal_scan_v09.py` | Receipt times missing from a snapshot are explicitly unknown, not retrospectively invented; scan is not execution authorization. |
| Signals → lifecycle | `lifecycle.py` records first confirmation/availability, rejects future signal timestamps, expires historical/stale opportunities; EXIT without holding creates no short/fill. `test_signal_lifecycle_v081.py`, `test_exit_readiness_v09.py` | BUY/EXIT/ACTIONABLE remain separate from a trade. |
| Lifecycle/manual input → Paper Preview | `risk.py`, `orders.py`: current rules/quotes, Decimal caps/costs, exchange maximum, risk profile preserved. `test_risk_explainability_v09.py`, `test_order_preview_v082.py`, `test_crypto_v08.py` | Recommendation requires a new Preview and can fail other risk gates. Manual Paper is a user decision; it need not be linked to a signal. |
| Preview → Confirm | Persisted payload/UUID, owner, explicit consent, 30s TTL, account/profile/rule revision, quote/spread drift and fresh risk check. UI collects current snapshots. `test_order_preview_v082.py::test_immutable_payload_and_idempotent_prepare`, `::test_revalidation` | Preview is an estimate; permitted current fill can differ within checked drift. |
| Confirm → Paper ledger | `BEGIN IMMEDIATE`, duplicate UUID returns existing order, guard/posting share transaction, rollback on storage error. Concurrent confirmations/restart and concurrent exits tested. `test_order_preview_v082.py::test_concurrent_confirmation_restart`, `test_paper_path_availability_v09.py` | Virtual fills only; not exchange fill capability. |
| Scanner → execution | No order/preview/executor imports or calls in `signal_scan.py`; explicit `execution_authorized=False`. New panel only invokes scan and displays result. Tests assert false authorization and input immutability. | A historical BUY/EXIT is never a fill. |
| Risk profile | No changes to `PROFILE` or other gate thresholds; daily/weekly loss, position/occupied/aggregate caps and stale/no-rules checks retained. New live candle gate only tightens data validity. | Stops are local and inactive while asleep/off; gaps/fees/residue remain assumptions. |
| Invest/user data | Diff inspection: no changes to legacy Invest storage, imports, portfolio/migration code. Tests use isolated temp storage; no user DB was supplied/opened. Workspace/legacy tests retained. | Does not certify an unseen real portfolio; Mac acceptance uses only clean data. |
| Real executor | `paper.LiveExecutionDisabled.submit/reconcile` raise; public market client is read-only. No live adapter added/connected, no keys used. `test_crypto_v08.py::test_no_short_averaging_stale_or_live` | Real execution remains technically disabled. |

Fresh local safety selection before the feed fix: **109 passed** (Python 3.12.14).
After the feed fix: **93 passed** in the affected feed/crypto/lifecycle/scan/
preview/runtime selection. Full final suite and exact-HEAD remote results must
be read from the final acceptance section, not inferred from these subsets.

## Platform and research limits

Physical Apple Silicon/Safari/Retina/restart/sleep-wake: **NOT RUN**. No supported
Mac attachment was provided. See `MAC_ACCEPTANCE.md` for clean checkout, strict
QA, isolated storage, production-vs-synthetic UI cases, single-owner test,
stop/restart and non-destructive rollback.

The original 897/919 and upstream 315 numbers in `VALIDATION.md` remain prior
reports; upstream code was not changed, so its suite was not repeated. No real
sealed dataset was opened/scored and no optimization/threshold tuning was run.
Synthetic holdout-invariance tests are engineering checks only.

Four claims remain separate: (1) engineering operation in tested environment,
(2) validity of historical evaluation, (3) independent statistical alpha,
(4) safe real exchange execution. This pass primarily validates (1). No new
profitability evidence is claimed and (4) is disabled. The next single priority
is the physical Mac/Safari acceptance, not v1.0 or strategy optimization.
