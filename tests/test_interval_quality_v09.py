"""Five-check acceptance tests for v0.9 interval-quality diagnostics.

Only synthetic, chronologically ordered candles are used. No exchange orders,
live predictions, or retrospective ForecastHistory records are created.
"""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import pytest

from moex_intelligence.crypto import forecast_evaluation as evaluation
from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.storage import Store

STEP = 900


def candles(count=1000, price=100.0):
    start = int(time.time() // STEP)*STEP - (count + 8)*STEP
    return [Candle(start + i*STEP, price, price + 1, price - 1, price, 10, True)
            for i in range(count)]


def check_finite_or_null(report):
    # Rejects JavaScript-invalid NaN and Infinity values in JSON output.
    data=report.as_dict()
    assert json.loads(json.dumps(data, allow_nan=False)) == json.loads(json.dumps(data))
    return data


def test_check_1_coverage_and_tail_counts_reconcile():
    series = candles()
    result = evaluation.evaluate_historical_baseline(series, 'BTCUSDT', '15')
    assert result.status == 'EVALUATED'
    for score in result.horizons:
        assert score.observations == result.origins >= 30
        inside = round(score.empirical_coverage * score.observations)
        assert score.below_interval + score.above_interval + inside == score.observations
        assert score.calibration_gap_percentage_points == pytest.approx(
            100*(score.empirical_coverage-score.nominal_coverage))
        assert score.mean_interval_score_pct >= score.mean_band_width_pct
        assert score.mean_interval_score_pct >= 0


def test_check_2_flat_market_has_zero_interval_score_but_not_validated():
    result = evaluation.evaluate_historical_baseline(candles(),'ETHUSDT','15')
    assert result.status == 'EVALUATED'  # sample size, NOT certified calibration
    assert 'does not establish' in result.note
    for score in result.horizons:
        assert score.empirical_coverage == 1
        assert score.below_interval == score.above_interval == 0
        assert score.mean_band_width_pct == 0
        assert score.mean_interval_score_pct == 0
        assert score.calibration_gap_percentage_points == pytest.approx(20)
    check_finite_or_null(result)


def test_check_3_winkler_exact_width_and_miss_penalty(monkeypatch):
    """Nominal central 80%: score width + 10 times outside miss distance."""
    def fixed_interval(past, horizons, **_kwargs):
        return [(99.0, 100.0, 101.0) for _h in horizons]
    monkeypatch.setattr(evaluation, 'ewma_price_envelope', fixed_interval)

    inside=evaluation.evaluate_historical_baseline(candles(price=100),'BTCUSDT','15')
    above=evaluation.evaluate_historical_baseline(candles(price=103),'BTCUSDT','15')
    below=evaluation.evaluate_historical_baseline(candles(price=97),'BTCUSDT','15')
    for a, b, c in zip(inside.horizons, above.horizons, below.horizons):
        assert a.mean_band_width_pct == pytest.approx(2)
        assert a.mean_interval_score_pct == pytest.approx(2)  # within interval
        assert b.above_interval == b.observations
        assert b.below_interval == 0
        assert b.empirical_coverage == 0
        assert b.mean_interval_score_pct == pytest.approx(22) # 2 + 10*(103-101)
        assert c.below_interval == c.observations
        assert c.above_interval == 0
        assert c.mean_interval_score_pct == pytest.approx(22) # 2 + 10*(99-97)


def test_check_4_score_uses_only_future_outcomes_not_future_model_inputs(monkeypatch):
    recorded = []
    original = evaluation.ewma_price_envelope
    def capture(past, horizons, **kwargs):
        recorded.append(tuple(past))
        return original(past, horizons, **kwargs)
    monkeypatch.setattr(evaluation, 'ewma_price_envelope', capture)

    baseline = candles()
    evaluation.evaluate_historical_baseline(baseline,'BTCUSDT','15')
    first = recorded[0]
    recorded.clear()
    altered = baseline[:700] + [
        replace(c, open=102, high=103, low=101, close=102)
        for c in baseline[700:]]
    result = evaluation.evaluate_historical_baseline(altered,'BTCUSDT','15')
    assert recorded[0] == first  # first origin is index 699; no leaked candle >= 700
    assert result.horizons[0].above_interval >= 0
    assert result.horizons[0].mean_interval_score_pct > 0


def test_check_5_extreme_legal_price_keeps_json_valid():
    series = candles()
    series[700] = replace(series[700], open=1e-320,high=1e-320,
                          low=1e-320,close=1e-320)
    result = evaluation.evaluate_historical_baseline(series,'SOLUSDT','15')
    report = check_finite_or_null(result)
    assert report['horizons'][0]['unbounded_percentage_errors'] > 0
    for horizon in report['horizons']:
        assert not isinstance(horizon['mean_interval_score_pct'], str)
        assert horizon['observations'] > 0


def test_check_6_cli_readonly_includes_scores_and_never_publishes(tmp_path):
    dbpath = tmp_path / 'market.sqlite3'
    store = Store(dbpath)
    store.save_candles('BTCUSDT','15',candles())
    before = hashlib.sha256(dbpath.read_bytes()).hexdigest()
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [sys.executable,str(root/'scripts/evaluate_forecast_v09.py'),
         '--database',str(dbpath),'--symbol','BTCUSDT','--timeframe','15'],
        capture_output=True,text=True,timeout=20)
    assert run.returncode == 0,run.stderr
    report = json.loads(run.stdout)
    for row in report['horizons']:
        assert row['mean_interval_score_pct'] == pytest.approx(0)
        assert row['calibration_gap_percentage_points'] == pytest.approx(20)
        assert row['below_interval'] == row['above_interval'] == 0
    assert hashlib.sha256(dbpath.read_bytes()).hexdigest() == before
    with store.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM forecasts').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM forecast_outcomes').fetchone()[0] == 0
