# Assistant 2.0 — basic, rc2

Четыре состояния показаны отдельно: Market Regime, Signal Lifecycle, Entry Quality, Attention. Причины и actual confirmed_at/age доступны в правой панели. Expired/Invalidated не дают активного диапазона входа. No Trade не означает запрет любой ручной операции: независимый Risk Manager остаётся обязательным серверным шлюзом.

Чистая `quality.assess` использует версионированный QualityPolicy. Настройки minimum Net R/R и maximum spread сохраняются вместе с Paper assumptions. Машиночитаемые причины: STALE_QUOTE, INVALID_PLAN, RISK_REJECTED, EXIT_PRECISION, LOW_NET_RR, WIDE_SPREAD, SIGNAL_EXPIRED, PRICE_DRIFT, AWAITING_CONFIRMATION, EDGE_NOT_VALIDATED.

Проверены Bullish + No Trade, Confirmed с отрицательным net R/R, stale bid/ask, expired/no signal, drift и отсутствие статистического преимущества. Никакой score не называется вероятностью. Статистическая стратегия не валидирована: Statistical edge not validated виден постоянно.

Basic, не финальный Assistant: правая панель ещё требует прокрутки; рассчитанные gross/net/cost breakdown доступны через server data, но не все сведены в отдельный компактный UI. Trade statistics и signal selection/linkage ещё не закончены. История стратегий не была переоптимизирована; поля формирования сигналов сохранены, изменена лишь поясняющая строка об издержках.
