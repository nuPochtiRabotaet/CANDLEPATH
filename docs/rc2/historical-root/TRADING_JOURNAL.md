# Журнал — статус rc2

Существующий журнал Paper и история заявок сохранены. Новые fill-записи содержат immutable снимок тарифа/assumptions, фактические fee currency/quantity/quote value, net received, cash_delta, allocated_basis для SELL, источник и quote provenance. Они доступны в исходной SQLite базе и через данные UI; старые fees и P&L не изменяются при настройке нового тарифа.

НЕ завершены: новый журнал завершённых экономических позиций, статистика win rate/expectancy/profit factor/max drawdown по определённой equity sequence, notes/фильтры/детальная карточка и передача конкретного пользовательски выбранного signal ID через preview. Существующие счётчики стратегий — количество сигналов, не доказанная доходность. FINAL требует отдельного этапа Journal & Performance; в этой сборке он не заявлен.
