# Cost Engine v1 — v0.8.2-rc2

`crypto/costs.py` — единый Decimal-модуль. Типы: FeeSchedule, ExecutionAssumptions, CostModel, EstimatedFill, SimulatedFill. Вызовы используют risk.py, orders.py, paper.py, position protection, lifecycle EXIT и UI. В JavaScript больше нет независимой денежной формулы: карточки получают серверный расчёт после debounce ~180ms. Дроби проводок сохраняются строками; float — только представление совместимого UI.

Market = Taker. Maker настраивается как будущий параметр, но matching/Limit исполнение не реализованы. SELL/base явно запрещён конструктором модели. Тарифы — пользовательские LOCAL PAPER assumptions. Приватный Bybit fee endpoint не вызывался.

BUY quote: gross notional = quantity × ask × (1 + slip); fee_quote = notional × taker; cash debit = notional + fee; received base = quantity. BUY base: fee_base = quantity × taker; received = quantity − fee_base; cash debit = gross notional. Эквивалент base fee в USDT показывается для отчёта, но НЕ списывается повторно. SELL quote: net proceeds = quantity × bid × (1 − slip) × (1 − taker).

Spread — разность ask/bid, не дополнительная комиссия. Slippage применяется к стороне исполнения. Round-trip cost = debit входа − net proceeds гипотетического немедленного выхода; включает spread/fee/slip ровно один раз. Net R/R использует действительно полученный нетто-объём; gross R/R — техническое сравнение без издержек.

Notional budget сохраняет смысл rc1: комиссия quote сверх суммы. All-inclusive total — жёсткий максимум списания с комиссией. Quantity округляется вниз один раз при Prepare. При Confirm остаётся фиксированной; если новый debit выше total cap, исполнение отклоняется, даже когда price drift укладывается в 10 bps. Notional-режим допускает исходный явно показанный drift, поэтому итог не является all-inclusive лимитом.

Каждый новый fill содержит `execution.values`, `execution.model`, engine_version, liquidity=taker, источник, Bid/Ask/time и фактический cash_delta. Позиция содержит cost_basis, effective_entry и entry_cost_model. Изменение тарифа влияет только на новые исполнения и оценки будущего выхода. Ни прошлые комиссии, ни реализованный P&L не пересчитываются.

## Точность и ограничения

Decimal использует стандартную 28-значную точность. Комиссия в base не округляется искусственно до trading quantity step: fee precision реального аккаунта не подтверждена. Поэтому полученный остаток может оказаться некратным шагу. Preview и Quality Policy явно показывают EXIT_PRECISION / No Trade; цена и риск до стопа в таком сценарии — математическая оценка, а не исполнимая защита. Ручной LOCAL PAPER BUY всё ещё может быть подтверждён осознанно. Full/partial SELL и защитный ордер с недопустимым количеством отклоняются; приложение не добавляет BTC, не округляет продажу скрыто и не создаёт фиктивный Filled. Для такого остатка доступны ожидание правил либо отдельное явное учётное списание в убыток без cash credit. Это существенное ограничение rc2; для FINAL нужен отдельный UX обработки fee dust/выбора исполнимого объёма.

Ни liquidation equity, ни stop scenario не гарантируют ликвидность/точность реального исполнения. Base fee currency, очередь, фактическая precision и тариф биржи здесь не воспроизводятся как подтверждённый API факт.
