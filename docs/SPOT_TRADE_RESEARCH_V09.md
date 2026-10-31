# CandlePath v0.9: offline SPOT trade-history research

Read-only, user-supplied, *unverified-origin* trade exports. Never identifies
them as authenticated Bybit exchange responses. No networking, API keys,
user database writes, paper or real trades, or retrospective live publication.

## Inputs

Daily UTF-8 CSV: `BTCUSDT_YYYY-MM-DD.csv` with exactly these headers:

```csv
id,timestamp,price,volume,side,rpi
```

- `timestamp`: Unix UTC milliseconds. Trades are ordered chronologically;
  tied millisecond executions preserve original file order.
- `volume`: base asset quantity (BTC for BTCUSDT), not USDT notional.
- `id`: consecutive within each daily export, to detect missing/duplicated
  raw records; IDs may restart across files.
- `side`: Buy/Sell; `rpi`: 0/1.
- Each source must match the day in its filename; malformed or implausible
  records fail instead of silently disappearing.
- Filenames, columns, IDs and checksums cannot independently prove Bybit
  provenance. Retain the original downloads.

## Run on your Mac (v0.9 branch containing this PR)

In the checked-out repository:

```bash
python scripts/evaluate_spot_trades_csv_v09.py \
  --input ~/Downloads/BTCUSDT_2026-10-25.csv \
          ~/Downloads/BTCUSDT_2026-10-26.csv \
          ~/Downloads/BTCUSDT_2026-10-27.csv \
          ~/Downloads/BTCUSDT_2026-10-29.csv \
  --symbol BTCUSDT --timeframes 1 15 \
  --output-dir ~/Desktop/candlepath-research-october \
  --evaluate --compare-momentum
```

Choose a **new output directory** for each run. The script never overwrites
existing candle CSVs or JSON reports. The original large trade CSVs remain
local; they are not added to Git or uploaded by the script.

This produces separate **continuous** OHLCV CSV files and one
`BTCUSDT_spot_trade_research.json` report. The absent **2026-10-28**
is never interpolated, and output files never cross it. Any missing minute
splits the 1m series; a 15m bar is only emitted when all 15 contributing
minute buckets are present.

With `--evaluate`, each continuous segment is re-read using the existing
strict `read_local_ohlcv()` validator, then passed to the actual
`evaluate_purged_walkforward()` implementation. Development folds are
historical and use only previously available candles. The last 20% of each
segment remains **SEALED_UNSCORED**. If a segment is too short (typically a
15-minute segment of a few days), it is reported as
`INSUFFICIENT_HISTORY` or `INSUFFICIENT` — never labelled successful.

No result establishes profitable execution, predictive skill, authenticated
market origin or calibrated confidence. The local source has not come through
Bybit's currently inaccessible public REST API.

## Validation and tests

```bash
python -m pytest tests/test_spot_trade_import_v09.py -q
```

CI also runs all existing Python tests, JavaScript geometry contracts and
a Chromium smoke test. Synthetic tests cannot authenticate any uploaded
source history. No raw user-supplied market files are committed.

## Paired directional challenger (optional)

The `--compare-momentum` flag requires `--evaluate`, computes the already
implemented **fixed, shrunk log-momentum candidate** against the flat Random
Walk median for the same continuous offline market segment, on the same
chronologically separated development folds. Every origin supplies both
models only the previous 120 CLOSED candles. Neither sees outcomes from
the last 20% sealed final holdout.

The output JSON contains a `directional_research` section per evaluated
segment: paired MAE, percentage MAE gain, interval score, empirical coverage,
directional hit fraction with descriptive Wilson bounds, fold origins, and
matching sealed-holdout SHA-256. Segments too short for a meaningful
walk-forward are **not promoted or labeled successful**.

**Interpretation:**
- Positive candidate MAE gain = lower absolute forecast error on that fold,
  not profitable trades or reliable directional accuracy.
- A 51% direction hit rate does not prove an advantage, especially after
  fees, spread, slippage, repeated hypothesis testing and market dependence.
- Contradictory folds or another session with negative gain are reasons to
  investigate robustness, not to cherry-pick.
- The new result explicitly says `RESEARCH_ONLY_NOT_APPROVED`, with
  `trading_edge_verified:false`. No live model, signal or paper trade changes.
- This is not the prospective final holdout evaluation. Never use the sealed
  20% for tuning; lock the candidate and study protocol before final scoring.
