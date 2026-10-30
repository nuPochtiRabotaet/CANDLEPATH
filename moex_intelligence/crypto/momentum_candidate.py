"""Causal, fixed-parameter directional research candidate; NOT a live trading model.

This model does NOT train or fit to the evaluation folds. It projects a heavily
shrunk and capped EWMA mean log-return and retains the same EWMA volatility
envelope as the existing flat Random Walk baseline. No BUY/SELL decisions,
confidence certification or user account/exchange access.
"""
import math

CANDIDATE_VERSION = "shrunk-log-momentum-ewma-v09-research-1"
DECAY = .94
DRIFT_SHRINK = .25
DRIFT_SIGMA_CAP = .25
MIN_HISTORY = 60
MAX_HISTORY = 120
Z80 = 1.2815515655446004


def momentum_envelope(closes, horizons=(1, 2, 4, 8)):
    """Future log-median drift is learned ONLY from preceding closed prices.

    No intrabar, future or label information can enter this pure function.
    Drift is shrunk and sigma-capped to resist chasing short-lived spikes.
    Nominal 80% bands are uncalibrated statistical research, not probability
    estimates of profitable orders.
    """
    if not isinstance(closes,(list,tuple)) or not MIN_HISTORY<=len(closes)<=MAX_HISTORY:
        raise ValueError("Momentum candidate requires 60-120 observed closes")
    if (not isinstance(horizons,(tuple,list)) or not horizons
            or any(type(h) is not int or not 1<=h<=64 for h in horizons)
            or list(horizons)!=sorted(set(horizons))):
        raise ValueError("Invalid research horizon sequence")
    try:
        prices=[float(c) if type(c) in (float,int) else float("nan") for c in closes]
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError("Unrepresentable observed price") from exc
    if any(not math.isfinite(p) or p<=0 for p in prices):
        raise ValueError("Invalid positive finite observed close")
    returns=[math.log(b)-math.log(a) for a,b in zip(prices,prices[1:])]
    if any(not math.isfinite(r) or abs(r)>=.7 for r in returns):
        raise ValueError("Extreme log-return: candidate unavailable")

    weights=[DECAY**i for i in range(len(returns))]
    denominator=sum(weights)
    newest=list(reversed(returns))
    drift_raw=sum(w*r for w,r in zip(weights,newest))/denominator
    second_moment=sum(w*r*r for w,r in zip(weights,newest))/denominator
    sigma=math.sqrt(second_moment)
    drift=max(-DRIFT_SIGMA_CAP*sigma,
              min(DRIFT_SIGMA_CAP*sigma,DRIFT_SHRINK*drift_raw))
    last=prices[-1]
    predictions=[]
    for h in horizons:
        try:
            median=last*math.exp(h*drift)
            radius=Z80*sigma*math.sqrt(h)
            lower=median*math.exp(-radius)
            upper=median*math.exp(radius)
        except (OverflowError,ValueError) as exc:
            raise ValueError("Unstable candidate projection") from exc
        if not all(math.isfinite(p) and p>0 for p in (lower,median,upper)):
            raise ValueError("Unstable candidate projection")
        if not lower<=median<=upper:
            raise ValueError("Invalid candidate quantile order")
        predictions.append((lower,median,upper))
    return tuple(predictions)
