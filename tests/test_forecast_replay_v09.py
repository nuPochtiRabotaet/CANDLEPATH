"""Historical REPLAY tests only. Synthetic series; no exchange or trading."""
from dataclasses import replace
import math
import random

import pytest

from moex_intelligence.crypto.forecast_baseline import (
    HistoricalVolatilityBaseline, ewma_price_envelope)
from moex_intelligence.crypto.forecast_evaluation import evaluate_historical_baseline
from moex_intelligence.crypto.market import Candle

STEP = 900
BASE = 1_760_000_400


def make_candles(count=1000, *, flat=False):
    assert BASE % STEP == 0
    rng = random.Random(271828)
    price = 100.0
    candles = []
    for i in range(count):
        if not flat:
            price *= math.exp(rng.gauss(0, .0015))
        candles.append(Candle(BASE+i*STEP, price, price*1.001, price*.999,
                              price, 4.0, True))
    return candles


def test_replay_scores_only_holdout_using_nonoverlapping_origins():
    rows = make_candles()
    report = evaluate_historical_baseline(rows, 'BTCUSDT', '15')
    assert report.status == 'EVALUATED'
    assert report.mode == 'HISTORICAL_REPLAY_NOT_LIVE'
    assert report.evaluation_start == rows[700].time
    assert report.origins >= 30 and report.skipped_origins == 0
    assert report.model_version == HistoricalVolatilityBaseline.version
    assert [s.horizon_candles for s in report.horizons] == [1,2,4,8]
    for s in report.horizons:
        assert s.observations == report.origins
        assert 0 <= s.empirical_coverage <= 1
        assert s.mean_absolute_error == s.random_walk_mae
        assert 0 < s.mean_band_width_pct < 20


def test_replay_calls_same_pure_model_as_live_engine(monkeypatch):
    # Compare first historical origin against mathematical live-model envelope
    # without mocking the real clock or manufacturing historical publications.
    from moex_intelligence.crypto import forecast_evaluation as ev
    rows = make_candles()
    seen = []
    original = ev.ewma_price_envelope

    def recording(closes, horizons, **kwargs):
        seen.append(tuple(closes))
        return original(closes, horizons, **kwargs)

    monkeypatch.setattr(ev, 'ewma_price_envelope', recording)
    report = ev.evaluate_historical_baseline(rows, 'BTCUSDT', '15')
    first_origin_index = 699
    assert len(seen) == report.origins
    assert seen[0] == tuple(c.close for c in rows[first_origin_index-119:first_origin_index+1])
    assert seen[0][-1] == rows[first_origin_index].close
    assert seen[0][-1] != rows[first_origin_index+1].close


def test_future_price_mutation_never_changes_first_origin_inputs(monkeypatch):
    from moex_intelligence.crypto import forecast_evaluation as ev
    rows = make_candles()
    first_inputs = []
    original = ev.ewma_price_envelope

    def capture(closes, horizons, **kwargs):
        if not first_inputs:
            first_inputs.append(tuple(closes))
        return original(closes, horizons, **kwargs)

    monkeypatch.setattr(ev, 'ewma_price_envelope', capture)
    ev.evaluate_historical_baseline(rows,'BTCUSDT','15')
    a = first_inputs.pop()
    mutated = [replace(c, open=c.open*2, high=c.high*2,
                       low=c.low*2, close=c.close*2) if i>=700 else c
               for i,c in enumerate(rows)]
    ev.evaluate_historical_baseline(mutated,'BTCUSDT','15')
    assert first_inputs.pop() == a


def test_flat_market_reports_coverage_without_inventing_predictive_skill():
    r = evaluate_historical_baseline(make_candles(flat=True),'ETHUSDT','15')
    assert r.status == 'EVALUATED'
    assert all(s.empirical_coverage == 1.0 and s.mean_absolute_error == 0
               and s.mean_band_width_pct == 0 for s in r.horizons)
    assert 'not actual past publications' in r.note


def test_insufficient_input_returns_explicit_not_enough_status():
    r = evaluate_historical_baseline(make_candles(100),'BTCUSDT','15')
    assert r.status == 'INSUFFICIENT'
    assert r.origins == 0 and not r.horizons
    assert r.evaluation_start is None


