"""Fixed causal research hypotheses; never imported by the trading UI."""
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd
from .analysis import indicators

VERSION = 'coliseum-catalog-0.2.0'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()).hexdigest()

def features(rows):
    f=indicators(rows); c=f.close; h=f.high; l=f.low; v=f.volume
    for n in (3,5,10,20,50):
        f[f'mean{n}']=c.rolling(n).mean(); f[f'roc{n}']=c.pct_change(n,fill_method=None)
        f[f'hi{n}']=h.shift().rolling(n).max(); f[f'lo{n}']=l.shift().rolling(n).min()
    f['ret']=c.pct_change(fill_method=None)
    f['vol']=f.ret.rolling(20).std(); f['volbase']=f.vol.shift().rolling(100).median()
    f['vw']=(c*v).rolling(20).sum()/v.rolling(20).sum().replace(0,np.nan)
    f['clv']=(2*c-h-l)/(h-l).replace(0,np.nan)
    f['body']=(c-f.open)/(h-l).replace(0,np.nan)
    f['lower']=(np.minimum(c,f.open)-l)/(h-l).replace(0,np.nan)
    f['range']=h-l
    f['stoch']=(c-l.rolling(14).min())/(h.rolling(14).max()-l.rolling(14).min()).replace(0,np.nan)
    f['macd']=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    f['macds']=f.macd.ewm(span=9,adjust=False).mean()
    return f

def hypotheses(f):
    c=f.close; p=f.shift(); up=c>p.close; down=c<p.close
    # Each pair is (entry condition, exit condition). Entries occur on a false->true edge.
    return {
    'trend_ema':('Trend',f.ema_fast>f.ema_slow,f.ema_fast<f.ema_slow),
    'trend_supertrend':('Trend',f.direction>0,f.direction<0),
    'trend_macd':('Trend',f.macd>f.macds,f.macd<f.macds),
    'trend_stack':('Trend',(f.mean5>f.mean20)&(f.mean20>f.mean50),c<f.mean20),
    'trend_pullback':('Trend',(c>f.ema_fast)&(p.close<=p.ema_fast)&(f.ema_fast>f.ema_slow),c<f.ema_slow),
    'trend_adx_rise':('Trend',(f.adx>25)&(f.adx>p.adx)&(c>f.ema_fast),f.adx<20),
    'trend_slope':('Trend',f.mean20.diff(5)>f.atr*.5,f.mean20.diff(5)<0),
    'trend_vwap':('Trend',(c>f.vw)&(f.vw>p.vw),c<f.vw),
    'trend_price_accel':('Trend',(f.roc5>f.roc10/2)&(f.roc10>0),f.roc5<0),
    'trend_volume':('Trend',(f.roc10>0)&(f.volume_ratio>1.5),f.roc5<0),
    'momentum_rsi':('Momentum',f.rsi>60,f.rsi<50),
    'momentum_streak':('Momentum',up.rolling(3).sum()==3,down.rolling(2).sum()==2),
    'momentum_impulse':('Momentum',(c-f.open)>f.atr,c<f.mean5),
    'momentum_relative':('Momentum',f.roc10>f.vol*2,f.roc5<0),
    'momentum_close_location':('Momentum',(f.clv>.8)&(f.range>f.atr),f.clv<-.5),
    'momentum_volume_expand':('Momentum',(v_positive(f))&(f.roc3>0),f.roc3<0),
    'revert_rsi':('Reversion',f.rsi<30,f.rsi>50),
    'revert_bollinger':('Reversion',c<f.bb_low,c>f.bb_mid),
    'revert_z_reentry':('Reversion',(p.zscore<-2)&(f.zscore>=-2),f.zscore>=0),
    'revert_stoch':('Reversion',f.stoch<.15,f.stoch>.5),
    'revert_vwap':('Reversion',c<f.vw-f.atr,c>f.vw),
    'revert_atr_ema':('Reversion',c<f.ema_fast-2*f.atr,c>f.ema_fast),
    'revert_streak':('Reversion',down.rolling(4).sum()==4,up.rolling(2).sum()==2),
    'revert_lower_wick':('Reversion',(f.lower>.6)&(f.rsi<40),c>f.mean10),
    'revert_false_break':('Reversion',(f.low<f.lo20)&(c>f.lo20),c>f.mean20),
    'revert_climax':('Reversion',(f.volume_ratio>2)&(f.ret<-f.vol*2),c>f.mean10),
    'revert_quiet_dip':('Reversion',(f.volume_ratio<.7)&(f.roc5<-.002),f.roc3>0),
    'revert_gap':('Reversion',(f.open<p.close-p.atr)&up,c>p.close),
    'break_donchian':('Breakout',c>f.hi20,c<f.lo10),
    'break_bollinger':('Breakout',c>f.bb_high,c<f.bb_mid),
    'break_squeeze':('Breakout',f['squeeze']&(c>f.hi20),c<f.mean20),
    'break_inside':('Breakout',(p.high<f.high.shift(2))&(p.low>f.low.shift(2))&(c>p.high),c<p.low),
    'break_narrow_range':('Breakout',(p.range==f.range.shift().rolling(7).min())&(c>p.high),c<f.mean10),
    'break_keltner':('Breakout',c>f.ema_fast+2*f.atr,c<f.ema_fast),
    'break_volume':('Breakout',(c>f.hi10)&(f.volume_ratio>2),c<f.lo5),
    'break_vol_expansion':('Breakout',(f.vol>f.volbase*1.5)&(c>f.hi5),c<f.mean10),
    'break_compression':('Breakout',(p.range<p.atr*.5)&(c>p.high),c<p.low),
    'break_retest':('Breakout',(p.close>f.hi20.shift())&(f.low<=p.close)&(c>p.close),c<f.mean10),
    'stat_mean_cross':('Statistical',c>f.mean20,c<f.mean20),
    'stat_median_cross':('Statistical',c>c.rolling(20).median(),c<c.rolling(20).median()),
    'stat_return_quantile':('Statistical',f.ret>f.ret.shift().rolling(100).quantile(.9),f.ret<0),
    'stat_down_quantile':('Statistical',f.ret<f.ret.shift().rolling(100).quantile(.1),f.ret>0),
    'stat_autocorr_trend':('Statistical',(f.ret.rolling(50).corr(f.ret.shift())>.2)&up,down),
    'stat_autocorr_revert':('Statistical',(f.ret.rolling(50).corr(f.ret.shift())<-.2)&down,up),
    'stat_skew_recovery':('Statistical',(f.ret.rolling(50).skew()<-1)&up,c>f.mean20),
    'stat_range_position':('Statistical',(c-f.lo50)/(f.hi50-f.lo50)>.8,c<f.mean20),
    'control_cash':('Control',pd.Series(False,index=f.index),pd.Series(False,index=f.index)),
    'control_periodic':('Control',pd.Series(np.arange(len(f))%48==0),pd.Series(np.arange(len(f))%48==16)),
    'control_positive_bar':('Control',up,down),
    'control_negative_bar':('Control',down,up),
    }

