# Архитектура rc2

База rc1 ZIP SHA256: b75143d7a132921959bebaba69693d9e3197977ea7cd05cca8dabcdc7fa7d231. Исходник не изменялся, работа в отдельной копии. Зависимости сохранены.

Market Data → analysis/lifecycle → quality.assess (advisory) → пользователь → orders.Prepare/Confirm → independent risk.plan → Paper transaction → ledger. costs.py является общей чистой Decimal-зависимостью risk/orders/paper/metrics/protect/UI. Сигналы не имеют submit. Lightweight Charts 5.2.1 продолжает работать через существующий Streamlit v2 component.

Конфигурация CostModel/QualityPolicy хранится в paper-state JSON. Прежние intent revisions теперь включают cost_model. Миграция schema 4 сохраняет все таблицы/записи и создаёт backup schema3. Она предотвращает чтение новой base-fee семантики rc1. Старые позиции читаются через legacy basis fallback; новые хранят явный cost_basis. Детали и ограничения: COST_ENGINE.md / ACCOUNTING_INVARIANTS.md.

Новых моделей прогнозирования/обучения нет. Точки для будущего Regime/Forecast/Decision остаются задачей следующего этапа, не готовым API.
