# Development checkpoint — v0.8.2-rc3

29 October 2026. Release source archive, not FINAL. Base restored from rc2 SHA256 4ec9f814c169f90306b7e63cc010c29dd413a88d6eab944902248d03a69ddf1d; baseline291 passed. User-owned investment logic/data preserved. No Git repository supplied; immutable source archives used as checkpoints.

Completed P0: rule-aware inventory and residue basis, sell-available, approved protection residue limit, retries/trigger recheck/rollback, active Stop/Target Prepare/Confirm, transactional guards, explicit writeoff.
Completed P1: full-ledger statistics and period filters, sampled equity, explicit signal/notes/risk provenance; assistant quality cost details.
Completed P2: persistent overlay preferences, Glow/markers/intensity reset, collapsible assistant, four UI blueprints and screenshots.
P3 foundation: pinned six-module day-trader-skill source review; typed intelligence contracts, append-only experimental forecast/outcome journal, UNAVAILABLE model. No upstream scripts executed/installed. No actual model/backtest/Demo execution.

Final checks:343 pytest pass; original4 regressions pass;32 Crypto browser scenarios;12 Invest scenarios/16 layouts; launcher start/stop/reuse;56 preserved source/config files. Exact evidence in TEST_REPORT_FINAL.md and docs/rc3. Actual Bybit REST returned HTML Site Unavailable; latest WS handshake timed out. Production correctly blocks actions. No actual API delivery or physical Mac acceptance claimed.

Next work: user Mac acceptance first; then v0.9 causal quantitative baselines + independent walk-forward/held-out evaluation, forecast publication/outcomes UI, Forecast Overlay only when useful. After stabilization: supported Bybit Demo adapter with persistent real fill reconciliation. Live remains technically blocked. Refer to ROADMAP.md and LIVE_MANUAL_REQUIREMENTS.md.

Artifacts: complete source ZIP with manifest; README, CHANGELOG, ARCHITECTURE, TEST_REPORT_FINAL, COST_ENGINE_FINAL, PERFORMANCE_REPORT, UI_BLUEPRINT_REPORT, SIGNAL_REPORT, FORECAST_REPORT, TRADING_GUIDE, SECURITY_STATUS; screenshot evidence under docs/rc3. Earlier root reports preserved as historical docs/rc2/historical-root. This checkpoint supersedes transient WIP checkpoints.

## v0.9 development checkpoint — 2026-10-30, partial Phase A

Base HEAD: f421d2123b62e8e03a4aa767ad1fd0243842f34e. Branch: feat/v0.9-research.
Implemented server bootstrap starting the shared process-level Paper runtime before browser sessions; canonical database path singleton, explicit shutdown, UI reuse, removed duplicate UI protection invocation. Invest source and ledger unchanged; real execution remains disabled.
Validation: full suite 345 passed in 20.35s with local sockets permitted; actual launcher start/health/stop passed without browser. Two new tests cover singleton and restart. Initial sandbox baseline encountered socket restrictions and is not a passing baseline claim.
Outstanding: open-position subprocess recovery, crash/concurrency injection, cross-process ownership, status UI, temporal contracts, all phases B–I, browser and physical Mac acceptance. This is NOT completed Phase A or a v0.9 release. Direct `streamlit run app.py` still requires Trade to initialize runtime; use the supported launcher/server_runtime entry point.

## v0.9 Phase A follow-up — process ownership (2026-10-30, review PR)

On top of the prior shared-paper-runtime commit: exclusive nonblocking `flock` per canonical Paper SQLite database path, with a descriptor held until the monitor thread stops. A second macOS/Linux process fails closed instead of opening a competing protection worker. Streamlit Trade detects conflicting ownership before it opens the database and prevents further Paper interaction; UI copy clarifies the launcher-before-browser behavior and no protection while Mac sleeps. A failed worker constructor releases ownership; shutdown does not release ownership while a worker is still alive. Old Invest data/code is untouched.

