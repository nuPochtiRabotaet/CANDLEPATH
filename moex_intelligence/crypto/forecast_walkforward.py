"""Development-only chronological multi-fold forecast assessment for v0.9.

The final slice is SEALED: it is quality-checked and fingerprinted, but never
fed to the model or used to score a fold. Its scores are not published here.
A fixed Random Walk/EWMA baseline requires no fitting; the purged-training
boundary is recorded for future supervised candidates, not misrepresented
as training done by the current model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

from .forecast_baseline import HistoricalVolatilityBaseline
from .forecast_evaluation import (
    ReplayReport, _closed_rows, evaluate_historical_baseline)
from .market import Bybit, seconds


@dataclass(frozen=True)
class FoldReport:
    number: int
    purged_training_end_exclusive: int
    purge_bars: int
    validation_start_index: int
    validation_end_exclusive: int
    validation_start_utc_seconds: int
    validation_last_close_utc_seconds: int
    result: ReplayReport


@dataclass(frozen=True)
class SealedHoldout:
    start_index: int
    end_exclusive: int
    closed_bars: int
    first_open_utc_seconds: int
    last_close_utc_seconds: int
    sha256: str
    evaluated: bool = False


@dataclass(frozen=True)
class WalkForwardReport:
    mode: str
    status: str
    symbol: str
    timeframe: str
    baseline_version: str
    total_closed_candles: int
    folds_requested: int
    folds_evaluated: int
    embargo_bars: int
    final_fraction: float
    folds: tuple[FoldReport, ...]
    sealed_final: SealedHoldout
    note: str

    def as_dict(self):
        return asdict(self)


def _jsonable_row(row):
    if isinstance(row, dict):
        return row
    return asdict(row)


def evaluate_purged_walkforward(
    candles, symbol: str, timeframe: str, *,
    folds: int = 3, final_fraction: float = .20,
    embargo_bars: int = 8, stride: int = 8,
    min_required_origins: int = 30,
) -> WalkForwardReport:
    """Evaluate fixed model across chronological, non-overlapping test folds.

    All scored outcome targets remain inside each fold; the final fraction
    never contributes to any model input or fold outcome. A possible
    supervised-model training cutoff is explicitly purged by embargo_bars
    (>= max horizon) before each fold. We do NOT fit any model here.
    """
    Bybit.validate(symbol, timeframe)
    if type(folds) is not int or not 2 <= folds <= 6:
        raise ValueError("Walk-forward folds must be an integer from 2 to 6")
    try:
        fraction = (float(final_fraction)
                    if type(final_fraction) in (float,int) else float("nan"))
    except (TypeError, ValueError, OverflowError):
        fraction = float("nan")
    if not math.isfinite(fraction) or not .10 <= fraction <= .35:
        raise ValueError("Final holdout fraction must be between 10% and 35%")
    horizon = max(HistoricalVolatilityBaseline.horizons)
    if type(embargo_bars) is not int or not horizon <= embargo_bars <= 64:
        raise ValueError("Purge/embargo must cover the longest forecast horizon")
    if type(stride) is not int or stride < horizon:
        raise ValueError("Origin stride must cover longest forecast horizon")
    if type(min_required_origins) is not int or min_required_origins < 1:
        raise ValueError("Invalid minimum of completed origins")

    checked = _closed_rows(candles, timeframe)
    count = len(checked)
    # Only the final incomplete candle may be omitted by _closed_rows().
    validated_candles = tuple(candles[:count])
    start_final = math.floor(count * (1 - fraction))
    earliest = HistoricalVolatilityBaseline.sample_bars + embargo_bars
    usable = start_final - earliest
    if usable < folds * (horizon + stride):
        raise ValueError("Not enough chronology before the sealed final holdout")

    boundaries = [earliest + (i * usable // folds) for i in range(folds + 1)]
    rows_final = validated_candles[start_final:]
    digest = hashlib.sha256(json.dumps(
        [_jsonable_row(c) for c in rows_final], sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    step = seconds(timeframe)
    sealed = SealedHoldout(
        start_index=start_final, end_exclusive=count,
        closed_bars=count - start_final,
        first_open_utc_seconds=checked[start_final][0],
        last_close_utc_seconds=checked[-1][0] + step,
        sha256=digest)

    results = []
    for i in range(folds):
        start, end = boundaries[i], boundaries[i + 1]
        # Purged cutoff for a hypothetical future supervised model. The fixed
        # baseline only observes already-closed candles at each origin.
        train_end = start - embargo_bars
        if train_end < HistoricalVolatilityBaseline.sample_bars:
            raise ValueError("Insufficient training-history buffer")
        # IMPORTANT: prefix ends at fold end, NEVER contains the sealed final.
        prefix = validated_candles[:end]
        assessment = evaluate_historical_baseline(
            prefix, symbol, timeframe, evaluation_window=(start, end),
            stride=stride, min_required_origins=min_required_origins)
        results.append(FoldReport(
            number=i + 1, purged_training_end_exclusive=train_end,
            purge_bars=embargo_bars, validation_start_index=start,
            validation_end_exclusive=end,
            validation_start_utc_seconds=checked[start][0],
            validation_last_close_utc_seconds=checked[end - 1][0] + step,
            result=assessment))

    evaluated = sum(f.result.status == "EVALUATED" for f in results)
    return WalkForwardReport(
        mode="PURGED_WALKFORWARD_RESEARCH_SEALED_FINAL",
        status="EVALUATED_DEVELOPMENT_ONLY" if evaluated == folds else "INSUFFICIENT",
        symbol=symbol, timeframe=timeframe,
        baseline_version=HistoricalVolatilityBaseline.version,
        total_closed_candles=count, folds_requested=folds,
        folds_evaluated=evaluated, embargo_bars=embargo_bars,
        final_fraction=fraction, folds=tuple(results),
        sealed_final=sealed,
        note="Development folds only. Final holdout is fingerprinted but NOT scored. "
             "The Random Walk/EWMA baseline is fixed and never fitted; the purge "
             "boundary is an explicit future-ML safety constraint. These historical "
             "results do not establish profitable directional prediction, "
             "prospective performance, calibrated confidence or trading profitability.")