def test_trailing_open_candle_excluded():
    rows = make_candles()
    last=rows[-1]
    partial=Candle(last.time+STEP,999,1000,998,999,5,False)
    r1=evaluate_historical_baseline(rows,'BTCUSDT','15')
    r2=evaluate_historical_baseline(rows+[partial],'BTCUSDT','15')
    assert r1 == r2


@pytest.mark.parametrize('change', [
    lambda r: r[:400]+r[401:],
    lambda r: r[:400]+[r[400]]+r[400:],
    lambda r: r[:400]+list(reversed(r[400:403]))+r[403:],
    lambda r: r[:400]+[replace(r[400],closed=False)]+r[401:],
    lambda r: r[:400]+[replace(r[400],time=r[400].time+1)]+r[401:],
])
def test_rejects_gaps_duplicates_disorder_partial_holes(change):
    with pytest.raises(ValueError):
        evaluate_historical_baseline(change(make_candles()),'BTCUSDT','15')


def test_malformed_configuration_rejected_and_never_publishes():
    rows=make_candles()
    for kwargs in ({'holdout_fraction':.75},{'holdout_fraction':float('nan')},
                   {'stride':1},{'stride':True},{'min_required_origins':0}):
        with pytest.raises(ValueError):
            evaluate_historical_baseline(rows,'BTCUSDT','15',**kwargs)
    with pytest.raises(ValueError):
        evaluate_historical_baseline(rows,'DOGEUSDT','15')


def test_price_envelope_mirrors_live_ewma_formula_exactly():
    closes=[c.close for c in make_candles(120)]
    returns=[math.log(b)-math.log(a) for a,b in zip(closes,closes[1:])]
    weights=[.94**i for i in range(len(returns))]
    var=sum(w*r*r for w,r in zip(weights,reversed(returns)))/sum(weights)
    observed=ewma_price_envelope(closes,(1,2,4,8))
    expected=tuple((closes[-1]*math.exp(-1.2815515655446004*math.sqrt(var)*math.sqrt(h)),
                    closes[-1],
                    closes[-1]*math.exp(1.2815515655446004*math.sqrt(var)*math.sqrt(h)))
                   for h in (1,2,4,8))
    assert observed == expected
    assert ewma_price_envelope([100.0]*90,(1,4)) == ((100.0,100.0,100.0),)*2


def test_cli_is_readonly_and_never_creates_historical_live_publications(tmp_path):
    import hashlib
    import json
    import subprocess
    import sys
    from pathlib import Path
    from moex_intelligence.crypto.storage import Store

    dbpath = tmp_path / 'existing.sqlite3'
    store = Store(dbpath)
    store.save_candles('BTCUSDT','15',make_candles())
    before = hashlib.sha256(dbpath.read_bytes()).hexdigest()
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root/'scripts/evaluate_forecast_v09.py'),
                             '--database',str(dbpath),'--symbol','BTCUSDT','--timeframe','15'],
                            capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['mode'] == 'HISTORICAL_REPLAY_NOT_LIVE'
    assert report['status'] == 'EVALUATED'
    assert hashlib.sha256(dbpath.read_bytes()).hexdigest() == before
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM forecasts').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM forecast_outcomes').fetchone()[0] == 0


def test_cli_missing_database_does_not_create_it(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    path=tmp_path/'absent.sqlite3'
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/evaluate_forecast_v09.py'),
                           '--database',str(path),'--symbol','BTCUSDT','--timeframe','15'],
                          capture_output=True,text=True,timeout=15)
    assert result.returncode == 2
    assert not path.exists()


def test_refactor_keeps_live_projection_and_identity_unchanged(monkeypatch):
    rows=make_candles(120)
    event_time=rows[-1].time+STEP+50
    monkeypatch.setattr('moex_intelligence.crypto.forecast_baseline.time.time',lambda: event_time)
    forecast=HistoricalVolatilityBaseline().forecast(rows,'SOLUSDT','15',event_time)
    assert forecast.status=='EXPERIMENTAL'
    assert forecast.model_version=='rw-ewma80-experimental-v1'
    envelope=ewma_price_envelope([c.close for c in rows],(1,2,4,8))
    assert [(p.lower,p.median,p.upper) for p in forecast.points]==[
        tuple(str(x) for x in quantile) for quantile in envelope]
    assert [p.target_time for p in forecast.points]==[
        rows[-1].time+STEP*(h+1) for h in (1,2,4,8)]
