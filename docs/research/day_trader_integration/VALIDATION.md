# Validation, local acceptance and rollback

## Revisions and scope

Integration base: `a0ca13d26cee204bf152ee20ef5bc8b1e7969e42` (PR #50 OPEN).
Upstream: `3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd`.

Code commits:

- `21bf30e`: explain Decimal caps; recommendation respects exchange maximum.
- `e14efe0`: causal, read-only scan completeness and opt-in selected-symbol UI.

The following documentation commit adds the audit/evidence/QA helpers. Its exact
SHA is available in `git log` and the final delivery report. Main and develop
were not changed. The requested PR base is `integration/v0.9-final-stabilization`.

## Executed checks

Linux x86_64, Python 3.12.14. Playwright 1.56.0, system Chromium, Node installed.
All application tests use synthetic/temporary data. No user portfolio or original
sealed market dataset was supplied, opened or scored. Synthetic sealed-holdout
invariance tests are software checks, not actual final evaluation.

| Check | Actual outcome | Evidence |
|---|---|---|
| PR #50 baseline `python -m pytest -q` | 897 passed, 49.49s | `evidence/baseline.txt` |
| New risk tests before change | 9 failed, 1 passed: missing diagnostics and recommendation exceeding exchange max; some binding fixtures subsequently corrected | historical initial log retained locally; final tests below |
| Focused final risk/Paper/inventory/crypto suite | 86 passed, 3.32s | `evidence/risk-focused.txt` |
| Added risk + scan tests | 22 passed, 0.53s | included in full suite |
| Full modified project `python -m pytest -q` | 919 passed, 50.31s; zero failed/skipped | `evidence/pytest.txt` |
| `python -m compileall -q moex_intelligence tests scripts` | passed | run after adding QA/benchmark helpers |
| `node --check moex_intelligence/components/trade.js` | passed | existing chart unchanged |
| `node scripts/verify_v09_forecast_geometry.js` | 41 checks passed | strict projection/fail-closed contracts |
| `node scripts/verify_v09_chart_updates.js` | passed | immutable history, volume/index contract |
| `python scripts/verify_v09_forecast_browser.py` | passed, Chromium | `evidence/forecast-browser.txt` |
| `CHROMIUM_PATH=/usr/bin/chromium python scripts/verify_coliseum_browser.py` | passed, real Streamlit/Chromium; four widths, export and sealed flag | `evidence/coliseum-browser.txt` |
| `python scripts/verify_day_trader_integration_browser.py` | passed, real Streamlit/Chromium; new panels, four widths, 25 USDT Preview/consent/cancel, zero JS errors and no fill | `evidence/browser.json`; `screenshots/` |
| Pinned upstream `unittest discover -s tests -v` | 315 passed, 10.615s | `evidence/upstream-tests.txt` |
| Risk microbenchmark | 86.43 → 98.08 µs median per plan, 7x1000 calls per version | `performance.json` |
| Real Bybit REST/WS and broker | NOT RUN, no claim | unnecessary for this local diagnostic change |
| Physical Apple Silicon / Safari / sleep-wake | NOT RUN, no physical Mac | local acceptance below |
| New head's GitHub CI | NOT OBSERVED | local evidence does not claim remote CI |

The microbenchmark uses the same synthetic state/clock in one process and loads
risk.py from the exact base via read-only `git show`. Diagnostics add about
11.65 µs (13.5%) in this narrow measurement. This is not a latency SLA, an
application throughput gain or a financial result. There is no baseline scan
report API, so no invented scan speedup is reported. The new optional scan
reuses existing validation/analysis only when manually requested; it is not a
new per-second research workload.

### Failed initial checks and resolution

- New tests initially failed as expected because diagnostics did not exist and
  the old recommendation exceeded a valid exchange maximum. Three new binding
  fixtures needed correction: cash normally cannot dominate the stricter
  occupied-capital cap, a request above max is already rejected, and existing
  portfolio risk had initially been too small to bind. No preexisting test or
  assertion was removed or weakened; all final adversarial checks pass.
- First new browser run used an obsolete keyed workspace selector. Second run
  waited for Trade while opt-in legacy mode starts in Invest. Corrected to the
  actual sidebar navigation and reran successfully.
- First Coliseum browser attempt looked for an uninstalled Playwright-bundled
  executable. Reran using installed `/usr/bin/chromium` successfully.
- GitHub REST API CONNECT was denied HTTP 403 by the cloud egress proxy, while
  authenticated Git and the public GitHub PR page worked. PR #50's embedded
  page metadata established OPEN/head/base state, independently checked with
  Git refs. API access for PR creation/CI remains a separate limitation. The
  `api.github.com` requirement was saved to the environment settings draft;
  a draft save does not apply network access or publish the environment.

## Reproduce locally

Use the existing Python 3.12/3.13 project environment. No new application
requirements or lockfile changes were needed. Playwright is a QA-only tool.

```bash
python -m pytest -q
python -m compileall -q moex_intelligence tests scripts
node --check moex_intelligence/components/trade.js
node scripts/verify_v09_forecast_geometry.js
node scripts/verify_v09_chart_updates.js
python scripts/verify_v09_forecast_browser.py
CHROMIUM_PATH=/path/to/chromium python scripts/verify_coliseum_browser.py
CHROMIUM_PATH=/path/to/chromium python scripts/verify_day_trader_integration_browser.py
PYTHONPATH=. python scripts/benchmark_day_trader_integration.py
```

The browser and Python suites use temporary `MOEX_DATA_DIR` fixtures; don't point
them at a real portfolio. The benchmark reads code from Git and creates no
account/market dataset. Do not replace fixture input with a sealed final file.

## Apple Silicon and Safari acceptance (unverified instructions)

Use a separate clean checkout so no old virtual environment/user files need to
be replaced. Never copy `.venv` from another platform. Python must be native
arm64/universal2, 3.12 or 3.13. From that checkout:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m pip install playwright==1.56.0
.venv/bin/python -m playwright install chromium
PATH="$PWD/.venv/bin:$PATH" bash scripts/verify_v09_local.command --strict
.venv/bin/python scripts/verify_coliseum_browser.py
.venv/bin/python scripts/verify_day_trader_integration_browser.py
```

Node must be installed for strict JS QA. With bundled Playwright Chromium,
CHROMIUM_PATH is unnecessary; with a system Chromium set its actual executable.
Playwright Chromium success on Mac is still not a Safari check.

For a manual Safari session, isolate data and retain the variable for stop:

```bash
export MOEX_DATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/candlepath-mac-qa-XXXXXX")"
bash start.command
# Open the launcher-provided loopback URL in Safari; inspect the checks below.
bash stop.command
```

Keep this temporary directory until acceptance is complete; do not substitute
`~/.moex-intelligence`. For offline reproducible synthetic UI use:

```bash
CANDLEPATH_ENABLE_LEGACY_INVEST=1 .venv/bin/python -m streamlit run tests/crypto_ui_fixture.py
```

This fixture mocks the protective monitor and is explicitly synthetic. It is
for UI checks, not proof of actual background protection or real market access.
Verify the following manually on Safari/Retina at 1024/1280/1440/1920:

- New sizing table/limiting ties, stale/no-rules error and readable decimal caps.
- Selected-symbol scan COMPLETE vs incomplete; cutoff and explicit scope.
- Ribbon/zoom/scroll and forecast layer unchanged; chart BUY/EXIT remain analytical.
- 25 USDT Preview -> consent -> Confirm or Cancel. A manual edit needs a new
  preview; sleep/wake/stale data must not bypass execution readiness.
- Opt-in Invest navigation, read-only history and imports tested only on copies.
- Launcher start/stop/restart and sleep/wake tested separately with fresh permitted
  market data; a local stop is inactive while the Mac/process is asleep/off.

Real Bybit verification, if separately performed on a permitted platform/region,
must use public/read-only data and must be recorded separately from these tests.
No private brokerage credentials are needed or requested.

## Safe rollback

There is no schema/data migration or new application dependency. Stop the app
before switching code; preserve your work and make your normal data backup.

- Before integration: from a clean worktree switch to
  `integration/v0.9-final-stabilization`. This leaves the feature branch and
  all user data recoverable. Do not reset or delete a checkout with local changes.
- After an approved merge: create a new rollback branch from the current
  integration head, revert `e14efe0` then `21bf30e`, and resolve any later UI
  changes explicitly. Re-run the Python/JS/browser checks and open a rollback PR.
  Do not force-push integration/main or revert unrelated work.
- No forecast publication, financial fill or user ledger row was created by this
  integration. Code rollback is not a request to reverse any later user action.
