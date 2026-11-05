"""Read-only, single-long hypothetical Paper-path research for CandlePath v0.9.

NOT the production Paper engine, not a fill simulator, and not an automatic
trading strategy. This isolated development-fold probe reuses the same
CostModel estimate arithmetic and EXISTING confirmed indicator signals.
Only closed user-supplied OHLCV; the final holdout is never replayed.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
import math
import json
from functools import lru_cache

from .analysis import analyze, VERSION as RULES_VERSION
from .costs import CostModel, D, estimate
from .forecast_evaluation import _closed_rows
from .forecast_walkforward import evaluate_purged_walkforward
from .market import seconds
from .risk import PROFILE
from .paper_risk_research import ResearchEquityGuards
from .paper_rules_research import ResearchSpotRules
from .signal_outcome_research import STRATEGIES

VERSION = "single-long-ohlcv-path-v09-research-4"
MAX_HOLD_BARS = 16
QTY_STEP = Decimal("0.000001")
CAP_FRACTION = Decimal(str(PROFILE["symbol"]))
RISK_FRACTION = Decimal(str(PROFILE["trade_risk"]))
HALT_DD_FRACTION = Decimal(str(PROFILE["stop_dd"]))


@lru_cache(maxsize=1)
def _cached_research_split(serialized, symbol, timeframe, minimum):
    return evaluate_purged_walkforward(json.loads(serialized), symbol, timeframe,
        min_required_origins=minimum)


def _positive_decimal(value, label):
    try:
        v = D(value)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError("Invalid " + label) from exc
    if not v.is_finite() or v <= 0:
        raise ValueError("Nonpositive or nonfinite " + label)
    return v


def _quote_at(mid, spread_bps):
    mid = _positive_decimal(mid, "historical quote")
    spread = D(spread_bps) / Decimal(20000)
    return {"ask": str(mid*(1+spread)), "bid": str(mid*(1-spread))}


def _buy_for_cash(cash, open_price, stop, spread_bps, model, assumed_rules=None):
    quote = _quote_at(open_price, spread_bps)
    unit = estimate("BUY", Decimal(1), quote, model)
    stop_quote = _quote_at(stop, spread_bps)
    stop_cash = estimate("SELL", unit.net_base, stop_quote, model).cash_delta
    debit_unit = -unit.cash_delta
    risk_unit = debit_unit - stop_cash
    if risk_unit <= 0:
        raise ValueError("Invalid positive stop-loss exposure")
    cap_qty = min(
        cash*CAP_FRACTION/debit_unit,
        cash*RISK_FRACTION/risk_unit,
        cash/debit_unit)
    step = assumed_rules.step if assumed_rules is not None else QTY_STEP
    if assumed_rules is not None:
        cap_qty=min(cap_qty,assumed_rules.maximum)
    qty = (cap_qty/step).to_integral_value(rounding=ROUND_FLOOR)*step
    if qty <= 0:
        return None
    buy = estimate("BUY", qty, quote, model)
    if -buy.cash_delta > cash:
        raise ValueError("Budget allocation exceeded available cash")
    actual_stop = estimate("SELL", buy.net_base, stop_quote, model)
    if -buy.cash_delta - actual_stop.cash_delta > cash*RISK_FRACTION:
        raise ValueError("Risk allocation exceeded stop budget")
    # Never invent a fill if this EXPLICIT assumed scenario would reject
    # minimum notional or leave a legally uncloseable base-fee residue.
    if assumed_rules is not None:
        if not assumed_rules.check_entry(buy,stop_quote["bid"],model):
            return None
    return buy


def _closed_exit(position, price, cash, spread_bps, model, reason, i, rows, assumed_rules=None):
    quote = _quote_at(price, spread_bps)
    if assumed_rules is not None and not assumed_rules.sellable_at(position["base"],quote["bid"],model):
        raise ValueError("UNEXECUTABLE_RESEARCH_EXIT: assumed rules reject full sale; no fabricated proceeds")
    sold = estimate("SELL", position["base"], quote, model)
    after = cash + sold.cash_delta
    pnl = sold.cash_delta - position["debit"]
    close_available = reason in ('STOP', 'TARGET', 'STOP_FIRST_AMBIGUOUS', 'FOLD_CLOSE_OPTIMISTIC')
    return after, {
        "strategy":position["strategy"], "signal_time":position["signal_time"],
        "entry_open_time":rows[position["entry_idx"]]["time"],
        "exit_event_time":(rows[i]["time"]+rows[1]["time"]-rows[0]["time"]
                           if close_available else rows[i]["time"]),
        "exit_time_precision": "BAR_CLOSE_AVAILABILITY" if close_available else "NEXT_OPEN",
        "exit_bar_open_time": rows[i]["time"],
        "reason":reason,
        "entry_price":str(position["entry_price"]),
        "exit_reference_price":str(D(price)),
        "base_quantity":str(position["base"]),
        "entry_total_debit":str(position["debit"]),
        "exit_net_credit":str(sold.cash_delta),
        "net_pnl_quote":str(pnl),
        "net_return_pct":str(Decimal(100)*pnl/position["debit"]),
    }


def simulate_paper_paths(candles, symbol, timeframe, *, assumed_spread_bps=4,
                         initial_cash="10000", max_hold_bars=MAX_HOLD_BARS,
                         cost_model=None, min_required_origins=30,
                         assumed_rules=None, strategy=None, research_signal_provider=None):
    """Evaluate isolated development-fold virtual paths, never live/Paper orders.

    Rules: one SPOT long at a time, deterministic strategy priority, max 25%
    account allocation, max .75% initial stop budget, block new entries at
    >=12% marked liquidation-equity drawdown, and UTC 3% daily / 6% weekly\n    marked-equity losses. Historical exchange lot/minimums and
    live quote freshness are NOT represented (fixed research quantity step).

    At each next candle OPEN: first exit on STOP/TARGET gap, then matching
    EXIT signal, then timeout. Never re-enter that same candle after closing.
    Intrabar STOP if low crosses stop; TARGET if high crosses target; if
    both are seen, conservatively assume STOP first. Intrabar stop fills
    at the exact threshold (optimistic in illiquid/slipping markets);
    spread/slippage and commissions are then applied. Positions unresolved
    at a fold end are force-liquidated at that last close, explicitly tagged
    optimistic. No execution/portfolio claims or actual time-of-day liquidity.
    """
    names = (strategy,) if research_signal_provider is not None else STRATEGIES
    if research_signal_provider is not None and (not callable(research_signal_provider) or not isinstance(strategy,str) or not strategy):
        raise ValueError('Research adapter requires candidate ID')
    if strategy is not None and strategy not in names:
        raise ValueError('Unknown strategy filter')
    if type(assumed_spread_bps) not in (float,int) or not math.isfinite(assumed_spread_bps) or not 0<=assumed_spread_bps<=100:
        raise ValueError("Assumed full spread must be 0..100 bps")
    if type(max_hold_bars) is not int or not 1<=max_hold_bars<=64:
        raise ValueError("Invalid fixed holding-bar limit")
    cash_start = _positive_decimal(initial_cash, "virtual initial cash")
    if cash_start < Decimal("100") or cash_start > Decimal("1000000000"):
        raise ValueError("Initial cash outside bounded research range")
    model = CostModel() if cost_model is None else cost_model
    if not isinstance(model, CostModel):
        raise ValueError("Expected validated CandlePath CostModel")
    if assumed_rules is not None and (
            not isinstance(assumed_rules, ResearchSpotRules)
            or assumed_rules.symbol != symbol):
        raise ValueError("Research rules missing or symbol mismatch")

    if research_signal_provider is None:
        split = evaluate_purged_walkforward(candles, symbol, timeframe,
            min_required_origins=min_required_origins)
    else:
        serialized=json.dumps([dict(c) if isinstance(c,dict) else asdict(c) for c in candles],
            sort_keys=True,allow_nan=False)
        split = _cached_research_split(serialized,symbol,timeframe,min_required_origins)
    closed = _closed_rows(candles, timeframe)
    rows = [dict(c) if isinstance(c, dict) else asdict(c)
            for c in candles[:len(closed)]]
    step=seconds(timeframe)
    reports=[]
    for fold in split.folds:
        start,end = fold.validation_start_index,fold.validation_end_exclusive
        # No signal engine can observe the sealed final 20% or future folds.
        discovered=(analyze(rows[:end], symbol, timeframe)["signals"] if research_signal_provider is None else research_signal_provider(rows[:end], symbol, timeframe))
        by_index={}
        for sig in discovered:
            time=sig.get("candle_time")
            if type(time) is not int or (time-rows[0]["time"])%step:
                raise ValueError("Noncausal or unaligned generated signal")
            origin=(time-rows[0]["time"])//step
            if not 0<=origin<end:
                raise ValueError("Generated signal exceeds available fold history")
            if sig.get("strategy") not in names or sig.get("type") not in ("BUY","EXIT") or sig.get("status")!="confirmed":
                raise ValueError("Invalid/unknown confirmed strategy signal")
            if (sig.get("timestamp") != time+step or
                    sig.get("reference_price") != rows[origin]["close"]):
                raise ValueError("Generated signal is inconsistent with closed candle")
            if sig["type"]=="BUY":
                levels=sig.get("risk_estimates",{})
                _positive_decimal(levels.get("stop"), "stop")
                _positive_decimal(levels.get("target"), "target")
            if start<=origin<end and (strategy is None or sig['strategy']==strategy):
                by_index.setdefault(origin,[]).append(sig)
        cash=cash_start
        high_water=cash_start
        max_drawdown=Decimal(0)
        risk_ledger=ResearchEquityGuards(cash_start, assumed_rules)
        pos=None
        trades=[]
        counts={"buys":0,"exits":0,"rejected_entry":0,
                "ignored_while_open":0,"blocked_drawdown":0,
                "blocked_day_loss":0,"blocked_week_loss":0,
                "rejected_rules":0,
                "ambiguous_stop_first":0,"forced_fold_close":0}
        for i in range(start+1,end):
            bar=rows[i]
            prior=by_index.get(i-1,())
            # At this OPEN only known information can block a new BUY.
            # The previous day's/week's close is the reset anchor; this
            # open's possible gap is never erased by period rollover.
            gate=risk_ledger.at_open(bar["time"],cash,pos,bar["open"],
                                     assumed_spread_bps,model)
            closed_at_open=False
            if pos is not None:
                # A gap skips a stop threshold: use the worse NEXT OPEN,
                # never invent a fill at the higher stop price.
                opened=D(bar["open"])
                reason=("STOP_GAP" if opened<=pos["stop"] else
                        "TARGET_GAP" if opened>=pos["target"] else
                        "RULE_EXIT" if any(s["type"]=="EXIT" and s["strategy"]==pos["strategy"] for s in prior) else
                        "MAX_HOLD" if i-pos["entry_idx"]>=max_hold_bars else None)
                if reason:
                    cash,done=_closed_exit(pos,opened,cash,assumed_spread_bps,model,reason,i,rows,assumed_rules)
                    trades.append(done);pos=None;counts["exits"]+=1
                    high_water=max(high_water,cash)
                    max_drawdown=max(max_drawdown,(high_water-cash)/high_water)
                    # A single bar must never close and reopen in the same
                    # next-open execution event.
                    closed_at_open=True
            if pos is None and not closed_at_open:
                candidates=[s for s in prior if s["type"]=="BUY"]
                if candidates:
                    candidates.sort(key=lambda s:(names.index(s["strategy"]),s["candle_time"]))
                    if gate is not None:
                        counts[gate]+=len(candidates)
                    elif i==end-1:
                        counts["rejected_entry"]+=len(candidates)
                    else:
                        s=candidates[0]
                        stop=_positive_decimal(s["risk_estimates"]["stop"],"stop")
                        target=_positive_decimal(s["risk_estimates"]["target"],"target")
                        price=_positive_decimal(bar["open"],"entry open")
                        # At the OPEN the original historical stop/target must
                        # still straddle the actual bid/ask, without refitting.
                        quote=_quote_at(price, assumed_spread_bps)
                        if not stop<D(quote["bid"])<=D(quote["ask"])<target:
                            counts["rejected_entry"]+=len(candidates)
                        elif assumed_rules is not None and not assumed_rules.levels_on_tick(stop,target):
                            counts["rejected_rules"]+=len(candidates)
                        else:
                            order=_buy_for_cash(cash,price,stop,assumed_spread_bps,model,assumed_rules)
                            if order is None:
                                counts["rejected_rules" if assumed_rules is not None else "rejected_entry"]+=len(candidates)
                            else:
                                debit=-order.cash_delta
                                cash-=debit
                                pos={
                                    "strategy":s["strategy"],"signal_time":s["candle_time"],
                                    "entry_idx":i,"entry_price":order.price,
                                    "base":order.net_base,"debit":debit,
                                    "stop":stop,"target":target,
                                }
                                counts["buys"]+=1
                                counts["ignored_while_open"]+=len(candidates)-1
            else:
                counts["ignored_while_open"]+=sum(s["type"]=="BUY" for s in prior)
            if pos is not None:
                low,high=D(bar["low"]),D(bar["high"])
                stop_hit=low<=pos["stop"]
                target_hit=high>=pos["target"]
                if stop_hit or target_hit:
                    if stop_hit and target_hit:
                        counts["ambiguous_stop_first"]+=1
                    cause=("STOP_FIRST_AMBIGUOUS" if stop_hit and target_hit else
                           "STOP" if stop_hit else "TARGET")
                    exit_px=pos["stop"] if stop_hit else pos["target"]
                    cash,done=_closed_exit(pos,exit_px,cash,assumed_spread_bps,model,cause,i,rows,assumed_rules)
                    trades.append(done);pos=None;counts["exits"]+=1
                    high_water=max(high_water,cash)
                    max_drawdown=max(max_drawdown,(high_water-cash)/high_water)
            # Every fold is separately capitalized and finished flat. This
            # liquidation is the final CLOSE, never the next-fold OPEN.
            if pos is not None and i==end-1:
                cash,done=_closed_exit(pos,bar["close"],cash,
                                       assumed_spread_bps,model,
                                       "FOLD_CLOSE_OPTIMISTIC",i,rows,assumed_rules)
                trades.append(done);counts["forced_fold_close"]+=1;counts["exits"]+=1
                pos=None
                high_water=max(high_water,cash)
                max_drawdown=max(max_drawdown,(high_water-cash)/high_water)
            # CLOSE mark uses this bar's fully observed outcome; it cannot
            # retroactively affect an entry already made at its OPEN.
            risk_ledger.at_close(bar["time"],cash,pos,bar["close"],
                                 assumed_spread_bps,model)
        if counts["buys"]!=len(trades) or counts["exits"]!=len(trades):
            raise ValueError("Unbalanced hypothetical virtual positions")
        reports.append({
            "fold":fold.number,"start_index":start,"end_exclusive":end,
            "starting_cash":str(cash_start),"ending_cash":str(cash),
            "net_return_pct":str(Decimal(100)*(cash/cash_start-1)),
            "max_realized_drawdown_pct":str(Decimal(100)*max_drawdown),
            "marked_equity_guards":risk_ledger.snapshot(),
            "trade_count":len(trades),"events":counts,
            "trades":trades})
    sufficient=split.status=="EVALUATED_DEVELOPMENT_ONLY" and all(
        f["trade_count"]>=30 for f in reports)
    return {
        "mode":"ISOLATED_SEALED_DEV_SINGLE_LONG_PATH_RESEARCH",
        "status":"DESCRIPTIVE_DEV_ONLY" if sufficient else "INSUFFICIENT_TRADE_SAMPLE",
        "symbol":symbol,"timeframe":timeframe,"version":VERSION,
        "strategy_filter":strategy,
        "rules_version":RULES_VERSION,"cost_model":model.snapshot(),
        "spread_assumed_full_bps":str(D(assumed_spread_bps)),
        "assumed_spot_rules":assumed_rules.snapshot() if assumed_rules else None,
        "max_hold_bars":max_hold_bars,"virtual_step":str(assumed_rules.step if assumed_rules else QTY_STEP),
        "safety_limits":{
            "maximum_symbol_fraction":str(CAP_FRACTION),
            "maximum_initial_stop_risk_fraction":str(RISK_FRACTION),
            "marked_drawdown_entry_halt_fraction":str(HALT_DD_FRACTION),
            "marked_day_loss_entry_halt_fraction":str(D(PROFILE["day_loss"])),
            "marked_week_loss_entry_halt_fraction":str(D(PROFILE["week_loss"])),
            "mark_basis":"AFTER_COST_HYPOTHETICAL_LIQUIDATION_AT_OPEN_AND_CLOSE",
            "max_open_positions":1},
        "final_holdout_sha256":split.sealed_final.sha256,
        "final_holdout_evaluated":False,
        "fold_evaluation_status":split.status,
        "folds":reports,
        "trading_edge_verified":False,"live_trading_enabled":False,
        "note":"Research on OHLCV, not production Paper, exchange execution, "
               "signal-certified strategy PnL or real trades. Opens use the "
               "next available candle OPEN; spread is assumed, not observed. "
               "At intrabar stop/target collisions STOP is first; gap exits "
               "use the OPEN, stop/target fills at thresholds are optimistic. "
               "Terminal liquidation at last fold close is optimistic. "
               "One long at a time, folds reset bankroll; exchange constraints "
               "are not verified. If provided, quantity and stop/target tick "
               "plus min-notional and projected full sellability are filtered "
               "against the supplied, UNVERIFIED hypothetical rules. An "
               "unexecutable actual exit FAILS CLOSED without invented PnL. "
               "Only capital allocation, "
               "initial stop risk, marked-equity drawdown and UTC day/week "
               "historical entry gates are modeled; not full production Paper "
               "gating, ongoing intrabar equity drawdown, "
               "min notional, partial fills or protective worker operations. "
               "Last 20% strictly sealed. No automatic trading-model promotion."}

