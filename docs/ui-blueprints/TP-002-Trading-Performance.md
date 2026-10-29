# TP-002 — Trading Performance

Цель: результат локальной практики по полному журналу, с прозрачными расходами и качеством данных.

## Layout

Свёртываемая область ниже терминала; toggle включает аналитику. Period tabs Всё /7д /30д /диапазон UTC. Четыре ключевые метрики: закрытые позиции, Net P&L, win rate, PF. Затем компактные поля costs/expectancy/holding/R и интерактивный Plotly equity chart высотой260px. Подробные закрытые позиции и strategy/TF в прокручиваемых таблицах. Снимок можно обновить кнопкой; кеш5с вне критического пути графика.

## Контракт

performance.report: consistent SQL snapshot всех orders, paper state, equity_samples. Несколько partial exits не создают несколько сделок. Cash и realized сверяются с ledger. Costs по времени fill; закрытые позиции по времени последнего выхода. Gross исключает только fees, net включает costs. PF undefined выводится как «—», не Infinity. Legacy неизвестные атрибуты остаются unknown.

## Состояния и ошибки

Пустой журнал: ноль закрытых, «—» для неопределённых метрик. Недостающие exits/cash metadata — warning неполной истории. MTM начинается с текущего мониторинга, нет ретроспективно выдуманной линии; stale points/gaps не соединяются. Sampled drawdown не обозначается как полный tick-level drawdown.

## Приёмка

360order fixture доказывает независимость от200-row display limit. Partial, residue/writeoff, restart, all/period, fee reconciliation проверяются. Source: crypto/performance.py, performance_ui.py, paper.py, storage.py; tests/test_performance_rc3.py. Screenshots ../rc3/browser/performance.png и equity-curve.png (QA, не реальная прибыль).

## Общие токены и ограничения

Chart #0D1519, panel #10191E, grid #33444C, text #D8E7E6, muted #839B9C, bull #31F3A2, bear #FF5474; glow #26FF99/#FF426B; candles #26B985/#D85168. Inter/system sans, 11–13px controls, 19–22px price, tabular figures, 6–16px gaps, 5–10px corner radii. Цвет всегда сопровождается текстом состояния. Стили scoped к Trade, Invest сохранён.

Приоритет — свечи. Desktop sidebar 290px (270px на узкой ширине), chart ~530px high, assistant independently scrolls. Assistant toggle даёт полную ширину графику. На 1024/1280/1440/1920 отсутствие горизонтального переполнения проверяется браузером. На ширине ≤680 панель переносится под график; это дополнительный layout, без заявления о полной мобильной приёмке.
