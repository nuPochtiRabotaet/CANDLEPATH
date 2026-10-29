# Future Manual Live / Demo prerequisites

rc3 has no enabled Demo or Live execution. Do not point Paper at a live account. Existing Read Only is not an execution adapter. Local simulated stops are not exchange-resident orders.

Before Demo: official supported platform/account (Global/EU/etc.), documented demo domains, server-side credentials, least privileges/no withdrawal, actual fee/rules/balance, marketUnit baseCoin semantics, limit/market step/min/max validation, slippage protection. Persist orderLinkId, asynchronous ACK, order/execution WS and REST reconciliation, duplicate/partial/cancel/reject recovery. Test real demo behavior; never infer fill from ACK.

Before Live: independent technical/security review and separate explicit owner permission; manual confirmation of exact amount, default-off adapter, kill switch, fresh prices, allocation/risk/daily limits, secret management/IP allowlist, exchange-supported Spot TP/SL accepted-status checks, partial-close coverage changes and crash recovery. If protection cannot be assured, enabling real trading remains blocked. No regional circumvention or alternate-host probing.
