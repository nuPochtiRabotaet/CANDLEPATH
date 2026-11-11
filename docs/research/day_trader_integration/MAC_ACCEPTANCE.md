# CandlePath v0.9 — Apple Silicon / Safari acceptance

Status: **NOT RUN on a physical Mac**. This is a reproducible acceptance protocol,
not a claim that macOS, Safari, Retina or sleep/wake has passed. Final exact-SHA
CI evidence and readiness matrix are recorded in Draft PR #51's acceptance section.
Previous `VALIDATION.md` numbers remain historical evidence for that environment.

## 1. Clean, pinned checkout

Use a new directory, never an old installation or a real portfolio directory.
Install Git, native arm64 Python **3.12** (3.13 is also supported by
`pyproject.toml`; 3.14 is excluded), and Node **22**. Node 22 is the CI target;
Node 24.22.1 also passed the JS contracts in the cloud acceptance pass. Install
Python/Node from their official installers or an existing trusted package manager.
Do not reuse an Intel/Rosetta virtualenv or disable macOS security protections.

In Terminal, replace the SHA below with the full final SHA in the PR acceptance
section. Do not substitute `main` or an unrecorded moving branch.

```bash
CANDLEPATH_ACCEPTANCE_SHA='<full final 40-character SHA from PR #51>'
CANDLEPATH_QA_ROOT="$(mktemp -d "$HOME/CandlePath-v09-acceptance-XXXXXX")"
git clone --branch feat/selective-day-trader-integration --single-branch \
  https://github.com/nuPochtiRabotaet/CANDLEPATH.git "$CANDLEPATH_QA_ROOT/source"
cd "$CANDLEPATH_QA_ROOT/source"
git checkout --detach "$CANDLEPATH_ACCEPTANCE_SHA"
test "$(git rev-parse HEAD)" = "$CANDLEPATH_ACCEPTANCE_SHA"
test -z "$(git status --porcelain)"
mkdir -p artifacts/mac-acceptance
uname -m
sw_vers
python3.12 -c 'import platform,sys; print(sys.version); print(platform.machine()); assert platform.machine()=="arm64"; assert sys.version_info[:2]==(3,12)'
node --version
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m pip install playwright==1.56.0
.venv/bin/python -m pip check
.venv/bin/python -m pip freeze > artifacts/mac-acceptance/packages.txt
.venv/bin/python -m playwright install chromium
```

Use existing authenticated Git access if this repository is private; never put a
credential into a command, document or screenshot. A failed wheel/hash/install is
FAIL/BLOCKED with the error retained, not permission to remove hashes or change
versions. App dependencies are hash-locked; Playwright is separately version-pinned
QA tooling (its transitive dependencies/browser revision must be recorded).

## 2. Automated checks on the Mac

These commands and filenames exist on the feature branch. The strict script runs
compileall, JS syntax, Forecast geometry, chart contracts, full pytest and Forecast
Chromium. The other two browser scripts must be run separately. Each browser
script isolates its own data; the strict script creates/removes its own temp DB.

```bash
set -o pipefail
PATH="$PWD/.venv/bin:$PATH" bash scripts/verify_v09_local.command --strict \
  2>&1 | tee artifacts/mac-acceptance/strict.log
.venv/bin/python scripts/verify_coliseum_browser.py \
  2>&1 | tee artifacts/mac-acceptance/coliseum.log
.venv/bin/python scripts/verify_day_trader_integration_browser.py \
  2>&1 | tee artifacts/mac-acceptance/day-trader.log
```

Require zero failures, skips and expected failures. `--strict` prevents missing
Node/Playwright being reported as PASS; inspect pytest's summary too. Chromium
success on the Mac remains **Chromium**, not Safari acceptance. All fixture data
is synthetic. No upstream suite rerun or strategy optimization is needed.

## 3. Isolated production launcher

