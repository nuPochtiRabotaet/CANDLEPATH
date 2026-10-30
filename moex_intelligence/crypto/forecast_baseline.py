"""Causal, uncalibrated baseline for Forecast Overlay v0.9.

Random Walk median + log-return EWMA volatility: a statistical reference,
NOT a profitable-strategy claim or a trained directional predictor. Future or
unclosed candles never contribute to the calculation.
"""
import hashlib
import math
import time

from .intelligence import Forecast, ForecastPoint
from .market import seconds, SYMBOLS, INTERVALS


class HistoricalVolatilityBaseline:
    version = 'rw-ewma80-experimental-v1'
    min_bars = 60
    sample_bars = 120
    horizons = (1, 2, 4, 8)
    nominal_coverage = .8
    z80 = 1.2815515655446004

    @staticmethod
    def _unavailable(symbol, timeframe, as_of, reason):
        return Forecast('unavailable', symbol, timeframe, time.time(),
                        max(0, as_of), 'rw-ewma80-experimental-v1',
                        'UNAVAILABLE', reason=reason)

    def forecast(self, closed_candles, symbol: str, timeframe: str, as_of: float) -> Forecast:
        """Calculate only as of a REAL observation cutoff (epoch seconds).

        Input may include the current partial candle, which is ignored. No
        synthetic/backfilled predictions are published from this function.
        """
        now = time.time()
        if symbol not in SYMBOLS or timeframe not in INTERVALS.values():
            return self._unavailable(symbol, timeframe, as_of, 'Unsupported market')
        if not math.isfinite(as_of) or as_of <= 0 or as_of > now + 2:
            return self._unavailable(symbol, timeframe, as_of, 'Invalid observation cutoff')
        step = seconds(timeframe)
        closed = []
        for raw in closed_candles:
            row = raw if isinstance(raw, dict) else vars(raw)
            if not row.get('closed'):
                continue
            candle_time, price = row.get('time'), row.get('close')
            if type(candle_time) is not int or candle_time < 0 or candle_time % step:
                return self._unavailable(symbol, timeframe, as_of, 'Invalid candle timestamp')
            if candle_time + step > as_of:
                return self._unavailable(symbol, timeframe, as_of, 'Closed candle is newer than observation cutoff')
            if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                return self._unavailable(symbol, timeframe, as_of, 'Invalid close price')
            closed.append((candle_time, float(price)))
        if len(closed) < self.min_bars:
            return self._unavailable(symbol, timeframe, as_of, 'Too few closed candles')
        closed = closed[-self.sample_bars:]
        if any(b[0] - a[0] != step for a, b in zip(closed, closed[1:])):
            return self._unavailable(symbol, timeframe, as_of, 'Missing, reordered or duplicate closed candles')
        last_time, last_close = closed[-1]
        last_close_time = last_time + step
        if not 0 <= now - last_close_time < step:
            return self._unavailable(symbol, timeframe, as_of, 'Last closed candle is stale')
        returns = [math.log(b[1] / a[1]) for a, b in zip(closed, closed[1:])]
        if not all(math.isfinite(v) and abs(v) < .7 for v in returns):
            return self._unavailable(symbol, timeframe, as_of, 'Extreme/invalid log return; forecast suppressed')
        # EWMA of squared log-returns, normalized so short samples do not bias toward zero.
        decay = .94
        weights = [decay ** i for i in range(len(returns))]
        variance = sum(w * r * r for w, r in zip(weights, reversed(returns))) / sum(weights)
        sigma = math.sqrt(variance)
        points = []
        for horizon in self.horizons:
            target = last_close_time + horizon * step
            spread = self.z80 * sigma * math.sqrt(horizon)
            lower, upper = last_close * math.exp(-spread), last_close * math.exp(spread)
            if not all(math.isfinite(v) and v > 0 for v in (lower, upper)):
                return self._unavailable(symbol, timeframe, as_of, 'Numerically unstable interval')
            points.append(ForecastPoint(target, str(lower), str(last_close), str(upper)))
        fingerprint = hashlib.sha256(f'{self.version}:{symbol}:{timeframe}:{last_time}'.encode()).hexdigest()[:16]
        return Forecast(fingerprint, symbol, timeframe, now, last_close_time,
                        self.version, 'EXPERIMENTAL', tuple(points), self.nominal_coverage,
                        reason='Random Walk median; EWMA volatility. Nominal 80% interval, NOT calibrated or validated.')


def candle_stream_ready(snapshot) -> bool:
    """Forecast data readiness is independent of order execution/quote readiness.

    A fresh tradeable bid/ask cannot substitute for a live, recent candle stream;
    conversely a temporarily invalid spread must not hide good market candles.
    """
    readiness = snapshot.get('readiness') or {}
    return (readiness.get('market_stream_active') is True
            and readiness.get('candle_data_fresh') is True
            and isinstance(snapshot.get('candles'), list))
