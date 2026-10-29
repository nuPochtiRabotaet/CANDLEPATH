# TEST REPORT — v0.8.2-rc2 · 28 октября 2026

Проверенный промежуточный этап Cost Engine + Assistant basic. Не v0.8.2 FINAL и не v0.9. Текущие результаты находятся в docs/rc2; отчёты прежних версий в архиве являются историческими.

## Реально выполнено

- Восстановленный неизменённый rc1: **263 passed in 41.59s**, docs/rc2/baseline.txt.
- Финальный полный pytest rc2: **291 passed in 37.10s**, docs/rc2/full-tests.txt. Добавлено 28 случаев. Прежние тесты не удалялись. Единственная правка существующего теста — ожидаемая версия SQLite 3→4; проверки сохранения данных сохранены.
- Новые проверки: BUY fee quote/base; net quantity; отсутствие двойной комиссии; стоимость частичной/полной продажи; conservation of basis; изменение тарифов без переписывания прошлых fills; amount 25 notional и total; превышение total при изменении цены; atomic preview revalidation; legacy migration; защита с net quantity/новым тарифом; fractional fee dust без фиктивного Filled; liquidation equity; Maker не применяется к Market; режим Bullish с No Trade, stale/expired/drift и policy validation.
- Crypto UI: **18 сценариев, 0 JS errors**, финальный результат в docs/rc2/browser/report.json. Реальный Chromium/Streamlit, явно синтетическая QA-фикстура. Проверяются подтверждение, отмена/Escape, 25 USDT total cap, BUY/partial/full SELL, base fee UI → ledger, lifecycle, слои/zoom, сохранение chart instance, stale gate, возврат Invest. Четыре ширины: 1024/1280/1440/1920; график больше половины экрана, без горизонтального overflow.
- Invest: неизменённый verify_v071_browser.py — **12 проверок, 16 layouts, 0 JS errors**, docs/rc2/invest-browser/results.json. Journal unchanged; history_loads=1. Проверены НКД облигаций, Decimal fee, sandbox reset, Advisor, импорт/дубликаты и смена journal revision.
- Launcher: настоящий start/health/reuse/stop и bash syntax — PASS, docs/rc2/runtime.json. Это Linux x86_64, не физический Mac.
- Production app.py: реальный Chromium, Connection Lost, 0 свечей, отключённые действия, 0 JS errors — docs/rc2/production/report.json.
- Сохранность: docs/rc2/preservation.json сравнивает проект с исходным ZIP SHA256 b75143d7a132921959bebaba69693d9e3197977ea7cd05cca8dabcdc7fa7d231. Ни одного исходного файла не удалено. Инвестиционные финансовые модули, workbench и Invest UI не менялись; компоненты trade и версия пакета изменены.

## Сеть, отдельно от QA

Настоящий REST Kline: HTTP 200, но HTML Site Unavailable, не JSON/retCode=0. Настоящий WebSocket: InvalidStatus, HTTP 200 вместо protocol upgrade. Обе попытки записаны в docs/rc2/network.json. Подключение к реальному рынку в этой среде **не подтверждено**. Это не опровергает успешную работу на Mac пользователя. Production не подменяет отсутствующий рынок QA-данными.

Приватный аккаунт, реальные комиссии аккаунта, Demo и Live не тестировались. Fee assumptions названы LOCAL PAPER; mock/protocol tests не считаются проверкой фактической доступности биржи.

## Ограничения и статус

| Статус | Содержание |
|---|---|
| Реализовано и протестировано | Decimal Cost Engine end-to-end, quote/base BUY fees, quote SELL, Market taker, basis/net inventory/P&L, immutable fee snapshot, notional/total budget, миграция, basic Assistant/Quality Policy, прежние защитные retry/market gates |
| Частично | Assistant ещё прокручивается; не все cost breakdown сведены в компактный UI. Maker — конфигурация будущего Limit, не исполнение. Base fee может оставить некратный step остаток: есть предупреждение/No Trade и честный отказ выхода, но нет полного управляемого dust UX |
| Не реализовано | Новый журнал закрытых сделок/статистика, явный выбор signal ID, подтверждаемая правка действующих Stop/Target, typed Forecast contracts, прогноз/ML/бэктестинг, Demo execution |
| Требует Mac | Finder/Gatekeeper, arm64 install, Safari, sleep/resume, длительная работа монитора, уведомления |
| Требует Bybit | Живые REST/WS и recovery на доступной платформе, actual private fee/balance, соответствие rules/precision аккаунту |
| Реальные средства | **NOT READY**. Никаких Demo/Live/autonomous заявок; локальная защита не биржевой стоп |

При base fee математическая stop-оценка может не соответствовать исполнимому количеству. Preview явно предупреждает, но ручной LOCAL PAPER BUY всё ещё возможен с согласием; это ограничение rc2, не готовая безопасная модель реальной биржи. Монитор не работает при остановке процесса или отсутствии свежего рынка.

## Воспроизведение

```bash
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_rc2_browser.py /path/to/chromium
.venv/bin/python scripts/verify_v071_browser.py --chromium /path/to/chromium --output docs/rc2/invest-browser
.venv/bin/python scripts/verify_rc2_network.py
PYTHONPATH=. .venv/bin/python scripts/verify_rc2_runtime.py
```

Screenshots: docs/rc2/browser (реальный UI, синтетический QA рынок), docs/rc2/invest-browser; production — реальная ошибка доступа. Браузерная проверка выявила нестабильное открытие dropdown валюты комиссии в Streamlit 1.66.1; отказ сохранён в browser-initial-failure.txt. Контрол заменён двумя явными radio-вариантами quote/base. Проверяется выбранный вариант и фактически сохранённый fee currency, без ослабления assertion.
