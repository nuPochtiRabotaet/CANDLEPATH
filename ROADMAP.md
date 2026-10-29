# Следующие этапы

- rc3 acceptance на Mac: миграция копии базы, Safari, размеры окна, сон/возврат, реальные REST+WS, обновление правил и долгий сеанс монитора. Не переносить тестовые котировки в production.
- v0.9 research: Random Walk/Historical Volatility baselines, causal crypto feature set, immutable published forecasts, chronological split + purging/embargo, walk-forward, финальная нетронутая выборка; эмпирическое покрытие, MAE/RMSE/pinball. Только после этого Forecast Overlay с границей истории и пометкой Experimental.
- v1.0: реалистичный бэктест next-available quote с fees/spread/gap/slippage, hold/random-walk comparators, sensitivity по режимам; optional LightGBM/XGBoost при доказанном улучшении baseline.
- v1.1: официальный Demo adapter, persistent reconciliation, partial fills/orderLinkId, duplicate WS events, account-specific fees/limits; автономная виртуальная торговля в отдельном режиме после тестов.
- v1.2: отдельно одобренный Manual Live Spot, независимый risk gate/kill switch, биржевые TP/SL, ключи минимальных прав, review региональной платформы и испытания. По умолчанию выключен; вывод средств/плечо не нужны.

До FINAL также требуются длительная эксплуатационная проверка, производительность на большом журнале и независимый review кода. Текущее имя намеренно v0.8.2-rc3, не v0.9 и не FINAL.
