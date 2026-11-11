# CandlePath v0.9: selective Day Trader Skill integration

Development-only review. No exchange orders, brokerage credentials, raw market
files, portfolio migrations or sealed-final evaluation are part of this work.

## Scope and exact sources

- CandlePath PR [#50](https://github.com/nuPochtiRabotaet/CANDLEPATH/pull/50)
  was OPEN with head `a0ca13d26cee204bf152ee20ef5bc8b1e7969e42` when inspected.
  Its head branch is `integration/v0.9-final-stabilization`; develop/v0.9 was
  `c6ae68a59ab364a33f9f3311d53da1e637db6380`. This change starts from the former
  and targets the integration branch, as explicitly requested by the owner.
  This supersedes AGENTS.md's general instruction to target develop directly.
- Upstream: [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill/tree/3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd),
  commit `3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd`.
- Read the existing `DAY_TRADER_SKILL_ADAPTATION.md` and `SOURCE_REVIEW.json`
  before implementation. The former reviews only six modules and describes an
  earlier rc3 state. Its statements that crypto replay/validation are missing
  are historical: the actual PR #50 has these features. The old document is
  preserved; this report and the expanded source manifest supersede its scope.
- `../SOURCE_REVIEW.json` now records all eleven source hashes, imports,
  entrypoints and executed offline test counts. The comparison is to actual
  PR #50 code, not the original MOEX snapshot or marketing claims.

## All eleven modules

Test counts below are the pinned upstream offline unittest run. They establish
fixture behavior, not data-source availability or independently validated alpha.
All 315 tests passed, including 11 repository/documentation tests.

| Module | Algorithm, assumptions and correctness limits | Upstream tests | CandlePath equivalent at PR #50 | Decision |
|---|---|---:|---|---|
| trader-scanner | Nasdaq symdir universe; daily RSI/price/volume setups; ORB first uses closes as a necessary-candidate filter, then fetches OHLC to confirm close above range high. Counts requested/fetched/unusable/unconfirmed and errors. Bounded confirmation can leave candidates unchecked; no hit is not a complete negative scan. NYSE calendar and Yahoo snapshots are specific assumptions. | 36: universe, fixtures, ORB forming bars, incomplete history, confirmation caps and HTTP fallbacks | `analysis.analyze`, `Feed` integrity/backfill, lifecycle; no aggregate requested/excluded scan contract | **Adapt** completeness diagnostics only. Preserve existing strategies; no US universe/calendar, new market subscription or trade authorization. |
| trader-news | Yahoo RSS and SEC Atom, keyword/ticker tagging, dedup by id/link/title/day, remembered seen ids. Keyword tags are context, not evidence. `select` admits up to now+10 minutes and items without publication time; unsuitable for causal trading features unchanged. | 17: RSS/Atom parsing, dedup, retention, fixtures and SEC identification | No equivalent news evidence service; market event diagnostics are not news | **Later** separate contextual evidence feed, never an execution input by default. |
| trader-entry | ORB/level breakout on completed 1m/5m bars with lag settlement, optional volume ratio and entry window. Missing chart O/H/L may be filled with close in parser; range completeness is clock-based rather than requiring every slot. This can misstate evidence on sparse input. | 39: forming/closed boundary, pending settlement, watch loop, replay and dates | `analysis`, `SignalLifecycle`, historical availability checks in Paper path | **Already Implemented** stronger immutable/closed-bar contracts. **Reject** parser repairs and NYSE timing. |
| trader-exit | Decimal cents, OR midpoint/low, fixed price/percent/ATR stop and R/price target; minimum stop distance and scheduled flatten time. Tick is fixed to cents and ATR may have fewer than 14 bars. Geometric R excludes actual transaction costs. | 14: stop variants, rounding, ATR, session bars and plan CLI | `costs.scenario`, `risk.plan`, `ProtectionPreview`, stop/target editor and gap-aware replay | **Already Implemented**. **Reject** cent rounding, 15:55 flatten, or automatic protective-level replacement. |
| trader-timemachine | Complete 78-slot NY sessions strictly before plan date; normalize each bar to previous close; sample historical neighboring slots independently. Fixed seed; separate fan simulation. Stop-first if both barriers touched; assigns exactly -1R to stops and replays entry at signal close. No fees/spread/slippage or gap-loss fill model. | 47: frozen fixture numbers, seed, complete sessions, look-ahead/cutoff, barrier/rule variants | `paper_path_research`, `signal_outcome_research`, `forecast_baseline`, `forecast_evaluation`, purged walk-forward and Coliseum | **Already Implemented** causal execution and sensitivity; **Later** independently tested UTC-seasonal challenger. **Reject** upstream replay/cost/probability semantics. |
| trader-risk | Per-order and batch reasons, duplicate fingerprint, caps, cash/exposure, PDT/day limits, entry windows; some exit checks become warnings. Mostly float USD. `price_times=None` explicitly treats every supplied price as fresh. Same-day risk verdict isn't CandlePath's short-lived revision guard. | 43: malformed/batch/bracket/duplicate orders, position/cash limits, timing and freshness | `risk`, `orders`, inventory, atomic `Paper.execute` and quote freshness | **Already Implemented** stronger financial and transactional gates. **Adapt** explanation structure only; **Reject** freshness default, floats, PDT/calendar and broader exit exemptions. |
| trader-budget | Compute whole-share caps from cash/budget, max loss, position/order caps; show binding constraint. Market reference=max(plan,fresh quote), cent rounding. Only first tie is marked, fees and spread not modeled by the sizing formula. | 31: caps/refusal, cash, whole shares, stale quotes and weighted allocations | `risk.plan.recommended`, `budget_quantity`, canonical Decimal cost engine | **Adapt** all tied binding caps from existing Decimal limits; fix recommendation exceeding exchange max. No alternate sizing engine or thresholds. |
| trader-broker | Exact Alpaca-field fingerprint, text yes parser, same-day risk match, JSON approval/result log; prints connector call, does not itself implement broker submission. Manual fill entry and float lot/cash updates are not transactionally coupled to state. | 18: yes rejection/acceptance, edited ticket, same-day gate, flattened proposal and manual FIFO fill | UUID OrderPreview, account/rules/profile revisions, consent, atomic commit and idempotence; remote executor blocked | **Reject** brokerage connectors, yes-in-chat approval and JSON financial ledger. Existing explicit Paper confirmation is stronger. |
| trader-alerts | Above/below/percent/time/opening-bell rules, rearm and persisted dedup. Rule id (often symbol+type) doesn't bind the changed level; `evaluate` uses supplied quotes without own freshness guard. Daily bell semantics are NYSE-specific. | 30: dedup/rearm, market clock, fixture quotes and bounded HTTP retry | Lifecycle notification id per signal/state; protective obligation/attempt lease, revisions, stale gates and restart tests | **Already Implemented** applicable dedup/recovery; **Reject** stale price evaluation, daily reset and treating an alert as execution. |
| trader-analyst | SEC XBRL quarterly concepts, Q4=annual-minus-three-quarters, TTM, YoY/margins, restatements, latest earnings exhibits, lag note. Latest restatements intentionally win; no historical as-of filing cutoff. Unit/duration/fiscal comparability still require review. | 13: Q4, TTM, restatement precedence, fiscal labels, exhibits and stale facts | Invest Advisor exists but is not an SEC point-in-time fundamentals pipeline | **Later** optional Invest context adapter; never mix latest restated facts into past crypto signals. |
| trader-pelosi | House Clerk ZIP/XML index; PTR text/PDF parsing; owner, ticker, amount ranges, options and filing delay; seen doc-id tracking. Disclosed trades may be weeks old, prices unknown, text extraction heuristic. External `pdftotext` required for PDFs. | 16: XML/ZIP, member filters, multiline PTRs, options, late disclosure and CLI | No counterpart needed for Bybit Spot; historical event arrival contracts would be required | **Reject** for v0.9 trading; **Later** only if owner requests a separate disclosure research feature. |

## Actually integrated

No upstream Python source was copied or imported by CandlePath. Two design ideas
were reimplemented using CandlePath's own existing services:

1. **Explainable Paper sizing.** `risk.plan()` exposes Decimal-string caps for
   individual risk, remaining portfolio risk, free cash including costs, symbol
   exposure, total occupied capital and exchange maximum quantity. Every tied
   step-rounded bound is listed. Minimum notional, quantity step, tick and the
   existing cost snapshot are shown. The recommendation now also respects the
   exchange maximum; the order gate already enforced it. Error gates, risk
   percentages, fees and the actual execution model were not relaxed.
2. **Scan completeness.** `signal_scan.scan_candidates()` audits an explicit
   requested Bybit Spot universe before passing the available closed prefix to
   the existing analyzer. It returns requested/scanned/excluded counts,
   COMPLETE/PARTIAL/INCOMPLETE, exclusion codes, cutoff and missing receipt-log
   disclosure. It rejects bad OHLCV, duplicates/gaps, stale/short history and
   mismatched identity. Unclosed/future/unavailable bars never create signals.
   The optional Trade panel checks only the selected instrument and labels that
   scope. It does not pretend to scan the whole exchange or fetch new markets.

Sizing is an estimate for the selected stop/quantity. Base-currency fees,
rounding and residue can change the per-unit loss on resize; every new quantity
still requires a new validated Preview. Hard drawdown/day/week/position/freshness
blocks can veto it. An informative cap is never authorization.

The immutable UUID behavior is intentionally retained: repeated prepare with the
same UUID returns the original frozen request, including when the caller edits
its local input. It cannot alter the pending order. Confirm accepts its stored
request only and revalidates account/rules/profile/market under the financial
transaction. A changed order requires a new UUID/preview. Existing tests check
that mutating the returned preview cannot mutate the stored request. This is
not replaced with the upstream same-day fingerprint flow.

## Entry/exit and alerts audit

The current signal timestamp is candle open+interval; provisional WATCHING and
POTENTIAL are separate from CONFIRMED. EXIT readiness already reuses sell_preview
(the stage-1 fix in PR #50), including quantity/rules/cost/dust checks. Existing
regressions exercise delayed sides, out-of-order book events, reconnect/backfill,
immutable history, duplicate notifications, restarted attempts, changed protective
levels, partial exits, concurrency and rollback. No reason was found to change
strategy thresholds or replace this machinery with upstream alerts.

New scan tests also cover delayed observed_at/available_at: a closed candle not
yet received cannot enter the analyzed prefix. Absent receipt timestamps remain
unknown, not fabricated historical availability. The scan result is a timestamped
manual diagnostic; it does not update live or feed the execution/lifecycle gate.

## Time Machine decision and challenger admission protocol

There is no verified development-market dataset in this environment from which
to demonstrate a slot-conditioned advantage. No original or revised sealed
holdout was inspected/scored. Synthetic tests and the upstream TSLA fixture are
not evidence that UTC seasonality improves Bybit Spot predictions. Therefore a
second simulator/challenger is **not admitted** in this PR.

A later challenger should be a sampling policy plugged into existing research
execution, not another ledger or barrier engine:

1. Freeze method/version, seed, input cutoff, dataset fingerprint and a UTC
   hour-of-week conditioning policy. Require minimum independent historical
   weeks per bin; otherwise return INSUFFICIENT_SAMPLE, never silently widen
   windows after seeing results. No NYSE slots or market-close rule.
2. Restrict all available_at/closed bars to each decision prefix. Use contiguous
   return/OHLC blocks so volatility dependence is retained, unlike independent
   upstream slot draws. Preserve hashes of old published forecasts.
3. Freeze chronological development folds, purging and embargo >= largest
   outcome horizon; use the existing sealed-holdout guard. No final scoring.
4. Compare paired origins to Random Walk and current EWMA baseline: pinball,
   coverage and width by horizon/regime, sample sizes and uncertainty. An equal
   median is not evidence of directional skill. Pre-register rejection criteria
   and prohibit tuning on the final holdout.
5. Reuse existing Paper path/Coliseum accounting for fees, spread, slippage,
   gaps, next-available entry, dust and stop-first/ambiguous sensitivity. Monte
   Carlo path counts are not independent market observations; net simulated R
   is not verified return or execution capability.
6. Admit only with reproducible development evidence and isolated experimental
   review. A negative comparison is a valid result; do not add UI confidence
   percentages or change production strategy selection from simulation alone.

## Later contextual information proposals

- **News:** immutable event envelope with source URL/hash, source event time,
  published_at, first_observed_at, available_at and revisions; dedup independent
  of delivery attempts; bounded retries and explicit partial-source coverage.
  Unknown or future publication time is quarantined. Sanitize external text,
  show provenance and permit opt-in context only; no price-causation claim.
- **Fundamentals:** an Invest-only point-in-time SEC adapter, accession-specific
  storage and unit/fiscal-period quality flags. Never retroactively replace
  historical features with later restatements. Q4 derivation is labeled and
  missing units/quarters block computation. It is unrelated to Crypto execution.
- **Disclosures:** only if separately requested: index by public filing/first
  observation rather than transaction date; retain ranges/unknown prices and
  revisions. PDF extraction is sandboxed and untrusted. No copy-trading signal.

## Excluded from integration

Upstream broker/Alpaca/IBKR commands, real keys/orders, conversational approvals,
JSON account updates, US tickers/NYSE/PDT/calendar, cent/whole-share money math,
news keyword trading signals, latest-restatement historical backfills, time-stop
flattening, stop-at-exactly-minus-1R gaps, signal-close ideal fills, uncalibrated
Monte Carlo odds and sealed-holdout parameter selection are all excluded.

## Licensing

Upstream is MIT, Copyright (c) 2026 Jake Schincariol. The complete original notice
remains in `../DAY_TRADER_SKILL_LICENSE.txt`. This PR transfers ideas, not source
or substantial portions of code. That notice must accompany any future copied
source. No new upstream runtime dependency, plugin, network destination or
credential was installed in CandlePath.
