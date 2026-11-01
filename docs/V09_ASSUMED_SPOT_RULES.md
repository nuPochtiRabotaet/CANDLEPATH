# CandlePath v0.9: offline assumed Spot symbol-rule scenarios

**RESEARCH ONLY. USER_SUPPLIED_UNVERIFIED_HISTORICAL_RULE_ASSUMPTION.**
Do not interpret this file as evidence that Bybit had these exact rules,
fees, prices or available liquidity during an October 2026 trading day.
No live exchange endpoints, secret credentials, production Paper or real orders.

## Why this exists

An OHLCV-only strategy can show profitable hypothetical fills that would
not be accepted by a real Spot venue: quantity not aligned to step, stop or
target prices not aligned to tick, order notional below exchange minimum,
or purchased quantity not fully closeable after a base-denominated fee.
This optional, explicit **scenario filter** rejects such entries rather
than inventing executable orders. If the scenario cannot support a later
full exit (for example after a huge price gap below minimum notional), the
offline experiment **FAILS CLOSED** and outputs no fabricated net P&L.

## Example hypothetical research rules

Save a local JSON file (do not commit account details or credentials):
```json
{
  "symbol": "BTCUSDT",
  "step": "0.001",
  "tick": "0.01",
  "minimum": "10",
  "maximum": "100",
  "as_of_utc_seconds": 1793404800,
  "note": "Research example only; not validated for historical Bybit orders"
}
```
The numbers above are **fabricated solely for demonstrating the schema**,
NOT a statement of actual BTCUSDT exchange specifications.

Amounts:
- `step`: base-asset quantity increment
- `tick`: quote-currency price increment
- `minimum`: quote-currency minimum order notional
- `maximum`: base-asset maximum single order quantity
- `as_of_utc_seconds`: source snapshot timestamp; **metadata only**
- `note`: plain-text provenance explanation

All four numerical values **must** be finite positive decimal **strings**.
The source file must be bounded UTF-8 JSON with no extra/missing/duplicate
keys, symbol mismatch, nonfinite constants or ambiguous numeric float
conversions. Its raw SHA-256 is included in the research result, and
the input bytes are never modified.

## Evaluate together with saved raw Spot trade CSVs

```bash
python scripts/evaluate_spot_trades_csv_v09.py \
  --input ~/Downloads/BTCUSDT_2026-10-25.csv \
          ~/Downloads/BTCUSDT_2026-10-26.csv \
          ~/Downloads/BTCUSDT_2026-10-27.csv \
          ~/Downloads/BTCUSDT_2026-10-29.csv \
  --symbol BTCUSDT --timeframes 1 15 \
  --output-dir ~/Desktop/candlepath-rules-new \
  --evaluate --simulate-paper-paths \
  --paper-rules-file ~/Downloads/research-btc-rules.json \
  --assumed-spread-bps 4
```

Rules are **optional**; omitting `--paper-rules-file` retains the previous
default virtual-step-only v0.9 research without any assertion of exchange
acceptance. This flag cannot be used outside explicit
`--simulate-paper-paths --evaluate` mode.

## Historical limitations

We only validate against a declared hypothetical rule scenario. A timestamp
does NOT prove when an exchange enforced those rules. We neither fetch nor
authenticate actual symbol rules. Exchange rules may vary across days,
order types, account configurations and jurisdictions. A strict scenario
may reject every signal due to unrounded indicator stop/target levels;
that is a useful finding, not a reason to silently round stops using
future observations. Some future exits can become unexecutable even when
the entry passed its projected stop sellability check. Such an exit raises
`UNEXECUTABLE_RESEARCH_EXIT` rather than inventing sale proceeds. Marked
equity conservatively gives **zero recovery** when assumed rules prohibit
full liquidation. Dust is never implicitly written off.

This is still not a complete historical exchange execution backtest:
no observed bid/ask or order book; no actual fills, liquidity, partial
fills, latency, symbol metadata verification or guaranteed market
execution; no margin/leverage or shorts. Last 20% chronological
final holdout stays unscored; no model tuning, historical rule
verification claim, automatic trading or change to `main`.
