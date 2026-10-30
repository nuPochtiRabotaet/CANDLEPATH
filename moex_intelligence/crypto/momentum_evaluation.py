"""Paired, causal development-fold evaluation of a directional challenger.

Never evaluates the sealed final holdout, publishes historical predictions,
creates trades, or touches Store. Both models see EXACTLY the same past price
window and are scored on the same future actual at every origin.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, DecimalException
import math

from .forecast_baseline import HistoricalVolatilityBaseline, ewma_price_envelope
from .forecast_evaluation import _closed_rows
from .forecast_walkforward import evaluate_purged_walkforward
from .momentum_candidate import CANDIDATE_VERSION, momentum_envelope
from .market import seconds


@dataclass(frozen=True)
class PairedHorizon:
    horizon_candles: int
    observations: int
    rw_mae: float | None
    candidate_mae: float | None
    candidate_mae_gain_pct: float | None
    rw_interval_score_pct: float | None
    candidate_interval_score_pct: float | None
    rw_coverage: float
    candidate_coverage: float
    nonflat_actuals: int
    candidate_nonflat_predictions: int
    candidate_direction_hit_rate: float | None
    direction_hits: int = 0
    direction_calls: int = 0
    direction_wilson_95_lower: float | None = None
    direction_wilson_95_upper: float | None = None
    direction_sample_sufficient: bool = False


@dataclass(frozen=True)
class PairedFold:
    fold_number: int
    origins: int
    skipped_origins: int
    validation_start_index: int
    validation_end_exclusive: int
    horizons: tuple[PairedHorizon, ...]


@dataclass(frozen=True)
class CandidateComparison:
    mode: str
    status: str
    symbol: str
    timeframe: str
    random_walk_version: str
    candidate_version: str
    folds: tuple[PairedFold, ...]
    final_holdout_sha256: str
    final_holdout_evaluated: bool
    note: str

    def as_dict(self):
        return asdict(self)


def _decimal(value):
    numeric=Decimal(str(value))
    if not numeric.is_finite():
        raise ValueError("Nonfinite candidate evaluation input")
    return numeric


def _finite(value):
    try:
        converted=float(value)
    except (ValueError,OverflowError,DecimalException):
        return None
    return converted if math.isfinite(converted) else None


def _score(lower, median, upper, actual, anchor):
    """Price-normalized 80% Winkler score and absolute error in Decimal."""
    low_d, mid_d, high_d, actual_d, anchor_d=map(
        _decimal,(lower,median,upper,actual,anchor))
    if not 0<low_d<=mid_d<=high_d or actual_d<=0 or anchor_d<=0:
        raise ValueError("Invalid interval for paired scoring")
    penalty=max(low_d-actual_d,Decimal(0))+max(actual_d-high_d,Decimal(0))
    interval=(high_d-low_d)+Decimal(10)*penalty
    return abs(mid_d-actual_d), Decimal(100)*interval/anchor_d, int(low_d<=actual_d<=high_d)




def _wilson_95(successes: int, trials: int):
    """Descriptive Wilson 95% interval; not an iid-market validity guarantee."""
    if (type(successes) is not int or type(trials) is not int
            or not 0 <= successes <= trials):
        raise ValueError("Invalid directional observation counts")
    if trials == 0:
        return (None, None)
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z*z/trials
    center = (p + z*z/(2*trials)) / denominator
    radius = z*math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials)) / denominator
    return max(0., center-radius), min(1., center+radius)

def compare_momentum_to_rw(candles,symbol,timeframe,*,folds=3,
                           final_fraction=.20,embargo_bars=8,stride=8,
                           min_required_origins=30) -> CandidateComparison:
    """Compare fixed candidates on identical causal, nonoverlapping outcomes.

    No parameters are fitted from the development folds. Final holdout is not
    provided to either model at any origin and its outcomes are not scored.
    """
    split=evaluate_purged_walkforward(
        candles,symbol,timeframe,folds=folds,final_fraction=final_fraction,
        embargo_bars=embargo_bars,stride=stride,
        min_required_origins=min_required_origins)
    # Split validation may inspect full file integrity and fingerprint the
    # final segment, but all model inputs are clipped to fold time boundaries.
    rows=_closed_rows(candles,timeframe)
    longest=max(HistoricalVolatilityBaseline.horizons)
    window=HistoricalVolatilityBaseline.sample_bars
    reports=[]
    complete=0
    for f in split.folds:
        start,end=f.validation_start_index,f.validation_end_exclusive
        origins=skipped=0
        buckets={h:{"n":0,"rw_abs":Decimal(0),"candidate_abs":Decimal(0),
                    "rw_interval":Decimal(0),"candidate_interval":Decimal(0),
                    "rw_covered":0,"candidate_covered":0,
                    "moving_actuals":0,"nonflat_predictions":0,"direction_hits":0}
                 for h in HistoricalVolatilityBaseline.horizons}
        for index in range(start-1,end-longest,stride):
            observed=tuple(p for _,p in rows[max(0,index+1-window):index+1])
            try:
                candidate=momentum_envelope(observed,HistoricalVolatilityBaseline.horizons)
                reference=ewma_price_envelope(observed,HistoricalVolatilityBaseline.horizons,
                                             z=HistoricalVolatilityBaseline.z80)
            except ValueError:
                skipped+=1
                continue
            anchor=observed[-1]
            origins+=1
            for h,c,r in zip(HistoricalVolatilityBaseline.horizons,candidate,reference):
                target=index+h
                if target>=end or rows[target][0]!=rows[index][0]+seconds(timeframe)*h:
                    raise ValueError("Causal evaluation crossed fold boundary")
                actual=rows[target][1]
                c_error,c_interval,c_hit=_score(*c,actual,anchor)
                r_error,r_interval,r_hit=_score(*r,actual,anchor)
                b=buckets[h]
                b["n"]+=1
                b["candidate_abs"]+=c_error
                b["rw_abs"]+=r_error
                b["candidate_interval"]+=c_interval
                b["rw_interval"]+=r_interval
                b["candidate_covered"]+=c_hit
                b["rw_covered"]+=r_hit
                if actual!=anchor:
                    b["moving_actuals"]+=1
                    if c[1]!=anchor:
                        b["nonflat_predictions"]+=1
                        if (c[1]>anchor)==(actual>anchor):
                            b["direction_hits"]+=1

        points=[]
        for h,b in sorted(buckets.items()):
            if not b["n"]:
                continue
            n=Decimal(b["n"])
            baseline=b["rw_abs"]/n
            challenger=b["candidate_abs"]/n
            gain=(Decimal(100)*(baseline-challenger)/baseline
                  if baseline>0 else None)
            wilson_low,wilson_high=_wilson_95(b["direction_hits"],b["moving_actuals"])
            points.append(PairedHorizon(
                horizon_candles=h,observations=b["n"],
                rw_mae=_finite(baseline),candidate_mae=_finite(challenger),
                candidate_mae_gain_pct=_finite(gain) if gain is not None else None,
                rw_interval_score_pct=_finite(b["rw_interval"]/n),
                candidate_interval_score_pct=_finite(b["candidate_interval"]/n),
                rw_coverage=b["rw_covered"]/b["n"],
                candidate_coverage=b["candidate_covered"]/b["n"],
                nonflat_actuals=b["moving_actuals"],
                candidate_nonflat_predictions=b["nonflat_predictions"],
                candidate_direction_hit_rate=(
                    b["direction_hits"]/b["moving_actuals"]
                    if b["moving_actuals"] else None),
                direction_hits=b["direction_hits"],
                direction_calls=b["nonflat_predictions"],
                direction_wilson_95_lower=wilson_low,
                direction_wilson_95_upper=wilson_high,
                direction_sample_sufficient=b["moving_actuals"]>=30))
        if origins>=min_required_origins:
            complete+=1
        reports.append(PairedFold(
            fold_number=f.number,origins=origins,skipped_origins=skipped,
            validation_start_index=start,validation_end_exclusive=end,
            horizons=tuple(points)))

    return CandidateComparison(
        mode="PAIRED_DIRECTIONAL_RESEARCH_SEALED_FINAL",
        status=("EVALUATED_DEVELOPMENT_ONLY"
                if complete==folds else "INSUFFICIENT"),
        symbol=symbol,timeframe=timeframe,
        random_walk_version=HistoricalVolatilityBaseline.version,
        candidate_version=CANDIDATE_VERSION,folds=tuple(reports),
        final_holdout_sha256=split.sealed_final.sha256,
        final_holdout_evaluated=False,
        note="Both models use identical pre-origin closed candles and are "
             "scored on identical later outcomes. Positive gain is exploratory, "
             "not verified predictive alpha or trading profit. Current candidate "
             "uses fixed shrinkage parameters with no model fitting. Final "
             "holdout remains SEALED and unscored. Direction hit rate includes "
             "all nonflat realized moves; flat candidate calls count as misses. "
             "Wilson 95% bounds are descriptive and do not imply independent "
             "market observations, statistical trading edge, or validated accuracy.")
