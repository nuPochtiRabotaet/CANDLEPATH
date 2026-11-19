"""Explicitly SYNTHETIC observations. These cases never estimate market returns."""
import asyncio
import calendar
import hashlib
import io
import math
import time
import zipfile
from datetime import date
from decimal import Decimal as D

import pytest

from scripts import run_trend_1h4h as runner
from moex_intelligence.crypto import trend_history as data
from moex_intelligence.crypto.analysis import indicators
from moex_intelligence.crypto.costs import CostModel, estimate
from moex_intelligence.crypto.paper_path_research import _quote_at
from moex_intelligence.crypto.trend_research import (
    CAPITAL, HYPOTHESES, daily_regimes, fold_dates, fold_windows, passive_daily, rules_for, signals)


def synthetic_bar(i, scale=1):
    def price(j):
        return scale * (30000 + 0.12 * j + 900 * math.sin(j / 57)
                        + 440 * math.sin(j / 17) + 90 * math.sin(j / 3))
    opening, close = price(i - 1), price(i)
    return dict(time=data.START + i * 3600, open=opening, high=max(opening, close) + scale * 4,
                low=min(opening, close) - scale * 4, close=close, volume=40., closed=True)


@pytest.fixture(scope="module")
def hourly():
    return [synthetic_bar(i) for i in range(576 * 24)]


def archive(symbol, month, corrupt=None):
    first = date.fromisoformat(month + "-01")
    start = calendar.timegm(first.timetuple())
    unit = 1000 if first.year < 2025 else 1_000_000
    lines = []
    for i in range(calendar.monthrange(first.year, first.month)[1] * 24):
        stamp = start + i * 3600
        b = synthetic_bar((stamp - data.START) // 3600, .06 if symbol == "ETHUSDT" else 1)
        fields = [stamp * unit, b["open"], b["high"], b["low"], b["close"], b["volume"],
                  (stamp + 3600) * unit - 1, 100, 5, 50, 10, 0]
        if i == 8 and corrupt:
            fields[corrupt[0]] = corrupt[1]
        lines.append(",".join(map(str, fields)))
    name = f"{symbol}-1h-{month}"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name + ".csv", "\n".join(lines))
    raw = stream.getvalue()
    return name + ".zip", raw, hashlib.sha256(raw).hexdigest() + "  " + name + ".zip"


@pytest.mark.parametrize("month", ["2024-02", "2025-07"])
def test_archive_checksum_units_full_utc_grid(month):
    _, raw, checksum = archive("BTCUSDT", month)
    bars, sha = data.parse_archive(raw, checksum, "BTCUSDT", month)
    assert sha == checksum.split()[0] and len(bars) in (29 * 24, 31 * 24)
    assert bars[-1]["time"] - bars[0]["time"] == (len(bars) - 1) * 3600
    with pytest.raises(ValueError, match="checksum"):
        data.parse_archive(raw + b"x", checksum, "BTCUSDT", month)
    with pytest.raises(ValueError, match="checksum"):
        data.parse_archive(raw, checksum, "ETHUSDT", month)


@pytest.mark.parametrize("field,value", [(0, 0), (6, 1), (4, "nan"), (5, -1), (2, 1)])
def test_corrupt_publisher_rows_fail_even_with_matching_hash(field, value):
    _, raw, checksum = archive("BTCUSDT", "2025-07", (field, value))
    with pytest.raises(ValueError):
        data.parse_archive(raw, checksum, "BTCUSDT", "2025-07")


def test_aggregation_cutoff_and_bad_inputs(hourly):
    bars = data.four_hour(hourly)
    assert len(bars) == 576 * 6 and bars[-1]["time"] + 14400 == data.DEV_END
    first = hourly[:4]
    assert bars[0] == dict(time=data.START, open=first[0]["open"], close=first[-1]["close"],
                           high=max(x["high"] for x in first), low=min(x["low"] for x in first),
                           volume=sum(x["volume"] for x in first), closed=True)
    for rows in (hourly[1:], hourly + [hourly[-1]], hourly[:1] + hourly[:-1],
                 [dict(hourly[0], closed=False)] + hourly[1:]):
        with pytest.raises(ValueError):
            data.four_hour(rows)


