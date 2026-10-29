# Архитектура rc3

Приложение остаётся Streamlit. `app.py` → существующий Invest или `crypto.ui.page`. Инвестиционные портфель, лаборатория, Advisor и `time_machine_core` сохранены. Тема Invest не изменена. Карта базовых модулей v0.7/v0.8 — в исторической документации `docs/`.

## Границы Crypto

Market Data (`market.py`, REST + управляемый WS Hub) → Indicators/Strategies (`analysis.py`) → Lifecycle (`lifecycle.py`) → Quality / Risk (`quality.py`, `risk.py`) → Preview (`orders.py`, `protection.py`) → Local Paper (`paper.py`) → SQLite (`storage.py`). Аналитика не вызывает исполнение. Frontend не получает API Secret и не определяет денежный результат.

| Модуль | Обязанность rc3 |
|---|---|
| inventory.py | Decimal decomposition; executable quantity, residue, basis, sale constraints |
| costs.py | Canonical taker fills, bid/ask once, slippage, base/quote fees; historical snapshot |
| orders.py | Immutable 30-second order preview, exact account/rules/profile guards; chosen signal and notes |
| protection.py | Prepare/cancel/confirm existing levels under BEGIN IMMEDIATE; no order on editing |
| paper.py | Atomic financial posting, retry attempts, no duplicate fill, rollback on failure |
| monitor.py | Process-scoped worker independent of open browser; Partial Coverage / Degraded status |
| performance.py | Full-ledger aggregation + periodic observed equity, coherent SQLite read snapshot |
| performance_ui.py | Opt-in report outside per-second chart fragment; five-second cache and explicit refresh |
| preferences.py | Strict UI schema; persisted separately from financial state |
| intelligence.py | Frozen RegimeSnapshot, Forecast/Point, DecisionContext, ForecastEngine Protocol; UNAVAILABLE default |
| components/trade.* | Lightweight Charts 5.2.1 component; time/price coordinate primitives, markers, editor drafts |

## Storage and migration

Crypto database is separate from MOEX ledger. Schema 4→5 creates a SQLite backup before additive migration. Existing orders and cash JSON are not rewritten. New rows: `equity_samples`, `ui_preferences`, `forecasts`, `forecast_outcomes`. Metadata is attached prospectively to new BUY fills; legacy metadata stays unknown. Forecasts/outcomes have SQLite update/delete guards. Publishing is idempotent by ID and content; different content for the same ID is rejected. Publication after a target has elapsed is rejected. `VALIDATED` publication is blocked until an independent validation registry exists.

## Concurrency and protection

Order and protection commits use BEGIN IMMEDIATE. An edit preview snapshots position identity/revision, account, rule revision, profile, cost assumptions and quote. Partial/full exit or another accepted edit invalidates it. A monitor that selected an old obligation rechecks position identity and current stop/target under the execution lock. Rejected execution restores the pre-posting financial state.

Protective obligation identity is distinct from attempt UUID. Retries have leases/backoff; rule changes can permit retry. Approved residue coverage is stored at BUY or protection confirmation. Changed rules cannot silently expand an unprotected remainder. Successful sale of available quantity does not erase owned residue. Aggregate stop risk includes zero recovery of unexecutable amounts; missing rules conservatively provide no assumed proceeds.

## UI and performance

One chart instance survives fragment updates. Incremental candle updates retain scales; primitives derive coordinates from the chart. Settings changes never reload history. Market subscriptions remain in the existing Hub. The chart fragment runs every second; this is not a browser-only streaming engine. Full indicator recalculation/cache still exists: seed checkpoint optimization is future work, not claimed implemented.

Performance reads all orders, not Store.orders()'s 200-row display window. MTM snapshots are throttled to one minute and captured on executions; they are not tick-by-tick. No interpolation across outages. Snapshot analytics may be five seconds old; refresh explicitly after inspecting trades.

## Future research/execution

ForecastEngine accepts causal closed candles and emits a typed Forecast. Existing investment Time Machine uses daily bars; a crypto intrabar adapter and independent validation are required before reuse. DecisionContext separates market regime, lifecycle, quality, risk and forecast. It exposes no submit method. No new dependencies or external day-trader scripts are installed.

LocalPaper is the only execution implementation enabled. Read Only is isolated. Demo/live adapters, authenticated exchange reconciliation, exchange TP/SL and independent delivery service are future stages; the existing pure reconcile_order function is a boundary test, not a working private execution service.
