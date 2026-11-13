# Intrabar visibility / causal observation — v0.9

Base inspected on 2026-11-13: PR #51 `8d916751c255626269c8677600c34649ebeccb36`
(open Draft) on PR #50 `a0ca13d26cee204bf152ee20ef5bc8b1e7969e42`
(open Draft). This branch stacks on #51; neither parent is merged.
Issue #31 is context, not closed by this engineering change.
No real execution, strategy thresholds, portfolio/ledger migrations, or raw-data edits.

## Cause and bounded fix

1. `analyze()` intentionally confirms only closed candles. Waiting for the close is
   mathematical confirmation latency, not a bug or proof of negative expectancy.
2. `provisional()` already existed, but ran only on Streamlit's one-second rerun.
   Conditions appearing and disappearing between reruns could be lost completely.
3. The chart read only published confirmed signals. It had no preliminary markers.
4. Chart bars use candle OPEN; signal.timestamp uses candle CLOSE. The old marker
   was placed at the next candle open (or hidden until that bar existed).
5. Fractional SQLite detection timestamps were rejected by the integer-only tooltip.

Feed now invokes the **existing SignalLifecycle** on accepted kline events.
`observe()` has no portfolio/risk/order operation; the existing UI risk checks
still determine ACTIONABLE separately. A single indicator pass checks the current
partial candle with explicit POTENTIAL status. `latest_only` limits rule/overlay
iteration to the tail, preserving the full indicator prefix and numerical seeds.
Closed/sync events keep full analysis. UI still computes its visual overlays once
per rerun; no incremental indicator formula or new signal/backtest engine was added.

Confirmed publication freezes observation metadata alongside the immutable signal.
Lifecycle records retain first potential time/price, current observed price, actual
confirmation/availability, cancellation count and the last 32 state transitions.
Notifications remain deduplicated per signal/state across restart and flicker.
No speculative signals are added to the confirmed historical journal.

## State and strategy contracts

`NO_SIGNAL -> WATCHING -> POTENTIAL -> CONFIRMED -> ACTIONABLE / EXPIRED / REJECTED_BY_RISK`

WATCHING is optional; a new condition can directly become POTENTIAL. A preliminary
condition can become INVALIDATED, reappear, or become WATCHING. Confirmed hypotheses
retain existing invalidation/expiry/risk transitions. Frozen signal facts and
confirmation times do not change when decision readiness changes.

| Strategy | Known before current candle closes | What remains provisional |
| --- | --- | --- |
| Trend Following BUY/EXIT | Prior regime/EMA crossing reference; indicator prefix | Current EMA21/55, ADX, Supertrend, price and cumulative volume; requires final close for confirmation |
| Mean Reversion BUY/EXIT | Prior RSI and prior Bollinger relationship | Current range regime and return to lower/middle Bollinger band; requires final close |
| Breakout Detection BUY/EXIT | Prior 20-bar high/low, prior compression, prior crossing reference | Current breakout/exit price and cumulative volume ratio; requires final close |

All three reuse exactly the old thresholds. WATCHING is only the existing EMA-nearby
BUY watch rule, not a newly invented EXIT watch rule. EXIT always means an exit-long
hypothesis, never a short entry or an executed sale. ACTIONABLE is a risk/readiness
result, not evidence of profit. No new strategy or Early Filtered trading rule ships.

## Time and chart contract

| Field / label | Meaning |
| --- | --- |
| candle_time | Source candle OPEN; marker placement only |
| timestamp | Source candle CLOSE boundary; never a discovery time |
| first_seen | First actual observation in this installation, possibly WATCHING |
| potential_detected_at | First actual POTENTIAL calculation; not retroactively inferred |
| source_event_at / received_at | Source event clock / local decoded event receipt |
| confirmed_at / available_at | Actual local observation of a valid closed-candle result |
| detected_at in immutable signals | Actual first journal publication; older history is discovered now |
| observed_price / observed_at | Price of the observed partial or final candle, not an executable bid/ask |
| ui_rendered_at | Browser-local first handoff to chart for that context/id/state; not guaranteed paint or network arrival |

