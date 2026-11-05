# Coliseum v0.2 — aggregate P&L cost attribution

This research-only audit follows draft PR #42. It does **not** alter trade
execution, the existing virtual Paper-path simulator, candidate signals,
selection thresholds, or production Paper/Live behavior.

## Reproduce

With the fixed PR #42 summary and manifest committed in this repository:

```sh
python scripts/coliseum_v02_cost_audit.py \
  docs/research/coliseum_v02/manifest.json \
  docs/research/coliseum_v02/result.json \
  /tmp/candlepath-coliseum-cost-audit.json

python -m pytest -q tests/test_coliseum_v02_cost_audit.py
```

The JSON output is **complete for all 300 candidate/scenario combinations**.
Every candidate has recovered aggregate entry/exit mid-price exposure,
pre-cost P&L, taker fees, half-spread losses, slippage losses, total costs,
net P&L, trade count, and turnover. It is deterministic; a conflicting
existing output file fails closed.

## Observations on the frozen, unverified 8,640-bar dataset

Amounts below sum **independent candidate experiments with restarted 10,000
USDT bankrolls**. They are *not* a portfolio equity curve, a real account
result, or a realistic deployable strategy basket.

| Scenario | Trades across candidate tests | Gross P&L before assumed costs (USDT) | Fees | Spread | Slippage | Net (USDT) | Gross-positive candidates | Net-positive candidates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LOW | 18,491 | -3,457.25 | 45,025.19 | 18,010.07 | 18,010.07 | -84,502.58 | 31 | 0 |
| PAPER | 15,842 | -3,135.66 | 76,504.34 | 15,300.87 | 38,252.16 | -133,193.03 | 33 | 0 |
| STRESS | 11,969 | -2,446.99 | 114,420.00 | 22,883.99 | 57,209.97 | -196,960.95 | 32 | 0 |

Under PAPER, total modeled transaction costs are approximately **97.65%
of the absolute combined net loss**. This means fees/spread/slippage
dominate the observed modeled losses; it does **not** mean the gross
strategies have established positive expected value. Even their *summed*
gross result is negative. The 33 gross-positive records are in-sample
and potentially correlated; zero have positive post-cost net P&L.

## Mathematical reconstruction, scope and verification

The existing PR #42 summary contains for every completed scenario:

- `N = sum(exit_net_credit - entry_total_debit)`
- `T = sum(entry_total_debit + exit_net_credit)` (cost-inclusive turnover)

Therefore `entry_debit = (T-N)/2` and
`exit_credit = (T+N)/2`, even when many trades are aggregated.

This study uses a symmetric quote-currency taker fee rate `f` for both
sides, assumed full spread `b` basis points, and per-side slippage
`s` basis points. Let `h=b/20000` and `r=s/10000`.
For aggregate mid-price notional exposures `E` (entry) and `X`
(exit), both of which are positive:

```text
entry_debit = E * (1+h) * (1+r) * (1+f)
exit_credit = X * (1-h) * (1-r) * (1-f)

gross P&L    = X - E
spread loss  = h * (E + X)
slippage loss= r * (E*(1+h) + X*(1-h))
fee loss     = f * (E*(1+h)*(1+r) + X*(1-h)*(1-r))
net P&L      = gross P&L - spread loss - slippage loss - fee loss
```

The formulas are verified against `moex_intelligence.crypto.costs.estimate`
with three PR #42 scenarios, rising/falling/flat prices and a zero-cost
control. The analysis checks participant identity, frozen manifest hash,
source fingerprint, development range, untouched holdout and each
candidate's P&L reconciliation. Missing trials and invalid cashflows fail
closed.

**Critical limits:** the inversion is exact only for the frozen symmetric
**quote-denominated** cost assumptions, not for arbitrary real-exchange
fee currencies or observed bid/ask. It cannot reconstruct each individual
fill, price path, stop/target/gap reason or intrabar exposure from sums.
Positive gross P&L is not proof of predictive edge; other execution
assumptions, actual liquidity, source provenance, and a long independent
history remain unverified.

## Decision gate

1. Keep PR #42 and this stacked PR as **Draft**; do not promote any
   candidate to Paper or Live trading.
2. Read the generated 300-row attribution, identify high-turnover and
   low-excursion strategies, and verify an independently sampled **trade
   ledger** against this aggregate decomposition once the original CSV
   becomes available for authorized local research.
3. Freeze any proposed changes to holding horizons / entry filters before
   running fresh longer historical data; maintain the original sealed 20%.
4. Finish multiplicity correction, dependence clustering, bootstrap and
   regime validation before treating selection as statistically meaningful.

The original local user CSV is **not stored in this PR**; this audit
runs from the preserved summary/manifest only. Public Bybit access and
real fills are not asserted.
