# CandlePath v0.9 — directional uncertainty hardening

This research-only patch extends the fixed momentum challenger output with:
- `direction_hits`: observed correct directions among nonflat actual outcomes.
- `direction_calls`: emitted nonflat directional predictions among nonflat actual outcomes.
- `direction_wilson_95_lower` / `direction_wilson_95_upper`: descriptive Wilson-score interval for observed directional hit frequency.
- `direction_sample_sufficient`: minimum 30 nonflat actual outcomes per fold/horizon for merely descriptive reporting.

The preexisting `candidate_direction_hit_rate` still counts **flat candidate predictions as misses** when the realized market moved. We do not quietly switch its denominator to just answered calls. When no nonflat outcomes exist, hit rate and Wilson bounds are **null**, never zero or fabricated 100%.

## Why the interval matters

A synthetic trend can yield perfect observed predictions while having finite sample uncertainty. For N correct out of N events, Wilson's lower bound remains below 1.0. This prevents an eye-catching raw 100% figure from being mistaken for certainty.

**Important:** These are descriptive binomial intervals. Historical candle returns are serially dependent; the Wilson construction does not correct for autocorrelation, regime shift, selection bias, multiple testing, or the final sealed holdout. It is not a calibration certificate, confidence of profitability, trade authorization, or proof of an ML edge.

## Five-check verification

1. Mathematical Wilson bounds: fixed cases, finite, [0,1], never excluding observed sample proportion.
2. Boundary cases: zero observations → null; invalid/inverted counts rejected.
3. Causal paired scoring: existing momentum vs Random Walk test suite and exact same fold origins unchanged.
4. Safety: sealed holdout not scored, no Store, no exchange API, no LIVE orders or user account changes.
5. GitHub CI: full pytest on exact PR head, Python compile, JS/Node and Chromium checks, inspect results before accepting.

This change affects only offline research reports, not live Crypto forecasting or v1.0. Merge base PR #14 first; main is unchanged.
