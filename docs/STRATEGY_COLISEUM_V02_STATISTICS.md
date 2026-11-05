# Strategy Coliseum v0.2.1 — statistical evidence layer (draft)

**Research only; this does NOT certify alpha or promote strategies.** This
branch is stacked on draft #42 and does not change production Paper, place orders,
merge any PR, or unseal the final 20% of the source dataset.

## What is measured

The research-only `simulate_paper_paths` has an opt-in
`collect_daily_equity=True` parameter. It records **end-of-UTC-day increments
in after-cost marked liquidation equity** per independently recapitalized
walk-forward fold. It includes zero-return days, unrealized after-cost marks,
and exact fold-end forced liquidation. End-of-day P&L sums must reconcile to
the fold's net return, or the research run fails. All bar-level calculations
remain inside the development folds. Original replay outputs are unchanged
when the flag is disabled.

The v0.2 runner now opts in, stores daily records alongside each PAPER/LOW/
STRESS fold and binds them to the existing content-addressed manifest and
trial cache. Research results from before this change cannot be resumed into
the same output directory: the frozen source-code fingerprint must reject
that reuse. Use a **new** empty output path.

`coliseum_statistics.evaluate_statistics` validates exactly aligned daily
series for **all PAPER candidates**, reconciles each fold and refuses missing,
corrupt, reordered or misaligned daily observations. Non-full UTC days (not
288 five-minute bars) are excluded from statistical testing but included in
the P&L reconciliation. Research cost scenarios remain distinct; inference
uses PAPER only, and the existing judge still separately gates STRESS.

1. **Dependence:** absolute Pearson correlation of synchronized full-day
   after-cost P&L; connection cutoff 0.85; constant-return series explicitly
   uninformative. Connected components flag potentially duplicate/divergent
   strategies. Correlation clusters are descriptive, not independent trials.
2. **Uncertainty:** with a sufficiently long panel, an explicitly exploratory
   deterministic day-block bootstrap (999 resamples, seed 20261105,
   3-day circular blocks **within each fold**) uses the **same sampled
   time indices across all candidates**. It returns per-candidate
   descriptive 90% percentile intervals for mean daily net P&L.
3. **Multiple testing:** centered, fixed-studentizer joint max-T resampling
   provides one-sided exploratory per-candidate and family-wise adjusted
   p-values for a positive mean day-level PAPER net P&L. All 100 dependent
   candidate variants remain in the family; negative/flat candidates do
   not become winners by omission. Zero-variance and nonpositive observed
   results have no affirmative p-value.

## Mandatory blockers, not a statistical stamp

- **At least 120 complete scored UTC days** across 3 development folds and
  at least 3 complete days in every fold, not just 120 raw calendar days.
  This is a conservative minimum diagnostics floor, not a power guarantee.
- Source must carry a recognized verified-archive label to *compute*
  exploratory p-values. An archive **label is NOT independent proof**:
  provenance, timestamp integrity, spreads and instrument rules require
  external verification even then.
- Existing local 8,640-bar user-supplied archive is unverified and too short.
  Therefore **p-values MUST be withheld** (`inference=NOT_COMPUTED`).
  Descriptive daily correlations may be computed but cannot certify edge.
- The final 20% sealed holdout is never scored. No prospective Paper/live
  validation, regime-stratified evidence, false-discovery certification or
  actual multi-year/500/2000-case experiment is supplied by this branch.
- A bootstrap that conserves synchronized candidates and fold boundaries
  still rests on approximate stationarity within each fold. The intervals
  are **not simultaneous post-selection confidence intervals**.
  Inferential adequacy needs independent quant review and richer history.

`statistical_acceptance` stays **false**, and production integrations stay
**zero**, regardless of exploratory p-values. The v0.1 judge remains the
deciding preliminary filter and can return zero, as it does on #42 history.

## Reproduce

From repository root with existing Python dependencies:

```bash
python -m pytest -q tests/test_coliseum_statistics.py tests/test_coliseum_v02.py
python scripts/run_coliseum_v02.py /path/BTCUSDT_spot_5m.csv /tmp/coliseum-v02-stat-new
python scripts/run_coliseum_v02.py /path/BTCUSDT_spot_5m.csv /tmp/coliseum-v02-stat-new
```

Examine `/tmp/coliseum-v02-stat-new/result.json` for
`statistics.inference`, blockers, correlation groups, full UTC days and the
unmodified `judge.qualified_count`. The historical CSV has not been provided
to this connector session: no new full 100-candidate historical rerun is
claimed. Run the integration on the original authorized local dataset, with
its SHA256 attested, before asserting empirical behavior/performance.

### Outstanding statistical acceptance work

Verified independent multi-month history; explicit regime stratification;
external evaluation of bootstrap coverage, calibrations and cross-correlated
selection; meaningful power and minimum economic benefit; forward Paper;
profiling actual 500/2,000 experiments; audit of real execution frictions.
No change enables trading.
