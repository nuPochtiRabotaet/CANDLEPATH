# TEST REPORT — v0.8.2-rc3, 29 October 2026

Название файла TEST_REPORT_FINAL.md соответствует запрошенному артефакту; сборка **rc3, не FINAL и не v0.9**. Все результаты ниже относятся к реально запущенным проверкам. Это не независимая финансовая валидация стратегии.

## Выполнено

| Проверка | Фактический результат | Артефакт |
|---|---|---|
| Baseline rc2 | 291 passed, 24.50s | docs/rc3/baseline.txt |
| Итоговый pytest | 343 passed, 33.80s | docs/rc3/full-tests.txt |
| Четыре предоставленные регрессии | 4 passed, 0.09s; также входят в343 | docs/rc3/four-regressions.txt |
| Chromium Crypto | 32 сценария; JS errors: 0 | docs/rc3/browser/report.json |
| Chromium Invest | 12 сценариев / 16 layouts; JS errors: 0 | docs/rc3/invest/results.json |
| Сохранность кода вне Crypto | 56 файлов совпадают с сохранённым P0 baseline | docs/rc3/preservation.json |
| Launcher process | start/health/reuse/stop PASS, shell syntax PASS | docs/rc3/runtime.json |
| Реальный REST Bybit | HTTP200, HTML Site Unavailable, не JSON/retCode0 | docs/rc3/network.json |
| Реальный public WebSocket | не установлен: TimeoutError, timed out during opening handshake | docs/rc3/network.json |
| Production UI без fixture | Connection Lost, ноль свечей, actions disabled, zero JS errors | docs/rc3/production/report.json |

Тесты выполнялись на Linux/Python3.12/Streamlit1.66.1, реальный Chromium headless. Отдельная browser fixture использует явно подписанные искусственные OHLCV. Это не проверка подключения Bybit. Известный успешный запуск пользователя на Mac не опровергнут этим сетевым отказом.

## Полностью реализовано и проверено в указанной среде

- Paper inventory decomposition, Decimal base/quote fees, exact sell-available, retained residue/basis, no silent rounding or fabricated full exit, zero-cash writeoff with revision/freshness checks.
- Protective retries, obligation/attempt separation, idempotence, rules refresh, retry throttle, approved residue limit, stale-trigger recheck and rollback after posting failure.
- Active Stop/Target Preview→Confirm with risk/quote/rules/account guards, cancel, concurrency against partial/full exit, double-confirm and restart.
- Full-ledger Performance (beyond200-row display limit), closed positions vs exit orders, cost/P&L reconciliation, periods, sampled equity, unknown legacy metadata, explicit chosen signal and notes provenance.
- Persistent Ribbon/Glow/markers/intensity/reset; real chart zoom/scroll and state persistence across browser reload, BTC/ETH/SOL and all seven timeframes; four widths1024/1280/1440/1920.
- Typed research boundary and immutable experimental forecast journal/outcomes. No active forecast.
- Invest sandbox regression leaves actual journal unchanged; history loads once during measured sandbox actions.

## Частично реализовано / ограничения

- Assistant отделяет regime/lifecycle/quality/attention, но прогноз UNAVAILABLE. Partial Coverage не означает защиту всей позиции.
- MTM samples only after rc3 monitoring starts, at most once/minute plus fills. No tick history, incomplete points/gaps explicit, drawdown sampled. Irregular sparse series не используются для заявлений Sharpe/Sortino.
- Protection independent of browser tab only while Python process is running. Это не постоянный системный сервис; сон/выключение и отсутствие свежих данных прекращают эффективную защиту.
- Public REST/WS implementations preserved and protocol/error tests pass. Actual Bybit OHLCV/stream unavailable in this environment; no live-network success claim.
- Frozen decision contracts implemented. Independent model validation registry and actual ForecastEngine not implemented; VALIDATED publication rejected.

## Не реализовано

- Crypto predictive model, probabilistic Forecast Overlay, independently validated backtest/coverage/accuracy, LightGBM/XGBoost, autonomous virtual agent.
- Bybit Demo submit, Live submit, private order/execution reconciliation service, exchange-resident Spot TP/SL.
- OS Keychain integration, deployment as authenticated multi-user server, independent security/code audit.

## Требует Mac / доступа к API

- setup/start from Finder/Terminal on actual macOS ARM, Gatekeeper, Safari/Retina, fresh dependency install, migration of a COPY of user's ledger, sleep/wake and prolonged monitoring.
- Actual Bybit spot REST+WS/reconnect/backfill in user's permitted region/platform. Private Read Only requires owner's valid minimal-rights key; not tested here.
- Demo requires separately available supported demo account and adapter implementation/testing. Live requires separate review and explicit owner authorization; current build remains blocked.

## Замечания к процессу

Исходные четыре v0.8-регрессии уже проходили на baseline rc2; rc3 расширяет покрытие и исправляет новые сценарии остатка/редактирования, не приписывает себе прежние исправления. Миграционный тест обновляет только ожидаемую schema4→5. Новый тест aggregate risk сначала обнаружил Decimal(float) в самой проверке; исправлен на Decimal(str), деньги в implementation уже считались через строки. Условие старого теста refresh step/max не ослаблялось — добавлена явная согласованная граница residue coverage.

Browser selector для новой проверки настроек исправлен под shadow DOM компонента; результаты успешного повтора перечислены выше. Старые отчёты rc2 в docs/rc2/historical-root — история, не текущая приёмка.

**NOT READY FOR REAL FUNDS.** Net P&L на синтетической проверке — бухгалтерская сверка, не доходность стратегии.
