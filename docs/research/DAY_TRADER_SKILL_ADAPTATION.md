# Day Trader Skill: исследование для MOEX Intelligence

Проверено 29 октября 2026. Репозиторий: https://github.com/Jakeschincariol/day-trader-skill

Зафиксирован commit **3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd** (20 октября 2026). Это обзор конкретного исходного кода, не проверка прибыльности. Код получен через GitHub; сторонние скрипты не запускались и не установлены в MOEX. MIT License, Copyright (c) 2026 Jake Schincariol; полный текст сохранён рядом в DAY_TRADER_SKILL_LICENSE.txt. Ни исполнение брокера, ни ключи не заимствованы. При будущем копировании существенных частей кода нужно сохранять уведомление MIT; этот релиз использует собственные реализации.

## Компоненты и решение

| Компонент | Найдено в исходниках | Сопоставление с MOEX | Решение |
|---|---|---|---|
| trader-timemachine/timemachine.py | Slot-conditioned OHLC bootstrap, 10 000 paths, seed 19, TP/SL/Neither, replay ORB | time_machine_core/simulator.py уже имеет reproducible block bootstrap/GBM, сценарии и издержки на дневных закрытиях | Перенести исследовательскую идею intrabar barrier replay; новый адаптер данных/горизонтов, не импорт CLI |
| trader-entry/entry.py | Только закрытые 1m/5m бары, breakout opening range / level, waiting/triggered/expired/no-data, volume threshold | crypto.analysis + lifecycle уже имеют POTENTIAL/CONFIRMED/expiry и времена доступности | Сохранить нашу систему; полезны отдельные контрактные tests входного окна и запаздывания |
| trader-exit/exit.py | OR midpoint/low, price, pct, ATR stops; цели R; cents rounding; flat-by NYSE | Cost Engine + Risk Manager + ProtectionPreview | Не копировать cent rounding/15:55; идеи сравнения stop rules — исследование, не автоматическая правка защиты |
| trader-risk/check.py | Независимые причины PASS/BLOCK; cash/position/trade count; окно сессии; bracket format; fingerprint | Независимый risk.py, quote_ok, atomic OrderPreview, immutable UUID | Не заменять. У нас Spot Decimal и свежие Bid/Ask; в upstream price_times=None считает переданные цены свежими, что неприемлемо для нашего execution gate |
| trader-budget/size.py | Объяснение ограничивающего лимита, whole-share sizing, max(plan, fresh price), min-R/R | budget_quantity, plan, total cap и net fees | Адаптировать только формат объяснения binding constraint; не переносить whole shares/float-cent arithmetic |
| trader-scanner/scan.py | Nasdaq universe, Yahoo spark batch of 20, daily patterns, ORB candidate→OHLC confirmation, partial result counts | Три spot-инструмента и прямой Bybit public stream | Сейчас не требуется сканер тысяч US stocks; полезен контракт качества/неполноты данных |

Все шесть Python CLI используют стандартную библиотеку; у MOEX уже есть NumPy/Pandas. Новых зависимостей не добавлено. Для текущего обзора не проверялись брокерный адаптер и весь upstream test suite. Локальные `trader/*.json` — последовательный обмен результатами CLI, а не транзакционный журнал биржевых исполнений.

## Методология Time Machine — что именно делает код

`parse_bars` отбрасывает незакрытые, off-grid и отсутствующие бары, ограничивает время данными и заданным now. `full_sessions` использует только дни строго раньше даты плана, с полными 78 пятиминутными барами 09:30–16:00 New York; неполные сессии исключаются. Минимум 20 сессий. `build_pool` нормирует OHLC бара на предыдущее закрытие. `simulate` для будущего слота выбирает соседний слот ±window (по умолчанию 2) и независимо выбирает прошлый бар. RNG локальный, seed явный; воспроизводимость требует также неизменного исходного пула и версии алгоритма.

Это сохраняет приблизительный внутридневной профиль по времени, но не последовательность блоков доходности и не кластеризацию волатильности между выбранными барами. Коэффициент открытия хранится в пуле, однако в симуляции барьеры проверяются по high/low, а путь продолжается close; отдельной модели исполнения gap нет.

Если оба барьера внутри бара, SL рассматривается первым. Это консервативное допущение о неизвестном порядке, не установленный факт. Stop outcome всегда −1R, даже при gap через стоп; это недооценивает возможный убыток исполнения. Комиссии, spread, slippage и fee currency в этих Monte Carlo R не включены. TP/SL исходы сохраняются после первого касания, но пути цены продолжаются до горизонта; терминальное распределение цены не равно распределению ликвидационной стоимости сделки.

Отдельные 2 000 paths с тем же seed формируют 5/25/50/75/95% квантили. Это эмпирические квантили симуляций, не проверенные интервалы покрытия будущего рынка. `p_green` также не является откалиброванной вероятностью прибыли после издержек. 10 000 paths повторно используют небольшой исторический пул: это не 10 000 независимых наблюдений рынка.

