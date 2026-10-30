"""Typed research boundary. No exchange execution capability or trained-model claim."""
from dataclasses import dataclass,asdict
from typing import Literal,Protocol
from decimal import Decimal, DecimalException
import json,time,math
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
                # Streamlit may recalculate an identical forecast during the
                # same candle with a later created_at. Keep the *first* record
                # immutable, while allowing a safe idempotent re-publication.
                previous=json.loads(old[0]);candidate=json.loads(body)
                if not forecast.data_as_of<=forecast.created_at<=now+2:
                    raise ValueError('Invalid causal timestamps')
                previous.pop('created_at',None)
                candidate.pop('created_at',None)
                if previous!=candidate:
                    raise ValueError('Published forecast is immutable')
                return json.loads(old[0])
            validate(forecast,now);db.execute('INSERT INTO forecasts VALUES(?,?,?)',(forecast.id,now,body))
        return json.loads(body)
    def reconcile(self,*,now=None):
        """Record actuals once, only after their target closed candle is available.

        One lookup for existing outcomes avoids repeating N*H SQLite queries for
        already settled predictions each time a new market candle arrives.
        """
        now=time.time() if now is None else now
        if not isinstance(now,(int,float)) or not (0<now<float('inf')):
            raise ValueError('Invalid reconciliation time')
        count=0
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=set(db.execute('SELECT forecast_id,target_time FROM forecast_outcomes'))
            for ident,body in db.execute('SELECT id,body FROM forecasts').fetchall():
                f=json.loads(body);step=seconds(f['timeframe'])
                for p in f['points']:
                    horizon=p['target_time']
                    if horizon>now or (ident,horizon) in existing:
                        continue
                    row=db.execute(
                        'SELECT body FROM candles WHERE symbol=? AND interval=? AND time=?',
                        (f['symbol'],f['timeframe'],horizon-step)).fetchone()
                    if not row:
                        continue
                    candle=json.loads(row[0])
                    if not candle['closed']:
                        continue
                    actual=Decimal(str(candle['close']))
                    covered=Decimal(p['lower'])<=actual<=Decimal(p['upper'])
                    outcome={'target_time':horizon,'actual':str(actual),'recorded_at':now,
                             'source':'persisted closed candle journal','covered':covered}
                    cur=db.execute('INSERT OR IGNORE INTO forecast_outcomes VALUES(?,?,?)',
                                   (ident,horizon,json.dumps(outcome)))
                    count+=cur.rowcount
        return count
    def records(self):
        """Read history without a separate SQL query for every forecast."""
        with self.store.connect() as db:
            rows=db.execute('SELECT published_at,body,id FROM forecasts ORDER BY published_at,id').fetchall()
            outcomes={}
            for ident,body in db.execute(
                    'SELECT forecast_id,body FROM forecast_outcomes ORDER BY forecast_id,target_time'):
                outcomes.setdefault(ident,[]).append(json.loads(body))
        return [{'published_at':published,'forecast':json.loads(body),
                 'outcomes':outcomes.get(ident,[])}
                for published,body,ident in rows]

    def scorecard(self, symbol=None, timeframe=None):
        """Descriptive audit of immutable real-time forecast outcomes.

        Fail closed on corrupt journal values. Treat a percentage that cannot
        be represented as a finite Python float as UNKNOWN, never Infinity.
        This is a diagnostic, not evidence of profitable trading.
        """
        buckets={}
        forecast_count=0
        max_float=Decimal("1.7976931348623157e308")
        for record in self.records():
            f=record["forecast"]
            if symbol and f["symbol"]!=symbol:continue
            if timeframe and f["timeframe"]!=timeframe:continue
            forecast_count+=1
            published={p["target_time"]:p for p in f["points"]}
            step=seconds(f["timeframe"])
            for o in record["outcomes"]:
                p=published.get(o["target_time"])
                if p is None:continue
                horizon=(o["target_time"]-f["data_as_of"])//step
                if horizon<=0:continue
                try:
                    actual=Decimal(str(o["actual"]))
                    median=Decimal(str(p["median"]))
                    if (not actual.is_finite() or not median.is_finite()
                            or actual<=0 or median<=0
                            or type(o["covered"]) is not bool):
                        raise ValueError("Invalid persisted outcome value")
                    pct=abs(median-actual)/actual*Decimal(100)
                    if not pct.is_finite() or pct<0:
                        raise ValueError("Invalid persisted outcome percentage")
                except (KeyError,TypeError,ValueError,DecimalException) as exc:
                    raise ValueError("Corrupt immutable forecast outcome journal") from exc
                b=buckets.setdefault(horizon,{"n":0,"covered":0,
                    "absolute_pct_error_sum":Decimal(0),"unrepresentable":0})
                b["n"]+=1
                b["covered"]+=int(o["covered"])
                b["absolute_pct_error_sum"]+=pct
                if pct>max_float:
                    b["unrepresentable"]+=1

        def safe_pct(value):
            try:
                converted=float(value)
            except (ValueError,OverflowError):
                return None
            return converted if math.isfinite(converted) else None

        return {"forecasts":forecast_count,"horizons":{
            h:{"observations":b["n"],
               "empirical_coverage":b["covered"]/b["n"],
               "mean_absolute_pct_error":safe_pct(
                   b["absolute_pct_error_sum"]/b["n"]),
               "unrepresentable_percentage_errors":b["unrepresentable"],
               "sufficient_sample":b["n"]>=30}
            for h,b in sorted(buckets.items())}}


def format_forecast_scorecard_pct(value):
    """UI-safe value formatter: never render Infinity or crash on null."""
    if type(value) not in (float,int) or not math.isfinite(value):
        return "недоступно (слишком большая ошибка)"
    return f"{value:.2f}%"
