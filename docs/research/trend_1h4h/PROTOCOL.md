# Trend Following, BTCUSDT / ETHUSDT Spot, 1h / 4h

Preregistration on f56732e8d49e5b0fd90591c2cff91650591f6efd, before requesting
price history. Two research hypotheses, eight paths, no parameter search.
This study compares each path separately. It does not pool their capital.

## Data

Freeze [2024-01-03, 2025-12-23) UTC (720 days). Only request the first 576
days, ending before 2025-08-01. The last 144 days are reserved and never
downloaded or scored. Check the original Coliseum holdout guard for overlap.
Use the official Binance Public Data monthly Spot 1h kline ZIPs and publisher
SHA-256 checksums, January 2024 through July 2025. Omit the first two days.
If that venue is unavailable for either instrument, rerun BOTH on Bybit V5
public Spot REST from the same dates. Select source by access and coverage
before simulation. Never mix venues or fill a gap. No keys. Local reproduction
can use the original public Binance archives with their checksum companions.
Reject unordered, duplicate, missing, off-grid, open, or invalid bars. Form UTC
4h candles from exactly four consecutive hourly bars. Publish fingerprints,
provenance and aggregates only. Historical OHLCV contains no executable quotes.

## Fixed rules

Use CandlePath indicators on closed prefixes, warm up at least 128 bars.
Bull = EMA21 > EMA55, ADX14 >= 20, and Supertrend(14,3) direction positive.
A enters on false → true. B requires bull on both bars, prior close <= its
EMA21, current close > current EMA21. Either exits on first loss of bull.
One long at a time. Next open or later, fixed stop close − 2 ATR14 (floor to
tick), target close + 4 ATR14 (ceil to tick). Invalid levels reject entry.
Maximum hold 16 bars. Use existing stop-first/gap precedence, period loss and
drawdown guards, size limited to 25% of cash and 0.75% stop risk. Start every
fold with 10,000 USDT. Assume quote fees, price tick 0.01, minimum notional
10 USDT, quantity step BTC 0.00001 / ETH 0.0001 and max quantity 100.
These illustrative constraints lack historical exchange attestation. A
non-executable exit invalidates the scenario. Threshold fills and terminal
close liquidation are optimistic. No depth, partial fills or latency data.

## Chronology and comparators

Reserve 36 warmup days followed by three consecutive 180-day windows. Omit
the first three days of each window. The remaining 177 complete UTC days
per fold start flat and finish flat. First decision is at the opening boundary
using the bar just closed. Each 72-hour purge/embargo covers the maximum
signal-to-timeout horizon (17 x 4h); no outcome or open position crosses a fold.
Indicators may use observed history during the embargo. No model is fitted.
Periods are disjoint, with possible dependence across time and instruments.

Run base (taker 10 bp/side, full spread 4 bp, slippage 5 bp/side) and double
(all three doubled). Attribute modeled costs on each executed path. Compare
against USDT at zero yield, buy-and-hold at 25% initial allocation (matched
capital cap), and 100% buy-and-hold for context. Charge each passive path the
same entry and liquidation costs and apply the same assumed quantity rules.
Entry is the first scored open, liquidation the final scored close.

Report trades, win rate, mean net USDT/trade, PF (undefined with zero losses),
net USDT, return on three separately funded folds (net / 30,000), maximum
within-fold open/close marked-to-liquidation drawdown, per-fold results and
entry volatility (ATR/close vs trailing 100-bar median). Report gross, fees,
spread and slippage. Do not compound across excluded periods.

## Evidence policy

On the synchronized daily equity changes divided by initial fold capital,
jointly test 16 base contrasts (eight paths minus cash and minus 25% passive).
Use CandlePath's fold-stratified circular-block max statistic, seed 20261105,
1,999 replicates, 3/7/14-day blocks. Report simultaneous 95% intervals and
one-sided adjusted p; primary display 7 days. These intervals describe *mean
daily excess*, not individual trade returns. No independent-trades assumption.
Double costs are sensitivity, not another selection contest.

For independent follow-up only, require the existing 30 trades/fold sample
gate, positive net expectancy in every base fold and overall at double costs,
positive return after excluding the best fold, lower bounds above zero and
adjusted p <= .05 versus both comparators for all three block lengths, and
marked drawdown within the existing 12% risk limit. Passing these conditional
screens permits independent review only. With weak evidence return NO TRADE /
INSUFFICIENT EVIDENCE. Without verified coverage return NOT EVALUABLE. No
automatic promotion, deployment, or opening the holdout.
