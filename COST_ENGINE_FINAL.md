# Cost Engine — rc3 verified implementation, not FINAL release

All authoritative quantity, basis, fees and cash arithmetic uses Decimal from decimal strings. Market BUY fills at ask × (1+slippage); SELL at bid × (1−slippage). Spread is not added a second time. Taker applies to Market. Maker is configured for future modeling only. Defaults and modified rates are explicit local assumptions, not verified account fees.

BUY quote: cash debit = quantity × fill + quote fee; received base = quantity. BUY base: debit = quantity × fill, received base = quantity − base fee. Cost basis equals cash debit; effective entry = basis/net base. SELL base fee is unsupported and rejected. SELL cash proceeds subtract exit quote fee. Partial exits allocate basis proportional to actually disposed base; final exit allocates the exact remaining basis.

`net holdings = sellable for one order + remaining after that order`. `Non-sellable residue` is distinct from a tradeable remainder limited only by max order size. Min notional is checked at modeled execution price, quantity steps are never silently rounded at execution. UI amount sizing floors explicitly before preview. User-confirmed sell-available is an exact quantity; stale rule/price/position changes require new preview.

Realized P&L = proceeds − allocated basis. Residue retains basis and unrealized P&L. Explicit writeoff creates Written Off, not Filled; cash delta is exactly zero and remaining basis becomes a loss. It requires the whole current remainder, current revision and fresh market/rules in UI. Private exchange dust handling is not simulated as accepted exchange execution.

Protection risk and new entry net outcomes use only legally executable quantity at stop/target; zero recovery is assumed for the remainder. Open aggregate risk uses the same rule-aware proceeds. No fresh rules → no assumed stop recovery. This can conservatively block a new position. Cash/equity mark still includes owned residue at Bid; immediate liquidation proceeds exclude unsold residue.

Gross R/R uses pre-cost distances; Net R/R uses after-cost outcomes. Round-trip cost compares current modeled BUY debit to current modeled SELL proceeds. Historical fill fee/slippage snapshots never change when configuration changes. Reported spread/slippage are decomposition, not additional debits.

Atomic lock + immutable UUID prevent duplicate successful posting. A late accounting exception rolls back balances/holdings before recording Rejected. The tests cover base fee residue, exact allocation, double confirmation, two competing exits, rule refresh, explicit writeoff and posting failure injection.
