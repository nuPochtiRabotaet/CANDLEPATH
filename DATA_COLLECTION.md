> rc2: новые Paper fills дополнительно сохраняют immutable execution.values/model, net_base, cash_delta и basis. Это локальные симуляционные записи, не реальные исполнения Bybit. Остальной документ описывает унаследованные механизмы сбора.

# Данные для будущих исследований

Сейчас реально сохраняются: historical/current candles с UTC timestamps/closed flag; неизменяемые confirmed signals и detected_at; lifecycle/notifications; paper balances/positions/orders/events/protective attempts; новые immutable preview payloads с quote snapshot, rules, риском и временем подготовки/подтверждения.

Непрерывная история L1 bid/ask, quote age, full depth orderbook, public trades, feature snapshots, published forecasts и будущие outcomes НЕ собираются. В памяти остаются текущие котировки/потоки. Это не готовый ML dataset; архив существующих свечей ограничен фактическими подписками и историей bootstrap/backfill.

Для v0.9 нужно до обучения: append-only UTC ingestion/event timestamps, symbol/venue/interval/schema versions, closed candle availability, indicator version/parameters/seed, вычисленный режим, источники bid/ask и их независимые timestamps, spread/gaps/reconnect events, precise order intent/fill/cost provenance, signal linkage и future labels после горизонта. Сохранять только наблюдённые значения, фиксировать missingness. Order Flow требует отдельного snapshot/delta reconstruction, sequence validation и bounded retention. Предпросмотры ручных действий не дают репрезентативного равномерного набора рынка.

Контракты Regime/Forecast/Decision пока описаны только в roadmap; новой обученной модели или работающего Forecast API нет.