Keep the same Terminal session and preserve the data path across restart. The
launcher stores supervisor metadata in this clean checkout's `.runtime`; its
`stop` command identifies its own supervisor rather than trusting an arbitrary PID.
All user-owned existing installations/data remain outside this test directory.

```bash
export MOEX_DATA_DIR="$CANDLEPATH_QA_ROOT/production-paper-data"
mkdir -p "$MOEX_DATA_DIR"
printf '%s\n' "$MOEX_DATA_DIR" > artifacts/mac-acceptance/data-dir.txt
git rev-parse HEAD > artifacts/mac-acceptance/sha.txt
bash start.command
.venv/bin/python -m moex_intelligence.launcher status
```

Open the printed `http://127.0.0.1:8501` (or 8502–8510) URL in **Safari**.
Record macOS/Safari/Python/Node versions, `devicePixelRatio`, viewport, source SHA,
feed/rules timestamps and whether public market access is permitted/available.
App health alone does not prove feed readiness or working Paper protection.
Require no Streamlit exceptions and `Security Center` to show no real execution.

No private keys are needed. In a permitted region, ordinary public Bybit reads
are allowed; a 403/451, unavailable network or invalid feed is BLOCKED for real
market readiness. Do not use alternate domains, proxies, VPNs or synthetic data
to claim real-data acceptance. No orders are sent to an exchange.

## 4. Safari / Retina UI and Paper acceptance

Use only the new isolated virtual account. For each case record PASS/FAIL/BLOCKED,
evidence, timestamps and SHA. Never click an Invest buy/import/reset on real data.

| Case | Required observation |
|---|---|
| Retina/layout | At practical widths 1024/1280/1440/1920 CSS px (external screen if needed), text/caps/dialogs readable, zoom/scroll/ribbon/Forecast behave, no console/Streamlit exceptions. Record widths that cannot be tested as NOT RUN. |
| Closed candle | A forming candle is only potential; confirmed signal is unavailable before its close/receipt. Historical BUY/EXIT is distinct from a Paper fill. |
| Sizing/scan | Decimal caps, tied limits and exchange maximum visible; scan shows selected-symbol scope, cutoff and COMPLETE/PARTIAL/INCOMPLETE; pressing scan leaves Paper order/fill counts unchanged. |
| Preview/Cancel | Prepare 25 USDT Paper BUY with valid stop/target; inspect immutable quantity/costs/rules, consent initially unchecked. Cancel leaves cash, positions and fills unchanged (intent/audit events may be written). |
| Preview/Confirm | With fresh permitted quote/rules, prepare anew; explicit consent and Confirm produce exactly one LOCAL PAPER fill. Confirm uses current quote/rules/risk checks, not the preview's stale estimate. Compare ledger/orders/cash with costs. |
| Retry/reload | A repeated delivery of the same intent ID must not add a second fill. A new deliberate BUY click has a new ID and is a different request; it is not the idempotency test. Backend concurrency/restart coverage is `tests/test_order_preview_v082.py::test_concurrent_confirmation_restart`. |
| Input changes | Cancel the old preview, edit size/levels, require a new preview. Existing preview payload stays fixed. A changed account/rules/risk profile invalidates it at confirmation. |
| Expiry | Wait more than 30 seconds after preview; old Confirm fails/disabled and no fill is added. Prepare anew. |
| No rules/stale | Missing/stale rules, crossed/missing bid/ask or stale quotes block new operations and actionable readiness; never reconstruct freshness from a display price. |
| EXIT | Without a position, EXIT creates no sale/short. With a position, valid manual Preview/Confirm is still required. |
| Invest | Default navigation remains Trade/Coliseum; enable legacy Invest only with `CANDLEPATH_ENABLE_LEGACY_INVEST=1` on this isolated data directory. Review read-only views; no actual portfolio supplied/changed. |

For repeatable offline **Safari UI only**, first stop the production launcher,
then run the existing fixture with another empty data directory:

