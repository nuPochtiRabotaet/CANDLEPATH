"""Explicit, UNVERIFIED spot-rule assumptions for sealed v0.9 research.

No exchange networking, implicit discovery or use by production Paper/Invest.
A user-provided JSON snapshot is a *scenario*, not proof that the same
tick/step/notional rules were effective on a historical candle.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

PROVENANCE = "USER_SUPPLIED_UNVERIFIED_HISTORICAL_RULE_ASSUMPTION"
_REQUIRED = {"symbol", "step", "tick", "minimum", "maximum",
             "as_of_utc_seconds", "note"}
MAX_FILE_BYTES = 16384


def _decimal(raw, name):
    if type(raw) is not str or len(raw) > 48 or not raw:
        raise ValueError(f"{name} must be a short decimal string")
    try:
        v = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid {name}") from None
    if not v.is_finite() or not Decimal("0") < v <= Decimal("1000000000000"):
        raise ValueError(f"Invalid positive bounded {name}")
    return v


def _pairs_no_dupes(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise ValueError("Duplicate field in assumed-rule file: " + key)
        obj[key] = value
    return obj


@dataclass(frozen=True)
class ResearchSpotRules:
    symbol: str
    step: Decimal
    tick: Decimal
    minimum: Decimal
    maximum: Decimal
    as_of_utc_seconds: int
    note: str
    original_sha256: str

    def snapshot(self):
        return {
            "symbol": self.symbol,
            "step": str(self.step),
            "tick": str(self.tick),
            "minimum": str(self.minimum),
            "maximum": str(self.maximum),
            "as_of_utc_seconds": self.as_of_utc_seconds,
            "note": self.note,
            "original_sha256": self.original_sha256,
            "provenance": PROVENANCE,
            "historically_verified": False,
            "exchange_accepted_fills_verified": False,
        }

    @staticmethod
    def _aligned(value, step):
        return (value / step) == (value / step).to_integral_value()

    def levels_on_tick(self, stop, target):
        return self._aligned(Decimal(str(stop)), self.tick) and self._aligned(
            Decimal(str(target)), self.tick)

    def sellable_at(self, quantity, bid, model):
        """Check one whole-quantity, unlevered hypothetical SELL."""
        from .costs import estimate
        qty = Decimal(str(quantity))
        if (not qty.is_finite() or qty <= 0 or qty > self.maximum or
                not self._aligned(qty, self.step)):
            return False
        filled = estimate("SELL", qty, {"bid": str(bid)}, model)
        return filled.notional >= self.minimum

    def check_entry(self, buy, worst_bid, model):
        if (buy.quantity > self.maximum or
                not self._aligned(buy.quantity, self.step)):
            return False
        if buy.notional < self.minimum:
            return False
        return self.sellable_at(buy.net_base, worst_bid, model)


def load_research_rules(path, symbol):
    """Validate a bounded UTF-8 JSON file; never mutate it or contact Bybit."""
    if type(symbol) is not str or not symbol:
        raise ValueError("Invalid expected symbol")
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Assumed-rule file missing or too large")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError("Assumed-rule file empty or too large")
    try:
        obj = json.loads(raw.decode("utf8"), object_pairs_hook=_pairs_no_dupes,
                         parse_constant=lambda v: (_ for _ in ()).throw(
                             ValueError("Nonfinite JSON constant")))
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Invalid UTF-8 JSON assumed-rule file") from None
    if type(obj) is not dict or set(obj) != _REQUIRED:
        raise ValueError("Assumed rules require exactly the documented seven fields")
    if obj["symbol"] != symbol:
        raise ValueError("Assumed-rule symbol mismatch")
    if type(obj["as_of_utc_seconds"]) is not int or not 0 < obj["as_of_utc_seconds"] < 4102444800:
        raise ValueError("Invalid UTC snapshot timestamp")
    if (type(obj["note"]) is not str or not 5 <= len(obj["note"]) <= 200
            or not obj["note"].strip()):
        raise ValueError("Assumed-rule provenance note is required")
    step = _decimal(obj["step"], "step")
    tick = _decimal(obj["tick"], "tick")
    minimum = _decimal(obj["minimum"], "minimum")
    maximum = _decimal(obj["maximum"], "maximum")
    if step > maximum:
        raise ValueError("Assumed-rule maximum below quantity step")
    if step < Decimal("0.000000000001") or tick < Decimal("0.000000000001"):
        raise ValueError("Assumed-rule quantity/price resolution too extreme")
    return ResearchSpotRules(
        symbol, step, tick, minimum, maximum, obj["as_of_utc_seconds"],
        obj["note"], hashlib.sha256(raw).hexdigest())
