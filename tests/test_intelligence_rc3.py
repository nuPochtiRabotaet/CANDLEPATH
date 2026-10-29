import sqlite3
from dataclasses import replace
import pytest
from moex_intelligence.crypto.intelligence import Forecast,ForecastPoint,ForecastHistory,UnavailableForecastEngine
from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.storage import Store


def sample():return Forecast('f1','BTCUSDT','15',1800,1799,'baseline-test-v1','EXPERIMENTAL',(ForecastPoint(2700,'90','100','110'),),.8)

def test_no_model_no_invented_forecast():
 f=UnavailableForecastEngine().forecast((),'BTCUSDT','15',1800)
 assert f.status=='UNAVAILABLE' and not f.points


def test_append_only_maturity_restart_and_candle_source(tmp_path):
 store=Store(tmp_path/'forecast.db');h=ForecastHistory(store);f=sample()
 original=h.publish(f,now=1800);assert h.publish(f,now=2800)==original
 with pytest.raises(ValueError):h.publish(replace(f,points=(ForecastPoint(2700,'90','105','110'),)),now=1800)
 assert h.reconcile(now=2701)==0
 # Future outcome unavailable until its closed candle is present and horizon elapsed.
 store.save_candles('BTCUSDT','15',[Candle(1800,100,108,98,105,10,False)])
 assert h.reconcile(now=2701)==0
 store.save_candles('BTCUSDT','15',[Candle(1800,100,108,98,105,10,True)])
 assert h.reconcile(now=2600)==0 and h.reconcile(now=2701)==1
 h=ForecastHistory(Store(store.path));assert h.reconcile(now=2800)==0
 r=h.records()[0];assert r['forecast']==original and r['outcomes'][0]['actual']=='105' and r['outcomes'][0]['covered']
 with store.connect() as db:
  with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE forecasts SET body='{}'")
  with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM forecast_outcomes')


@pytest.mark.parametrize('changes',[
 {'data_as_of':1801},{'created_at':1900},{'status':'VALIDATED','validation_reference':'unreviewed-claim'},
 {'points':(ForecastPoint(1800,'90','100','110'),)}, {'points':(ForecastPoint(2701,'90','100','110'),)},
 {'points':(ForecastPoint(2700,'110','100','90'),)}, {'points':(ForecastPoint(2700,'NaN','100','110'),)},
 {'interval_coverage':1.0}])
def test_reject_leakage_retroactive_and_false_validation(tmp_path,changes):
 with pytest.raises(ValueError):ForecastHistory(Store(tmp_path/'f.db')).publish(replace(sample(),**changes),now=1800)