```bash
bash stop.command
MOEX_DATA_DIR="$CANDLEPATH_QA_ROOT/synthetic-ui-data" \
  CANDLEPATH_ENABLE_LEGACY_INVEST=1 .venv/bin/python -m streamlit run \
  tests/crypto_ui_fixture.py --server.address 127.0.0.1 --server.port 8511 \
  --server.fileWatcherType none
```

The fixture explicitly labels artificial candles and mocks the protective monitor.
It can exercise Preview/Confirm/Cancel with virtual money; it cannot establish
actual worker protection or Bybit availability. Toggle `QA: устаревшая цена` to
check stale blocking; toggle `QA: предварительный BUY` to inspect potential vs
confirmed markers. Cancel a prepared preview, toggle stale, then prepare again;
no new fill is permitted. Stop the foreground fixture with Ctrl-C before restarting
the real launcher. Record fixture results separately from production/market cases.

## 5. Restart, sleep/wake, single owner and stop

For production cases re-export the **production-paper-data** path and restart
`bash start.command`. If permitted fresh data is unavailable, record the affected
protection/market cases BLOCKED; do not infer a pass from synthetic UI.

1. Record virtual cash, positions and order IDs. `bash stop.command`, then
   `bash start.command` with the same `MOEX_DATA_DIR`; verify records persist and
   no duplicate fill appears. Old expired previews cannot execute. On reconnection
   a protective Paper action may occur only after valid quotes/rules and trigger
   revalidation; retain its reason in the journal.
2. Repeat `bash start.command` sequentially: it should reuse its own healthy server.
   To test independent process ownership, keep it running and, from another
   Terminal in the same checkout with the same absolute data path, run:

   ```bash
   MOEX_DATA_DIR='<absolute production-paper-data path recorded above>' \
     .venv/bin/python -c 'from moex_intelligence.crypto.runtime import start,shutdown; start(); shutdown()'
   ```

   Expect a nonzero exit and the "another instance owns Paper" error. The first
   worker remains active and ledger orders unchanged. If this succeeds, FAIL the
   ownership case and stop testing. Do not remove the lock file or kill arbitrary
   processes. Simultaneous starts racing on launcher metadata are not certified;
   use one launcher and sequential start/stop. OS ledger ownership is separately
   tested by `tests/test_runtime_v09.py`.
3. Create an unconfirmed preview, sleep for over 30 seconds, wake. No activity is
   protected while asleep/off. Old preview must not fill, feed is unready until
   fresh data/rules recover; require a new Preview. Verify protection heartbeat
   recovers or stays explicitly degraded. Record actual sleep duration and ledger.
4. Disconnect network with no new orders pending; stale/connection-lost must block
   new operations. Reconnect; readiness requires fresh data and live worker status,
   never merely a cached chart. No region restrictions may be bypassed.
5. Stop safely with `bash stop.command`; `launcher status` must say not running.
   Preserve `.runtime/app.log` and acceptance logs; never use `pkill streamlit`.
   The virtual ledger stays on disk. Export evidence only after stopping writers.

## 6. Rollback without losing files

Stop the launcher from the checkout that started it; preserve the entire QA root,
including Paper SQLite, journals and logs. Return to your previous installation
in its original directory; this procedure never moved or edited it. Do not point
older code at a newer test DB or overwrite any real portfolio. A fresh checkout
of base `a0ca13d26cee204bf152ee20ef5bc8b1e7969e42` can be tested with a **new**
empty data directory; no reset, cleanup, schema downgrade or force-push is needed.
Code rollback does not reverse financial or later virtual ledger actions.

## Acceptance boundary

Only after actual Mac evidence may its rows change from NOT RUN. Research
engineering, historical-test validity, statistically supported alpha, and safe
real execution are four separate claims. This protocol primarily checks the first.
Sealed holdout remains unopened; strategy thresholds are unchanged. Real execution
is disabled. Next single priority: complete this physical Mac/Safari protocol.
