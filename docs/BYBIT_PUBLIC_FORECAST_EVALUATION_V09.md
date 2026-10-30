# CandlePath v0.9 — public Bybit SPOT historical verification

Status: experimental research. No orders, credentials, user portfolio/SQLite access or retroactive forecast publication.

## Official source

Bybit V5 Spot: https://bybit-exchange.github.io/docs/v5/market/kline

- Obtain the public Bybit server clock via GET /v5/market/time.
- Read GET /v5/market/kline with category=spot, exact symbol and interval, limit up to 1000 and inclusive end in milliseconds.
- The endpoint returns rows newest first; a currently open candle can have an unfinished close.
- Freeze the current exchange-time boundary and request only prior closed candles (end = current_candle_open_ms - 1).
- Iterate backward with end = oldest_open_ms - 1, checking each row, page, and continuity.
- Reject missing/stale latest candle, gaps, duplicates, wrong categories, wrong markets, unaligned UTC timestamps, malformed/nonfinite OHLCV, future candles and inconsistent high/low.
- Cap pages and requested history; never treat incomplete history as full evaluation.

## Run locally (with authorized public Bybit access)

    python scripts/evaluate_bybit_public_v09.py --symbol BTCUSDT --timeframe 15 --bars 1600

Optional report file (written only after verified success):

    python scripts/evaluate_bybit_public_v09.py --symbol ETHUSDT --timeframe 60 --bars 1600 --output eth-history.json

Report includes source identity BYBIT_V5_SPOT_PUBLIC_REST, server UTC timestamp, first/last candle, pages, count, SHA256 digest of normalized closed candles, and the EXISTING causal holdout forecast metrics. A PUBLIC_REST_HISTORY_VERIFIED status requires a successful actual public REST fetch plus validation. The report never claims profitable forecasts. Model remains Random Walk + EWMA, nominal 80% uncalibrated bands; median is flat.

## Five verification gates

1. **Source contract:** public HTTP/JSON V5 spot, exact category/symbol/interval, newest-first bounded pagination, no credentials.
2. **Causality/data quality:** closed candles only, strict UTC boundaries, missing/duplicate/corrupt/out-of-order/partial data fail closed.
3. **Math/provenance:** existing holdout replay only, never retrofit live forecasts; record UTC dates and SHA256; strict finite-safe JSON.
4. **Nonmutation and failure handling:** no Store or SQLite writes; network/403/451 or API errors exit explicitly as NOT VERIFIED, with no synthetic fallback.
5. **Independent CI and live probe:** full Python/JS/Node/Chromium test suite on actual PR head. A separate real Bybit public HTTP probe is diagnostic; if unavailable, GitHub reports that it was unverified even if CI tests are green.

## Limitations

This is retrospective analysis, not proof of a predictive edge or validated coverage. No direction model, BUY/SELL, real orders, or autonomous agent is activated. The public API may be restricted by network or geography; no circumvention will be attempted. macOS/Safari, actual WebSocket reconnection and prospective forecast calibration are separate release gates. Main remains unchanged.