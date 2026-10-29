# TR-002 — Intelligent Trend Ribbon 2.0

Цель: компактное отображение causal-направления над/под ценой без изменения алгоритма ради картинки. Источник — analysis.overlay (EMA/ATR/Supertrend/режим). Зелёная/розовая лента строится по time/price координатам серии, а не абсолютным экранным точкам. Нейтральное направление не рисуется.

## Layout и взаимодействие

Основная зона свечного графика, preset toolbar сверху, тонкая строка toggles снизу. Ribbon/Glow/BUY-EXIT независимы. Intensity 0–100, step5, default85; фактическая alpha = 0.38 × intensity/100. Glow radius =12 × intensity/100. Меню style также содержит толщину 1–4px, opacity линий и цвета EMA. Reset восстанавливает серверные defaults. Preferences сохраняются в отдельной таблице SQLite и применяются к инструментам/TF и новому сеансу.

## Состояния и ошибки

Отключённый слой действительно удаляет markers/скрывает primitive, candles сохраняются. Clean — только рынок. Stale/Connection Lost сохраняет доступную историю с предупреждением, выключает торговые действия. Нет истории — пустая зона с ожиданием. Никаких выдуманных BUY/SELL. SELL означает EXIT long, не short.

## Приёмка

Chart instance/viewport сохраняются при обновлении и toggles; zoom и scroll работают. Цена/время привязаны к шкалам при resize. Settings survive reload/symbol/TF. Реальные скриншоты: ../rc3/browser/terminal-1024.png, terminal-1280.png, terminal-1440.png, terminal-1920.png (QA synthetic, явно подписаны). Проверки: scripts/verify_rc3_browser.py, tests/test_preferences_rc3.py.

Source: components/trade.js OverlayPrimitive/layers/readPrefs, trade.html, trade.css; crypto/preferences.py, crypto/ui.py. Использован vendored Lightweight Charts5.2.1, createSeriesMarkers и series primitive; официальный API https://tradingview.github.io/lightweight-charts/docs/plugins/series-primitives.

## Общие токены и ограничения

Chart #0D1519, panel #10191E, grid #33444C, text #D8E7E6, muted #839B9C, bull #31F3A2, bear #FF5474; glow #26FF99/#FF426B; candles #26B985/#D85168. Inter/system sans, 11–13px controls, 19–22px price, tabular figures, 6–16px gaps, 5–10px corner radii. Цвет всегда сопровождается текстом состояния. Стили scoped к Trade, Invest сохранён.

Приоритет — свечи. Desktop sidebar 290px (270px на узкой ширине), chart ~530px high, assistant independently scrolls. Assistant toggle даёт полную ширину графику. На 1024/1280/1440/1920 отсутствие горизонтального переполнения проверяется браузером. На ширине ≤680 панель переносится под график; это дополнительный layout, без заявления о полной мобильной приёмке.
