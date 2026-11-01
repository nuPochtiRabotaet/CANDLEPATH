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

from .analysis import analyze, VERSION as RULES_VERSION
from .costs import CostModel, D, estimate
from .forecast_evaluation import _closed_rows
from .forecast_walkforward import evaluate_purged_walkforward
from .market import seconds
from .risk import PROFILE
from .signal_outcome_research import STRATEGIES

VERSION = "single-long-ohlcv-path-v09-research-1"
MAX_HOLD_BARS = 16
QTY_STEP = Decimal("0.000001")
CAP_FRACTION = Decimal(str(PROFILE["symbol"]))
RISK_FRACTION = Decimal(str(PROFILE["trade_risk"]))
HALT_DD_FRACTION = Decimal(str(PROFILE["stop_dd"]))


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


def _buy_for_cash(cash, open_price, stop, spread_bps, model):
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
    qty = (cap_qty/QTY_STEP).to_integral_value(rounding=ROUND_FLOOR)*QTY_STEP
    if qty <= 0:
        return None
    buy = estimate("BUY", qty, quote, model)
    if -buy.cash_delta > cash:
        raise ValueError("Budget allocation exceeded available cash")
    actual_stop = estimate("SELL", buy.net_base, stop_quote, model)
    if -buy.cash_delta - actual_stop.cash_delta > cash*RISK_FRACTION:
        raise ValueError("Risk allocation exceeded stop budget")
    return buy


