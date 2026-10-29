# MOEX Intelligence — Codex handoff

## Snapshot

- Base release: **v0.8.2-rc3**, captured 2026-10-29.
- Design Bible: `docs/design_bible/` (specification, interactive concept board and four visual references).
- This repository is the source of truth after import. Previous ZIP archives remain backups, not Git history.
- **No live trading**: do not enable live order execution or transmit real API credentials. Bybit API availability and all macOS launcher flows must be checked on the owner's machine.

## How to work

1. Read `README.md`, `ARCHITECTURE.md`, `ROADMAP_v0.9.md`, `DEVELOPMENT_CHECKPOINT.md`, `SECURITY_STATUS.md` and `docs/design_bible/README.md` before changing the code.
2. Preserve both Invest and Crypto functionality. Work in small, reviewable commits.
3. Use branches and pull requests for feature changes; do not alter the `main` snapshot without review.
4. Run `python -m pytest -q` in an appropriate Python environment and report actual outcomes rather than assuming historical reports still pass.
5. Prioritize safety, persistent state, stop/target behavior, accounting invariants, order previews and journal accuracy; do not claim profitability or predictive accuracy without out-of-sample backtesting.

## Planned v0.9 work

Follow `ROADMAP_v0.9.md`: forecast journaling and measurable predictions, backtests, a safe demo/paper workflow, UX refinement and verification of the Bybit connection on the owner's Mac. Never autonomously trade real funds as part of development.
