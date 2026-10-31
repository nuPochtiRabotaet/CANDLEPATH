"""Offline import of user-supplied Bybit-style SPOT public trade CSV files.

No exchange calls, credentials, SQLite changes, trading orders or authenticated
provenance claims. Trade IDs and timestamps are validated; missing minutes are
never interpolated, and incomplete higher-timeframe buckets are discarded.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import math
from pathlib import Path
import re

from .market import Bybit, MarketError, seconds

TRADE_HEADER = ["id", "timestamp", "price", "volume", "side", "rpi"]
CANDLE_HEADER = ["open_time_ms", "open", "high", "low", "close", "volume"]
MAX_TRADE_BYTES = 512 * 1024 * 1024
MAX_INPUT_DAYS = 31
MIN_TIMESTAMP_MS = 946684800000


def _positive(raw: str, field: str) -> Decimal:
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field} in trade CSV") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"Nonpositive or nonfinite {field} in trade CSV")
    try:
        if not math.isfinite(float(value)):
            raise ValueError(f"Unrepresentable {field} in trade CSV")
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"Unrepresentable {field} in trade CSV") from exc
    return value


def _merge(bucket, price: Decimal, volume: Decimal):
    if bucket is None:
        return [price, price, price, price, volume]
    if price > bucket[1]:
        bucket[1] = price
    if price < bucket[2]:
        bucket[2] = price
    bucket[3] = price
    bucket[4] += volume
    return bucket


def read_spot_trade_minutes(paths, symbol: str):
    """Stream sorted daily exports into exact 1-minute OHLCV and source hashes.

    Same-millisecond trades preserve their original CSV order. Trade IDs must
    be consecutive *within* a daily export to detect truncated/missing rows.
    Missing calendar days and missing minute buckets remain missing.
    """
    Bybit.validate(symbol, "1")
    if not isinstance(paths, (tuple, list)) or not 1 <= len(paths) <= MAX_INPUT_DAYS:
        raise ValueError("Provide between 1 and 31 daily trade CSV paths")
    path_list = [Path(p) for p in paths]
    if len(set(p.resolve() for p in path_list)) != len(path_list):
        raise ValueError("Duplicate input path")
    ordered = []
    for path in path_list:
        match = re.fullmatch(re.escape(symbol) + r"_(\d{4}-\d{2}-\d{2})\.csv", path.name)
        if not match:
            raise ValueError("Expected SYMBOL_YYYY-MM-DD.csv for the chosen Spot symbol")
        day = datetime.strptime(match.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        ordered.append((day, path))
    ordered.sort()
    if len({day for day, _ in ordered}) != len(ordered):
        raise ValueError("Duplicate UTC trade day")
    minutes = {}
    provenance = []
    for day, path in ordered:
        if not path.is_file() or path.stat().st_size > MAX_TRADE_BYTES:
            raise ValueError("Missing or oversized trade CSV")
        before = path.stat()
        h = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                h.update(chunk)
        day_start = int(day.timestamp() * 1000)
        day_end = day_start + 86400000
        prev_time = prev_id = None
        count = 0
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != TRADE_HEADER:
                raise ValueError(f"{path.name}: unexpected trade columns")
            for line, row in enumerate(reader, 2):
                if None in row or any(row.get(k) is None for k in TRADE_HEADER):
                    raise ValueError(f"{path.name}:{line}: invalid field count")
                try:
                    stamp = int(row["timestamp"])
                    trade_id = int(row["id"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{path.name}:{line}: invalid timestamp or ID") from exc
                if (stamp < MIN_TIMESTAMP_MS or not day_start <= stamp < day_end
                    or (prev_time is not None and stamp < prev_time)):
                    raise ValueError(f"{path.name}:{line}: out-of-order or out-of-day timestamp")
                if prev_id is not None and trade_id != prev_id + 1:
                    raise ValueError(f"{path.name}:{line}: missing/duplicate/out-of-order trade ID")
                if row["side"].lower() not in ("buy", "sell") or row["rpi"] not in ("0", "1"):
                    raise ValueError(f"{path.name}:{line}: invalid side or RPI")
                price = _positive(row["price"], "price")
                amount = _positive(row["volume"], "base volume")
                minute = stamp // 60000 * 60000
                minutes[minute] = _merge(minutes.get(minute), price, amount)
                prev_time, prev_id = stamp, trade_id
                count += 1
        after = path.stat()
        if count == 0 or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"{path.name}: empty or modified during import")
        provenance.append({
            "name": path.name, "sha256": h.hexdigest(), "trades": count,
            "first_day_utc": day.strftime("%Y-%m-%d"), "market_verification": False})
    return minutes, provenance


def _aggregate(minutes, interval: str):
    step_ms = seconds(interval) * 1000
    bins = {}
    for minute, value in sorted(minutes.items()):
        start = minute // step_ms * step_ms
        bucket = bins.get(start)
        if bucket is None:
            bins[start] = [value.copy(), 1]
        else:
            dest, count = bucket
            if value[1] > dest[1]:
                dest[1] = value[1]
            if value[2] < dest[2]:
                dest[2] = value[2]
            dest[3] = value[3]
            dest[4] += value[4]
            bucket[1] = count + 1
    expected_minutes = step_ms // 60000
    # Never invent an OHLCV candle when any contributing minute is absent.
    return {t: b for t, (b, count) in bins.items() if count == expected_minutes}


def segment_spot_trade_minutes(minutes, symbol: str, interval: str):
    """Return contiguous, fully covered candle segments in UTC milliseconds."""
    Bybit.validate(symbol, interval)
    if seconds(interval) % 60:
        raise ValueError("Only whole-minute timeframes are supported")
    step_ms = seconds(interval) * 1000
    buckets = _aggregate(minutes, interval)
    segments = []
    current = []
    for moment, values in sorted(buckets.items()):
        if current and moment != current[-1][0] + step_ms:
            segments.append(current)
            current = []
        current.append((moment, values))
    if current:
        segments.append(current)
    return segments


def write_spot_candle_segments(segments, output_dir: str | Path, symbol: str, interval: str):
    """Write new, never-overwritten CandlePath OHLCV CSVs; no input edits."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    planned = []
    for segment in segments:
        start = datetime.fromtimestamp(segment[0][0] / 1000, timezone.utc).strftime("%Y%m%dT%H%M")
        end = datetime.fromtimestamp(segment[-1][0] / 1000, timezone.utc).strftime("%Y%m%dT%H%M")
        filename = f"{symbol}_{interval}m_{start}_{end}.csv" if interval != "D" else f"{symbol}_1D_{start}_{end}.csv"
        target = output / filename
        if target.exists():
            raise FileExistsError(f"Output already exists: {target}")
        planned.append((target, segment))
    outputs = []
    for target, segment in planned:
        with target.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(CANDLE_HEADER)
            for stamp, ohlcv in segment:
                writer.writerow([stamp, *(str(x) for x in ohlcv)])
        outputs.append(target)
    return outputs
