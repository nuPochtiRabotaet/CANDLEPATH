# SP-002 — Active Stop / Target Editor

Цель: редактировать защиту существующей виртуальной позиции, сохраняя явное согласие на изменение риска.

## Layout и поток

Draft STOP/TARGET draggable lines + numeric inputs. Saved PAPER STOP/TARGET отдельно (если уровни совпадают, подписи не дублируют линию). Inline delta: old/new Stop/Target, risk delta, Net R/R. Кнопка «Изменить защиту · предпросмотр» открывает dialog max550px/90vh: old/new levels, risks, distances, covered quantity and residue, warning process-local monitoring, expiry30s, consent, Apply/Cancel. Footer остаётся доступным при прокрутке.

## Контракт

ProtectionPreview snapshots owner, position ID/revision, account, risk profile, rules/cost revision, quote/spread. Prepare не меняет ledger. Atomic confirm повторно проверяет stale, drift, position and old trigger; only then saves levels/revision/approved residue limit and audit event. No order/no cash change. Double confirm idempotent.

## Ошибки

Если позицию частично/полностью закрыли, поменялось правило/тариф или активная защита уже сработала, confirm rejected; новый preview обязателен. Cancel/Escape не меняют уровни. Monitor rechecks latest levels under the same lock, предотвращая исполнение устаревшего stop. Increased risk must fit limits; smaller risk can be accepted without расширения лимита.

## Приёмка

Tests cover cancel, consent, stale, rules, spread/drift, account changes, partial/full exit, repeated ID, restart, monitor/edit race. Source: crypto/protection.py, inventory.py, risk.py, paper.py, ui.py; components/trade.*; tests/test_inventory_protection_rc3.py. Screenshot ../rc3/browser/stop-target-confirmation.png.

## Общие токены и ограничения

Chart #0D1519, panel #10191E, grid #33444C, text #D8E7E6, muted #839B9C, bull #31F3A2, bear #FF5474; glow #26FF99/#FF426B; candles #26B985/#D85168. Inter/system sans, 11–13px controls, 19–22px price, tabular figures, 6–16px gaps, 5–10px corner radii. Цвет всегда сопровождается текстом состояния. Стили scoped к Trade, Invest сохранён.

Приоритет — свечи. Desktop sidebar 290px (270px на узкой ширине), chart ~530px high, assistant independently scrolls. Assistant toggle даёт полную ширину графику. На 1024/1280/1440/1920 отсутствие горизонтального переполнения проверяется браузером. На ширине ≤680 панель переносится под график; это дополнительный layout, без заявления о полной мобильной приёмке.
