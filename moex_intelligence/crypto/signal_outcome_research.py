"""Offline, strictly causal diagnostic of existing CandlePath BUY signals.

Research-only fixed-horizon open-to-open outcomes, NOT executed trades,
full strategy backtests, orders, trained probabilities or validated alpha.
All outcomes stay inside development folds; the final 20% remains sealed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import math

from .analysis import analyze, VERSION as RULES_VERSION
from .costs import CostModel, D, estimate
from .forecast_evaluation import _closed_rows
from .forecast_walkforward import evaluate_purged_walkforward
from .market import seconds

HORIZONS = (1, 2, 4, 8)
STRATEGIES = ("Trend Following", "Mean Reversion", "Breakout Detection")
RESEARCH_VERSION = "signal-next-open-fixed-horizon-v09-1"


@dataclass(frozen=True)
class SignalOutcome:
    strategy: str
    horizon_candles: int
    observations: int
    positive_gross: int
    positive_net: int
    mean_gross_return_pct: float | None
    mean_net_return_pct: float | None
    median_net_return_pct: float | None
    mean_abs_move_pct: float | None
    min_net_return_pct: float | None
    max_net_return_pct: float | None
    sample_sufficient: bool


@dataclass(frozen=True)
class SignalFold:
    number: int
    start_index: int
    end_exclusive: int
    confirmed_buy_signals: int
    confirmed_exit_signals: int
    scored_buy_signals: int
    unscored_boundary_signals: int
    outcomes: tuple[SignalOutcome, ...]


@dataclass(frozen=True)
class SignalAudit:
    mode: str
    status: str
    symbol: str
    timeframe: str
    rules_version: str
    research_version: str
    folds: tuple[SignalFold, ...]
    fold_evaluation_status: str
    final_holdout_sha256: str
    final_holdout_evaluated: bool
    cost_model: dict
    assumed_full_spread_bps: float
    signal_sample_sufficient: bool
    note: str

    def as_dict(self):
        return asdict(self)


def _cash_return(entry_open, exit_open, spread_bps, cost_model):
    """Fixed hypothetical round trip using actual CandlePath Paper cost math.

    Quote tape/bid-ask is unavailable. Symmetric assumed spread is applied to
    midlike observed opens. Both sides then pay configured taker fee and
    slippage; no actual fill availability or liquidity is claimed.
    """
    entry = D(entry_open)
    exit = D(exit_open)
    half_spread = spread_bps / Decimal(20000)
    ask = entry * (Decimal(1) + half_spread)
    bid = exit * (Decimal(1) - half_spread)
    if bid <= 0:
        raise ValueError("Assumed spread invalidates historical bid")
    buy = estimate("BUY", "1", {"ask": str(ask), "bid": str(ask)}, cost_model)
    # A quote-currency BUY fee is the current default. For base-denominated
    # fees, sell exactly the acquired, net-of-fee base to preserve accounting.
    sell = estimate("SELL", str(buy.net_base),
                    {"bid": str(bid), "ask": str(bid)}, cost_model)
    initial = -buy.cash_delta
    if initial <= 0:
        raise ValueError("Invalid modeled historical entry cost")
    return Decimal(100) * (sell.cash_delta / initial - Decimal(1))


def _summary(strategy, h, gross_values, net_values):
    n = len(net_values)
    if not n:
        return SignalOutcome(strategy, h, 0, 0, 0, None, None, None,
                             None, None, None, False)
    if n != len(gross_values):
        raise ValueError("Mismatched signal outcomes")
    arr = sorted(net_values)
    middle = (arr[n // 2] if n % 2 else (arr[n // 2 - 1] + arr[n // 2]) / 2)
    return SignalOutcome(
        strategy, h, n,
        sum(x > 0 for x in gross_values), sum(x > 0 for x in net_values),
        float(sum(gross_values) / n), float(sum(net_values) / n),
        float(middle), float(sum(abs(x) for x in gross_values) / n),
        float(arr[0]), float(arr[-1]), n >= 30)


def audit_buy_signal_outcomes(candles, symbol, timeframe, *,
                              folds=3, final_fraction=.20,
                              embargo_bars=8, stride=8,
                              min_required_origins=30,
                              assumed_spread_bps=0,
                              cost_model=None):
    """Validate causal chart-rule outcomes on sealed-development folds only.

    A BUY confirmed at candle i's close may enter only at candle (i+1) OPEN.
    For horizon h, close the hypothetical round trip at candle (i+1+h) OPEN
    strictly inside the same development fold. This is deliberately not
    stop/target, paper order, actual fill or account-level PnL simulation.

    EXIT signals are counted, never treated as new short positions. Multiple
    BUY signals/overlapping horizons may share outcomes: do not interpret
    their samples as independent or as compounded trading capital.
    """
    if type(assumed_spread_bps) not in (int, float) or not math.isfinite(assumed_spread_bps):
        raise ValueError("Spread assumption must be finite numeric bps")
    if not 0 <= assumed_spread_bps <= 100:
        raise ValueError("Spread assumption must be 0-100 bps")
    spread = D(assumed_spread_bps)
    model = CostModel() if cost_model is None else cost_model
    if not isinstance(model, CostModel):
        raise ValueError("Expected validated CandlePath CostModel")

    split = evaluate_purged_walkforward(
        candles, symbol, timeframe, folds=folds,
        final_fraction=final_fraction, embargo_bars=embargo_bars,
        stride=stride, min_required_origins=min_required_origins)
    checked = _closed_rows(candles, timeframe)
    rows = [dict(c) if isinstance(c, dict) else asdict(c)
            for c in candles[:len(checked)]]
    if len(rows) != len(checked):
        raise ValueError("Unstable validated candle length")
    step = seconds(timeframe)
    reports = []
    total_scored = 0

    for fold in split.folds:
        start, end = fold.validation_start_index, fold.validation_end_exclusive
        # The rule engine sees no candles beyond THIS fold's final dev candle.
        historical = analyze(rows[:end], symbol, timeframe)
        result = {(name, h): ([], []) for name in STRATEGIES for h in HORIZONS}
        buys = exits = scored = boundary = 0
        for signal in historical["signals"]:
            if (signal.get("status") != "confirmed" or
                signal.get("strategy") not in STRATEGIES or
                signal.get("type") not in ("BUY", "EXIT")):
                raise ValueError("Unknown or unconfirmed strategy signal")
            timestamp = signal.get("candle_time")
            if type(timestamp) is not int or (timestamp - rows[0]["time"]) % step:
                raise ValueError("Noncausal or unaligned signal")
            origin = (timestamp - rows[0]["time"]) // step
            if not start <= origin < end:
                continue
            if signal.get("timestamp") != timestamp + step or signal["reference_price"] != rows[origin]["close"]:
                raise ValueError("Signal timestamp/reference disagrees with closed candle")
            if signal["type"] == "EXIT":
                exits += 1
                continue
            buys += 1
            entry_index = origin + 1
            if entry_index >= end:
                boundary += 1
                continue
            entry_price = D(rows[entry_index]["open"])
            counted = False
            for h in HORIZONS:
                exit_index = entry_index + h
                if exit_index >= end:
                    continue
                exit_price = D(rows[exit_index]["open"])
                gross = Decimal(100) * (exit_price / entry_price - 1)
                net = _cash_return(entry_price, exit_price, spread, model)
                result[(signal["strategy"], h)][0].append(gross)
                result[(signal["strategy"], h)][1].append(net)
                counted = True
            if counted:
                scored += 1
            else:
                boundary += 1
        scores = tuple(_summary(name, h, *result[(name, h)])
                       for name in STRATEGIES for h in HORIZONS)
        total_scored += scored
        reports.append(SignalFold(
            fold.number, start, end, buys, exits, scored, boundary, scores))

    # Thin slices or 0/very few actual BUY confirmations never pass as proven.
    samples_sufficient = bool(reports) and all(
        s.sample_sufficient for f in reports for s in f.outcomes)
    status = ("DESCRIPTIVE_DEV_ONLY" if split.status == "EVALUATED_DEVELOPMENT_ONLY"
              else "INSUFFICIENT_FOLD_HISTORY")
    if total_scored < 30 or not samples_sufficient:
        status = "INSUFFICIENT_SIGNAL_SAMPLE"
    return SignalAudit(
        mode="PAST_ONLY_SIGNAL_OUTCOME_AUDIT_NOT_TRADING",
        status=status, symbol=symbol, timeframe=timeframe,
        rules_version=RULES_VERSION, research_version=RESEARCH_VERSION,
        folds=tuple(reports), fold_evaluation_status=split.status,
        final_holdout_sha256=split.sealed_final.sha256,
        final_holdout_evaluated=False, cost_model=model.snapshot(),
        assumed_full_spread_bps=float(spread),
        signal_sample_sufficient=samples_sufficient,
        note="Hypothetical fixed-horizon next-open-to-next-open BUY outcomes; "
             "not real fills, bid/ask, a stop/target/EXIT strategy backtest, "
             "calibrated prediction, net portfolio profit or validated trading edge. "
             "Default 0-bps spread is an OPTIMISTIC bound with hypothetical "
             "taker commissions and slippage. SELL/EXIT only counted, not shorted. "
             "Overlapping signal/horizon outcomes are dependent. Each fold's "
             "rules see only its historical prefix; final holdout is SHA-fingerprinted "
             "but NEVER evaluated or used for model/threshold selection.")
