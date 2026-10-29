# MOEX Intelligence v0.8.2-rc2

**Промежуточный релиз Cost Integrity + Assistant basic, не FINAL.** Полный исходный проект; Invest и действующий криптотерминал сохранены.

Новое: единый Decimal Cost Engine для preview/risk/исполнения/учёта/защиты, настраиваемые Paper Taker/Maker assumptions (Market только Taker), BUY fee в quote/base, SELL fee в quote, нетто-объём и cost basis, два режима суммы 25 USDT — notional и total cap. Исторические комиссии не пересчитываются. Assistant отдельно показывает regime/signal/quality/attention, включая No Trade.

## macOS / Apple Silicon

Остановите rc1 через его stop.command и оставьте старую папку/архив. Распакуйте весь новый проект. Нужен Python 3.12/3.13; на Apple Silicon arm64/universal2. Не переносите старую .venv.

```bash
cd ~/Desktop/moex-intelligence-v0.8.2-rc2
chmod u+x *.command
bash setup.command
bash start.command
```

Данные: прежняя `~/.moex-intelligence` или MOEX_DATA_DIR. Crypto schema 3→4 создаёт `.before-rc2` backup; MOEX база не мигрирует. Для отката остановите приложение, сохраните новые данные отдельно и восстановите backup. Schema 4 нельзя открывать rc1.

Trade → Paper Trading. Внизу «Paper · комиссии и Quality Policy» задайте предположения. В amount-режиме Notional означает комиссию сверх суммы, Total — жёсткий максимум debit. Откройте preview, проверьте параметры, подтвердите. Изменение цены/тарифа/баланса может потребовать новый preview. Все сделки виртуальные.

**Ограничение base fee:** net quantity иногда не кратен торговому step. Preview предупреждает, Quality показывает No Trade; ручной Paper BUY всё ещё разрешён. Такой полный выход/стоп будет отклонён до изменения условий; приложение не выдумывает BTC и не округляет продажу скрыто. Выберите другое количество/модель комиссии. Старый остаток можно отдельно списать в учётный убыток без возврата cash. Это одна из задач до FINAL.

Монитор работает только при запущенном процессе и свежем рынке. Сон/выключение прекращают наблюдение. Active protection editing не реализовано; drag меняет только черновик.

Документы: COST_ENGINE.md, ACCOUNTING_INVARIANTS.md, ASSISTANT_2_REPORT.md, TRADING_JOURNAL.md, TEST_REPORT.md, UX_REVIEW.md, SECURITY_STATUS.md, ROADMAP_v0.9.md. Скриншоты: docs/rc2/browser и production. Запуск сети на Mac: check_bybit.command.

NOT READY for live funds. Реальные, Demo и автономные заявки отключены. Прогнозного ML/Overlay нет. Новый журнал/статистика и подтверждаемая правка действующих TP/SL остаются следующими этапами.
