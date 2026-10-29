# Security — NOT READY for live funds

Публичный рынок, LOCAL PAPER и прежний server-side Read Only. Нет Demo submit, Live submit, withdraw API или автономного исполнения. Секреты не передаются компоненту. Default bind loopback, XSRF/CORS включены. Приватные тарифы аккаунта не запрашивались.

Manual gateway сохраняет owner/consent, expiry, quote/rules/account/profile guards, atomic UUID idempotency. Изменение CostModel аннулирует preview через account revision. Total budget повторно проверяется внутри транзакции. UI advisory No Trade не подменяет Risk Manager.

Локальная защита зависит от активного процесса и свежих данных. Сон/остановка Mac прекращают её. Fee dust может быть неторгуем по текущему step; такой защитный выход будет Rejected, никогда фиктивно Filled. Предупреждение показано до покупки. Это локальная симуляция; server-side Bybit TP/SL нет.

Для Live требуются отдельный аудит/разрешение, private reconciliation, реальные fee/precision semantics, биржевая защита, kill switch и проверки аккаунта/платформы. Keychain/IP allowlist не реализованы. Обхода региональных ограничений нет.
