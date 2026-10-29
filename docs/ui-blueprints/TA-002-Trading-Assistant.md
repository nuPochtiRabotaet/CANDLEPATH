# TA-002 — Trading Assistant

Цель: дать пользователю отдельные оценки режима рынка, lifecycle, качества входа и требуемого внимания. Bullish не является BUY, No Trade не подменяет обязательный risk gate.

## Layout

Правая панель: regime + signal state; две компактные карточки Entry Quality / Attention; две причины; confirmation age/entry range/candle timer. Ниже optional notifications/explanations, затем quantity/amount, draft Stop/Target, risk, costs, preview buttons. Detail cost panel берёт Gross/Net RR, round-trip fee/cost, exit fee/slippage с сервера. Forecast: UNAVAILABLE до подключения проверяемой модели. Длинные сведения в details, а не в чат.

## Контракт и состояния

Sources: analysis.regime, lifecycle.active, quality_assessment, canonical plan, protection.status. POTENTIAL явно Awaiting Confirmation; EXPIRED/INVALIDATED не подаются как актуальная возможность. Реальный сигнал можно явно выбрать для журнала; ручной вход может быть без него. Пока server seq не совпадает с UI seq, значения показывают ожидание и BUY недоступен. Stale Bid/Ask и risk errors блокируют исполнение. No Trade по аналитической политике — предупреждение, а не выдуманный запрет любой ручной сделки.

## Приёмка

Ни один сигнал не вызывает submit. Buttons только prepare, отдельный consent+confirm. Timestamp и причины из алгоритма; нет процентов вероятности прибыли. Панель сворачивается. Source: crypto/quality.py, lifecycle.py, risk.py, intelligence.py, ui.py; components/trade.*. Screenshot ../rc3/browser/terminal-1440.png. Tests: quality/lifecycle suites + browser scenarios.

## Общие токены и ограничения

Chart #0D1519, panel #10191E, grid #33444C, text #D8E7E6, muted #839B9C, bull #31F3A2, bear #FF5474; glow #26FF99/#FF426B; candles #26B985/#D85168. Inter/system sans, 11–13px controls, 19–22px price, tabular figures, 6–16px gaps, 5–10px corner radii. Цвет всегда сопровождается текстом состояния. Стили scoped к Trade, Invest сохранён.

Приоритет — свечи. Desktop sidebar 290px (270px на узкой ширине), chart ~530px high, assistant independently scrolls. Assistant toggle даёт полную ширину графику. На 1024/1280/1440/1920 отсутствие горизонтального переполнения проверяется браузером. На ширине ≤680 панель переносится под график; это дополнительный layout, без заявления о полной мобильной приёмке.