@pytest.mark.parametrize("hypothesis", HYPOTHESES)
def test_confirmed_prefix_invariance_and_exact_rule(hourly, hypothesis):
    rows = hourly[:1800]
    rules = rules_for("BTCUSDT")
    found = signals(rows, "60", hypothesis, rules)
    assert {s["type"] for s in found} == {"BUY", "EXIT"}
    for length in (190, 674, 1234):
        assert signals(rows[:length], "60", hypothesis, rules) == [
            s for s in found if s["timestamp"] <= rows[length]["time"]]
    frame = indicators(rows)
    for s in found:
        i = (s["candle_time"] - data.START) // 3600
        assert s["timestamp"] == rows[i + 1]["time"] and s["reference_price"] == rows[i]["close"]
        if s["type"] == "BUY":
            prev, curr = frame.iloc[i - 1], frame.iloc[i]
            assert curr.direction > 0 and curr.ema_fast > curr.ema_slow and curr.adx >= 20
            prior_bull = prev.direction > 0 and prev.ema_fast > prev.ema_slow and prev.adx >= 20
            if hypothesis == "EMA_PULLBACK":
                assert prior_bull and prev.close <= prev.ema_fast and curr.close > curr.ema_fast
            else:
                assert not prior_bull
            levels = s["risk_estimates"]
            assert rules.levels_on_tick(levels["stop"], levels["target"])
            assert D(levels["stop"]) < D(str(curr.close)) < D(levels["target"])
    with pytest.raises(ValueError, match="closed"):
        signals(rows + [dict(rows[-1], closed=False)], "60", hypothesis, rules)


def test_common_utc_folds_embargo_and_protected_interval(monkeypatch, tmp_path):
    data.check_calendar()
    dates = fold_dates()
    assert data.SEALED_END - data.DEV_END == 144 * data.DAY
    for tf in ("60", "240"):
        step = int(tf) * 60
        for info, (n, start, end) in zip(dates, fold_windows(tf), strict=True):
            assert data.START + (start + 1) * step == info["first_open"]
            assert data.START + end * step == info["end_exclusive"] <= data.DEV_END
            assert info["end_exclusive"] - info["first_open"] == 177 * data.DAY
            assert info["first_open"] - info["purge_start"] >= 17 * step
            if n > 1:
                assert dates[n - 2]["end_exclusive"] == info["purge_start"]
    monkeypatch.setattr(data, "ROOT", tmp_path)
    guard = tmp_path / "docs/research/original_holdout_guard.json"
    guard.parent.mkdir(parents=True)
    guard.write_text('{"sealed_interval":[%d,%d]}' % (data.START - 1, data.START + 1))
    with pytest.raises(ValueError, match="overlaps"):
        data.check_calendar()


def test_bybit_backfill_never_requests_reserved_hour(monkeypatch):
    requests = []
    async def mock_get(self, path, params=None):
        if path == "/v5/market/time":
            return dict(time=int(time.time() * 1000), retCode=0)
        assert path == "/v5/market/kline"
        assert data.START * 1000 <= params["start"] < params["end"] < data.DEV_END * 1000
        requests.append(params)
        stamps = range(params["start"], params["end"] + 1, 3600000)
        series = [[str(stamp), "100", "101", "99", "100", "80"] for stamp in reversed(stamps)]
        return dict(retCode=0, result=dict(category="spot", symbol=params["symbol"], list=series))
    monkeypatch.setattr(data.Bybit, "get", mock_get)
    rows, meta = asyncio.run(data.bybit_history())
    assert len(requests) == 2 * 14
    assert all(len(rows[s]) == 576 * 24 for s in data.SYMBOLS)
    assert all(len(meta["instruments"][s]["pages"]) == 14 for s in data.SYMBOLS)