Local verification using the shipped rc3 sources overlaid with the v0.9 branch changes: 45 targeted tests passed, including subprocess contention, release/restart, failure cleanup and existing launcher/order tests. `python -m compileall` passed. An optional-dependencies-restricted test run recorded 320 passed, 11 failed solely due to missing streamlit/mcp imports; full collection blocked by the same missing dependencies (4 collection errors). Do not claim the full 345+ suite passed. Physical Mac launcher/Safari, actual Bybit network, position recovery and prolonged operation have NOT been verified. Phase A remains partial; no live orders or reliable forecast have been activated.

## v0.9 Phase B — first experimental forecast overlay (2026-10-30, review PR)

Added causal Random Walk median + EWMA volatility baseline for latest valid Bybit closed candles only, four future candle horizons, model-implied uncalibrated 80% intervals, and visible forecast line/fan inside existing Lightweight Charts with an independent toggle. Inactive when market data are stale, invalid or insufficient. NO directional predictive skill, trained model, validated confidence, profitability or BUY/SELL decisions are claimed. Existing signal markers and Paper execution remain independent. The forecast is not yet auto-published to the immutable outcome journal. See docs/FORECAST_BASELINE_V09.md for methodology and acceptance gaps.

Local verification on rc3 source overlaid with v0.9 branch changes: 9 new forecast tests, 24 focused tests and 302 available regression tests passed; JS syntax check + Python compileall passed. Full test suite remains blocked by missing Streamlit and MCP dependencies; real Bybit and macOS Safari browser checks remain pending. This is a DEVELOPMENT PR, not a completed v0.9 release.

## v0.9 Forecast Integrity Audit — 2026-10-30 (review PR, not released)

Ten-part code/causality/data/readiness/persistence/browser test audit in docs/FORECAST_AUDIT_V09.md. Three confirmed regressions were addressed:
1. Separate forecast candle-stream readiness from trading quote/bid-ask readiness, fail closed if no fresh kline stream.
2. Publication of the same forecast across Streamlit reruns is idempotent despite different creation timestamps; conflicting forecast body still fails, immutable original remains untouched.
3. Empty-data/chart transition with a retained quote previously caused a JS timeToCoordinate(undefined) crash and preserved stale projection; both faults fixed and checked in real local Chromium on synthetic candles.

Live experimental forecasts are now first journaled immutably in SQLite and reconciled to closed-candle outcomes when the last closed candle changes. Failure to safely persist suppresses the forecast instead of showing an unauditable prediction.

Verification (local rc3 source overlaid with v0.9 feature changes): 26 focused tests passed; 318 dependency-compatible tests passed with 25 deselected. An earlier broader run gave 332 passed, 11 failed due to missing Streamlit/MCP imports; full collection had four import errors. Real Chromium synthetic-graph smoke script passed (render, toggle, stale status, empty-feed recovery); JS syntax and Python compileall passed. macOS Safari, actual Bybit REST/WS, full requirements suite, historical calibration and proven directional prediction are outstanding.

Changes remain stacked in development PRs only; main untouched, LIVE disabled.

## v0.9 incremental research — causal offline replay (2026-10-30; PR review)

Added a separate, strictly read-only historical replay tool for the EXPERIMENTAL Random Walk/EWMA Forecast. A shared pure mathematical helper supplies both the existing live Forecast Overlay and offline evaluation, preserving its original model version and quantile formula. Walk-forward origins use only pre-origin closed candles; chronological final 30% is the default diagnostic holdout, with origin spacing 8 candles and minimum 30 origins. Reports observed interval coverage, absolute and relative prediction error, band width, and the explicitly equivalent flat Random Walk median baseline.

New files: moex_intelligence/crypto/forecast_evaluation.py, scripts/evaluate_forecast_v09.py, tests/test_forecast_replay_v09.py, docs/FORECAST_REPLAY_V09.md. No retrospective evaluations are written into the immutable live forecast journal; the existing crypto SQLite file is opened in read-only mode for CLI evaluation. No trading or user holdings changed.

