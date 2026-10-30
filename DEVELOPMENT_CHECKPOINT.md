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
