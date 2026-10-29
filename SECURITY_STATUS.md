# Security / execution status — rc3

LOCAL PAPER only. No Demo/Live submit path enabled, no autonomous orders, no withdrawal API. Pure reconcile_order tests do not constitute exchange integration. Public data needs no key. Private Read Only uses server-side environment configuration and permission checks; no keys were supplied or tested in this run.

Preserved protections: loopback launcher, CORS/XSRF, hashed dependency lock, isolated Crypto SQLite, version checks/backups, Decimal balances, UUID idempotence, account/rule/profile/quote freshness gates, no leverage/short/averaging, explicit manual confirmation. Frontend contains no key input or secret payload. No external day-trader scripts installed.

New protections: retained residue basis, explicit zero-cash writeoff; approved protective residue limit; transactional stop editor and execution trigger recheck; rejected posting rollback; full-ledger reconciliation warnings; immutable prediction/outcome tables. No user portfolio database is packaged in the ZIP.

Limitations: local single-user app, not a multi-tenant public service; local files are not encrypted by the application; Keychain/IP allowlist integration not implemented. Forecast DB immutability protects normal app operations, not an administrator who edits the database file. Protection monitor is process-bound, not an always-on service. Sleeping Mac stops monitoring. No exchange-resident protective order has been verified. NOT READY FOR REAL FUNDS.
