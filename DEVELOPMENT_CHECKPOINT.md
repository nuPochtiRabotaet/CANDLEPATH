# Development checkpoint — v0.8.2-rc3

29 October 2026. Release source archive, not FINAL. Base restored from rc2 SHA256 4ec9f814c169f90306b7e63cc010c29dd413a88d6eab944902248d03a69ddf1d; baseline291 passed. User-owned investment logic/data preserved. No Git repository supplied; immutable source archives used as checkpoints.

Completed P0: rule-aware inventory and residue basis, sell-available, approved protection residue limit, retries/trigger recheck/rollback, active Stop/Target Prepare/Confirm, transactional guards, explicit writeoff.
Completed P1: full-ledger statistics and period filters, sampled equity, explicit signal/notes/risk provenance; assistant quality cost details.
Completed P2: persistent overlay preferences, Glow/markers/intensity reset, collapsible assistant, four UI blueprints and screenshots.
P3 foundation: pinned six-module day-trader-skill source review; typed intelligence contracts, append-only experimental forecast/outcome journal, UNAVAILABLE model. No upstream scripts executed/installed. No actual model/backtest/Demo execution.

Final checks:343 pytest pass; original4 regressions pass;32 Crypto browser scenarios;12 Invest scenarios/16 layouts; launcher start/stop/reuse;56 preserved source/config files. Exact evidence in TEST_REPORT_FINAL.md and docs/rc3. Actual Bybit REST returned HTML Site Unavailable; latest WS handshake timed out. Production correctly blocks actions. No actual API delivery or physical Mac acceptance claimed.

Next work: user Mac acceptance first; then v0.9 causal quantitative baselines + independent walk-forward/held-out evaluation, forecast publication/outcomes UI, Forecast Overlay only when useful. After stabilization: supported Bybit Demo adapter with persistent real fill reconciliation. Live remains technically blocked. Refer to ROADMAP.md and LIVE_MANUAL_REQUIREMENTS.md.

Artifacts: complete source ZIP with manifest; README, CHANGELOG, ARCHITECTURE, TEST_REPORT_FINAL, COST_ENGINE_FINAL, PERFORMANCE_REPORT, UI_BLUEPRINT_REPORT, SIGNAL_REPORT, FORECAST_REPORT, TRADING_GUIDE, SECURITY_STATUS; screenshot evidence under docs/rc3. Earlier root reports preserved as historical docs/rc2/historical-root. This checkpoint supersedes transient WIP checkpoints.
