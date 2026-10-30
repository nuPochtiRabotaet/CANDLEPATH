"""Strict, read-only local CSV OHLCV importer for CandlePath v0.9 research.

This DOES NOT authenticate the origin of a file. Unlike the live Bybit V5
public REST evaluator, CSV-based results are always labelled USER_SUPPLIED.
No Store/SQLite access, exchange request, orders, or publication of forecasts.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import time

from .forecast_evaluation import evaluate_historical_baseline
from .market import Bybit, Candle, MarketError, seconds

_HEADERS = ("open_time_ms", "open", "high", "low", "close", "volume")
_MAX_BYTES = 12 * 1024 * 1024
_MAX_ROWS = 50_000
_MIN_MS = 946684800000  # 2000-01-01 00:00:00 UTC


@dataclass(frozen=True)
class LocalOHLCV:
    symbol: str
    interval: str
    file_sha256: str
    normalized_sha256: str
    row_count: int
    first_open_ms: int
    last_closed_at_ms: int
    candles: tuple[Candle, ...]


def _price(cell: str, column: str, line: int) -> float:
    try:
        result = float(cell)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"CSV row {line}: invalid {column}") from exc
    if not math.isfinite(result):
        raise ValueError(f"CSV row {line}: nonfinite {column}")
    if column == "volume":
        if result < 0:
            raise ValueError(f"CSV row {line}: negative volume")
    elif result <= 0:
        raise ValueError(f"CSV row {line}: nonpositive {column}")
    return result


def read_local_ohlcv(path: str | Path, symbol: str, interval: str,
                     *, now: float | None = None) -> LocalOHLCV:
    """Validate a complete, time-ordered CSV of fully closed UTC SPOT candles.

    The column names are explicit and the file is locally sourced, hence no
    public-exchange provenance is claimed. All rows must be contiguous.
    """
    Bybit.validate(symbol, interval)
    filepath = Path(path).expanduser()
    if not filepath.is_file():
        raise ValueError("CSV input file does not exist")
    with filepath.open("rb") as stream:
        raw = stream.read(_MAX_BYTES + 1)
    if not raw or len(raw) > _MAX_BYTES:
        raise ValueError("CSV file is empty or larger than 12 MiB")
    fingerprint = hashlib.sha256(raw).hexdigest()
    try:
        body = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV is not UTF-8 encoded") from exc

    cutoff_value = time.time() if now is None else now
    try:
        cutoff = (float(cutoff_value)
                  if type(cutoff_value) in (float, int) else float("nan"))
    except (TypeError, ValueError, OverflowError):
        cutoff = float("nan")
    if not math.isfinite(cutoff) or cutoff <= 0:
        raise ValueError("Invalid UTC observation cutoff")
    step_ms = seconds(interval) * 1000

    reader = csv.DictReader(io.StringIO(body, newline=""))
    if not reader.fieldnames or tuple(reader.fieldnames) != _HEADERS:
        raise ValueError("CSV columns must exactly match open_time_ms,open,high,low,close,volume")

    rows: list[Candle] = []
    last_ms = None
    for line, data in enumerate(reader, start=2):
        if line > _MAX_ROWS + 1:
            raise ValueError("CSV exceeds 50,000 candles")
        if None in data or any(data.get(column) is None for column in _HEADERS):
            raise ValueError(f"CSV row {line}: inconsistent column count")
        stamp = data["open_time_ms"]
        if not isinstance(stamp, str) or not stamp.isascii() or not stamp.isdecimal():
            raise ValueError(f"CSV row {line}: open_time_ms must be an integer in milliseconds")
        moment_ms = int(stamp)
        if moment_ms < _MIN_MS or moment_ms % step_ms:
            raise ValueError(f"CSV row {line}: UTC-aligned millisecond timestamp required")
        if moment_ms + step_ms > cutoff * 1000:
            raise ValueError(f"CSV row {line}: unclosed/future candle is forbidden")
        if last_ms is not None and moment_ms - last_ms != step_ms:
            raise ValueError(f"CSV row {line}: duplicate, missing or reordered candle")
        values = [_price(data[column], column, line) for column in _HEADERS[1:]]
        try:
            candle = Candle(moment_ms // 1000, *values, True)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"CSV row {line}: inconsistent OHLCV prices") from exc
        rows.append(candle)
        last_ms = moment_ms

    if not rows:
        raise ValueError("CSV contains no closed candles")
    canonical = json.dumps([asdict(c) for c in rows],
                           sort_keys=True, separators=(",", ":"), allow_nan=False)
    return LocalOHLCV(
        symbol=symbol, interval=interval, file_sha256=fingerprint,
        normalized_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        row_count=len(rows), first_open_ms=rows[0].time * 1000,
        last_closed_at_ms=(rows[-1].time + seconds(interval)) * 1000,
        candles=tuple(rows))


def evaluate_local_ohlcv(path: str | Path, symbol: str, interval: str, *,
                         now: float | None = None, holdout_fraction: float = 0.30,
                         stride: int = 8, min_required_origins: int = 30) -> dict:
    dataset = read_local_ohlcv(path, symbol, interval, now=now)
    evaluation = evaluate_historical_baseline(
        dataset.candles, symbol, interval,
        holdout_fraction=holdout_fraction, stride=stride,
        min_required_origins=min_required_origins)
    metadata = {key: value for key, value in asdict(dataset).items()
                if key != "candles"}
    metadata["first_open_utc"] = datetime.fromtimestamp(
        dataset.first_open_ms / 1000, timezone.utc).isoformat()
    metadata["last_closed_utc"] = datetime.fromtimestamp(
        dataset.last_closed_at_ms / 1000, timezone.utc).isoformat()
    metadata.update({
        "source": "USER_SUPPLIED_CSV_UNVERIFIED",
        "verified_bybit_http": False,
        "note": "The input file is structurally validated but its market origin "
                "and authenticity have NOT been verified by any exchange.",
    })
    return {
        "verification": "LOCAL_FILE_FORMAT_VALIDATED_NOT_MARKET_VERIFIED",
        "historical_replay_only": True,
        "market": metadata,
        "evaluation": evaluation.as_dict(),
        "limitations": "No actual exchange response, provenance certification, "
                       "calibrated probability, trading strategy or profitability is established.",
    }
