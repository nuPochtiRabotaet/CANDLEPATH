"""Compatibility API routed through the shared MOEX Reader data engine."""
from datetime import date
import asyncio
import numpy as np
import pandas as pd
from moex import BASE, ISS, identifier
from moex_intelligence.data import get_engine, describe_response, require_equity


def _get_json(session, url, params=None):
    """Legacy seam retained; networking now uses Reader's retries/validation."""
    path = url.removeprefix(BASE).removesuffix('.json')
    return asyncio.run(ISS().get(path, params))[0]


def detect_market_board(session, symbol):
    symbol = identifier(symbol)
    meta = describe_response(_get_json(session, f'{BASE}/securities/{symbol}.json'), symbol)
    require_equity(meta)
    return meta['market'], meta['board'], meta['name']


def load_moex_daily(symbol, start, end):
    frame, meta = get_engine().frame_sync(symbol, start, end)
    require_equity(meta)
    return frame, meta


def demo_daily(days=420, seed=1007, end=date(2026, 1, 30)):
    """Synthetic prices, fixed end date: reproducible across days and machines."""
    from moex_intelligence.validation import integer
    integer(days, 'days', 65, 2600)
    integer(seed, 'seed', 0, 1_000_000)
    rng = np.random.default_rng(seed)
    close = 280 * np.exp(np.cumsum(rng.normal(.00025, .014, days)))
    opening = np.r_[280, close[:-1]] * np.exp(rng.normal(0, .002, days))
    spread = rng.uniform(.001, .012, days)
    frame = pd.DataFrame({'OPEN': opening, 'HIGH': np.maximum(opening, close)*(1+spread),
                          'LOW': np.minimum(opening, close)*(1-spread), 'CLOSE': close,
                          'VOLUME': rng.integers(10000, 1000000, days)},
                         index=pd.bdate_range(end=end, periods=days, name='TRADEDATE'))
    import hashlib
    return frame, {'symbol': 'DEMO', 'name': 'Искусственные данные — не SBER', 'board': 'SYNTHETIC',
                    'market': 'shares', 'asset_type': 'equity', 'source': 'SYNTHETIC / seed=1007' if seed == 1007 else f'SYNTHETIC / seed={seed}',
                    'demo_data': True, 'currency': 'RUB', 'lot_size': 1, 'price_adjustment': 'synthetic',
                    'history_sha256': hashlib.sha256(frame.to_csv().encode()).hexdigest(),
                    'warnings': ['Synthetic weekday calendar; not real quotes or MOEX trading calendar.']}
