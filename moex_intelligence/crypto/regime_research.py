"""Strict, past-only volatility regime labels for OFFLINE v0.9 research.

Predetermined relative-RMS thresholds; no fitting, future labels, or trade
decisions. Uses only closes in the same 120-bar causal window given to both
competing price models. Labels describe changes in *past* volatility and are
not forecasts of the next market regime.
"""
import math

REGIME_VERSION = "trailing-rms-ratio-20-v09-1"
REGIMES = ("EXPANDING", "STABLE", "CONTRACTING")
EXPANDING_RATIO = 1.25
CONTRACTING_RATIO = 0.80


def classify_past_volatility(closes):
    """Compare RMS of the latest 20 returns to all earlier available returns.

    Requires exactly 120 price observations, giving 20 recent returns and
    99 older returns. No current candle, future price or scored outcome enters
    this classifier. Invalid and extreme inputs fail closed.
    """
    if not isinstance(closes, (tuple, list)) or len(closes) != 120:
        raise ValueError("Volatility classifier requires exactly 120 closed prices")
    if any(type(p) not in (int, float) for p in closes):
        raise ValueError("Invalid observed price type")
    try:
        prices = [float(p) for p in closes]
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Unrepresentable observed price") from exc
    if not all(math.isfinite(p) and p > 0 for p in prices):
        raise ValueError("Invalid positive finite observed price")
    returns = [math.log(prices[i]) - math.log(prices[i - 1])
               for i in range(1, len(prices))]
    if not all(math.isfinite(r) and abs(r) < .7 for r in returns):
        raise ValueError("Invalid/extreme observed return")
    older = returns[:-20]
    recent = returns[-20:]
    old_sigma = math.sqrt(sum(r*r for r in older) / len(older))
    new_sigma = math.sqrt(sum(r*r for r in recent) / len(recent))
    if old_sigma == 0:
        return "EXPANDING" if new_sigma > 0 else "STABLE"
    ratio = new_sigma / old_sigma
    if ratio >= EXPANDING_RATIO:
        return "EXPANDING"
    if ratio <= CONTRACTING_RATIO:
        return "CONTRACTING"
    return "STABLE"
