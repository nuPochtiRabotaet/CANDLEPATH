"""Honest OFFLINE walk-forward diagnostics for the v0.9 statistical baseline.

This is a historical replay, not a publication of predictions made in the past.
No forecasts are written to ForecastHistory; no trades are executed. Each origin
uses only closed candles at or before that origin. Later candles score outcomes.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Sequence

from .forecast_baseline import HistoricalVolatilityBaseline, ewma_price_envelope
from .market import INTERVALS, SYMBOLS, seconds


@dataclass(frozen=True)
class HorizonScore:
    horizon_candles: int
    observations: int
    empirical_coverage: float
    mean_absolute_error: float
    mean_absolute_percentage_error: float
    mean_band_width_pct: float
    random_walk_mae: float
    nominal_coverage: float = HistoricalVolatilityBaseline.nominal_coverage


@dataclass(frozen=True)
class ReplayReport:
    mode: str
    status: str
    symbol: str
    timeframe: str
    model_version: str
    closed_candles: int
    evaluation_start: int | None
    origins: int
    skipped_origins: int
    min_required_origins: int
    horizons: tuple[HorizonScore, ...]
    note: str

    def as_dict(self):
        return asdict(self)


def _closed_rows(candles: Sequence, timeframe: str):
    """Reject incomplete/ambiguous histories rather than silently backfilling."""
    if not isinstance(candles, (tuple, list)):
        raise ValueError('Expected an ordered candle list')
    step = seconds(timeframe)
    rows = []
    for i, candle in enumerate(candles):
        try:
            raw = candle if isinstance(candle, dict) else vars(candle)
        except TypeError as exc:
            raise ValueError('Malformed candle') from exc
        closed = raw.get('closed')
        if closed is False and i == len(candles) - 1:
            continue  # The only permitted incomplete candle is the last one.
        if closed is not True:
            raise ValueError('Only the last candle may be open')
        moment, price = raw.get('time'), raw.get('close')
        if type(moment) is not int or moment < 0 or moment % step:
            raise ValueError('Unaligned candle time')
        if type(price) not in (int, float) or not math.isfinite(price) or price <= 0:
            raise ValueError('Invalid candle close')
        if rows and moment - rows[-1][0] != step:
            raise ValueError('Reordered, repeated or missing candles')
        rows.append((moment, float(price)))
    return rows


def evaluate_historical_baseline(candles, symbol, timeframe, *,
                                 holdout_fraction=0.30, stride=8,
                                 min_required_origins=30):
    """Chronological, non-overlapping-origin replay against *held-out* prices.

    A fixed, never-fitted Random Walk/EWMA baseline is evaluated at origins
    inside the last holdout_fraction of the provided chronological dataset.
    At each origin, the baseline sees at most the previous 120 closes. Its
    forward scores are computed only after the envelope was generated.

    This does NOT optimize model parameters, claim statistical independence,
    automatically validate calibration, or include trading fees. It reports
    diagnostic descriptive scores and keeps all replay rows out of the live
    immutable forecast journal.
    """
    if symbol not in SYMBOLS or timeframe not in INTERVALS.values():
        raise ValueError('Unsupported market')
    if type(holdout_fraction) is not float and type(holdout_fraction) is not int:
        raise ValueError('Invalid holdout fraction')
    if not math.isfinite(holdout_fraction) or not 0.10 <= holdout_fraction <= 0.50:
        raise ValueError('Holdout fraction must be between 0.10 and 0.50')
    if type(stride) is not int or stride < max(HistoricalVolatilityBaseline.horizons):
        raise ValueError('Stride must cover the longest horizon (nonoverlapping origins)')
    if type(min_required_origins) is not int or min_required_origins < 1:
        raise ValueError('Invalid origin minimum')

    rows = _closed_rows(candles, timeframe)
    step = seconds(timeframe)
    window = HistoricalVolatilityBaseline.sample_bars
    max_horizon = max(HistoricalVolatilityBaseline.horizons)
    # The first scored future bar must be in the untouched chronological holdout.
    holdout_start = max(window, math.floor(len(rows) * (1 - holdout_fraction)))
    first_origin = holdout_start - 1
    last_origin = len(rows) - 1 - max_horizon
    sums = {h: {'n': 0, 'hits': 0, 'abs': 0., 'ape': 0., 'width': 0.}
            for h in HistoricalVolatilityBaseline.horizons}
    origins = skipped = 0

    if first_origin >= window - 1 and last_origin >= first_origin:
        for idx in range(first_origin, last_origin + 1, stride):
            # CRITICAL: the forecast gets ONLY <=idx historical prices.
            past = [price for _, price in rows[max(0, idx + 1 - window):idx + 1]]
            try:
                envelope = ewma_price_envelope(past, HistoricalVolatilityBaseline.horizons,
                                               z=HistoricalVolatilityBaseline.z80)
            except ValueError:
                skipped += 1
                continue
            origins += 1
            for h, (lo, median, hi) in zip(HistoricalVolatilityBaseline.horizons, envelope):
                target_index = idx + h
                # If this assertion breaks, never report scores from a leaked horizon.
                assert rows[target_index][0] == rows[idx][0] + h * step
                actual = rows[target_index][1]
                b = sums[h]
                b['n'] += 1
                b['hits'] += int(lo <= actual <= hi)
                b['abs'] += abs(median - actual)
                b['ape'] += 100 * abs(median - actual) / actual
                b['width'] += 100 * (hi - lo) / median

    scores = tuple(HorizonScore(
        horizon_candles=h, observations=b['n'], empirical_coverage=b['hits']/b['n'],
        mean_absolute_error=b['abs']/b['n'], mean_absolute_percentage_error=b['ape']/b['n'],
        mean_band_width_pct=b['width']/b['n'],
        # Current model uses a flat Random Walk median; it CANNOT beat itself.
        random_walk_mae=b['abs']/b['n'])
        for h, b in sums.items() if b['n'])

    status = 'EVALUATED' if origins >= min_required_origins else 'INSUFFICIENT'
    start = rows[holdout_start][0] if holdout_start < len(rows) else None
    return ReplayReport(
        mode='HISTORICAL_REPLAY_NOT_LIVE', status=status, symbol=symbol,
        timeframe=timeframe, model_version=HistoricalVolatilityBaseline.version,
        closed_candles=len(rows), evaluation_start=start, origins=origins,
        skipped_origins=skipped, min_required_origins=min_required_origins,
        horizons=scores,
        note='Historical replay, not actual past publications or proof of directional accuracy. '
             'Nominal 80% bands are uncalibrated; the median is identical to Random Walk. '
             'No trading fees or execution assumptions were evaluated.')
