# Market Evidence Recorder / frozen A-B-C protocol

Development only. Base PR #52: f56732e8d49e5b0fd90591c2cff91650591f6efd.
PR pages inspected: #50 DRAFT a0ca13d26cee204bf152ee20ef5bc8b1e7969e42
(base develop/v0.9); #51 DRAFT 8d916751c255626269c8677600c34649ebeccb36
(base integration/v0.9-final-stabilization); #52 DRAFT f56732e8d49e5b0fd90591c2cff91650591f6efd
(base feat/selective-day-trader-integration). Feature branch starts at #52 and
is intended to target fix/v09-intrabar-signal-visibility. No merge/main change.
GitHub GraphQL returned Forbidden: latest workflow runs and Issue #31 discussion
could not be reliably checked through the API. Known historical 946 passes are
not claimed as new verification. Existing PR52 Feed.observe, transient lifecycle,
immutable closed candles, CostModel, Coliseum and Paper paths are reused.

## Operation and boundaries

Enable deliberately before launching the existing server:

```bash
export CANDLEPATH_RECORD_EVIDENCE=1
bash start.command
```

One per-market file under the configured MOEX_DATA_DIR/research-evidence/ stores
WebSocket envelopes actually delivered to Feed.receive. No extra subscriptions,
API keys or broker calls. The recorder is off by default; it does not backfill
fake observations from OHLCV. It records public kline/ticker/book messages with
source ts/ids as received, Spot identity, local receive and processing UTC seconds,
monotonic process time/session, and source-clock delta of UNKNOWN uncertainty.
That delta combines clock skew and transit delay: it is not network latency.
The source's actual message cadence is retained, not a claim of per-tick tape.
REST seed history is NOT reconstructed as prior intrabar observations. Source
failure/recovery messages are journaled through the existing Feed.event path.

Feed-side SignalLifecycle observations are copied with strategy version/parameters,
first potential/confirmation times, transitions and observed price. Only changed
or freshly observed records are included; portfolio/risk-plan fields are excluded.
Display paint time stays null: PR52 ui_payload_at is a server payload timestamp,
not proof that a human/browser saw a marker. No browser acknowledgement is added.

Dedup uses the canonical envelope SHA256, retained across restarts. Reordered
packets remain in receipt/append order; existing Feed gates decide whether to
apply them. A processing_result is a snapshot after the handler, NOT a claim
that an out-of-order packet was applied. Rejected messages are retained with
reason. Replay is read-only, bounded and requires both receive and processing
at/before cutoff. Backward local receive clocks make timestamp replay fail
closed. Cross-machine clock precision, tick completeness and economic evaluability
remain UNVERIFIED; this API never emits VERIFIED.

SQLite FULL transactions, WAL, immutable triggers and an append hash chain
provide committed-prefix recovery and corruption detection. Hashes are not
cryptographic authentication against an administrator rewriting the whole file.
Default limit: 100000 journal records (a market message can produce several
records), 64 MiB SQLite pages, 64 KiB per record; checkpoint every 100 pages.
At capacity/failure recording stops visibly (BLOCKED), without silently deleting
old evidence or changing trading. Archive stopped files explicitly; do not reset
a live journal. Keep external long-lived SQLite readers closed so WAL checkpoints
can complete. Existing Feed callbacks incur synchronous journal overhead; this
small implementation has no unreliable background queue/drop policy.

Raw message and signal writes are separate transactions. An interrupted handler
can leave a market envelope without a corresponding result/observation. Such
segments must be excluded from causal/economic evaluation, never inferred from
later candles. Replay pages are audit data, not a simulated execution engine.
Restart seeds are historical; ignore historical lifecycle records as new entries.

The existing Security Center expander exposes source readiness and recorder
status, last receive time/age, reported gaps/rejections and the last available
quote with its field timestamps. Missing timestamps stay unknown. Quote status
is not an assertion that every event has contemporaneous executable bid/ask.
Data sufficiency conservatively reports NOT EVALUABLE WITH AVAILABLE DATA until
a separately reviewed continuous tape eligibility/evaluation pipeline exists.

## Frozen research protocol (specification only, no economic run)

Population: Trend Following, Mean Reversion and Breakout Detection, existing
strategy version and unchanged parameters. Register a dataset/tape hash, code
SHA, source/platform, UTC collection dates, gap boundaries, clock assumptions,
quote availability, cost profile, split plan and experiment ID before evaluation.
Only newly observed, continuous development tape qualifies. Do not open or score
the existing sealed final 20%, and do not optimize parameters/filter on it.

