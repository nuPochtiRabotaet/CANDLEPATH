"""v0.9 replay round-two regressions. Fixtures are SYNTHETIC, not market claims."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import pytest

from moex_intelligence.crypto.forecast_evaluation import evaluate_historical_baseline
from moex_intelligence.crypto.forecast_baseline import HistoricalVolatilityBaseline, ewma_price_envelope
from moex_intelligence.crypto.market import Candle, seconds
from moex_intelligence.crypto.storage import Store

STEP=900


def series(count=1000,step=STEP):
    start=int(time.time()//step)*step-(count+10)*step
    return [Candle(start+i*step,100+i*.02,101+i*.02,
                   99+i*.02,100+i*.02,5,True) for i in range(count)]


def test_01_extreme_price_jump_keeps_json_valid_and_tail_counted():
    rows=series()
    rows[700]=replace(rows[700],open=1e-320,high=1e-320,low=1e-320,close=1e-320)
    report=evaluate_historical_baseline(rows,'BTCUSDT','15')
    score=report.horizons[0]
    assert score.unbounded_percentage_errors>=1
    assert score.mean_absolute_percentage_error is None
    assert score.observations>0
    json.dumps(report.as_dict(),allow_nan=False)


def test_02_oversized_candle_integer_returns_validation_error():
    rows=[vars(r).copy() for r in series()]
    rows[699]['close']=10**400
    with pytest.raises(ValueError,match='Invalid candle close'):
        evaluate_historical_baseline(rows,'BTCUSDT','15')


def test_03_oversized_live_asof_returns_unavailable_not_overflow():
    f=HistoricalVolatilityBaseline().forecast(series(100),'BTCUSDT','15',10**400)
    assert f.status=='UNAVAILABLE' and not f.points


def test_04_oversized_live_price_returns_unavailable_not_overflow():
    rows=[vars(r).copy() for r in series(100)]
    rows[-1]['close']=10**400
    f=HistoricalVolatilityBaseline().forecast(rows,'BTCUSDT','15',time.time())
    assert f.status=='UNAVAILABLE' and not f.points


def test_05_pure_envelope_fails_closed_on_oversized_int():
    with pytest.raises(ValueError,match='Invalid observed price'):
        ewma_price_envelope([100.,10**400],(1,))


def test_06_bad_ohlc_high_is_rejected():
    rows=[vars(r).copy() for r in series()]
    rows[699]['high']=rows[699]['close']-1
    with pytest.raises(ValueError,match='Inconsistent OHLCV'):
        evaluate_historical_baseline(rows,'BTCUSDT','15')


def test_07_bad_volume_is_rejected():
    rows=[vars(r).copy() for r in series()]
    rows[699]['volume']=float('nan')
    with pytest.raises(ValueError,match='Inconsistent OHLCV'):
        evaluate_historical_baseline(rows,'BTCUSDT','15')


def test_08_future_closed_candle_is_rejected():
    rows=[vars(r).copy() for r in series()]
    rows[-1]['time']=int(time.time()//STEP)*STEP+STEP
    with pytest.raises(ValueError,match='Future candle'):
        evaluate_historical_baseline(rows,'BTCUSDT','15')


def test_09_random_walk_comparator_stays_identical():
    report=evaluate_historical_baseline(series(),'BTCUSDT','15')
    assert report.status=='EVALUATED' and report.origins>=30
    assert all(s.random_walk_mae==s.mean_absolute_error for s in report.horizons)
    assert all(s.mean_absolute_percentage_error is not None for s in report.horizons)


def test_10_offline_cli_cannot_publish_or_modify_existing_db(tmp_path):
    db=tmp_path/'original.sqlite3';store=Store(db)
    store.save_candles('BTCUSDT','15',series())
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    root=Path(__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,str(root/'scripts/evaluate_forecast_v09.py'),
                        '--database',str(db),'--symbol','BTCUSDT','--timeframe','15'],
                       capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stderr
    assert json.loads(run.stdout)['mode']=='HISTORICAL_REPLAY_NOT_LIVE'
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    with store.connect() as sql:
        assert sql.execute('SELECT COUNT(*) FROM forecasts').fetchone()[0]==0
        assert sql.execute('SELECT COUNT(*) FROM forecast_outcomes').fetchone()[0]==0


@pytest.mark.parametrize('symbol,interval',[('BTCUSDT','1'),('ETHUSDT','60'),('SOLUSDT','D')])
def test_11_assets_and_timeframes(symbol,interval):
    report=evaluate_historical_baseline(series(step=seconds(interval)),symbol,interval)
    assert report.status=='EVALUATED' and len(report.horizons)==4
    assert all(s.observations==report.origins for s in report.horizons)


def test_12_missing_ohlcv_is_rejected():
    rows=[vars(r).copy() for r in series()]
    rows[-3].pop('volume')
    with pytest.raises(ValueError,match='Missing or invalid OHLCV'):
        evaluate_historical_baseline(rows,'BTCUSDT','15')
