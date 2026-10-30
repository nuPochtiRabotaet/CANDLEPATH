"""Cross-language mathematical parity, without exchange credentials or trades.

Uses the real Python Forecast output as JS chart input rather than independently
inventing chart numbers. All candles are synthetic and time-causally closed.
"""
from dataclasses import asdict
from decimal import Decimal
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from moex_intelligence.crypto.forecast_baseline import HistoricalVolatilityBaseline
from moex_intelligence.crypto.market import Candle

NODE = shutil.which('node')
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_v09_forecast_geometry.js'
STEP = 900


def scene(symbol='BTCUSDT'):
    now=time.time()
    boundary=int(now//STEP)*STEP
    candles=[]
    for i in range(120):
        price=100+(.06*i)+.3*math.sin(i/9)
        t=boundary-(120-i)*STEP
        candles.append(Candle(t,price,price+.2,price-.2,price,3.,True))
    forecast=HistoricalVolatilityBaseline().forecast(candles,symbol,'15',now)
    assert forecast.status=='EXPERIMENTAL'
    payload={'symbol':symbol,'interval':'15',
             'readiness':{'forecast_feed_ready':True,'candle_data_fresh':True},
             'candles':[asdict(c) for c in candles],
             'intelligence':{'forecast':asdict(forecast)}}
    return forecast,payload


def browser_projection(payload):
    if NODE is None:
        pytest.skip('Node.js needed for Python→JS chart contract test')
    result=subprocess.run([NODE,str(SCRIPT),'--project-json'],input=json.dumps(payload),
                          text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('symbol',['BTCUSDT','ETHUSDT','SOLUSDT'])
def test_real_python_model_renders_at_exact_future_closes(symbol):
    forecast,payload=scene(symbol)
    projected=browser_projection(payload)
    assert projected is not None
    expected=[int(forecast.data_as_of)]+[p.target_time for p in forecast.points]
    assert [p['time'] for p in projected['line']]==expected
    assert [p['time'] for p in projected['profile']]==expected
    assert projected['grid']==[
        {'time':int(forecast.data_as_of)+STEP*i} for i in range(1,9)]
    assert projected['line'][0]['value']==pytest.approx(payload['candles'][-1]['close'])
    for orig,paint in zip(forecast.points,projected['profile'][1:]):
        assert Decimal(str(paint['lower']))==Decimal(orig.lower)
        assert Decimal(str(paint['median']))==Decimal(orig.median)
        assert Decimal(str(paint['upper']))==Decimal(orig.upper)
        assert paint['lower']<=paint['median']<=paint['upper']


def test_partial_candle_never_changes_projection():
    forecast,payload=scene()
    initial=browser_projection(payload)
    latest=payload['candles'][-1]['time']+STEP
    payload['candles'].append({'time':latest,'open':9000.,'high':10000.,'low':8000.,
                                'close':9999.,'volume':1.,'closed':False})
    assert browser_projection(payload)==initial
    assert initial['line'][0]['time']==forecast.data_as_of


@pytest.mark.parametrize('change',[
    lambda d: d['intelligence']['forecast'].__setitem__('data_as_of',
                                                        d['intelligence']['forecast']['data_as_of']-STEP),
    lambda d: d['intelligence']['forecast']['points'][0].__setitem__('lower','1e999'),
    lambda d: d['intelligence']['forecast']['points'][0].__setitem__('median','0'),
    lambda d: d['readiness'].__setitem__('candle_data_fresh',False),
])
def test_corrupt_python_output_cannot_partially_render(change):
    _,payload=scene()
    change(payload)
    assert browser_projection(payload) is None
