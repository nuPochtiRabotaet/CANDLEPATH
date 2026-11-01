# CandlePath v0.9 — sealed, sequential Paper-path research

**Development-fold-only OHLCV simulation. This is NOT the production Paper
worker, not exchange execution, not a calibrated strategy, and not v1.0.**

Previous research sampled hypothetical fixed-horizon outcomes for every
BUY independently. This stage deliberately makes those positions mutually
exclusive, deducts cash on entry, returns cash on exit, respects a bounded
capital/stop-risk budget, and handles existing confirmed BUY and matching
EXIT signals with stop/target and timeout exits.

## Run locally on the public Spot daily trade CSV files

```bash
python scripts/evaluate_spot_trades_csv_v09.py \
  --input ~/Downloads/BTCUSDT_2026-10-25.csv \
          ~/Downloads/BTCUSDT_2026-10-26.csv \
          ~/Downloads/BTCUSDT_2026-10-27.csv \
          ~/Downloads/BTCUSDT_2026-10-29.csv \
  --symbol BTCUSDT --timeframes 1 15 \
  --output-dir ~/Desktop/candlepath-paper-paths-new \
  --evaluate --simulate-paper-paths \
  --assumed-spread-bps 4 --paper-initial-cash 10000 \
  --paper-max-hold-bars 16
```

Each input is validated for format, day and chronology; gaps are split into
separate output segments. Choose a NEW output directory every time; all
outputs are create-only. User CSVs are never committed to GitHub or altered.
Market provenance remains USER_SUPPLIED_TRADE_CSV_UNVERIFIED.

## Deterministic assumptions, deliberately conservative where possible

- Uses existing `analysis.analyze()` indicator BUY/EXIT rules and
  `CostModel.estimate()` for Paper-equivalent quote/base fees and slippage.
  Defaults are local Paper assumptions (10 bps taker fee and 5 bps execution
  slippage **per side**), **not account-specific Bybit fees**.
- One Spot **long** at a time; no leverage, shorts, netting or averaging.
  When several BUY signals appear together, choose a fixed strategy priority
  (Trend Following, Mean Reversion, Breakout); no tuning on future outcomes.
- Signals from closed candle `i` may only execute at candle `i+1` **OPEN**.
  We assume that next open is attainable; actual exchange fills, order-book
  volume and intra-candle liquidity remain unverified.
- Fixed single-symbol allocation ceiling of 25% of virtual cash/equity
  and maximum **initial** stop exposure 0.75% including modeled costs.
  With no open position, this experimental single-symbol model sizes using
  free virtual cash. These are *research* limits, not an exchange order gate.
- **At each candle OPEN, before any new entry**, estimate after-cost
  liquidation equity as free cash plus net simulated SELL proceeds from
  any open long at the current historical open; at candle CLOSE after
  all known outcomes, mark equity again. This is NOT a guaranteed fill
  or observed bid/ask quote. It does not include all intrabar marks.
- Block new BUY entries when **marked** peak-to-equity drawdown >=12%,
  when loss from the last preceding UTC day's closing-equity anchor is
  >=3%, or when loss from the last preceding ISO week's closing-equity
  anchor is >=6%. Use UTC, not the computer's local timezone.
  **Crucially**, rollover uses the last *previous candle's CLOSE
  valuation*, not the first post-rollover OPEN: midnight gap losses
  must not disappear through anchor reset.
- These are entry restrictions, **not automatic kill-switch exits**;
  existing stop/target/EXIT logic continues while a long is open. Fixed
  simulated quantity grid 0.000001 base does **not** claim real Bybit
  quantity/tick/min-notional compliance.
- A matching strategy EXIT closes at the **next open**. Unrelated EXITs
  cannot close someone else's position; EXIT alone never opens a short.
- Stop/target are fixed to the confirmed signal's historical risk levels.
  At the OPEN a stop gap exits at the gap price (not a fake favorable stop
  fill). Inside a candle, low<=stop and high>=target is **ambiguous** without
  tick data; assume STOP first. An intrabar threshold fill at the specified
  price remains optimistic, with spread/slippage still applied.
- Positions still open after 16 bars exit on the next OPEN; positions at
  a development-fold boundary exit at the last candle CLOSE, tagged
  `FOLD_CLOSE_OPTIMISTIC`. This closure is an explicit optimistic
  approximation, not a live order. Fold trade reports include this
  event separately from real next-open exits.
- Each development fold begins independently with the specified bankroll.
  Returns are *not* compounded across folds; outcomes only belong to their
  own fold. Cross-fold/open-to-final-holdout orders are forbidden.

## Safety and missing capabilities

The last 20% of each continuous dataset is SHA-sealed **but never scored**;
new intrabar outcomes and accounting remain strictly inside chronological
development folds. Minimum 30 completed positions per fold before marking
a descriptive sample count sufficient; this does not establish independence
or statistical trading edge. No virtual executions go to `Store`, Paper,
SQLite, Bybit REST/WS, accounts, API keys or real orders.

The research module is **not** a faithful execution of the production
`Paper.execute` risk/protection worker: it does not simulate observed
bid/ask tapes, exchange symbol rules/minimums, complete risk planning,
intrabar marked-equity drawdowns, day/week risk across disconnected
historical segments, order lifecycle persistence, partial fills,
network outages, liquidation residues, overnight holds or concurrent
assets. The day/week guards now added are *offline approximations*
with model-cost after-liquidation marks, not the exact production
per-position Paper gate. This narrower scope is intentional for v0.9, with the limitations
documented in report JSON. Do NOT use hypothetical returns as a claim of
profitability or promote the model into real trading.

Tests check next-open chronology, gaps, same-bar STOP-first ambiguity,
target gaps, matching EXIT, fixed hold timeout, one-position allocation,
final seal invariance, no future signals, corrupt inputs, no overwrite and
full CLI integration. Physical Mac/Safari and authenticated Bybit
market/quote acceptance remain independent unfinished gates.

## Causal risk-gate reporting (research version 2)

Each fold also outputs `marked_equity_guards` with after-cost marked
peak drawdown, maximum daily/weekly anchored declines, current UTC
period anchors and counts of OPEN and CLOSE observations.
A missing mark, an out-of-order candle, or an invalid after-cost equity
must fail closed rather than silently yielding a risk-free entry.
`events.blocked_day_loss`, `blocked_week_loss` and
`blocked_drawdown` count rejected BUY candidates by gate priority.
`max_realized_drawdown_pct` remains as a separate legacy metric;
the *marked* measure is the one used at the OPEN entry gate.

This is **not** an exchange-verified risk estimate. There is no claim
that the OHLCV CLOSE can be liquidated at the modeled bid, nor that
the intrabar path is fully reconstructable. Frozen baseline rule
parameters remain unchanged; last 20% of each contiguous dataset
stays sealed. Tests enforce UTC rollover anchors, past-only entry
decisions, gap losses, count reconciliation and no live effects.