- A: first observed CONFIRMED after trustworthy source close and local receipt.
- B: first actually received POTENTIAL (not reconstructed from final candle).
- C: POTENTIAL persists on two DISTINCT source observations separated by >=2
  local monotonic seconds in the same uninterrupted session, same strategy/id/
  candle/direction and no intervening invalidation. Two UI polls, duplicate
  delivery or time spent disconnected do not count. This is a frozen hypothesis,
  not an optimal parameter or an authorization to trade.

Use identical sequential single-long capital/risk constraints, signal-conflict
policy, minimum quantity/notional/tick, barrier priorities and canonical CostModel
for all arms. No independent overlapping hypothetical trade for each signal.
Entry is first available executable quote AFTER detection+5/15/30 seconds;
never interpolate price across a gap or execute at the signal candle's close.
Stops crossed by a gap execute at next available bid, not ideal stop. Preserve
stop-first ambiguity sensitivity using existing Paper-path/Coliseum machinery;
OHLC-only paths cannot economically score B/C. Include base/quote fees, spread
once, slippage, quantity rounding and retained dust/cost basis. Never write any
experiment fills into the user's Paper ledger. Unobserved liquidity/partial fills
remain explicit assumptions and grounds to reject overly strong conclusions.

Report paired arms on the same eligible tape intervals with:

- unique observed signals, cancellations (POTENTIAL then INVALIDATED before
  confirmation), unresolved/right-censored signals separately; cancelled/eligible
  potential denominator, not all historical candles;
- detection-to-confirm delay for matched confirmations; source/receipt/processing
  deltas separately with clock uncertainty, browser display latency UNKNOWN;
- detection-price versus first executable-quote change, by delay scenario;
- sequential completed trade count, win rate, net quote expectancy, profit factor
  (undefined with no loss denominator), maximum chronological equity drawdown,
  average realized net R using frozen initial risk; zero trades means insufficient
  sample, never a profitable result;
- fee/spread/slippage decomposition without double subtraction; delay sensitivity
  at 5/15/30 seconds, cancellation and gap/ambiguity rates, excluded intervals;
- paired confidence intervals resampling contiguous UTC days/blocks across all
  arms, clustering overlapping horizons/signals. Effective sample size is not
  simulation count. Freeze block policy on chronological development folds with
  embargo >= maximum trade horizon. No IID per-signal confidence intervals;
- matched buy/hold, Random Walk and existing baseline comparisons after identical
  costs; regime breakdown uses causal regime at decision time, not hindsight.

Until continuous sequential intrabar+quote tape, completed observations and
credible availability clocks exist, B/C output must be exactly:
**NOT EVALUABLE WITH AVAILABLE DATA**. No winner, profit, expectancy or win-rate
is calculated in this PR. There is no parameter sweep, ML or autonomous executor.

## Validation and rollback

Tests: synthetic Feed -> Recorder, POTENTIAL/cancellation/CONFIRMED after receipt,
duplicate and late packets, immutable prefix, missing/invalid closure rejection,
clock rollback, restart dedup, corruption detection, hard-exit transaction rollback,
no Paper rows/orders. Existing PR52 tests cover feed gaps, restart historical
classification, provisional lifecycle and renderer timestamp semantics.

Benchmark script `PYTHONPATH=. python scripts/benchmark_evidence_v09.py` measures
synthetic local FULL SQLite append latency/throughput at 300/3000 journal rows,
status read and integrity scan. See benchmark.json. It measures no exchange delay.

Run project pytest, compileall, JS syntax/geometry/chart contracts and its three
Chromium scripts. On this cloud host loopback must be included in BOTH NO_PROXY
and no_proxy; do not unset external proxy settings. Physical Mac/Safari and real
Bybit collection were not performed; Linux/Chromium is not their acceptance.
On Apple Silicon use native Python3.12/3.13 and the existing strict local QA
script on a TEMPORARY MOEX_DATA_DIR. Verify opt-in recording, stop/restart,
sleep/wake gaps and status with the owner's permitted public source separately.

Rollback: stop the app, unset CANDLEPATH_RECORD_EVIDENCE and switch back to the
PR52 base on a clean checkout, or revert this PR in a reviewable branch. Preserve
research files as evidence. No user portfolio/schema migration needs reversal.

### Verified delivery evidence

Public workflow page [43426794039](https://github.com/nuPochtiRabotaet/CANDLEPATH/actions/runs/43426794039)
shows Success for PR52's f56732e revision. This is baseline evidence only, not
CI for the Recorder branch. It was visible through the public web fallback even
though GraphQL/workflow API access is denied. PR creation was attempted with
base fix/v09-intrabar-signal-visibility and failed with
`Post https://api.github.com/graphql: Forbidden`; no Draft PR number is claimed.
The feature branch is pushed. New-head remote CI remains unverified.