Local verification on staged rc3 + incremental v0.9 source: 43 targeted tests passed; 348 broad tests passed with 11 missing Streamlit/MCP dependency import failures and 4 collection errors. This is NOT a complete clean GitHub-branch test run, and GitHub Actions was already blocked before jobs could start. Temporary database CLI checked on 1000 synthetic candles (37 origins); no persisted forecast records were created. Actual Bybit data, Safari and calibrated model advantage remain UNVERIFIED.

Next: independent validation with genuine saved candles and separate untouched time periods; fix CI pre-job failures; full macOS acceptance; compare simple baseline/advanced candidate before any forecast-driven BUY/SELL. This is not a v0.9 release.

## v0.9 replay numerical hardening and full CI recovery — 2026-10-30

Ten repeatable review passes and evidence: docs/FORECAST_REPLAY_ROUND2_V09.md. New deterministic tests in tests/test_forecast_replay_round2_v09.py.

Confirmed faults fixed: replay forecast MAPE infinity/JSON failure on extreme future price (Decimal accumulation, nullable unrepresentable metrics, explicit overflow count); OverflowError on enormous integer timestamps/prices (controlled UNAVAILABLE / ValueError); malformed high/low/volume and future-dated closed candles accepted by historical replay (now fail closed). The validated mathematical baseline, historical-only split and read-only SQLite contract remain unchanged.

GitHub Actions pre-job blocker diagnosed: job-level `runner.temp` unavailable during workflow expression evaluation. Replaced with runner-agnostic /tmp path and explicit requirements.in cache-dependency-path. Real GitHub Actions execution #41072216320 on the stacked branch succeeded: Python source compilation, JS syntax, **408 full Python tests passed (19.95s)**, synthetic Chromium forecast chart smoke, diagnostics artifact upload. This supersedes earlier notes saying that all CI jobs failed before starting; they are now historical findings.

Remaining independent acceptance: physical macOS/Safari, current Bybit REST+WS market candles, uninterrupted/sleep-resume Paper monitor, independent forecast calibration/walk-forward on genuine data, and orderly PR integration. v0.9 is not released; real trading remains disabled.

## v0.9 experimental interval-quality metrics — 2026-10-30, development PR

Added to historical-only forecast evaluation: proper 80% Winkler interval score normalized to median price, signed empirical-minus-nominal coverage gap, and counts of lower/upper interval misses. This prevents portraying excessively wide bands as a successful model merely because raw historical coverage is high. The live EWMA/Random Walk engine, forecast IDs, market data, UI chart, Paper runtime and crypto/Invest databases were not changed. Tests include hand-calculated penalty values, zero-width flat market, extreme finite-safe output, chronology and read-only CLI. Full five-check verification and actual GitHub CI result belong in the review report docs/FORECAST_INTERVAL_QUALITY_V09.md; do not claim a validated directional model or release on this basis.

## v0.9 chart forecast geometry integrity (2026-10-30, development PR)

Found one-candle temporal misalignment between ForecastPoint.target_time (future candle closing boundary) and Lightweight Charts candle opening timestamps. Replaced the prior target_time-minus-step visual convention with an anchored, strictly validated end-boundary projection: the latest observed close is plotted at its data_as_of, future quantiles at their true target_time. Added a separate hidden whitespace-only future time grid to preserve the proportional time spacing of +1/+2/+4/+8 horizons on the chart's ordinal axis. Both the median and uncertainty fan derive from exactly the same projection validator; invalid/stale market or empty candles hide both layers and clear old series. Added deterministic Node geometry tests, Python-to-JavaScript value/time parity tests, and expanded Chromium smoke for geometry, malformed data, trailing open candle and recovery. See docs/FORECAST_CHART_GEOMETRY_V09.md. Full GitHub Actions acceptance remains required; this is not proof of alpha, real Bybit/Safari integration, or a v0.9 release.

## v0.9 public Bybit Spot historical evaluation — development PR