def test_passive_flat_price_charges_round_trip_once(hourly):
    rules, model = rules_for("BTCUSDT"), CostModel()
    rows = [dict(r, open=1000., close=1000.) for r in hourly[:48]]
    fold = dict(fold=1, start_index=-1, end_exclusive=48)
    actual = list(passive_daily(rows, dict(folds=[fold], timeframe="60"), D(".25"), model, 4, rules).values())
    quote = _quote_at(1000, 4)
    unit = estimate("BUY", 1, quote, model)
    qty = ((CAPITAL / 4 / -unit.cash_delta) // rules.step) * rules.step
    expected = estimate("SELL", qty, quote, model).cash_delta + estimate("BUY", qty, quote, model).cash_delta
    assert actual == [expected, 0] and expected < 0


def test_missing_data_and_bad_checksum_never_score_or_mix_venues(monkeypatch, tmp_path):
    no_network = lambda *args: pytest.fail("unexpected secondary request")
    monkeypatch.setattr(runner, "bybit_history", no_network)
    report = runner.run(tmp_path)
    assert report["status"] == "NOT EVALUABLE" and report["paths"] == {}
    def corrupted(*args):
        raise ValueError("bad checksum")
    monkeypatch.setattr(runner, "binance_history", corrupted)
    assert runner.run()["error"] == "bad checksum"


def test_complete_offline_study_on_synthetic_archives_only(tmp_path, monkeypatch):
    """All eight paths, both costs and full inference, with NO market evidence."""
    data_dir = tmp_path / "financial-data"
    monkeypatch.setenv("MOEX_DATA_DIR", str(data_dir))
    for symbol in data.SYMBOLS:
        for y, months in [(2024, range(1, 13)), (2025, range(1, 8))]:
            for month in months:
                name, raw, checksum = archive(symbol, f"{y}-{month:02d}")
                (tmp_path / name).write_bytes(raw)
                (tmp_path / (name + ".CHECKSUM")).write_text(checksum)
    report = runner.run(tmp_path)
    assert report["status"] == "EXPLORATORY" and len(report["paths"]) == 8
    assert runner.run(tmp_path) == report
    assert not data_dir.exists() and not report["sealed_evaluated"] and not report["validated"]
    stats = report["statistics"]
    assert stats["observations"] == 531 and len(stats["columns"]) == 16
    assert [t["block"] for t in stats["tests"]] == [3, 7, 14]
    assert all(len(t["lower"]) == len(t["adjusted_p"]) == 16 for t in stats["tests"])
    for scenarios in report["paths"].values():
        assert scenarios["decision"] == "NO TRADE / INSUFFICIENT EVIDENCE"
        assert not scenarios["gates"]["provenance"]
        for label in ("base", "double"):
            r = scenarios[label]
            assert r["trades"] > 0 and sum(f["trade_count"] for f in r["folds"]) == r["trades"]
            costs = {k: D(v) for k, v in r["modeled_costs_usdt"].items()}
            gross = costs.pop("gross_pnl")
            assert abs(gross - sum(costs.values()) - D(r["net_pnl"])) < D("1e-8")
            regimes = r["regime_at_day_open"].values()
            assert sum(g["days"] for g in regimes) == 531
            assert abs(sum(D(g["net_usdt"]) for g in regimes) - D(r["net_pnl"])) < D("1e-8")
            assert r["benchmarks_pct"]["USDT"] == "0"
            assert all("HOLD_25" in f["benchmarks_pct"] for f in r["folds"])


def test_day_regime_known_at_midnight_before_first_open(hourly):
    labels = daily_regimes(hourly[:1000], "60")
    cutoff = hourly[720]["time"]
    assert cutoff % data.DAY == 0
    prefix = daily_regimes(hourly[:720], "60")
    assert prefix[cutoff // data.DAY] == labels[cutoff // data.DAY]
    assert max(prefix) == cutoff // data.DAY

def test_no_fabricated_scores_on_dual_source_outage(monkeypatch):
    def blocked(_):
        raise data.SourceUnavailable("archive unavailable")
    async def unavailable():
        raise ValueError("Bybit unavailable")
    monkeypatch.setattr(runner, "binance_history", blocked)
    monkeypatch.setattr(runner, "bybit_history", unavailable)
    report = runner.run()
    assert (report["archive_error"], report["error"]) == ("archive unavailable", "Bybit unavailable")
    assert report["decision"] == "NO TRADE / INSUFFICIENT EVIDENCE"
    assert not report["paths"] and "statistics" not in report