Confirmed source-candle arrows explicitly say `BUY · close` / `EXIT · close`.
Hover and selection explain close/receipt availability. POTENTIAL uses translucent
arrows; WATCHING uses a muted circle. Strategies on the same candle/type/state are
grouped with a count, while hover retains every unique strategy. Marker plans are
compared before calling setMarkers, avoiding redraws on unchanged snapshots.
Invalidation removes only the preliminary arrow. Historical confirmations stay.
Instrument/timeframe switching resets chart marker state. A local expiry timer hides
stale preliminary arrows even if another server payload never arrives.
Legacy signals with missing metadata say "нет данных"; no times are fabricated.

## Reliability and causal evidence

The Feed validates local and source-time close boundaries, OHLCV, continuity and
closed-candle immutability before observation. Duplicate events do not refresh
freshness or observations. Older event timestamps are ignored. Conflicting equal
source timestamps fail closed. Old candle resends do not renew current-bar freshness.
A rejected candle latches an error until successful REST synchronization; ticker
traffic cannot make an unhealed candle stream ready. Stale/disconnected streams
hide preliminary arrows and invalidate preliminary lifecycle state on the UI check.
An ordinary reconnect must obtain fresh kline observations before showing candidates.
UI risk/marker data excludes observations made after its market snapshot.

Tests exercise real formulas for BUY and EXIT, a 100 ms cancelled condition between
UI polls, exact boundary without confirm, delayed confirm, previous-close + new-bar
batch, duplicate/reordered/conflicting events, gap, stale/disconnect/reconnect,
clock drift, timestamp separation, restart, immutable publication, and prevention
of portfolio/risk calls from observation. Existing full causal-prefix and sealed
holdout tests remain part of the suite. This is tested evidence for these contracts,
not a proof against every possible source defect or a physical-market certification.

## Local latency evidence

`python scripts/benchmark_intrabar_v09.py`: deterministic **synthetic** replay,
500 candles and 100 updates, Linux/Python 3.12.14, with historical lifecycle
records preloaded as on startup. Final local measurement (shared host):

| Measured scope | Median ms | p95 ms | Maximum ms |
| --- | ---: | ---: | ---: |
| Old two full analysis passes, calculation only | 100.774 | 157.618 | 173.364 |
| New event receipt to journal/lifecycle publication, including SQLite | 9.644 | 16.066 | 52.748 |
| New indicator stage | 7.953 | 11.667 | 50.717 |
| New lifecycle + signal publication | 0.985 | 1.515 | 7.266 |

These scopes differ: the baseline excludes old polling/UI/storage. Do not call this
an end-to-end network/UI speedup. Existing Streamlit presentation remains 1 second
plus scheduling, overlay calculation and transfer/render time. An event shorter
than that can be recorded without ever being shown as a current arrow. No claim
that every exchange tick is received: upstream Bybit kline cadence is a separate
limit. Full indicator arrays remain O(history), intentionally preserving seeds.
No high-frequency market polling was added.

`signal_timing` exposes processing stages and source-clock delta. That delta mixes
network/queue delay with clock offset; it is **not** verified pure network latency.
The browser records local render-call duration separately. Real WS/REST latency,
physical display paint, UI transfer and Safari timing are NOT MEASURED here.
Final CI repeats the small deterministic replay and retains its JSON.

## Profitability comparison: NOT EVALUABLE WITH AVAILABLE DATA

No sequential intrabar tape with verified receipt/event timestamps and executable
quote observations is available in this checkout. The known user OHLCV file has
finished bars, not the path inside each bar, and is not present here. No raw user
history, final 20% holdout or independent sample was opened/scored.

