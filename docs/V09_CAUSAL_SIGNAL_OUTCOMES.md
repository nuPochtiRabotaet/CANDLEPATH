# CandlePath v0.9 — offline BUY-signal outcome diagnostic

**Research-only. No orders, no positions, no trading P&L claims.**

## Purpose
Previously v0.9 evaluated statistical price envelopes (Random Walk and
shrunk momentum). This is a separate diagnostic of the **actual existing**
chart indicator rules: Trend Following, Mean Reversion, Breakout Detection.
All code executes offline on user-supplied, validated Spot OHLCV candles.

## Reproducible research command
Starting from the v0.9 development branch containing this implementation:

```bash
python scripts/evaluate_spot_trades_csv_v09.py \
  --input ~/Downloads/BTCUSDT_2026-10-25.csv \
          ~/Downloads/BTCUSDT_2026-10-26.csv \
          ~/Downloads/BTCUSDT_2026-10-27.csv \
          ~/Downloads/BTCUSDT_2026-10-29.csv \
  --symbol BTCUSDT --timeframes 1 15 \
  --output-dir ~/Desktop/candlepath-signal-audit-new \
  --evaluate --compare-momentum --audit-signals \
  --assumed-spread-bps 4
```

Choose a NEW output directory for every run; writes are exclusive-create.
No trade CSVs or user data are committed to GitHub. Provenance stays
`USER_SUPPLIED_TRADE_CSV_UNVERIFIED`; no Bybit auth/API calls.

## What is actually measured

- Uses the existing exact `analysis.analyze()` signal rules and current
  `CostModel` (default 10 bps taker commission **per side**, 5 bps
  slippage **per side**).
- BUY confirmed at candle `i` close may enter hypothetically only at
  **next candle (i+1) open**; EXITs are only counted, never shorted.
- Measures a fixed holding period of `h = 1,2,4,8` bars, exiting at
  candle `i+1+h` **open**. Both sides use next-available historical OPEN
  prices, never the signal close as a fictitious executable fill.
- Calculates gross open-to-open percent movement and hypothetical net
  percent outcome by applying the **same estimate function used by Paper**.
  An assumed full bid-ask spread is symmetric around the observed OHLCV
  open; this is NOT an actual quote. Default `0` bps spread is explicitly
  optimistic. Pass a positive sensitivity such as 4 bps to explore risk.
- Outputs separate fold/strategy/horizon counts, positive gross/net samples,
  mean gross/net, net median, min/max, and count-based sample sufficiency.
  The samples are overlapping signal outcomes and are **not independent**.
- A single BUY signal is not a filled trade and does not allocate capital,
  account for stop/target fills, concurrent positions, order sizing, partial
  executions, the actual EXIT logic or portfolio drawdown. These missing
  contracts are intentionally **not** smuggled into v0.9; a full executable
  next-available-quote simulation remains a later milestone.

## Causality and data integrity

- Splits continuous blocks at missing days/minutes with no fabricated data.
- Reuses the existing three-fold `evaluate_purged_walkforward` boundaries.
  Each rule engine invocation is limited to one fold's history `[:end]`,
  never the final sealed 20%. Signal discovery is left-to-right causal.
- Observations crossing a fold's right boundary are **discarded**, not scored
  against the following fold or sealed holdout.
- Final data SHA-256 must match existing baseline's sealed fingerprint.
  Mutating final-holdout prices must not alter any development-fold result.
- If signal counts are sparse or fold history inadequate, status is
  `INSUFFICIENT_SIGNAL_SAMPLE` or `INSUFFICIENT_FOLD_HISTORY`.
  Count-based sufficiency (>=30 per strategy/horizon/fold) is NOT
  statistical independence or proof of an edge.

## Interpretation
Even a positive average outcome does not establish a strategy's value:
OHLCV-only fills are hypothetical, bid-ask assumptions uncertain, and
losses/volume/fees may change. Do not calibrate thresholds on these dev
folds then score the *same* folds as unseen. Freeze rules before releasing
the final holdout and obtain new market history.

**The live rule engine, live forecast overlay, paper portfolio, immutable
forecast journal and trading controls remain unchanged. Real trading
stays hard-disabled.**
