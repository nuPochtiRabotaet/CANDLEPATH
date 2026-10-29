from datetime import timedelta
import numpy as np
import pandas as pd
from .data import get_engine, market_today
from .validation import integer


def compare_frames(first, second, meta_a, meta_b):
    if meta_a.get('asset_type')=='bond' or meta_b.get('asset_type')=='bond':
        raise ValueError('Сравнение облигации по одной цене некорректно: нужны купоны, НКД и погашение.')
    if meta_a.get('currency') not in {'RUB','SUR'} or meta_b.get('currency') not in {'RUB','SUR'}:
        raise ValueError('Для сравнения разных валют необходим FX-ряд.')
    joined=pd.concat([first.CLOSE.rename('asset'),second.CLOSE.rename('benchmark')],axis=1,join='inner')
    if len(joined)<65 or not np.isfinite(joined.to_numpy()).all() or (joined<=0).any().any():
        raise ValueError('Меньше 65 общих корректных дневных наблюдений.')
    returns=joined.pct_change().dropna()
    variance=float(returns.benchmark.var(ddof=1))
    stats=[]
    for col,meta in [('asset',meta_a),('benchmark',meta_b)]:
        s=joined[col]
        stats.append({'symbol':meta['symbol'],'asset_type':meta['asset_type'],'return_pct':float((s.iloc[-1]/s.iloc[0]-1)*100),
                      'drawdown_pct':float((s/s.cummax()-1).min()*100),'volatility_pct':float(returns[col].std(ddof=1)*np.sqrt(252)*100)})
    return {'instruments':[meta_a,meta_b],'first_date':str(joined.index[0].date()),'last_date':str(joined.index[-1].date()),'observations':len(joined),
            'stats':stats,'beta':float(returns.asset.cov(returns.benchmark)/variance) if variance>0 else None,
            'normalized_prices':{'dates':joined.index.strftime('%Y-%m-%d').tolist(),
                'asset':(joined.asset/joined.asset.iloc[0]*100).tolist(),'benchmark':(joined.benchmark/joined.benchmark.iloc[0]*100).tolist()},
            'limitations':['Сравнение изменения цен, без дивидендов, налогов и расходов на покупку.',
                           'Даты пересечены явно; оставлено одинаковое окно. Индекс нельзя купить напрямую.',
                           'Это историческое сравнение, не рейтинг привлекательности или прогноз.']}


async def compare_instruments(symbol,benchmark='SBMX',lookback_days=730):
    integer(lookback_days,'lookback_days',120,3650)
    end=market_today()-timedelta(days=1);start=end-timedelta(days=lookback_days)
    first,a=await get_engine().frame(symbol,start,end)
    second,b=await get_engine().frame(benchmark,start,end)
    return compare_frames(first,second,a,b)