| Variant | Signals/trades; cancellation share; detection delay/price change; expectancy; PF; drawdown; costs; delta |
| --- | --- |
| A — Confirmed | NOT EVALUATED on a common independent dataset |
| B — Early Potential | NOT EVALUABLE WITH AVAILABLE DATA |
| C — Early Filtered | NOT EVALUABLE WITH AVAILABLE DATA |

Existing Strategy Coliseum, Cost Engine, Causal Signal Outcomes, Paper-path and
purged walk-forward remain the research path. Their OHLCV next-open fills cannot
establish the seconds when intrabar conditions arose. Synthetic replay above is
functional evidence only. No arbitrary OHLC path, invented fills or return estimates.
The persistent lifecycle diagnostic is not a complete raw market tape.

For a separate evaluation, first acquire an allowed sequential partial-candle/quote
tape with receive times and provenance. Freeze a filter before examining outcomes
(e.g. condition persists across a second distinct update at least 2 s later), freeze
manual execution delay assumptions (5/15/30 s sensitivity), use the first actually
available quote after observation + delay, and reuse Cost Engine fees/spread/slippage
and sequential long accounting. Missing quotes or history mean NOT EVALUABLE, not a
favorable fill. Preserve sealed final 20%. Only after this engineering acceptance,
separately investigate 1h/4h trend following, fixed-filter Donchian and BUY regime
filters; never bundle their thresholds into this fix.

## Physical Mac / Safari protocol — NOT RUN

From a clean checkout of the PR's **exact tested SHA**:

```bash
git fetch origin fix/v09-intrabar-signal-visibility
git switch --detach <exact-tested-SHA>
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
export MOEX_DATA_DIR="$(mktemp -d -t candlepath-intrabar)"
.venv/bin/python -m pytest -q tests/test_intrabar_signals_v09.py tests/test_signal_lifecycle_v081.py
node scripts/verify_v09_chart_updates.js
.venv/bin/python scripts/benchmark_intrabar_v09.py
.venv/bin/python -m streamlit run app.py
```

Use Market Data and permitted public data only. In Safari verify preliminary BUY
and EXIT are distinct from solid close markers, hover all strategies, compare source
open/close/discovery/confirmation, change symbol/timeframe, lose/recover network,
sleep/wake, and restart. Confirm stale hypotheses disappear and prior confirmations
retain exact times. A missing live example is NOT RUN, not a pass; synthetic tests
provide a deterministic case. No real or Paper transaction is needed. Keep private
portfolio storage untouched. Roll back by opening the parent SHA with a separate
empty MOEX_DATA_DIR, never resetting or migrating an existing database.

Local Chromium launch was attempted and blocked by environment socket policy
(`process_singleton_posix.cc: socket() failed: Operation not permitted`). Browser
acceptance must be recorded from the exact-head GitHub Actions run. Linux Chromium
is not physical Apple Silicon/Safari/Retina/sleep-wake acceptance.

## Local verification / final CI evidence

- Focused Feed/lifecycle/risk/formula suite: **74 passed**, including **19 new
  intrabar cases**. Forecast fixture follow-up: **30 passed**.
- Full Linux/Python 3.12.14 suite: **946 passed**, 0 failed/skipped/xfail, 57.47 s.
  Command: `MOEX_DATA_DIR=<isolated /tmp directory> python -m pytest -q
  --disable-warnings --junitxml=<temporary report>`.
- Python compilation, JS syntax, chart update/intrabar contracts and **41 Forecast
  geometry checks**: PASS. Browser launch: local BLOCKED as detailed above.
- First full run: 944 passed, 2 failed due old synthetic Forecast Feed objects
  omitting the now-required source event timestamp. Fixed only fixture construction
  to provide accepted source time; retained all assertions and the stricter gate.
  This concrete failure justified the second full run above.
- Exact pushed SHA, GitHub Actions URL and remote browser results are recorded in
  the Draft PR body after CI. Do not infer remote PASS from this local report.
