"""Closed-bar trend adapters and fixed UTC development folds. Research only."""
from decimal import ROUND_CEILING, ROUND_FLOOR

import numpy as np

from .analysis import indicators, regime
from .coliseum_catalog import digest
from .costs import D, CostModel, ExecutionAssumptions, FeeSchedule, budget_quantity, estimate
from .market import seconds
from .paper_path_research import _quote_at, _replay_folds
from .paper_rules_research import ResearchSpotRules
from .trend_history import DAY, START, SYMBOLS, check_development

HYPOTHESES = ("EMA_REGIME", "EMA_PULLBACK")
CAPITAL = D(10000)


def rules_for(symbol):
    if symbol not in SYMBOLS:
        raise ValueError("Unregistered study symbol")
    fields = dict(symbol=symbol, step=D("0.00001" if symbol == "BTCUSDT" else "0.0001"),
                  tick=D("0.01"), minimum=D(10), maximum=D(100), as_of_utc_seconds=START,
                  note="Preregistered illustrative constraints; historical accuracy unverified")
    fingerprint = digest({k: str(v) for k, v in fields.items()})
    return ResearchSpotRules(**fields, original_sha256=fingerprint)


def signals(prefix, timeframe, hypothesis, rules):
    if hypothesis not in HYPOTHESES or timeframe not in ("60", "240"):
        raise ValueError("Unregistered trend path")
    if any(r["closed"] is not True for r in prefix):
        raise ValueError("Trend research requires closed bars")
    if len(prefix) <= 128:
        return []
    f = indicators(prefix)
    bull = (f.ema_fast > f.ema_slow) & (f.adx >= 20) & (f.direction > 0)
    previous = bull.shift(fill_value=False)
    buy = bull & ~previous
    if hypothesis == "EMA_PULLBACK":
        buy = bull & previous & (f.close.shift() <= f.ema_fast.shift()) & (f.close > f.ema_fast)
    sell = previous & ~bull
    result = []
    for i in np.flatnonzero((buy | sell).to_numpy()):
        if i < 128:
            continue
        bar = prefix[i]
        item = dict(strategy=hypothesis, type="EXIT" if sell.iloc[i] else "BUY",
                    candle_time=bar["time"], timestamp=bar["time"] + seconds(timeframe),
                    reference_price=bar["close"], status="confirmed")
        if item["type"] == "BUY":
            close, atr = D(bar["close"]), D(f.atr.iloc[i])
            stop = ((close - 2 * atr) / rules.tick).to_integral_value(rounding=ROUND_FLOOR) * rules.tick
            target = ((close + 4 * atr) / rules.tick).to_integral_value(rounding=ROUND_CEILING) * rules.tick
            if not 0 < stop < close < target:
                continue
            item["risk_estimates"] = dict(stop=str(stop), target=str(target))
        result.append(item)
    return result


def fold_windows(timeframe):
    step = seconds(timeframe)
    for n in range(3):
        purge_start = START + (36 + 180 * n) * DAY
        start = purge_start + 3 * DAY
        end = purge_start + 180 * DAY
        # Engine starts at the FOLLOWING open; the first origin closes exactly at start.
        yield n + 1, (start - START) // step - 1, (end - START) // step


def portfolio_paths(rows, symbol, timeframe, hypothesis, multiplier, *, signal_provider=signals):
    check_development(rows, timeframe)
    if multiplier not in (1, 2):
        raise ValueError("Unregistered cost scenario")
    rules = rules_for(symbol)
    model = CostModel(FeeSchedule(taker=str(D(".001") * multiplier)),
                      ExecutionAssumptions(slippage_bps=str(5 * multiplier)))
    spread = 4 * multiplier
    folds = _replay_folds(
        rows, symbol, timeframe, fold_windows(timeframe), names=(hypothesis,), strategy=hypothesis,
        research_signal_provider=lambda prefix, _, tf: signal_provider(prefix, tf, hypothesis, rules),
        model=model, cash_start=CAPITAL, assumed_spread_bps=spread, assumed_rules=rules,
        max_hold_bars=16, record_equity=True)
    return dict(folds=folds, timeframe=timeframe), model, spread


def passive_daily(rows, report, allocation, model, spread, rules):
    """Daily changes in liquidation value, including entry and exit costs exactly once."""
    daily = {}
    for fold in report["folds"]:
        start, end = fold["start_index"] + 1, fold["end_exclusive"]
        opening = _quote_at(rows[start]["open"], spread)
        quantity = min(rules.maximum, budget_quantity(CAPITAL * allocation, opening,
                                                       rules.step, model, "total"))
        buy = estimate("BUY", quantity, opening, model)
        cash = CAPITAL + buy.cash_delta
        if cash < 0 or not rules.check_entry(buy, opening["bid"], model):
            raise ValueError("Passive entry violates assumed rules")
        previous = CAPITAL
        for row in rows[start:end]:
            close_time = row["time"] + seconds(report["timeframe"])
            if close_time % DAY:
                continue
            closing = _quote_at(row["close"], spread)
            if not rules.sellable_at(buy.net_base, closing["bid"], model):
                raise ValueError("Passive mark violates assumed sale rules")
            equity = cash + estimate("SELL", buy.net_base, closing, model).cash_delta
            daily[(fold["fold"], (close_time - 1) // DAY)] = equity - previous
            previous = equity
    return daily


def fold_dates():
    return [dict(fold=n, purge_start=START + (i + 1) * 3600 - 3 * DAY,
                 first_open=START + (i + 1) * 3600, end_exclusive=START + end * 3600)
            for n, i, end in fold_windows("60")]


def daily_regimes(rows, timeframe):
    """A UTC day's label uses only the bar that closed at that day's start."""
    step = seconds(timeframe)
    frame = indicators(rows)
    return {(int(row.time) + step) // DAY: regime(row) for _, row in
            frame.loc[(frame.time + step) % DAY == 0].iterrows()}
