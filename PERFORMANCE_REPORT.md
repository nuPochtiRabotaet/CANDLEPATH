# Performance — rc3

Implemented in crypto/performance.py, opt-in UI in performance_ui.py. Full SQL ledger scan under one consistent read snapshot; display limit 200 does not affect statistics. Tests include 360 orders / 120 positions and period boundaries.

Closed positions require BUY plus exact disposal of net base and no remaining live position. Partial exits do not inflate trade count/win rate. Writeoff is included as a zero-recovery accounting loss, explicitly marked. Orphan exits/missing cash deltas produce incomplete-history warnings; legacy strategy/timeframe/risk remain unknown. No automatic signal attribution to a manual trade.

Metrics: closed positions, wins/losses/breakeven, win rate, average win/loss, expectancy, profit factor, net P&L, holding time, planned Net R/R and realized R where initial risk exists; grouped by strategy/timeframe. PF is null when there are no losses (never Infinity). Gross adds actual fees back to net and still includes modeled spread/slippage. Fees/slippage/half-spread in the selected period are reported separately without subtracting twice.

Time filters select positions by final exit UTC after lifetime aggregation; costs select actual fill timestamps. Consequently costs during a period and total lifetime fees of positions closed in that period may differ legitimately. Partial-position count describes the complete current ledger, not only the filtered interval.

Realized equity = initial capital + cumulative realized P&L at exit events. Observed MTM = cash + holdings marked at Bid; no estimated future exit fees. Samples at most once/minute plus fills/writeoffs. Stale prices mark the point incomplete; gaps over two minutes are not connected. Drawdown is relative to observed peaks inside the selected period, not tick-level or full historical drawdown. No pre-rc3 MTM reconstruction. Frozen fill snapshots prevent changed fees rewriting history.

Limitations: no deposits/withdrawals in this isolated paper account; no Sharpe/Sortino claim from sparse irregular samples; no independent backtest, strategy significance or return guarantee. Millions of ledger rows have not been benchmarked. Full report computes outside the critical chart fragment, caches five seconds, and exposes refresh.
