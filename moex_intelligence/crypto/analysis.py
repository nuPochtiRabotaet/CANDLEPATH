"""Causal, formula-based indicators and strategies. No fitted probability model."""
import hashlib,json,math
from dataclasses import asdict,dataclass
from typing import Protocol
import numpy as np
import pandas as pd
VERSION='rules-1.0'
PARAMS={'ema_fast':21,'ema_slow':55,'atr':14,'adx':14,'rsi':14,'supertrend_multiplier':3,'breakout':20,'volume_ratio':1.2}
class FutureScorer(Protocol):
    def score(self,features:dict,*,model_version:str)->dict:...
def ema(values,n):return pd.Series(values,dtype=float).ewm(span=n,adjust=False).mean().to_numpy()
def wilder(values,n):
    a=np.asarray(values,float);out=np.full(len(a),np.nan)
    if len(a)>=n:
        out[n-1]=np.mean(a[:n])
        for i in range(n,len(a)):out[i]=(out[i-1]*(n-1)+a[i])/n
    return out

def indicators(rows):
    f=pd.DataFrame(rows);h=f.high.to_numpy();l=f.low.to_numpy();c=f.close.to_numpy();prev=np.r_[c[0],c[:-1]]
    f['ema_fast']=ema(c,21);f['ema_slow']=ema(c,55)
    tr=np.maximum(h-l,np.maximum(abs(h-prev),abs(l-prev)));a=wilder(tr,14);f['atr']=a
    delta=np.diff(c,prepend=c[0]);gain=wilder(np.maximum(delta,0),14);loss=wilder(np.maximum(-delta,0),14)
    with np.errstate(divide='ignore',invalid='ignore'):f['rsi']=np.where((gain==0)&(loss==0),50,np.where(loss==0,100,100-100/(1+gain/loss)))
    up=np.diff(h,prepend=h[0]);down=-np.diff(l,prepend=l[0]);plus=wilder(np.where((up>down)&(up>0),up,0),14);minus=wilder(np.where((down>up)&(down>0),down,0),14)
    with np.errstate(divide='ignore',invalid='ignore'):dx=np.where(plus+minus>0,100*abs(plus-minus)/(plus+minus),0)
    adx=np.full(len(c),np.nan)
    if len(c)>13:adx[13:]=wilder(dx[13:],14)
    f['adx']=adx;mid=pd.Series(c).rolling(20).mean();std=pd.Series(c).rolling(20).std(ddof=0);f['bb_mid']=mid;f['bb_low']=mid-2*std;f['bb_high']=mid+2*std
    with np.errstate(divide='ignore',invalid='ignore'):f['zscore']=(c-mid)/std.replace(0,np.nan)
    f['volume_ratio']=f.volume/f.volume.shift(1).rolling(20).mean().replace(0,np.nan)
    upper=(h+l)/2+3*a;lower=(h+l)/2-3*a;trend=np.full(len(c),np.nan);direction=np.zeros(len(c))
    for i in range(13,len(c)):
        if i==13:trend[i]=upper[i];direction[i]=-1;continue
        upper[i]=upper[i] if upper[i]<upper[i-1] or c[i-1]>upper[i-1] else upper[i-1]
        lower[i]=lower[i] if lower[i]>lower[i-1] or c[i-1]<lower[i-1] else lower[i-1]
        direction[i]=1 if (direction[i-1]<0 and c[i]>upper[i]) else -1 if (direction[i-1]>0 and c[i]<lower[i]) else direction[i-1]
        trend[i]=lower[i] if direction[i]>0 else upper[i]
    f['supertrend']=trend;f['direction']=direction
    f['resistance']=f.high.shift(1).rolling(20).max();f['support']=f.low.shift(1).rolling(20).min()
    f['squeeze']=(4*std/mid).shift(1)<(4*std/mid).shift(1).rolling(100,min_periods=40).median()
    return f

def regime(row):
    if not math.isfinite(row['adx']) or not math.isfinite(row['atr']):return 'Uncertain'
    if row['atr']/row['close']>.04:return 'High Volatility'
    if row['adx']<20:return 'Range'
    return 'Bullish' if row['ema_fast']>row['ema_slow'] and row['direction']>0 else 'Bearish' if row['ema_fast']<row['ema_slow'] and row['direction']<0 else 'Uncertain'

