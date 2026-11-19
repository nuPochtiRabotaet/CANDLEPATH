# Volatility Breakout on BTCUSDT and ETHUSDT Spot

Frozen before the first breakout replay or inspection of its outcomes. Base
a389b4b421995dbf1ccda0eae502ed110370481f includes the previous development
study. PR #52 is Draft at f56732e8d49e5b0fd90591c2cff91650591f6efd. Issue #31
is open. Python 3.12.14, numpy 2.5.4, pandas 2.3.3, httpx 0.28.1. The companion
SHA256SUMS records this protocol, the dependency locks, the public data manifest
in the previous aggregate report, and the protected Coliseum interval metadata.

## Attempt ledger and estimand

The eight earlier EMA regime/pullback paths generated 16 contrasts on these
same dates. All eight received NO TRADE / INSUFFICIENT EVIDENCE. Here one
fixed Donchian/volatility hypothesis has four separately capitalized paths
(BTCUSDT/ETHUSDT × 1h/4h) and eight primary contrasts. Thus 12 development
paths and 24 primary contrasts have been considered in the two studies.
The earlier 100-candidate BTC 5m tournament is separate. No parameter search.
H1 requires positive after-cost excess versus both cash and 25% passive
exposure. For each path the null includes nonpositive mean daily excess against
either comparator. Absence of evidence does not establish the null.

## History and embargo

Use only Binance Public Data Spot 1h monthly ZIPs 2024-01 through 2025-07 for
both symbols. Verify the published SHA-256 for each ZIP, all 38 archive hashes
and both hourly and 4h fingerprints from the pinned previous study. A local
copy with an identical fingerprint is admissible with its actual transport
identified. Stop on a missing archive, changed fingerprint, bad grid, invalid
OHLCV, duplicate, incomplete bar or source failure. A paired checksum supplied
by a local user alone cannot establish provenance. No alternative venue.

Use [2024-01-03, 2025-08-01) UTC, 13,824 completed hours per instrument,
3,456 UTC 4h bars aggregated from four consecutive hours. Never request or
score the new holdout [2025-08-01, 2025-12-23), nor the original protected
Coliseum history. Retain 36 warmup days and three windows of 180 days. Omit
the first 72 hours of each window; this covers the 17 × 4h horizon from
signal bar open through timeout. First permissible origin closes at the first
scored open. Indicators can use the past embargo bars. No trained parameters.

| Fold | First scored open (UTC) | Exclusive end (UTC) | Days |
| --- | --- | --- | ---: |
| 1 | 2024-02-11 | 2024-08-06 | 177 |
| 2 | 2024-08-09 | 2025-02-02 | 177 |
| 3 | 2025-02-05 | 2025-08-01 | 177 |

## Entry, sizing and liquidation

Evaluate each closed bar i with 20 preceding bars. Use the existing trailing
maximum of High[i-20:i] and Wilder ATR14 seeded with the mean of the first
14 TRs. TR is max(high-low, abs(high-previous close), abs(low-previous close)).
Enter on close[i] strictly above the prior maximum and TR[i] >= 1.25 ×
ATR[i-1], with finite positive prior ATR. Every qualifying bar is eligible
when flat. No rising-edge, EMA, volume or regime filter. Signal becomes known
at the close. First modeled entry is the following available open. One long
at a time in each independent scenario, no short or pyramiding. No discretionary
EXIT. Stop = signal close − 2 × prior ATR (floor to tick), target = signal
close + 4 × prior ATR (ceil to tick). Reject invalid protection or entry quotes
outside the original levels. Max hold 16 bars, checked at open under the
existing engine. Gaps execute at the available open, ambiguous bars stop first,
remaining positions close at the final fold close. Same-open exit/re-entry is
blocked. Intrabar fills have bar-close availability and threshold-fill optimism.

Start flat with 10,000 USDT per fold. Existing engine caps position at 25%
of available capital and initial stop risk at 0.75%; retain its daily/weekly
loss and drawdown gates. Assumed Spot rules are tick 0.01, minimum notional
10 USDT, maximum 100 base units, BTC quantity step 0.00001 and ETH 0.0001.
These model inputs lack historical exchange attestation. Entry and exit use
Decimal arithmetic, taker fee 10 bp/side in quote, full spread 4 bp, slippage
5 bp/side. Stress doubles all three and reruns the complete sequential path.

## Reporting and decision

Compare with zero-yield USDT, and 25%/100% initial buy-and-hold bought at
first fold open and liquidated at final close with identical modeled costs.
Report trade count, win fraction, total/mean net USDT, PF (undefined if no
losses), fee/spread/slippage, fold P&L, returns, and maximum within-fold
marked-to-liquidation drawdown sampled at opens and closes. Aggregate return
= sum of net USDT divided by 30,000. Remove the best base fold and report
remaining net USDT and return on the remaining 20,000. No compounding across
resets. Depth, queueing, actual execution latency and intrabar DD are unknown.

Use 531 aligned daily changes in liquidation equity divided by 10,000.
Compute eight contrasts jointly against USDT and 25% buy-and-hold using
CandlePath's fold-stratified synchronized circular-block max statistic. Seed
20261105, 1,999 replicates, blocks 3/7/14 days. Report mean daily excess,
simultaneous two-sided 95% intervals, one-sided adjusted p at each block.
Primary display uses 7 days. Trade expectancy uses USDT per closed trade.
Also report min(1, 2 × within-family adjusted p) as a two-study Bonferroni
sensitivity. This accounts descriptively for the two named research families;
adaptive reuse of the period prevents an independent confirmation claim.

Require >=30 completed trades and positive net expectancy in each base fold,
positive total net at double costs, positive net after removing best fold,
maximum base marked DD <=12%, verified data and passing causal checks, and
positive simultaneous lower bound with adjusted p <=0.05 versus both primary
comparators for every block length. Only independent research review is
permitted upon passing all gates. Otherwise NO TRADE / INSUFFICIENT EVIDENCE.
If the declared data are unavailable, publish NOT EVALUABLE with missing
metrics. Neither synthetic QA nor the prior strategy's aggregate return
constitutes evidence for this hypothesis.
