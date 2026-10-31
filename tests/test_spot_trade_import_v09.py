"""Strict offline SPOT trade conversion and causal research integration tests."""
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moex_intelligence.crypto.offline_ohlcv import read_local_ohlcv
from moex_intelligence.crypto.spot_trade_import import (
    read_spot_trade_minutes, segment_spot_trade_minutes, write_spot_candle_segments)


def utc_millis(iso):
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


def write_trades(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        out = csv.writer(stream)
        out.writerow(["id", "timestamp", "price", "volume", "side", "rpi"])
        out.writerows(rows)
    return path


def sample_rows(start, length, first_id=1):
    return [(first_id + n, start + n * 60000, str(80000 + n % 17),
             "0.0025", "Buy" if n % 2 else "Sell", "0") for n in range(length)]


def test_same_millisecond_trade_order_and_base_volume(tmp_path):
    start = utc_millis("2026-10-25T00:00:00")
    rows = sample_rows(start, 15)
    # Multiple executions at the exact same millisecond remain distinct:
    rows.insert(1, (1001, start, "80010", "1.25", "Buy", "0"))
    rows[0] = (1000, start, "80000", "0.0025", "Sell", "0")
    for i in range(2, len(rows)):
        rows[i] = (1000 + i, *rows[i][1:])
    path = write_trades(tmp_path/"BTCUSDT_2026-10-25.csv", rows)
    minutes, sources = read_spot_trade_minutes([path], "BTCUSDT")
    assert sources[0]["trades"] == 16
    assert sources[0]["market_verification"] is False
    first = minutes[start]
    assert first[0] == Decimal("80000")
    assert first[1] == Decimal("80010")
    assert first[3] == Decimal("80010")
    assert first[4] == Decimal("1.2525")
    chunks = segment_spot_trade_minutes(minutes, "BTCUSDT", "15")
    assert len(chunks) == 1 and len(chunks[0]) == 1
    dest = tmp_path/"export"
    emitted = write_spot_candle_segments(chunks, dest, "BTCUSDT", "15")
    dataset = read_local_ohlcv(emitted[0], "BTCUSDT", "15")
    assert dataset.row_count == 1
    assert dataset.candles[0].volume == pytest.approx(1.2875)
    assert dataset.candles[0].high == 80014


def test_gaps_split_minutes_and_discard_partial_15m(tmp_path):
    start = utc_millis("2026-10-25T00:00:00")
    rows = sample_rows(start, 31)
    rows.pop(10)  # one genuinely missing minute inside the first 15m bin
    rows = [(i+1,*row[1:]) for i, row in enumerate(rows)]
    path = write_trades(tmp_path/"BTCUSDT_2026-10-25.csv", rows)
    minutes, _ = read_spot_trade_minutes([path], "BTCUSDT")
    minute_groups = segment_spot_trade_minutes(minutes, "BTCUSDT", "1")
    assert [len(g) for g in minute_groups] == [10, 20]
    fifteen = segment_spot_trade_minutes(minutes, "BTCUSDT", "15")
    assert len(fifteen) == 1 and len(fifteen[0]) == 1
    assert fifteen[0][0][0] == start + 15 * 60000
    # Final 1-minute partial bin (at minute 30) is excluded from 15m output.


def test_absent_calendar_day_is_never_synthesized(tmp_path):
    a = utc_millis("2026-10-27T23:58:00")
    b = utc_millis("2026-10-29T00:00:00")
    paths = [
        write_trades(tmp_path/"BTCUSDT_2026-10-27.csv", sample_rows(a, 2)),
        write_trades(tmp_path/"BTCUSDT_2026-10-29.csv", sample_rows(b, 2))]
    minutes, _ = read_spot_trade_minutes(paths[::-1], "BTCUSDT")
    groups = segment_spot_trade_minutes(minutes, "BTCUSDT", "1")
    assert [len(g) for g in groups] == [2, 2]
    assert groups[1][0][0] == b
    out = write_spot_candle_segments(groups, tmp_path/"out", "BTCUSDT", "1")
    assert len(out) == 2
    assert all(read_local_ohlcv(p, "BTCUSDT", "1").row_count == 2 for p in out)


@pytest.mark.parametrize("mutation", [
    lambda r: r.__setitem__(1,(r[0][0],*r[1][1:])),   # repeated ID
    lambda r: r.__setitem__(1,(999,*r[1][1:])),       # omitted ID
    lambda r: r.__setitem__(1,(r[1][0],r[0][1]-1,*r[1][2:])), # reversed time
    lambda r: r.__setitem__(1,(r[1][0],r[1][1],"NaN",*r[1][3:])),
    lambda r: r.__setitem__(1,(r[1][0],r[1][1],r[1][2],"-2",*r[1][4:])),
    lambda r: r.__setitem__(1,(*r[1][:-1],"42")),  # invalid RPI
])
def test_fail_closed_on_broken_trades(tmp_path, mutation):
    start = utc_millis("2026-10-25T00:00:00")
    rows = sample_rows(start, 3)
    mutation(rows)
    path = write_trades(tmp_path/"BTCUSDT_2026-10-25.csv", rows)
    with pytest.raises(ValueError):
        read_spot_trade_minutes([path], "BTCUSDT")
    assert not list(tmp_path.glob("*_1m_*.csv"))


def test_duplicates_and_wrong_symbol_rejected(tmp_path):
    path = write_trades(tmp_path/"BTCUSDT_2026-10-25.csv",
                        sample_rows(utc_millis("2026-10-25T00:00:00"), 2))
    with pytest.raises(ValueError, match="Duplicate input"):
        read_spot_trade_minutes([path, path], "BTCUSDT")
    with pytest.raises(ValueError, match="Expected"):
        read_spot_trade_minutes([path], "ETHUSDT")


def test_existing_output_never_overwritten(tmp_path):
    path = write_trades(tmp_path/"BTCUSDT_2026-10-25.csv",
                        sample_rows(utc_millis("2026-10-25T00:00:00"), 15))
    minutes, _ = read_spot_trade_minutes([path], "BTCUSDT")
    groups = segment_spot_trade_minutes(minutes, "BTCUSDT", "15")
    emitted = write_spot_candle_segments(groups, tmp_path/"out", "BTCUSDT", "15")
    fingerprint = hashlib.sha256(emitted[0].read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        write_spot_candle_segments(groups, tmp_path/"out", "BTCUSDT", "15")
    assert hashlib.sha256(emitted[0].read_bytes()).hexdigest() == fingerprint


def test_cli_uses_actual_walkforward_engine_and_seals_final_holdout(tmp_path):
    start = utc_millis("2026-10-25T00:00:00")
    first = write_trades(tmp_path/"BTCUSDT_2026-10-25.csv",
                         sample_rows(start, 1440))
    second = write_trades(tmp_path/"BTCUSDT_2026-10-26.csv",
                          sample_rows(start + 1440 * 60000, 160, first_id=9000))
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (first, second)]
    out = tmp_path/"research"
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root/"scripts/evaluate_spot_trades_csv_v09.py"),
               "--input", str(first), str(second), "--symbol", "BTCUSDT",
               "--timeframes", "1", "15", "--output-dir", str(out),
               "--evaluate"]
    run = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["source"] == "USER_SUPPLIED_TRADE_CSV_UNVERIFIED"
    assert report["no_orders"] and report["no_api_calls"]
    outputs = {r["timeframe"]:r for r in report["outputs"]}
    one = outputs["1"]
    assert one["candles"] == 1600
    assert one["research_status"] == "EVALUATED_DEVELOPMENT_ONLY"
    assert one["final_status"] == "SEALED_UNSCORED"
    assert one["development"]["sealed_final"]["evaluated"] is False
    assert one["development"]["folds_evaluated"] == 3
    assert outputs["15"]["research_status"] in ("INSUFFICIENT_HISTORY", "INSUFFICIENT")
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in (first, second)] == hashes
    rerun = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert rerun.returncode == 2   # exclusive create, no silent overwrite
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in (first, second)] == hashes
