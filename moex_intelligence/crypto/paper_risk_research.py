"""Causal marked-to-liquidation equity checkpoints for offline v0.9 research.

This is deliberately NOT the production Paper risk gate. It uses the Paper
CostModel liquidation arithmetic with an assumed spread, timestamps in UTC,
and only prior CLOSE observations for day/week period baselines.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from .costs import D, estimate
from .risk import PROFILE


def _periods(open_time: int):
    if type(open_time) is not int or open_time < 0:
        raise ValueError("Invalid historical UTC open timestamp")
    day = datetime.fromtimestamp(open_time, timezone.utc)
    year, week, _ = day.isocalendar()
    return day.date().isoformat(), f"{year}-W{week:02d}"


def liquidation_equity(cash, position, reference_price, spread_bps, model, assumed_rules=None):
    """Cash plus after-cost liquidation proceeds at a known candle OPEN/CLOSE."""
    # Local import avoids duplicating spread conventions from the replay.
    from .paper_path_research import _quote_at
    equity = D(cash)
    if position is not None:
        quote = _quote_at(reference_price, spread_bps)
        # Zero recovery for holdings rendered uncloseable by assumed rules;
        # never invent proceeds from an illegal liquidation.
        if assumed_rules is None or assumed_rules.sellable_at(
                position["base"], quote["bid"], model):
            sold = estimate("SELL", position["base"], quote, model)
            equity += sold.cash_delta
    if not equity.is_finite() or equity <= 0:
        raise ValueError("Invalid hypothetical after-cost liquidation equity")
    return equity


class ResearchEquityGuards:
    """One-fold UTC guards; not persisted and never reads account state."""

    def __init__(self, initial_cash, assumed_rules=None):
        start = D(initial_cash)
        if not start.is_finite() or start <= 0:
            raise ValueError("Invalid research cash")
        self.assumed_rules = assumed_rules
        self.high_water = start
        self.last_close_equity = start
        self.day_anchor = start
        self.week_anchor = start
        self.day_key = None
        self.week_key = None
        self.max_marked_drawdown = Decimal(0)
        self.max_day_loss = Decimal(0)
        self.max_week_loss = Decimal(0)
        self.open_marks = 0
        self.close_marks = 0
        self._last_open = None

    def _observe(self, equity):
        self.high_water = max(self.high_water, equity)
        self.max_marked_drawdown = max(
            self.max_marked_drawdown,
            (self.high_water-equity)/self.high_water)
        self.max_day_loss = max(
            self.max_day_loss,
            (self.day_anchor-equity)/self.day_anchor)
        self.max_week_loss = max(
            self.max_week_loss,
            (self.week_anchor-equity)/self.week_anchor)

    def at_open(self, time, cash, position, opening, spread_bps, model):
        """Take a causal open mark before deciding a new BUY.

        On a UTC day/week boundary the anchor is the *previous closed*
        valuation, not the first post-gap open (which would hide gap losses).
        """
        if self._last_open is not None and time <= self._last_open:
            raise ValueError("Equity marks must be strictly chronological")
        day, week = _periods(time)
        if self.day_key != day:
            self.day_anchor = self.last_close_equity
            self.day_key = day
        if self.week_key != week:
            self.week_anchor = self.last_close_equity
            self.week_key = week
        equity = liquidation_equity(cash, position, opening, spread_bps, model,
                                    self.assumed_rules)
        self._last_open = time
        self.open_marks += 1
        self._observe(equity)
        return self._entry_status(equity)

    def _entry_status(self, equity):
        dd = (self.high_water-equity)/self.high_water
        day_loss = (self.day_anchor-equity)/self.day_anchor
        week_loss = (self.week_anchor-equity)/self.week_anchor
        # Match the numerical policy from the existing Paper risk PROFILE.
        if dd >= D(PROFILE["stop_dd"]):
            return "blocked_drawdown"
        if day_loss >= D(PROFILE["day_loss"]):
            return "blocked_day_loss"
        if week_loss >= D(PROFILE["week_loss"]):
            return "blocked_week_loss"
        return None

    def at_close(self, time, cash, position, closing, spread_bps, model):
        """After-event close mark; cannot affect an already-made OPEN decision."""
        if time != self._last_open:
            raise ValueError("Close mark must match the last opened candle")
        equity = liquidation_equity(cash, position, closing, spread_bps, model,
                                    self.assumed_rules)
        self._observe(equity)
        self.last_close_equity = equity
        self.close_marks += 1
        return equity

    def snapshot(self):
        return {
            "max_marked_drawdown_pct": str(self.max_marked_drawdown*100),
            "max_marked_day_loss_pct": str(self.max_day_loss*100),
            "max_marked_week_loss_pct": str(self.max_week_loss*100),
            "open_marks": self.open_marks,
            "close_marks": self.close_marks,
            "day_anchor_final": str(self.day_anchor),
            "week_anchor_final": str(self.week_anchor),
            "equity_at_last_close": str(self.last_close_equity),
            "marking": "OPEN_BEFORE_ENTRY_AND_CLOSE_AFTER_EVENTS_LIQUIDATION_COST",
            "period_timezone": "UTC",
        }
