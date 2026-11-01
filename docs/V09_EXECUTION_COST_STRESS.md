# CandlePath v0.9 — fixed offline execution-cost stress research

**Research only. Not a live trading signal, a verified Bybit backtest or
an estimate of account-specific execution fees.**

## Why

A strategy can appear mildly profitable if you assume an unrealistically
small bid-ask spread or an inexpensive fill. The **optional** v0.9 stress
report repeats the same frozen indicator rule set, historical inputs and
sealed development folds under three **predeclared** cost assumptions.
It never picks the best settings or uses future data to optimize the
model. No live quotes, API keys, user account or Paper database are accessed.

## Frozen scenarios

| Research label | Assumed full bid/ask spread | Modeled slippage per side |
| --- | ---: | ---: |
| LOW_COST_ASSUMPTION | 0 bps | 2 bps |
| PAPER_LIKE_ASSUMPTION | 4 bps | 5 bps |
| STRESSED_COST_ASSUMPTION | 15 bps | 15 bps |

On all three scenarios, local default Paper taker commission **10 bps per
side** is added. These numbers are **hypothetical sensitivity settings,
not market observations, actual historical spread or verified account
fees**. Even the stress setting might underestimate genuine execution
costs during a market shock.

## Command

```bash
python scripts/evaluate_spot_trades_csv_v09.py \
  --input ~/Downloads/BTCUSDT_2026-10-25.csv \
          ~/Downloads/BTCUSDT_2026-10-26.csv \
          ~/Downloads/BTCUSDT_2026-10-27.csv \
          ~/Downloads/BTCUSDT_2026-10-29.csv \
  --symbol BTCUSDT --timeframes 1 15 \
  --output-dir ~/Desktop/candlepath-cost-stress-new \
  --evaluate --simulate-paper-paths --stress-paper-costs
```

Optional strict **unverified rule scenario** can be included via
`--paper-rules-file ~/Downloads/research-btc-rules.json` to reject
hypothetically unexecutable Spot quantities and whole-position exits.

This is an extra CPU-intensive calculation because the existing path
research is re-run for every cost scenario. Each input must be a
validated chronological, fully closed Spot trade-day CSV. The importer
splits gaps into separate contiguous segments; it does not fabricate
missing days or prices. Output files are exclusive-create. User trade
files are never modified, uploaded to GitHub or authenticated as genuine
Bybit exports. The final 20% of each segment remains SEALED/UNSCORED.

## Interpretation / limitations

The output `paper_cost_stress_research` includes the three scenarios,
the same final SHA256 holdout and fold boundaries, number of hypothetical
trades, fold starting/ending cash, conditional net return and marked
drawdown. Different execution assumptions can alter quantity sizing,
risk-gate eligibility and even which simulated signals enter. Thus
different scenarios are **not necessarily paired trade-by-trade**.
Comparing their gross returns without checking trade counts is invalid.
Fold bankroll resets deliberately; no compounded account return exists.

No trend of scenario returns demonstrates a profitable strategy, future
directional edge or trading recommendation. In particular, analyzing
the same development folds under multiple costs does NOT authorize
model fitting, threshold optimization or opening the sealed holdout.
Spread and slippage can be asymmetric in reality; simulated stop/target
fills and fold-close liquidations remain optimistic in some cases.

No production Paper worker, exchange metadata, bid/ask tape, order-book
liquidity, latency, partial fills, market impact, funding, leverage,
position reconciliation or real trades are modeled here. This module
does **not** mark v0.9 or any future trading version as ready for live use.
