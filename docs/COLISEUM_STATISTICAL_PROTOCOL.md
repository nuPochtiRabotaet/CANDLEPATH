# Frozen protocol — Coliseum research v0.2, 2026-11-05

Register BEFORE new outcomes. Existing monthly development sample is already
known and is diagnostic only. Never use its final 20% to design or tune methods.

Primary estimand: mean daily marked-liquidation P&L / 10000 initial fold capital,
relative to cash (zero), synchronized across ALL registered candidates. Fold
bankroll resets must not create returns. Trade expectancy is descriptive, NOT
an IID significance test. Minimum 180 complete daily observations; >=30 per fold.

Method: centered synchronized circular moving-block bootstrap, separately within
each fold, block lengths 3/7/14 days, 1999 replicates, seed 20261105. Common sampled
indices preserve candidate dependence. Fixed bootstrap SE studentization and
single-step max statistic provide approximate familywise error control (FWER),
not an exact finite-sample guarantee or Hansen SPA implementation. Report adjusted
one-sided p-values and simultaneous two-sided 95% bands for mean daily P&L.
Require positive lower bound and adjusted p<=.05 at ALL three block lengths.
White Reality Check is a useful global-null alternative but does not itself
identify individual survivors. SPA is deferred: no claim to reproduce its
studentization/truncation. Assumptions: weak dependence, finite moments, approximate
within-fold stationarity. Regime changes/rare tails can invalidate coverage.

Correlation: aligned DAILY outcomes only; constants have undefined correlation.
Connected components at positive rho>=.95 are descriptive dependence groups,
not proof of economic independence. Near identical vectors use explicit atol.
At most one candidate per component after existing judge eligibility; never add
back rejected candidates. All tested variants remain in multiplicity denominator.
No winners from incomplete roster, unverified/short data or development-only tests.
Never produce STATISTICALLY_VALIDATED automatically: independent study review is
separate. Synthetic null experiments test implementation/calibration only.

A: longer holding (16 vs32 bars), paired daily net change/cost per exposure;
reject improvement if simultaneous band includes zero or stress outcome worsens.
B: fixed low-vol filter vs unfiltered, paired turnover and net; reject if no net
improvement after costs. C: 5m vs15m, causal complete aggregation, equal calendar
windows; reject if paired net improvement uncertain. D: rho>=.95/identical daily
vectors indicate redundant outcomes, NOT identical economic mechanisms. Freeze
A/C candidates and data windows before running; no post-hoc threshold tuning.
This release reports B/D diagnostics; A/C experiments remain NOT EXECUTED unless
explicitly listed in measured results. No nominal top-20 requirement.

References: White (2000), Econometrica, doi:10.1111/1468-0262.00152;
Romano & Wolf (2005), Econometrica, doi:10.1111/j.1468-0262.2005.00615.x.
