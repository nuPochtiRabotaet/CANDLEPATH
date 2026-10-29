"""Typed research boundary. No exchange execution capability or trained-model claim."""
from dataclasses import dataclass,asdict
from typing import Literal,Protocol
from decimal import Decimal
import json,time
from .market import seconds

@dataclass(frozen=True)
class RegimeSnapshot:
    symbol:str
    timeframe:str
    as_of:float
    regime:Literal['Bullish','Bearish','Range','High Volatility','Uncertain']
    method_version:str='causal-indicators-v1'
    reasons:tuple[str,...]=()

@dataclass(frozen=True)
class ForecastPoint:
    target_time:int
    lower:str
    median:str
    upper:str

@dataclass(frozen=True)
class Forecast:
    id:str
    symbol:str
    timeframe:str
    created_at:float
    data_as_of:float
    model_version:str
    status:Literal['UNAVAILABLE','EXPERIMENTAL','VALIDATED']
    points:tuple[ForecastPoint,...]=()
    interval_coverage:float|None=None
    validation_reference:str|None=None
    reason:str=''

@dataclass(frozen=True)
class DecisionContext:
    symbol:str
    timeframe:str
    evaluated_at:float
    regime:RegimeSnapshot
    signal_id:str|None
    signal_state:str
    entry_quality:str
    attention:str
    risk_allowed:bool
    risk_reasons:tuple[str,...]
    forecast:Forecast

class ForecastEngine(Protocol):
    def forecast(self,closed_candles:tuple,symbol:str,timeframe:str,as_of:float)->Forecast:...

class UnavailableForecastEngine:
    def forecast(self,closed_candles,symbol,timeframe,as_of):
        return Forecast('unavailable',symbol,timeframe,time.time(),as_of,'none','UNAVAILABLE',reason='Прогнозная модель не активирована / не прошла проверку')


def validate(forecast,now):
    if forecast.status!='EXPERIMENTAL' or not forecast.points:raise ValueError('Only experimental forecasts accepted until independent validation registry exists')
    if forecast.timeframe not in ('1','5','15','30','60','240','D') or not forecast.symbol or not forecast.id or not forecast.model_version:raise ValueError('Invalid forecast identity')
    if not 0<forecast.data_as_of<=forecast.created_at<=now+2:raise ValueError('Invalid causal timestamps')
    if forecast.interval_coverage is None or not 0<forecast.interval_coverage<1:raise ValueError('Invalid interval coverage')
    times=[p.target_time for p in forecast.points]
    if times!=sorted(set(times)) or times[0]<=now:raise ValueError('Cannot publish an already elapsed horizon')
    for p in forecast.points:
        if type(p.target_time) is not int or p.target_time%seconds(forecast.timeframe):raise ValueError('Horizon must align to UTC interval boundary')
        q=[Decimal(x) for x in (p.lower,p.median,p.upper)]
        if not all(v.is_finite() and v>0 for v in q) or not q[0]<=q[1]<=q[2]:raise ValueError('Invalid quantiles')


class ForecastHistory:
    """Append-only predictions and separate immutable outcomes from closed candles.
    No historical backfilling of purported live forecasts is accepted.
    """
    def __init__(self,store):self.store=store
    def publish(self,forecast,*,now=None):
        now=time.time() if now is None else now;body=json.dumps(asdict(forecast),sort_keys=True,allow_nan=False)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT body FROM forecasts WHERE id=?',(forecast.id,)).fetchone()
            if old:
                if old[0]!=body:raise ValueError('Published forecast is immutable')
                return json.loads(old[0])
            validate(forecast,now);db.execute('INSERT INTO forecasts VALUES(?,?,?)',(forecast.id,now,body))
        return json.loads(body)
    def reconcile(self,*,now=None):
        now=time.time() if now is None else now;count=0
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for ident,body in db.execute('SELECT id,body FROM forecasts').fetchall():
                f=json.loads(body);step=seconds(f['timeframe'])
                for p in f['points']:
                    if p['target_time']>now:continue
                    row=db.execute('SELECT body FROM candles WHERE symbol=? AND interval=? AND time=?',(f['symbol'],f['timeframe'],p['target_time']-step)).fetchone()
                    if not row:continue
                    candle=json.loads(row[0])
                    if not candle['closed']:continue
                    outcome={'target_time':p['target_time'],'actual':str(candle['close']),'recorded_at':now,'source':'persisted closed candle journal',
                        'covered':Decimal(p['lower'])<=Decimal(str(candle['close']))<=Decimal(p['upper'])}
                    cur=db.execute('INSERT OR IGNORE INTO forecast_outcomes VALUES(?,?,?)',(ident,p['target_time'],json.dumps(outcome)));count+=cur.rowcount
        return count
    def records(self):
        with self.store.connect() as db:
            rows=db.execute('SELECT published_at,body,id FROM forecasts ORDER BY published_at').fetchall()
            return [{'published_at':r[0],'forecast':json.loads(r[1]),'outcomes':[json.loads(o[0]) for o in db.execute('SELECT body FROM forecast_outcomes WHERE forecast_id=? ORDER BY target_time',(r[2],))]} for r in rows]
