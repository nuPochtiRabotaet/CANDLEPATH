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
