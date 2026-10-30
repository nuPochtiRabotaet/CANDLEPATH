"""Read-only Bybit V5 SPOT history acquisition for v0.9 forecast diagnostics.

Uses only public REST /v5/market/time and /v5/market/kline. Never supplies
credentials, initializes Store, writes a portfolio DB or publishes forecasts.
Only complete, gap-free, verified closed candles may be scored.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import time

from .forecast_evaluation import evaluate_historical_baseline
from .market import Bybit, Candle, MarketError, seconds

_MAX_PAGE = 1000
_MAX_BARS = 5000


@dataclass(frozen=True)
class PublicSpotHistory:
    symbol: str
    interval: str
    server_time_ms: int
    first_open_ms: int
    last_closed_at_ms: int
    requested_bars: int
    returned_bars: int
    pages: int
    sha256: str
    candles: tuple[Candle, ...]


def _server_time_ms(body):
    try:
        ms = int(body["time"])
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise MarketError("Invalid Bybit server timestamp") from exc
    if ms <= 0 or abs(ms - int(time.time() * 1000)) > 5 * 60_000:
        raise MarketError("Bybit clock is invalid or differs from local clock by over 5 minutes")
    return ms


def _parse_page(body, symbol, interval, *, end_ms, latest_closed_boundary_ms, limit):
    try:
        result = body["result"]
        if result["category"] != "spot" or result["symbol"] != symbol:
            raise MarketError("Bybit returned a different market")
        raw_rows = result["list"]
    except (KeyError, TypeError) as exc:
        raise MarketError("Invalid Bybit kline response structure") from exc
    if not isinstance(raw_rows, list) or len(raw_rows) > limit:
        raise MarketError("Invalid Bybit kline page size")
    step_ms = seconds(interval) * 1000
    last_ms = None
    parsed = []
    for row in raw_rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise MarketError("Invalid Bybit OHLCV row")
        try:
            if isinstance(row[0], bool) or not str(row[0]).isdigit():
                raise ValueError("Noninteger timestamp")
            moment_ms = int(row[0])
            values = [float(v) for v in row[1:6]]
        except (ValueError, TypeError, OverflowError) as exc:
            raise MarketError("Invalid numeric value in Bybit OHLCV row") from exc
        if (moment_ms < 0 or moment_ms % step_ms != 0
                or moment_ms > end_ms
                or moment_ms + step_ms > latest_closed_boundary_ms):
            raise MarketError("Future, partial or unaligned Bybit candle")
        if last_ms is not None and moment_ms >= last_ms:
            raise MarketError("Bybit page is not strictly newest-first")
        last_ms = moment_ms
        try:
            parsed.append(Candle(moment_ms // 1000, *values, True))
        except (TypeError, ValueError, OverflowError) as exc:
            raise MarketError("Corrupt Bybit OHLCV candle") from exc
    return parsed


async def collect_public_spot_history(symbol: str, interval: str, *,
                                      bars: int = 1600, connector: Bybit | None = None,
                                      max_pages: int = 5,
                                      pause_seconds: float = 0.15) -> PublicSpotHistory:
    """Fetch an anchored historic sequence with deterministic backwards paging.

    Fails closed on missing pages, duplicate/gapped candles, unsupported markets,
    clock skew, HTTP errors or region restrictions. Returned candles are
    chronologically ascending and fully closed at the server observation cutoff.
    """
    Bybit.validate(symbol, interval)
    if type(bars) is not int or not 400 <= bars <= _MAX_BARS:
        raise MarketError("Requested bars must be an integer from 400 to 5000")
    if type(max_pages) is not int or not 1 <= max_pages <= 10 or bars > max_pages * _MAX_PAGE:
        raise MarketError("Pagination limit is insufficient for requested bars")
    if not isinstance(pause_seconds, (int, float)) or not math.isfinite(pause_seconds) or not 0 <= pause_seconds <= 2:
        raise MarketError("Invalid pagination pause")

    api = connector or Bybit()
    server = await api.get("/v5/market/time")
    if not isinstance(server, dict) or server.get("retCode") != 0:
        raise MarketError("Bybit server time request failed")
    server_ms = _server_time_ms(server)
    step_ms = seconds(interval) * 1000
    cutoff_ms = (server_ms // step_ms) * step_ms
    # The API's last open candle may still be changing. Never request it.
    end_ms = cutoff_ms - 1
    seen = set()
    descending = []
    page_count = 0

    while len(descending) < bars and page_count < max_pages:
        limit = min(_MAX_PAGE, bars - len(descending))
        response = await api.get("/v5/market/kline", {
            "category": "spot", "symbol": symbol, "interval": interval,
            "end": end_ms, "limit": limit,
        })
        if not isinstance(response, dict) or response.get("retCode") != 0:
            raise MarketError("Bybit kline request failed")
        page = _parse_page(
            response, symbol, interval, end_ms=end_ms,
            latest_closed_boundary_ms=cutoff_ms, limit=limit)
        page_count += 1
        if not page:
            break
        if any(c.time in seen for c in page):
            raise MarketError("Repeated candle across Bybit history pages")
        seen.update(c.time for c in page)
        if descending and page[0].time != descending[-1].time - seconds(interval):
            raise MarketError("Missing or overlapping Bybit history page")
        descending.extend(page)
        oldest_ms = page[-1].time * 1000
        if oldest_ms >= end_ms:
            raise MarketError("Bybit pagination made no backward progress")
        end_ms = oldest_ms - 1
        if len(descending) < bars and pause_seconds:
            await asyncio.sleep(pause_seconds)

    if len(descending) != bars:
        raise MarketError(f"Incomplete Bybit history: {len(descending)}/{bars} closed candles")
    ascending = tuple(reversed(descending))
    step = seconds(interval)
    if any(b.time - a.time != step for a, b in zip(ascending, ascending[1:])):
        raise MarketError("Bybit history contains gaps or reordered candles")
    if ascending[-1].time + step > cutoff_ms // 1000:
        raise MarketError("Bybit history includes an unclosed candle")

    canonical = json.dumps([asdict(c) for c in ascending],
                           sort_keys=True, separators=(",", ":"), allow_nan=False)
    return PublicSpotHistory(
        symbol=symbol, interval=interval, server_time_ms=server_ms,
        first_open_ms=ascending[0].time * 1000,
        last_closed_at_ms=(ascending[-1].time + step) * 1000,
        requested_bars=bars, returned_bars=len(ascending), pages=page_count,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(), candles=ascending)


async def evaluate_public_spot_history(symbol: str, interval: str, *,
                                       bars: int = 1600, connector: Bybit | None = None,
                                       pause_seconds: float = 0.15):
    """Actual Bybit evaluation only when public REST requests fully succeed.

    Never turn API failures into synthetic "real-market" observations.
    The scores are retrospective, not prospective live predictions.
    """
    snapshot = await collect_public_spot_history(
        symbol, interval, bars=bars, connector=connector,
        pause_seconds=pause_seconds)
    report = evaluate_historical_baseline(snapshot.candles, symbol, interval)
    if report.status != "EVALUATED":
        raise MarketError("Not enough independent replay origins for evaluation")
    metadata = {key: value for key, value in asdict(snapshot).items()
                if key != "candles"}
    metadata.update({
        "source": "BYBIT_V5_SPOT_PUBLIC_REST",
        "endpoint": "/v5/market/kline",
        "retrieved_at_utc": datetime.fromtimestamp(
            snapshot.server_time_ms / 1000, timezone.utc).isoformat(),
        "first_open_utc": datetime.fromtimestamp(
            snapshot.first_open_ms / 1000, timezone.utc).isoformat(),
        "last_closed_at_utc": datetime.fromtimestamp(
            snapshot.last_closed_at_ms / 1000, timezone.utc).isoformat(),
        "evidence": "Confirmed remote HTTP/JSON + gap-free closed-candle sequence",
    })
    return {
        "verification": "PUBLIC_REST_HISTORY_VERIFIED",
        "historical_replay_only": True,
        "market": metadata,
        "evaluation": report.as_dict(),
        "limitations": "Historical replay does not establish predictive skill, "
                       "calibrated probability, actual past publications or trading profit.",
    }
