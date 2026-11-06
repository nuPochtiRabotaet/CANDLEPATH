# Strategy Coliseum v0.1 — research-only selection gate

## Scope

A strict judge for **precomputed** strategy results, not a new trading or
backtesting engine. Zero survivors is valid. Up to 20 may be shortlisted for
**further independent research** — never automatically added to the Strategy
Engine or allowed to execute Paper/Live orders.

Pipeline: verified historical data -> frozen candidate manifest -> causal
signals -> existing simulate_paper_paths + CostModel -> three development
folds at LOW/PAPER/STRESS cost -> Coliseum judge -> independently untouched
evaluation -> prospective forward Paper -> separately approved integration.

The current PR builds only the judge and tests. It does **not** generate or
backtest 100, 500 or 2,000 strategies; that is the next phase.

## Input and reproducibility

Call:

    python -m moex_intelligence.crypto.strategy_coliseum_research STUDY_JSON FROZEN_ROSTER_JSON OUTPUT_JSON

STUDY_JSON follows the summary shape from draft PR #40
(scripts/deep_paper_validation_v09.py): source_sha256, source, rows,
development_end_exclusive, sealed_final_evaluated=false and results with
exactly LOW/PAPER/STRESS maps keyed by candidate ID. Each result contains
trades, net_pnl, expectancy, profit_factor, win_rate, max_drawdown and exactly
three chronological fold objects with fold, trade_count and net_return_pct.

All reports must represent separately capitalized 10,000 USDT folds on
5-minute BTCUSDT. Different markets/capital require a schema/version update,
not an assumption. Every fold's P&L must reconcile with the aggregate.

The roster is a JSON array with unique id, family, spec_sha256. Compute the
SHA256 from a canonical full strategy specification including code revision,
parameters, symbol, timeframe, execution rules and random seed — not only
from shared source code. Freeze it before looking at trial results. Submitted
IDs must exactly match each cost scenario, including losing candidates.
Missing/extra/duplicated entries invalidate the entire tournament.

A provenance label must be exactly VERIFIED_PUBLIC_ARCHIVE or
VERIFIED_LOCAL_ARCHIVE to pass the preliminary source gate. **A label is
not proof**: independently verify data origin, SHA256, timestamps, gaps and
calendar coverage before treating any result as evidence.

The output contains every submitted candidate and rejection reason, a
stable selection fingerprint, sealed-holdout status and explicit
no-autonomous/no-production flags. Output is create-only.

## Preliminary gates — not optimized on current BTC data

- >=180 days of complete 5-minute history (>=51,840 rows, with separate
  timestamp/gap verification).
- >=60 trades overall and >=10 in each of 3 development folds.
- Positive PAPER expectancy and total P&L, profit factor >=1.20, positive
  net outcome in all folds.
- Positive STRESS net outcome and every stress fold; worst observed
  PAPER drawdown <=10%. Observed OHLCV drawdown underestimates possible
  intrabar drawdown.
- Sort deterministically by worst PAPER fold, then STRESS net, PAPER net,
  candidate ID. Shortlist <=20 total, <=4 per family.
- Reject missing/nonfinite/inconsistent results and any evaluated final
  holdout. The last >=20% is never used by this module.

**Passing does not prove alpha.** With thousands of trials, selection bias,
dependent folds and correlated strategies can produce false winners. Family
caps do not prove independent strategies.

## Existing evidence

PR #40 used 8,640 five-minute bars (around 30 days) with unverified source
provenance. Trend Following, Mean Reversion and Breakout Detection all
produced negative net expectancy at standard and reduced costs. The judge
must shortlist **zero** of these from that report. Its 1,728 final bars
remain sealed. PR #40 is still draft/unmerged; no real order is involved.

## Next Work task — effort High

Read this PR and PR #40 first. Do not recreate the judge or Paper Engine.

1. Integrate report/roster adapter without merging drafts automatically.
   Independently verify historical data coverage, source and timestamp
   integrity. Preserve existing final holdout.
2. Define an initial frozen universe of 50–100 distinct hypotheses across
   trend, mean reversion, breakout and volatility regimes. A parameter
   grid is not 100 independent ideas. Account for *all* trial attempts.
3. Run the existing simulated execution/cost/risk logic for every candidate.
   No invented Order Flow from OHLCV: use verified public trade history if
   and only if it is genuinely available.
4. Make deterministic, content-addressed, resumable batch experiments with
   measured performance and resource limits. Grow to 500/2,000 only after
   proving 100-case reproducibility and acceptable compute cost.
5. Extend judging with multiple-testing corrections, block resampling,
   dependence/correlation analysis and untouched independent evaluation.
   Fix statistically unjustified assumptions; report negative/empty outcomes.
6. Select 0–20 candidates for further prospective Paper testing, **not**
   automatic production integration. Explicit human approval is required.

No Live/autonomous orders; do not mutate user datasets, portfolios, main
or develop/v0.9. No automatic PR merges. Mac/Safari, process sleep/resume,
and Bybit connectivity remain separately unverified.
