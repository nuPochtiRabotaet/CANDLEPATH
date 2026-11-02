# CandlePath v0.9 — pre-practice engine safety audit (2026-11-02)

**Status:** fixes merged into `develop/v0.9`. **Not a release, not
production- or live-trading-approved.** The stable `main` was NOT modified.

## Scope / what was actually examined

- The whole existing Python/Node/Chromium GitHub CI suite, plus the new
  regression tests below.
- Code-path review of Bybit public REST/WebSocket Feed, immutable closed
  candle journal and REST backfill, Paper quote gate, OrderPreview prepare/
  confirm, persisted Paper BUY/SELL accounting, Stop/Target protection,
  local monitor, and read-only sealed development-fold prediction/strategy
  research.
- Synthetic injected historical/book events and corrupted/untrusted prices.
  No authentic exchange fills, physical macOS/Safari or user portfolio data
  were used or altered.

## Confirmed defects fixed

**PR #26** [market feed durability & WebSocket book deltas](https://github.com/nuPochtiRabotaet/FUCKBINANCEANDMOEX/pull/26),
merged as `bd8be4a65449f8a9e7852d19edb7a77ccc2cb2e5`:
1. A one-sided or empty Bybit level-1 delta previously set the untouched
   bid/ask side to zero. Unchanged sides and their own freshness timestamps
   must persist. An explicit zero-quantity removal remains non-executable.
2. Older cached orderbook values previously overrode newer ticker prices.
   Each bid/ask side now respects the newest event timestamp.
3. A gap/unconfirmed candle or storage exception could mutate Feed memory
   and/or event watermark before rejecting the event or writing to SQLite.
   Validate first, persist, then atomically expose the new in-memory view.
   The same sequencing now applies to REST sync.
4. **6 new regression tests** assert no phantom book side, no stale price
   rollback, no memory/journal corruption on gap or disk failures.
   [CI #41398626198](https://github.com/nuPochtiRabotaet/FUCKBINANCEANDMOEX/actions/runs/41398626198):
   **670/670** Python tests and synthetic Chromium passed.

**PR #27** [strict closed candle and numeric ingress](https://github.com/nuPochtiRabotaet/FUCKBINANCEANDMOEX/pull/27),
merged as `d1ecfa493633a662f2aefc61d5fbcc93c93608c7`:
1. Python `bool("false")` is True. A malformed string flag could
   otherwise be treated as a confirmed kline. Now only actual Boolean
   confirmations are accepted, including in the reusable Candle object.
2. Malformed or excessively large numeric data could raise uncaught
   `OverflowError` or propagate a bad public quote. Input validation,
   snapshot filters and `risk.quote_ok` fail closed instead.
3. A crossed public ticker bid/ask is rejected.
4. **15 new tests**, [CI #41399198156](https://github.com/nuPochtiRabotaet/FUCKBINANCEANDMOEX/actions/runs/41399198156):
   **685/685** Python tests and synthetic Chromium passed.

**PR #28** [Paper safety freshness and price ordering](https://github.com/nuPochtiRabotaet/FUCKBINANCEANDMOEX/pull/28),
merged as `3f99458bb90a3c4cb252359106b6aee3bdda04bb`:
1. Truthy strings such as `"false"`, integers and lists cannot replace
   literal Boolean `fresh=True` at the executable-quote gate.
2. Values such as `bid="100"`, `ask="99"` compare lexically in Python
   but represent a **crossed market**. Compare normalized numeric sides.
3. Tests use the actual `Paper.execute` path to prove forged freshness
   cannot create a virtual position, and `risk.plan` rejects crossed quotes.
4. **14 new tests**, [CI #41399778758](https://github.com/nuPochtiRabotaet/FUCKBINANCEANDMOEX/actions/runs/41399778758):
   **699/699** Python tests and synthetic Chromium passed.

All of these defects were demonstrated by synthetic adversarial scenarios,
**not** observed production executions. The protective change is intentionally
fail-closed rather than pretending the external market was verified.

## Boundaries / unverified before practical use

- The optional Bybit public REST step still reports **REAL BYBIT HISTORY
  NOT VERIFIED** because access is blocked or limited by region/platform.
  No fake candles are substituted as real. Public WebSocket availability and
  orderbook consistency in the user's actual network are not established.
- GitHub CI uses Linux and Chromium; a *physical Mac/Safari* launch,
  environment setup, database migrations/backup, CPU/memory, sleep/resume,
  restart/reconnect and process monitor cannot be confirmed here.
- The local Paper protective worker runs **only while its process is alive**.
  Mac sleep/offline status means virtual protection is not actively monitored.
  Paper fills and offline historical Paper-paths are not exchange fills.
- Initial forecast baseline, momentum candidate, sealed historical fold
  metrics and volatility labels are **research only**. No demonstrated net
  positive trading edge, calibrated live confidence or guaranteed protection.
  Final 20% historical holdout remains sealed in the research paths.
- Real account execution, demo/live order adapters and autonomous orders
  remain OFF. No credentials are required by this audit.

## Physical Mac preflight checklist (manual, after backup)

1. Preserve the existing v0.8.2-rc3 folder and a backup of local
   `~/.moex-intelligence` (or `MOEX_DATA_DIR`). Never overwrite user
   holdings or migrate the old MOEX ledger during the test.
2. Launch `develop/v0.9` in an isolated test data directory using the
   project's macOS installer and launcher. Verify startup, stop and
   restart; test a second competing process is rejected by the Paper lock.
3. Open BTCUSDT 15m in Safari; inspect status, actual data source, OHLCV
   continuity, bid <= ask, quote age and freshness. If Bybit is unavailable,
   the system must show a loss of connectivity **and must not permit orders**.
4. Only if public quotes and rules verify, use **virtual Paper money** to
   test prepare/confirm/cancel, a tiny mock position, Stop/Target preview,
   duplicate click/idempotence and a process restart. Never enter API keys
   or attempt a real order.
5. Disconnect network, sleep/wake the Mac, then reconnect. Inspect the
   monitor's heartbeat, explicit degraded status, recovery and immutable
   candle journal. Do not assume local protective stops can operate offline.
6. Check imported CSV research separately from the live Paper ledger:
   no writes to portfolios, no closed-history overwrites, no scoring of
   the sealed final holdout.

**Preliminary gate:** code regression safety for the audited cases passed;
the user should not treat practical Paper/Bybit readiness as verified until
Mac and real network acceptance complete. **Do not enable live trading.**
