# CandlePath — agent development rules

These instructions apply to this repository. Read this file first. The current active integration branch is `develop/v0.9`. Use `CANDLE_VISION.md` for product direction and `docs/V09_INTEGRATION_CHECKPOINT.md` for integration/release constraints. Historical root `DEVELOPMENT_CHECKPOINT.md` entries are dated; verify present Git/code state rather than treating old results as current.

## Scope and safety (non-negotiable)

- Work on **CandlePath v0.9 Alpha only** unless the user explicitly changes scope. Do not start v1.0, turn on live or autonomous exchange execution, or make real trades.
- Do not write directly to `main`; start short isolated branches from the current `develop/v0.9` HEAD and create reviewable PRs targeting `develop/v0.9`. Do not auto-merge PRs without explicit authorization.
- Preserve legacy MOEX Invest source, portfolio/history, migrations and all user-owned data. Never delete, reset, or migrate live user databases for a test.
- Use isolated temporary `MOEX_DATA_DIR`, synthetic data or local read-only research fixtures for automated tests. Never commit raw market CSV, account credentials, API keys, private portfolios or secrets.
- Paper trades are virtual. Offline strategy research is **not** the live Paper worker and does not establish real fill capability, positive return or risk-free stops. Distinguish these precisely.
- Preserve candle-event causality: signals from a closed candle cannot be executable before confirmation; historical fills must use next-available prices. Never leak future observations into indicators, decisions or parameter selection.
- Respect chronological evaluation, purging/embargo, and the sealed final 20% holdout. Never inspect, score or tune against the sealed holdout without a separately approved final evaluation plan.
- Show `NO TRADE`, `UNAVAILABLE`, `INSUFFICIENT_SAMPLE` or `EXPERIMENTAL` when supported. No uncalibrated probability or claim of directional alpha, profitable signals or a ready-to-trade system.
- Fail closed on stale/crossed/invalid market quotes, broken history, missing symbol rules, ambiguous execution, persistent storage failures or missing protective worker. Local stops are inactive when Mac/app is off or asleep.

## Token-efficient workflow

1. Inspect Git branch/working tree and relevant current checkpoint first. Read only task-related modules, tests and references; do not repeatedly ingest the entire repository.
2. Formulate **one small, testable change** with the user-visible problem, current behavior, intended behavior, boundaries, and acceptance tests. Prefer fixing existing code over a parallel subsystem.
3. Reuse existing Feed, `analysis.analyze()`, `SignalLifecycle`, Paper, `CostModel`, risk planning, immutable market journal and offline research scripts. Do not write a second implementation casually.
4. Begin with concise plan (max 5 points); then execute without repeated confirmation for ordinary reversible changes. Ask before destructive or irreversible actions.
5. Run focused unit/integration tests first; use full Python/JS/Chromium CI when preparing a PR or when shared interfaces/invariants are touched. Never hide failures by changing skip markers or relaxing assertions.
6. Limit output to essential files/line ranges, diffs, failures and results. Do not dump entire logs or code files unless needed to debug. Be precise about simulated vs real market observations.
7. Commit narrow, reviewable changes with tests; do not blend cosmetic UI redesign, feature requests, research parameter tuning, and reliability fixes in one PR.
8. On completion record changed files, commands, **actual** pass/fail/skip counts, unverified physical Mac/Bybit steps, risks and next action in a concise checkpoint. Prefer updating the relevant current v0.9 checkpoint over appending large narrative to legacy reports.
9. For uncertain implementation facts, inspect current source before making claims. A previous CI run, local user's report, or research sample is evidence only for the particular revision/environment tested.
10. Effort guidance: Medium for narrow routine edits; **High for causal signal, Paper monetary invariants, safety and integration**; Extra High only when an unusually hard correctness question justifies the cost.

## Required verification focus

- Signal timestamps, closed-candle gates, deduplication, historical stability, state transitions, lifecycle expiry/invalidation and stale-feed behavior.
- Clear distinction between `BUY` hypothesis, `EXIT` indicator, `ACTIONABLE` authorization and an actual confirmed **Paper** fill. A bare `EXIT` must not start a short or imply that a position was sold.
- Next-open history, matching strategy exits, stop/target and gap precedence, spread/fees/slippage, Decimal-based virtual balance accounting, size/tick/min-notional constraints, and idempotent preview/confirm.
- Negative/adversarial cases, restart/process ownership, network interruption, immutable data, and Invest regression. Track browser and real macOS acceptance separately.
- Do not change strategy thresholds after examining the reserved final holdout. Compare to honest baselines and report sample size and uncertainty.

## Current entry point for phase 1

Read `docs/V09_STAGE1_BUY_SELL_PAPER_QA.md` for the bounded BUY/EXIT and Paper audit assignment. `scripts/verify_v09_local.command` runs local checks; absent Node/Playwright means those checks were **skipped**, not passed. The project remains v0.9 development-only.
