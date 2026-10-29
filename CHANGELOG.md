# v0.8.2-rc3 — 29 October 2026

- Preserve Invest, MOEX data, existing Bybit connector and manual-only boundary.
- Separate net holdings / sellable / residue; retain proportional basis after exact sell-available; explicit writeoff has zero cash recovery.
- Protection retry respects approved residue coverage; fresh-rule recovery, old-trigger recheck and rejected-posting rollback.
- Active Stop/Target prepare/cancel/confirm with transactional revisions, current quote/risk/rules guards, no trade created by editing.
- Full-ledger Performance, closed-position aggregation, fee/slippage transparency, sampled MTM and realized equity, UTC filters, strategy/timeframe groups.
- Explicit signal and notes provenance; state at preview and actual fill recorded separately; unknown legacy metadata remains unknown.
- Persistent Ribbon/Glow/BUY-EXIT/intensity settings, reset, collapsible Assistant; scale-attached primitive and chart instance retained.
- Typed research contracts, UNAVAILABLE forecast state, append-only experimental forecast/outcome journal; no model or backtest fabricated.
- Pinned six-module Day Trader Skill review, MIT notice, source hashes, adaptation constraints; no upstream script installed/executed.
- Additive Crypto schema 5 with v4 backup. New checks and real browser screenshots in docs/rc3.

This is a tested intermediate release, not FINAL. Demo/Live/ML forecast remain unavailable. See TEST_REPORT_FINAL.md for evidence and limitations.

---

# v0.8.2-rc2 — Cost Integrity / Assistant basic

- Общий Decimal Cost Engine, versioned fee snapshots, quote/base BUY, quote SELL, net inventory/cost basis и partial realized allocation.
- Notional vs all-inclusive budget; изменение тарифа аннулирует preview, total cap перепроверяется при Confirm.
- Риск/monitor/metrics/UI используют общий расчёт; JS-дубликат денежной формулы удалён.
- Quality Policy и четыре независимых статуса Assistant; No Trade advisory, без выдуманных вероятностей.
- Сокращённый modal, исправлены раннее закрытие Cancel и скрытие поля суммы; QA маркировка.
- Schema 4 с backup .before-rc2, старые записи не переписываются. В прежнем migration test обновлено только ожидаемое число схемы.
- Это rc2, не FINAL: active protection updates, journal/statistics, signal selection и typed predictive contracts ещё отсутствуют.

# v0.8.2-rc1 — 28 октября 2026

Промежуточный проверенный этап, не финальная приёмка полного ТЗ v0.8.2.

- Chart-first Trade без левой навигации, возврат Invest, отдельный amount/quantity ввод.
- Серверный manual Prepare/Confirm/Execute для BUY/SELL/full close; immutable TTL preview, consent, повторная проверка quote/account/rules/risk, atomic idempotency.
- Действующее окно подтверждения по Design Bible, quote provenance, цена/комиссия/риск/границы.
- Crypto migration v3 с backup и сохранением ledger; monitor health/last_success; Security Center Preview.
- Сохранены v0.8.1 protection/dust/rules/freshness fixes и lifecycle. Новых зависимостей нет.
- Maker/Taker/Base commissions, Assistant 2.0, новая trade statistics и predictive contracts пока не реализованы.

# 0.8.1 — 2026-10-28

Проверенный этап Reliability & Signal Lifecycle: четыре независимые регрессии, persistent protective retries, dust prevention и явное списание старых виртуальных остатков, Spot orderbook.1 с независимыми timestamps, периодическое обновление правил, локальный монитор защиты, lifecycle/expiry/entry zone, уведомления, schema v2 и backup. Invest сохранён. Forecast, Maker/Taker rework, Demo/Live — не реализованы. Подробности FIXES.md и TEST_REPORT.md.

# CHANGELOG

## 0.8.0 — 2026-10-27

Добавлено пространство Trade в существующий MOEX Intelligence v0.7.1. Invest, портфель, инвестиционная лаборатория, финансовые цели, модели, Reader/Time Machine/MCP сохранены.

- Bybit V5 spot REST/WS: BTC/ETH/SOL, семь интервалов, UTC, кэш, backfill, дедупликация и контроль закрытых свечей, ограниченные подписки, heartbeat/reconnect/stale gating.
- Lightweight Charts **5.2.1** встроен локально с лицензией: свечи, объёмы, crosshair, zoom/scroll, динамические линии, native scale-bound Trend Ribbon, v5 `createSeriesMarkers`, tooltip объяснений, четыре пресета и отдельные слои.
- EMA, Wilder ATR/RSI/ADX, Supertrend, Bollinger; формульный regime classifier и три версионированные стратегии. Подтверждённые сигналы только на закрытых свечах, стабильные ID и detected_at. Повторяющиеся BUY продолжающегося пробоя устранены.
- Компактный Trading Assistant, мгновенный предварительный расчёт количества/издержек/риска, серверная проверка, перетаскиваемые Stop/Target, уровни виртуальной позиции.
- Независимый Aggressive Risk Profile: лимиты риска/капитала, позиции, дневной/недельный убыток, просадка. No short/leverage/averaging.
- Отдельный SQLite paper ledger, атомарные UUID-заявки, частичное/полное закрытие позиции, комиссии, bid/ask и проскальзывание, P&L и защитные виртуальные уровни. FSM и интерфейс будущей сверки исполнений.
- Опциональный server-only Private Read Only UNIFIED; allowlist GET и выходных полей, обязательная проверка прав. Реальное создание заявок отсутствует.
- Новая точка резервного копирования before-v0.8, отдельная crypto schema v1. Явный pin уже существующего websockets 17.3; версии остальных Python-зависимостей сохранены.
- Добавлены количественные, протокольные и браузерные проверки, диагностика Bybit, документация и реальные скриншоты QA.

Ограничения выпуска: Bybit из среды сборки возвращает `Site Unavailable`; успешный live feed не подтверждён. Private/Demo не проверены с аккаунтом; Bybit Demo adapter не активирован, доступна локальная альтернатива. Нет модели биржевой очереди/частичных market-fill; есть частичное закрытие позиции. Полный отчёт — TEST_REPORT.md.