def v_positive(f):
    return (f.volume>f.volume.shift())&(f.volume.shift()>f.volume.shift(2))

def roster():
    # Formula source digest binds all fixed periods/thresholds, alongside execution spec.
    code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    dummy=[dict(time=i*300,open=100.,high=101.,low=99.,close=100.,volume=1.,closed=True) for i in range(150)]
    result=[]
    for idea,(family,_,__) in hypotheses(features(dummy)).items():
        for variant in ('unfiltered','low_volatility'):
            spec=dict(version=VERSION,code_sha256=code,idea=idea,variant=variant,
                family=family,symbol='BTCUSDT',timeframe='5',seed=0,warmup=128,
                stop_atr=2,target_atr=4,max_hold_bars=16,entry='rising_edge_next_open',
                variant_rule='ATR/close <= prior 100-bar median' if variant!='unfiltered' else 'none')
            result.append(dict(id=idea+'__'+variant,family=family,idea=idea,spec=spec,spec_sha256=digest(spec)))
    return result

class CandidateProvider:
    def __init__(self, rows, spec, shared=None):
        self.rows=rows; self.f=features(rows) if shared is None else shared[0]; self.spec=spec
        self.conditions=hypotheses(self.f) if shared is None else shared[1]
    def __call__(self, prefix, symbol, timeframe):
        if symbol!='BTCUSDT' or timeframe!='5' or prefix!=self.rows[:len(prefix)]:
            raise ValueError('Candidate prefix mismatch')
        f=self.f.iloc[:len(prefix)]; s=self.spec; cid=s['id']
        _,buy,sell=self.conditions[s['idea']]; buy=buy.iloc[:len(f)].fillna(False);sell=sell.iloc[:len(f)].fillna(False)
        if s['spec']['variant']=='low_volatility':
            ratio=self.f.atr/self.f.close
            buy=buy&(ratio<=ratio.shift().rolling(100).median()).iloc[:len(f)]
        buy=buy&~buy.shift(fill_value=False); sell=sell&~sell.shift(fill_value=False)
        result=[]
        for i in np.flatnonzero((buy|sell).to_numpy()):
            if i<128:continue
            r=f.iloc[i]; kind='EXIT' if sell.iloc[i] else 'BUY'
            result.append(dict(id=digest([s['spec_sha256'],int(r.time),kind]),strategy=cid,type=kind,
                candle_time=int(r.time),timestamp=int(r.time)+300,reference_price=float(r.close),status='confirmed',
                risk_estimates=dict(stop=max(float(r.close-s["spec"]["stop_atr"]*r.atr),.01),target=float(r.close+s["spec"]["target_atr"]*r.atr))))
        return result