`history_replay` прогоняет ORB по историческим сессиям; вход принят равным закрытию сигнального бара, выход проверяется начиная со следующего. Для MOEX нужен следующий реально доступный ask/бар, чтобы не считать цену сигнального close исполнимой задним числом. Признаки ORB causal, но это допущение исполнения оптимистично. В `verdict` доля TP условна на TP-or-SL и сравнивается с 1/(1+R); Neither и costs не входят в этот порог. Код выводит предупреждения при большой доле Neither и противоположном знаке average R. Наша система не должна превращать такой heuristic verdict в разрешение сделки.

## Сравнение с time_machine_core

Текущий модуль MOEX работает с дневными close, сохраняет короткие блоки log returns, имеет resource bounds, seed, издержки на вход/выход и wealth paths после закрытия. Барьеры срабатывают по закрытию дня с исполнением на цене закрытия; intraday OHLC и последовательность TP/SL внутри свечи он не моделирует. Коэффициенты 252 и горизонты в торговых днях нужны инвестиционной части и не должны меняться ради крипто.

Нельзя просто подать пятиминутные BTC closes в этот API и объявить корректную годовую волатильность или 24/7 forecast. Общие части (валидация, bounded computation, metadata, reproducibility) можно использовать через явные контракты, сохранив старую инвестиционную семантику.

## Архитектура v0.9

Bybit immutable closed bars + data cutoff → отдельный Crypto Research Dataset → causal OHLC/block bootstrap baseline → barrier evaluator → Cost Engine assumptions → ForecastResult/ResearchResult → immutable forecast history → UI. Ни исследовательский движок, ни прогноз не вызывают submit. Проверенный Risk Manager остаётся отдельным шлюзом.

Горизонты задаются секундами/числом баров: 1h/4h/12h/24h/несколько календарных дней. Нет NYSE close, weekend closure и переноса американского PDT/calendar в BTC. UTC внутри; локальное время — форматирование. Сезонность hour-of-week можно вводить только при достаточной истории и независимом сравнении. Кэш ключуется data hash, cutoff, interval, horizon, model version, seed и costs; движение слайдера не перезагружает рынок.

Интерфейс результата отдельно хранит TP-first/SL-first/Neither **simulation frequencies**, net R distribution, model/sample sizes, assumptions, ambiguity policy и validation status. До проверки — Experimental / Not Validated; при отсутствии модели — UNAVAILABLE без будущих цен.

## Обязательные тесты и оценка

1. Cutoff и prefix invariance: добавление будущих баров не меняет старый результат; текущий бар не попадает в обучение.
2. Repeatability: одинаковые dataset hash/seed/version дают идентичный результат; новый seed не меняет историю старых прогнозов.
3. Zero/negative/nonfinite OHLC, high<low, дубликаты, out-of-order, пропуски и мало истории отклоняются явно.
4. Горизонты 1/4/12/24h, 1m/15m/4h и переход UTC суток/выходных без торгового закрытия.
5. Оба барьера в одном баре: pessimistic/optimistic sensitivity, отдельная ambiguity rate; gap execution не ограничивается −1R искусственно.
6. Next available quote execution, bid/ask spread и round-trip fee/slippage, net base inventory и residue, без двойной комиссии.
7. Chronological split, embargo не меньше target horizon при пересечении labels, walk-forward. Final test untouched; normalization только на train.
8. Random Walk baseline, directional accuracy, MAE/RMSE, pinball loss и эмпирическое coverage по горизонтам/режимам. Не подбирать модель по final test.
9. Net expectancy, turnover, drawdown и trade count на causal execution; нулевые сделки не дают фиктивный Profit Factor.
10. Forecast записывается до target time. Изменение старых quantiles запрещено; actual outcome добавляется отдельно.

## Побочные эффекты и ограничения

Upstream data CLI обращаются к Yahoo Finance и Nasdaq Trader; read/write путей `trader/*.json`, polling с backoff и вывод в stdout/stderr. Risk/budget читают локальные portfolio/config/state и могут писать JSON; нет SQLite isolation. Это не Bybit V5. Скрипты не выполнялись, реальные brokerage keys не запрашивались. Дополнительные broker/news/SEC/другие skills не подключаются.

Итог: установить весь пакет вместо MOEX — нецелесообразно. Ценность — в объяснимом плане, barrier outcomes и дисциплине replay. Торговый шлюз, сетевой источник, рыночный календарь, sizing и вероятностные заявления переносить нельзя. Следующий шаг — самостоятельный 24/7 исследовательский прототип на закрытых Bybit OHLC с указанными тестами, после завершения P0/P1 текущего релиза.

## Current integration follow-up

The six-module rc3 review above is historical. For the complete eleven-module
review against CandlePath PR #50, actual selective changes, rejected transfers,
and challenger admission criteria, see [day_trader_integration/AUDIT.md](day_trader_integration/AUDIT.md).
The expanded [SOURCE_REVIEW.json](SOURCE_REVIEW.json) records the pinned source
hashes and separately identifies the isolated upstream offline test execution.