def _closed_exit(position, price, cash, spread_bps, model, reason, i, rows):
    sold = estimate("SELL", position["base"], _quote_at(price, spread_bps), model)
    after = cash + sold.cash_delta
    pnl = sold.cash_delta - position["debit"]
    return after, {
        "strategy":position["strategy"], "signal_time":position["signal_time"],
        "entry_open_time":rows[position["entry_idx"]]["time"],
        "exit_event_time":(rows[i]["time"]+rows[1]["time"]-rows[0]["time"]
                           if reason=="FOLD_CLOSE_OPTIMISTIC" else rows[i]["time"]),
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
                         cost_model=None, min_required_origins=30):
    """Evaluate isolated development-fold virtual paths, never live/Paper orders.

    Rules: one SPOT long at a time, deterministic strategy priority, max 25%
    account allocation, max .75% initial stop budget, block new entries at
    >=12% realized equity drawdown. Historical exchange lot/minimums and
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

    split = evaluate_purged_walkforward(
        candles, symbol, timeframe, min_required_origins=min_required_origins)
    closed = _closed_rows(candles, timeframe)
    rows = [dict(c) if isinstance(c, dict) else asdict(c)
            for c in candles[:len(closed)]]
    step=seconds(timeframe)
    reports=[]
    for fold in split.folds:
        start,end = fold.validation_start_index,fold.validation_end_exclusive
        # No signal engine can observe the sealed final 20% or future folds.
        discovered=analyze(rows[:end], symbol, timeframe)["signals"]
        by_index={}
        for sig in discovered:
            time=sig.get("candle_time")
            if type(time) is not int or (time-rows[0]["time"])%step:
                raise ValueError("Noncausal or unaligned generated signal")
            origin=(time-rows[0]["time"])//step
            if not 0<=origin<end:
                raise ValueError("Generated signal exceeds available fold history")
            if sig.get("strategy") not in STRATEGIES or sig.get("type") not in ("BUY","EXIT") or sig.get("status")!="confirmed":
                raise ValueError("Invalid/unknown confirmed strategy signal")
            if (sig.get("timestamp") != time+step or
                    sig.get("reference_price") != rows[origin]["close"]):
                raise ValueError("Generated signal is inconsistent with closed candle")
            if sig["type"]=="BUY":
                levels=sig.get("risk_estimates",{})
                _positive_decimal(levels.get("stop"), "stop")
                _positive_decimal(levels.get("target"), "target")
            if start<=origin<end:
                by_index.setdefault(origin,[]).append(sig)
        cash=cash_start
        high_water=cash_start
        max_drawdown=Decimal(0)
        pos=None
        trades=[]
        counts={"buys":0,"exits":0,"rejected_entry":0,
                "ignored_while_open":0,"blocked_drawdown":0,
                "ambiguous_stop_first":0,"forced_fold_close":0}
        for i in range(start+1,end):
            bar=rows[i]
            prior=by_index.get(i-1,())
            if pos is not None:
                # A gap skips a stop threshold: use the worse NEXT OPEN,
                # never invent a fill at the higher stop price.
                opened=D(bar["open"])
                reason=("STOP_GAP" if opened<=pos["stop"] else
                        "TARGET_GAP" if opened>=pos["target"] else
                        "RULE_EXIT" if any(s["type"]=="EXIT" and s["strategy"]==pos["strategy"] for s in prior) else
                        "MAX_HOLD" if i-pos["entry_idx"]>=max_hold_bars else None)
                if reason:
                    cash,done=_closed_exit(pos,opened,cash,assumed_spread_bps,model,reason,i,rows)
                    trades.append(done);pos=None;counts["exits"]+=1
                    high_water=max(high_water,cash)
                    max_drawdown=max(max_drawdown,(high_water-cash)/high_water)
                    # A single bar must never close and reopen in the same
                    # next-open execution event.
                    continue
            if pos is None:
                candidates=[s for s in prior if s["type"]=="BUY"]
                if candidates:
                    candidates.sort(key=lambda s:(STRATEGIES.index(s["strategy"]),s["candle_time"]))
                    if (high_water-cash)/high_water>=HALT_DD_FRACTION:
                        counts["blocked_drawdown"]+=len(candidates)
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
                        else:
                            order=_buy_for_cash(cash,price,stop,assumed_spread_bps,model)
                            if order is None:
                                counts["rejected_entry"]+=len(candidates)
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
                    cash,done=_closed_exit(pos,exit_px,cash,assumed_spread_bps,model,cause,i,rows)
                    trades.append(done);pos=None;counts["exits"]+=1
                    high_water=max(high_water,cash)
                    max_drawdown=max(max_drawdown,(high_water-cash)/high_water)
        # Every fold is separately capitalized, rather than carrying a
        # position or a learned rule into the next development fold.
        if pos is not None:
            final=end-1
            cash,done=_closed_exit(pos,rows[final]["close"],cash,
                                   assumed_spread_bps,model,"FOLD_CLOSE_OPTIMISTIC",
                                   final,rows)
            trades.append(done);counts["forced_fold_close"]+=1;counts["exits"]+=1
            high_water=max(high_water,cash)
            max_drawdown=max(max_drawdown,(high_water-cash)/high_water)
        if counts["buys"]!=len(trades) or counts["exits"]!=len(trades):
            raise ValueError("Unbalanced hypothetical virtual positions")
        reports.append({
            "fold":fold.number,"start_index":start,"end_exclusive":end,
            "starting_cash":str(cash_start),"ending_cash":str(cash),
            "net_return_pct":str(Decimal(100)*(cash/cash_start-1)),
            "max_realized_drawdown_pct":str(Decimal(100)*max_drawdown),
            "trade_count":len(trades),"events":counts,
            "trades":trades})
    sufficient=split.status=="EVALUATED_DEVELOPMENT_ONLY" and all(
        f["trade_count"]>=30 for f in reports)
    return {
        "mode":"ISOLATED_SEALED_DEV_SINGLE_LONG_PATH_RESEARCH",
        "status":"DESCRIPTIVE_DEV_ONLY" if sufficient else "INSUFFICIENT_TRADE_SAMPLE",
        "symbol":symbol,"timeframe":timeframe,"version":VERSION,
        "rules_version":RULES_VERSION,"cost_model":model.snapshot(),
        "spread_assumed_full_bps":str(D(assumed_spread_bps)),
        "max_hold_bars":max_hold_bars,"virtual_step":str(QTY_STEP),
        "safety_limits":{
            "maximum_symbol_fraction":str(CAP_FRACTION),
            "maximum_initial_stop_risk_fraction":str(RISK_FRACTION),
            "realized_drawdown_entry_halt_fraction":str(HALT_DD_FRACTION),
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
               "One long at a time, folds reset bankroll, fixed quantity step "
               "not verified against exchange rules. Only capital allocation, "
               "initial stop risk and realized drawdown limits are modeled; "
               "not full daily/weekly Paper gating, open-equity drawdown, "
               "min notional, partial fills or protective worker operations. "
               "Last 20% strictly sealed. No automatic trading-model promotion."}
