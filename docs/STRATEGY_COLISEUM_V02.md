# Strategy Coliseum v0.2 — executable development checkpoint

Research only. No winners certified and no production strategy integration.
Base develop c6ae68a. Explicit dependencies copied from draft #41 (judge/tests/docs)
and #40 (research timing correction/filter/tests). Neither PR is merged.

## Reproduce

From repository root, with project dependencies installed:

```
python scripts/run_coliseum_v02.py /path/BTCUSDT_spot_5m.csv /tmp/coliseum-study
# Same command resumes and checks equality of the final deterministic result.
python scripts/run_coliseum_v02.py /path/BTCUSDT_spot_5m.csv /tmp/coliseum-study
python -m pytest -q tests/test_coliseum_v02.py
```

100 registered candidates = 50 explicitly named hypotheses x unfiltered/low-volatility
variants. Variants are dependent, not independent discoveries. Six families cover
trend, momentum, mean reversion, breakout, statistical hypotheses and controls.
The canonical spec contains formula-source SHA256, version, fixed thresholds via
source hash, execution policy and seed. No threshold was selected using outcomes.
The manifest is written before signals; source/code/runtime/cost changes reject
resume. All three cost scenarios account for every candidate, including zero-trade
and failed trials. Failures invalidate the whole tournament. CLI uses an OS lock;
per-trial results are atomic, identity-bound and checksum-verified. An interrupted
uncommitted trial is recomputed, completed trials reused. Temporary files do not
count as completed trials. No pickle or executable user expressions.

Signals use shared causal features computed on development data only. Each provider
returns only signals belonging to the supplied fold prefix. Prefix equivalence is
tested for every candidate. Existing simulate_paper_paths performs next-open fills,
matching exits, stop-first collisions, gap handling, marked equity risk limits and
CostModel accounting. Existing purged walk-forward is cached once by complete
candle content and parameters, not replaced. All candidates have identical folds,
128-bar warmup, 2 ATR stop/4 ATR target, 16-bar maximum hold, 25% capital allocation
and .75% initial stop-risk limits. Long-only, one position per candidate; these are
independent experiments, NOT a combined 100-strategy portfolio.

LOW/PAPER/STRESS: per-side fees 5/10/20 bps, slippage 2/5/10 bps,
full spread 4/4/8 bps. Turnover is cost-inclusive entry debit plus exit credit,
not exact gross traded notional. Folds each restart with 10,000 USDT. Drawdown is
worst fold OPEN/CLOSE sampled liquidation drawdown, not full intrabar drawdown.

## Data and statistical limits

Official Bybit REST historical request returned HTML Site Unavailable in this
cloud environment, not JSON OHLCV. No access restrictions were bypassed.
Available CSV has 8,640 continuous 5m records. Source remains
USER_SUPPLIED_CSV_UNVERIFIED; last 1,728 are only integrity-checked/hashed by
existing splitter, never passed to feature generation or outcome scoring.
No independent long-history experiment exists. This dataset is known development
data and cannot establish out-of-sample alpha. Pipeline deliberately cannot label
an arbitrary imported CSV verified. Judge source/history gates prevent promotion.

Existing judge thresholds and family cap are unchanged. Multiple-comparison
correction, block-bootstrap uncertainty, return-correlation clustering and
regime-stratified validation remain NOT IMPLEMENTED. Three dependent folds and a
month of one symbol cannot support a 100-way significance claim. Control candidates
are experimental timing controls, not a risk-matched buy-and-hold benchmark.
Missing historical instrument rules, observed spread and order flow remain limits.
No inferred buy/sell volume is used. No trained models or supervised fitting occurs;
existing purge boundaries are metadata, not evidence of trained-model validation.

This is a working 100-candidate research pipeline checkpoint, not completion of
all v0.2 statistical acceptance. 500/2,000 full experiments and multi-year memory
scaling remain unmeasured. Next gate: verified long independent history, frozen
multiple-testing and dependence policy BEFORE outcomes, then larger experiments.
Mac/Safari and live connectivity are not validated by these offline tests.

## Actually executed checks — 2026-11-05

- 103 focused tests passed; 823 full Python tests passed, no skips (56.98 s).
- JS syntax, 32 geometry checks, chart contract and synthetic Chromium passed.
- Full available historical experiment: 100 candidates x 3 cost scenarios,
  75.56 s; peak Linux process RSS 131,088 KiB (~128 MiB), including dependencies.
- Resume: 0.332 s; final result equality enforced byte-equivalently after canonical
  JSON serialization. 0 failures, 0 qualified, 0 positive PAPER net candidates;
  5 PAPER candidates had no trades. No strategy tuning was performed.
- Full registry/spec hashes and all rejected results: research/coliseum_v02/.
- CI status belongs to the exact PR head and is reported separately in its body.