Added a separate read-only public REST data acquisition and evaluation path (moex_intelligence/crypto/bybit_history_evaluation.py, scripts/evaluate_bybit_public_v09.py). It uses Bybit V5 public time + spot kline endpoints, strictly excludes incomplete current candles using Bybit server time, paginates newest-first history backward (up to 5,000 rows), rejects stale/missing/duplicate/unaligned/invalid OHLCV, and records UTC provenance plus SHA256 of normalized input. It reuses existing historical holdout evaluation and does not create retrospective live forecasts, connect credentials, access Store, mutate SQLite or trade. CI includes a separate optional real Bybit REST diagnostic; a regional/network refusal is recorded as **not verified**, not disguised by unit tests. Five review gates and limitations: docs/BYBIT_PUBLIC_FORECAST_EVALUATION_V09.md. No claim of live data success until confirmed by actual HTTP/CI evidence; no change to main or release status.

## v0.9 read-only local CSV OHLCV evaluation — development PR

A strictly validated locally sourced CSV importer offers historical replay when official Bybit public REST is unavailable. The six-column open_time_ms,open,high,low,close,volume schema uses UTC open timestamp in milliseconds, fully closed contiguous candles, finite positive OHLC and nonnegative volume, bounded UTF-8 file size and rows. The reader emits two SHA256 digests (original bytes and normalized data), explicit UTC boundaries and **USER_SUPPLIED_CSV_UNVERIFIED** provenance; it does not certify that the file contains authentic Bybit prices. The CLI uses the existing v0.9 statistical replay and never opens Store/SQLite, contacts Bybit, creates retrospective live forecasts or trades. Optional JSON output is create-only to prevent file clobbering. See docs/OFFLINE_OHLCV_CSV_V09.md and five verification gates; full CI results must be recorded before acceptance. Stacked branch, main unchanged.

## v0.9 multi-fold causal walk-forward / sealed holdout — development PR

Introduced explicit half-open evaluation windows to the existing historical replay without changing its default output. The new fixed-model multi-fold evaluator uses three chronological development folds, a recorded purge boundary >= the largest prediction horizon, 8-bar spaced origin tests, and reserves a final 20% as **sealed and unscored**. Every prediction outcome is contained inside its fold. A SHA256 fingerprint identifies the final data segment without evaluating it. A separate CLI uses the strictly read-only local OHLCV CSV importer; no exchange call, SQLite migration, retroactive live forecast publication, API key or live order. This is NOT model fitting: current Random Walk/EWMA remains a fixed experimental baseline. See docs/WALKFORWARD_SEALED_V09.md, including five verification gates and explicit limitations. Full CI/real-data acceptance required before treating this milestone as finished.

## v0.9 live published-forecast scorecard finite safety — development PR

The actual SQLite-backed forecast outcome scorecard used unbounded float conversion and a numeric Streamlit format specifier, risking Infinity or a UI failure after an extreme but positive price move. Added Decimal-based finite-safe percentage reporting (unrepresentable -> None/null and explicit count), corruption detection for invalid stored outcomes, and a UI-safe formatter. Normal observations preserve prior values and schema; immutable forecasts/outcomes are never modified. Synthetic tests cover normal math, extreme price, invalid journal values, idempotent reconciliation and UI text. See docs/FORECAST_SCORECARD_FINITE_V09.md. This is not a claim of validated forecast skill or completed v0.9 acceptance; full CI, actual Bybit and macOS/Safari remain separate gates.

## v0.9 isolated causal momentum challenger — research PR

Added a *non-live, fixed-parameter* shrinked EWMA log-momentum interval candidate in moex_intelligence/crypto/momentum_candidate.py. Development-only paired evaluation compares its future medians and nominal band against exactly matched Random Walk EWMA origins/outcomes inside existing purged walk-forward folds, reporting MAE, relative gain/loss, interval score, empirical coverage and direction hit rate. Flat candidate calls count as misses on nonflat actuals; no optimization on evaluation labels. The final 20% of observations remains sealed, only fingerprinted, and is never included in forecasts or scores. CLI takes read-only USER_SUPPLIED_CSV_UNVERIFIED input, may create a new JSON report, never accesses Store, Bybit credentials or trades. It is NOT a validated AI predictor and cannot drive live BUY/SELL. Mathematical details, tests and five gates: docs/MOMENTUM_CHALLENGER_V09.md. Exact-head CI remains required before review acceptance.
