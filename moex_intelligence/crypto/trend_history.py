"""Fixed Spot data contract for the preregistered trend study. No account access."""
import calendar
import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from .bybit_history_evaluation import _parse_page, _server_time_ms
from .coliseum_catalog import digest
from .market import Bybit, Candle, seconds


SYMBOLS = ("BTCUSDT", "ETHUSDT")
START = int(datetime(2024, 1, 3, tzinfo=timezone.utc).timestamp())
DAY = 86400
DEV_END = START + 576 * DAY
SEALED_END = START + 720 * DAY
ARCHIVE = "https://data.binance.vision/data/spot/monthly/klines"
ROOT = Path(__file__).resolve().parents[2]


class SourceUnavailable(ValueError):
    """Public files or transport unavailable, as distinct from corrupted data."""


def check_calendar():
    guard = json.loads((ROOT / "docs/research/original_holdout_guard.json").read_text())
    start, end = guard["sealed_interval"]
    if start >= end or max(start, START) < min(end, DEV_END):
        raise ValueError("Development overlaps protected history")
    if DEV_END > datetime.now(timezone.utc).timestamp():
        raise ValueError("Development period has not closed")


def check_development(rows, timeframe):
    """Reject trailing partial bars, gaps or extra rows including reserved dates."""
    step = seconds(timeframe)
    if timeframe not in ("60", "240") or len(rows) != (DEV_END - START) // step:
        raise ValueError("Incorrect development coverage")
    for i, row in enumerate(rows):
        candle = Candle(**row)
        if not candle.closed or candle.time != START + i * step:
            raise ValueError("Incomplete or reordered development series")


def four_hour(hourly):
    check_development(hourly, "60")
    result = []
    for i in range(0, len(hourly), 4):
        group = hourly[i:i + 4]
        bar = Candle(group[0]["time"], group[0]["open"], max(r["high"] for r in group),
                     min(r["low"] for r in group), group[-1]["close"],
                     sum(r["volume"] for r in group), True)
        result.append(asdict(bar))
    return result


def parse_archive(raw, checksum, symbol, month):
    """Verify the exact publisher file and its entire chronological monthly grid."""
    filename = f"{symbol}-1h-{month}.zip"
    sha = hashlib.sha256(raw).hexdigest()
    if not re.fullmatch(rf"{sha}\s+\*?{re.escape(filename)}", checksum.strip()):
        raise ValueError(f"Publisher checksum mismatch for {filename}")
    first = date.fromisoformat(month + "-01")
    days = calendar.monthrange(first.year, first.month)[1]
    first_ts = calendar.timegm(first.timetuple())
    unit = 1_000_000 if first.year >= 2025 else 1000
    rows = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if (len(infos) != 1 or infos[0].filename != filename[:-4] + ".csv"
                or infos[0].file_size > 2_000_000):
            raise ValueError("Unexpected kline archive contents")
        with archive.open(infos[0]) as stream:
            for i, fields in enumerate(csv.reader(io.TextIOWrapper(stream, encoding="ascii"))):
                stamp = first_ts + i * 3600
                if (len(fields) != 12 or int(fields[0]) != stamp * unit
                        or int(fields[6]) != (stamp + 3600) * unit - 1):
                    raise ValueError("Invalid or missing Binance hourly observation")
                rows.append(asdict(Candle(stamp, *map(float, fields[1:6]), True)))
    if len(rows) != days * 24:
        raise ValueError("Incomplete monthly archive")
    return [r for r in rows if r["time"] >= START], sha


def archive_file(client, url, folder):
    name = url.rsplit("/", 1)[-1]
    if folder is not None:
        path = folder / name
        if not path.is_file():
            raise SourceUnavailable(f"Missing archive file {name}")
        if path.stat().st_size > 2_000_000:
            raise ValueError("Oversized local archive")
        return path.read_bytes()
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 2_000_000:
                    raise ValueError("Oversized public archive")
            return bytes(raw)
    except httpx.HTTPError as exc:
        raise SourceUnavailable(f"{name}: {exc}") from exc


def binance_history(folder=None):
    source = "BINANCE_PUBLIC_DATA_HTTPS" if folder is None else "LOCAL_BINANCE_ARCHIVES_PROVENANCE_UNVERIFIED"
    histories, manifest = {}, {}
    with httpx.Client(timeout=20) as client:
        for symbol in SYMBOLS:
            rows, files = [], {}
            month = date(2024, 1, 1)
            while month < date(2025, 8, 1):
                label = month.strftime("%Y-%m")
                url = f"{ARCHIVE}/{symbol}/1h/{symbol}-1h-{label}.zip"
                check = archive_file(client, url + ".CHECKSUM", folder)
                part, sha = parse_archive(archive_file(client, url, folder), check.decode("ascii"), symbol, label)
                rows.extend(part)
                files[url] = sha
                month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
            check_development(rows, "60")
            histories[symbol] = rows
            manifest[symbol] = dict(files=files, hourly_sha256=digest(rows), bars=len(rows))
    return histories, dict(source=source, instruments=manifest)


async def bybit_history():
    api = Bybit()
    server = _server_time_ms(await api.get("/v5/market/time"))
    if DEV_END * 1000 > server:
        raise ValueError("History has not closed on Bybit")
    histories, manifest = {}, {}
    for symbol in SYMBOLS:
        rows, pages = [], []
        for start in range(START, DEV_END, 1000 * 3600):
            end = min(start + 1000 * 3600, DEV_END)
            params = dict(category="spot", symbol=symbol, interval="60", start=start * 1000,
                          end=end * 1000 - 1, limit=(end - start) // 3600)
            body = await api.get("/v5/market/kline", params)
            part = _parse_page(body, symbol, "60", end_ms=params["end"],
                               latest_closed_boundary_ms=DEV_END * 1000, limit=params["limit"])
            if len(part) != params["limit"]:
                raise ValueError("Incomplete Bybit history page")
            rows.extend(asdict(c) for c in reversed(part))
            pages.append(dict(params=params, raw_rows_sha256=digest(body["result"]["list"])))
        check_development(rows, "60")
        histories[symbol] = rows
        manifest[symbol] = dict(pages=pages, hourly_sha256=digest(rows), bars=len(rows))
    return histories, dict(source="BYBIT_V5_PUBLIC_HTTPS", instruments=manifest)
