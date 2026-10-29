# Инварианты виртуального учёта

Для каждой позиции cost_basis — оставшаяся фактическая сумма USDT, потраченная на её получение. При base fee она включает стоимость удержанного BTC через меньший received quantity; прибавлять quote-equivalent комиссии второй раз запрещено.

- BUY: cash уменьшается на debit, basis увеличивается на тот же debit; inventory увеличивается только на net_base.
- SELL части q из held H: allocated_basis = basis × q/H; realized += net_proceeds − allocated_basis; cash += net_proceeds. Оставшаяся basis уменьшается на allocated_basis. Последний выход списывает весь оставшийся basis, не заново округлённую пропорцию.
- Полный цикл: cash = initial + realized, когда позиций нет.
- С открытыми позициями: cash + sum(remaining basis) = initial + realized.
- Mark equity = cash + sum(net qty × Bid) = initial + realized + mark unrealized.
- Liquidation equity дополнительно оценивает будущие SELL fee/slip по текущему тарифу. Она показана отдельно, не смешивается с историческими расходами.
- Повтор order UUID возвращает прежний результат без повторной проводки. Guard и финансовое проведение остаются в одном BEGIN IMMEDIATE.
- Write-off = realized − remaining basis, cash неизменён; это Written Off, не Filled.

Старые позиции без cost_basis читаются через прежнее entry × qty + entry_fee. Их исходные записи не меняются миграцией. Существующие orders без execution snapshot сохраняют свой записанный fee/P&L; отсутствие snapshot нельзя трактовать как фактически подтверждённый новый тариф.

Schema 4 блокирует открытие новой семантики старым приложением. Переход с schema 3 создаёт SQLite backup `.before-rc2`. В старом тесте миграции изменено только ожидаемое число schema 3→4; проверки сохранности данных не ослаблены.