def analyze(rows,symbol,interval,*,include_forming=False,latest_only=False):
    if not rows:return {'overlay':[],'signals':[],'regime':'Uncertain'}
    f=indicators(rows);signals=[];overlay=[]
    from .market import seconds
    for i,r in (f.iloc[-1:] if latest_only else f).iterrows():
        if i<55:continue
        mode=regime(r);d=1 if mode=='Bullish' else -1 if mode=='Bearish' else 0
        # ATR-offset EMA ribbon; always on the relevant side of the actual price.
        edge=min(r.ema_fast,r.close)-.25*r.atr if d>0 else max(r.ema_fast,r.close)+.25*r.atr
        overlay.append({'time':int(r.time),'fast':r.ema_fast,'slow':r.ema_slow,'supertrend':r.supertrend,'upper':edge if d>0 else edge+r.atr,'lower':edge-r.atr if d>0 else edge,'direction':d})
        if not r.closed and not include_forming:continue
        prev=f.iloc[i-1];conditions=[]
        if mode=='Bullish' and r.close>r.ema_fast and (prev.close<=prev.ema_fast or regime(prev)!='Bullish') and r.volume_ratio>=1:
            conditions.append(('Trend Following','BUY',['EMA21 > EMA55; ADX ≥ 20','Supertrend восходящий','Закрытие выше EMA21; объём ≥ среднего']))
        elif mode=='Bearish' and regime(prev)!='Bearish':conditions.append(('Trend Following','EXIT',['EMA21 < EMA55; ADX ≥ 20','Supertrend нисходящий; выход из long, не short']))
        if mode=='Range' and prev.close<prev.bb_low and r.close>=r.bb_low and prev.rsi<35:conditions.append(('Mean Reversion','BUY',['Возврат внутрь Bollinger(20,2)','Предыдущий RSI14 < 35; ADX < 20']))
        if mode=='Range' and prev.close<prev.bb_mid and r.close>=r.bb_mid:conditions.append(('Mean Reversion','EXIT',['Достигнута средняя Bollinger; потенциальный выход']))
        if bool(r.squeeze) and r.close>r.resistance and prev.close<=prev.resistance and r.volume_ratio>=1.2:conditions.append(('Breakout Detection','BUY',['Пробой максимума 20 предыдущих свечей','Предшествующее сжатие Bollinger','Объём ≥ 1,2 среднего прошлых свечей']))
        if r.close<r.support and prev.close>=prev.support:conditions.append(('Breakout Detection','EXIT',['Закрытие ниже поддержки 20 предыдущих свечей']))
        for strategy,kind,reasons in conditions:
            key=f'{symbol}:{interval}:{strategy}:{VERSION}:{int(r.time)}:{kind}'
            signals.append({'id':hashlib.sha256(key.encode()).hexdigest()[:24],'symbol':symbol,'exchange':'Bybit','timeframe':interval,'strategy':strategy,'strategy_version':VERSION,'timestamp':int(r.time)+seconds(interval),'candle_time':int(r.time),'type':kind,'reference_price':r.close,'indicators':{k:float(r[k]) if math.isfinite(r[k]) else None for k in ['ema_fast','ema_slow','atr','adx','rsi','volume_ratio']},'risk_estimates':{'stop':max(r.close-2*r.atr,.01),'target':r.close+4*r.atr},'status':'confirmed' if r.closed else 'POTENTIAL','explanation':reasons,'regime':mode,'parameters':PARAMS,'invalidation':'Закрытие ниже стопа / смена режима; исполнение проверяется отдельно','cost_assumption':'Издержки не фиксируются сигналом: актуальный Cost Engine snapshot сохраняется при предпросмотре и исполнении'})
    closed=f[f.closed]
    return {'overlay':overlay,'signals':signals,'regime':regime(closed.iloc[-1]) if len(closed)>55 else 'Uncertain','atr':float(closed.iloc[-1].atr) if len(closed)>55 else None}
