# Volatility Breakout — real development market run (2026-11-19)

**Decision: NO TRADE / INSUFFICIENT EVIDENCE.** This report records the **new** successful GitHub Actions market run; it does not modify the preregistration or replace the earlier blocked `RESULTS.md` attempt.

- [GitHub Actions run #44514120915](https://github.com/nuPochtiRabotaet/CANDLEPATH/actions/runs/44514120915) — **success** on exact commit `260b1d96dbfd76d6902913775fce42a04809fba3`.
- [Run artifact: two JSON reports](https://github.com/nuPochtiRabotaet/CANDLEPATH/actions/runs/44514120915/artifacts/14524866213), retained until approximately 2026-12-03.
- Two complete runs: same source, **byte-identical** JSON; SHA-256 `9b4289f36bd4d2f75d1f6ca565b22f01e767bd2b1ce49945dea597f771317280`.
- Source: Binance Public Data via HTTPS. All **38** registered Spot monthly 1h archives matched publisher checksums and the preceding study's fingerprints. BTC and ETH each contained 13,824 1h bars; 4h was aggregated causally.
- Preregistration: `edf3aa8352f6ca00fcf72dd15dc8c899b9fcdf7d`; protocol SHA-256 `07feec2b7db1fd55752794b3db5fd5c6ec1c69ac33bf8328d947ab292140767c`.
- Evaluation: 3 disjoint 177-day development folds, 10,000 USDT starting cash per fold; aggregate return = P&L / 30,000 USDT, **not annualized**. The final holdout was not evaluated.
- Locked dependencies, registered hashes and focused causality/accounting tests passed in the Actions job. This is a historical OHLCV simulation, **not executed trading or independent confirmation**.

## Net results, after modeled fees, spread and slippage

| Spot variant | Trades | Win rate | PF | Mean net USDT/trade | Net USDT | Net % | Max within-fold DD % | Net % with 2x costs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT 1h | 282 | 34.75% | 0.608 | -7.68 | -2,166.17 | -7.22% | 10.13% | -12.04% |
| BTCUSDT 4h | 76 | 42.11% | 0.970 | -0.92 | -69.69 | -0.23% | 4.77% | -2.13% |
| ETHUSDT 1h | 277 | 38.99% | 0.727 | -7.09 | -1,964.20 | -6.55% | 9.81% | -11.95% |
| ETHUSDT 4h | 82 | 39.02% | 1.072 | +2.76 | +226.38 | +0.75% | 5.53% | -1.08% |

All four variants lost to their matched 25%-allocation buy-and-hold: BTC **+7.78%**, ETH **+3.93%**, versus a zero-yield USDT baseline at 0%. Full-capital buy-and-hold is included in the JSON only as additional context.

Fold net USDT:
- BTC 1h: -591.06 / -574.14 / -1,000.97.
- BTC 4h: +140.26 / +46.51 / -256.45.
- ETH 1h: -817.96 / -590.63 / -555.62.
- ETH 4h: +29.91 / -12.65 / +209.12.

The ETH 4h positive aggregate is **not robust**: one losing fold, fewer than 30 trades in two folds (27/25/30), and negative results with double costs.

## Joint statistical assessment

The registered family of **eight** daily contrasts (four paths versus USDT and matched HOLD_25) used 531 aligned daily observations, synchronized fold-stratified circular-block bootstrap, blocks 3/7/14 days, 1,999 replicates, seed 20261105. All registered `stable_candidates` are empty.

For the primary 7-day block:
- ETH 4h versus USDT: mean **+0.426 bps/day**, simultaneous 95% CI **[-3.894, +4.747] bps/day**, one-sided adjusted **p = 0.905**.
- ETH 4h versus HOLD_25: mean **-1.797 bps/day**, CI **[-11.102, +7.509]**, adjusted **p = 1.000**.
- BTC 1h versus USDT: mean **-4.079 bps/day**, CI **[-6.793, -1.365]**, adjusted **p = 1.000** for the *positive-edge* alternative.

No strategy obtained a positive simultaneous confidence lower bound and adjusted p <= 0.05 versus both comparators across all three block lengths. These CIs concern **mean daily excess return**, not terminal portfolio return or P&L per trade.

## Safety, interpretation and next gate

- Causal gates, data provenance and registered base risk limits passed; the sample, all-positive-fold, stress and simultaneous-significance gates rejected the candidate strategies.
- The machine field `validated: false` is intentionally retained: this is development-only exploratory evidence. Profitability remains **unverified**, and the sealed holdout stays untouched.
- Historical OHLCV cannot verify order-book liquidity, true execution latency, partial fills, intrabar extrema of portfolio equity or historical exchange constraints. Threshold stop and final close pricing may be optimistic.
- Do not deploy or promote any of these fixed rules to live trading, and do not tweak parameters after observing this test.

**Recommended next step:** independent methodological review of this finished experiment and a *new, separately preregistered* strategy family on a non-sealed research design; avoid adaptive re-fitting on the same development window.
