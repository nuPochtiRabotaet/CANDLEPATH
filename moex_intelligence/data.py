"""Shared Reader-backed data layer for MCP, CLI and Streamlit."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import logging
import threading
import time
from collections import OrderedDict
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from moex import ISS, identifier, rows
from .config import Settings

log = logging.getLogger(__name__)


def market_today():
    return datetime.now(ZoneInfo('Europe/Moscow')).date()


def date_range(start, end):
    first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if first > last or (last - first).days > 3660:
        raise ValueError('Date range must be ordered and no longer than 3660 days.')
    return first, last


def describe_response(payload, symbol):
    """MOEX /securities/{id} uses description + boards, not securities."""
    desc = {r['name']: r['value'] for r in rows(payload, 'description')} if 'description' in payload else {}
    old = rows(payload, 'securities') if 'securities' in payload else []
    boards = [r for r in rows(payload, 'boards') if r.get('engine') == 'stock'
              and r.get('market') in {'shares', 'bonds'} and r.get('is_traded', 1)]
    if not boards:
        raise ValueError(f'{symbol}: no supported traded shares/bonds board found')
    boards.sort(key=lambda r: (not bool(r.get('is_primary')), r.get('boardid') not in {'TQBR', 'TQTF', 'TQOB'}, r['boardid']))
    board = boards[0]
    kind = str(desc.get('TYPE', '')).lower()
    return {'symbol': symbol, 'name': desc.get('SHORTNAME', old[0].get('SHORTNAME', symbol) if old else symbol),
            'market': board['market'], 'board': board['boardid'],
            'currency': board.get('currencyid'), 'board_unit': board.get('unit'),
            'asset_type': 'bond' if board['market'] == 'bonds' else ('fund' if any(s in kind for s in ['etf', 'fund', 'ppif']) or board['boardid'] in {'TQTF','TQIF'} else 'equity'),
            'description': desc, 'demo_data': False}


def normalize_history(records):
    if not records:
        raise ValueError('MOEX returned no historical observations for this range.')
    frame = pd.DataFrame(records)
    if not {'TRADEDATE', 'CLOSE'} <= set(frame.columns):
        raise ValueError('History requires TRADEDATE and CLOSE.')
    try:
        dates = pd.to_datetime(frame['TRADEDATE'], format='%Y-%m-%d', errors='raise')
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid history date; no rows discarded.') from exc
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError('Duplicate, missing or unordered history dates; no rows discarded.')
    for col in ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME', 'FACEVALUE', 'ACCRUEDINT']:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors='coerce')
    invalid = ~np.isfinite(frame['CLOSE']) | (frame['CLOSE'] <= 0)
    if invalid.any():
        bad = frame.loc[invalid, 'TRADEDATE'].tolist()[:5]
        raise ValueError(f'Invalid/missing CLOSE on {bad}; no rows silently removed. Select a valid contiguous period.')
    frame = frame.drop(columns=['TRADEDATE'])
    frame.index = pd.DatetimeIndex(dates, name='TRADEDATE')
    return frame


class DataEngine:
    def __init__(self, client=None, ttl=None):
        self.client = client or ISS()
        self.ttl = Settings.from_env().cache_ttl if ttl is None else ttl
        self._cache = OrderedDict()
        self._lock = threading.RLock()

    async def _cached(self, key, loader):
        with self._lock:
            item = self._cache.get(key)
            if item and time.monotonic() - item[0] < self.ttl:
                result = copy.deepcopy(item[1])
                result['cache'] = {'hit': True, 'age_seconds': round(time.monotonic() - item[0], 3), 'ttl_seconds': self.ttl}
                return result
        result = await loader()
        with self._lock:
            self._cache[key] = (time.monotonic(), copy.deepcopy(result))
            self._cache.move_to_end(key)
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
        result['cache'] = {'hit': False, 'age_seconds': 0, 'ttl_seconds': self.ttl}
        log.info('data_loaded kind=%s', key[0])
        return result

    async def search(self, query, limit=10):
        return await self._cached(('search', query, limit), lambda: self.client.search(query, limit))

    def clear_quotes(self, symbols=None):
        """Explicit refresh invalidates price cache, preserving independent histories."""
        selected=set(symbols) if symbols is not None else None
        with self._lock:
            for key in list(self._cache):
                if key[0]=='quote' and (selected is None or key[1] in selected):del self._cache[key]

    async def quote(self, ticker, board='TQBR', market='shares'):
        ticker, board = identifier(ticker), identifier(board)
        return await self._cached(('quote', ticker, board, market), lambda: self.client.quote(ticker, board, market))

    async def history(self, ticker, start, end, board='TQBR', market='shares'):
        ticker, board = identifier(ticker), identifier(board)
        date_range(start, end)
        return await self._cached(('history', ticker, start, end, board, market), lambda: self.client.history(ticker, start, end, board, market))

    async def snapshot(self, tickers, board='TQBR'):
        if not 1 <= len(tickers) <= 10:
            raise ValueError('Supply 1–10 tickers')
        result = []
        for ticker in tickers:
            try:
                result.append(await self.quote(ticker, board))
            except ValueError as exc:
                result.append({'ticker': ticker, 'error': str(exc)})
        return {'results': result, 'notice': 'Sequential snapshots are not simultaneous; selected basket only.'}

    async def describe(self, symbol):
        symbol = identifier(symbol)
        if symbol == 'IMOEX':
            return {'symbol':'IMOEX','name':'Индекс Мосбиржи','market':'index','board':'SNDX',
                    'asset_type':'index','currency':'RUB','board_unit':'points','demo_data':False,
                    'source':'https://iss.moex.com/iss/engines/stock/markets/index/boards/SNDX/securities/IMOEX.json'}
        async def load():
            payload, url = await self.client.get(f'/securities/{symbol}', {'iss.only': 'description,boards'})
            from moex import envelope
            return envelope(describe_response(payload, symbol), url)
        return await self._cached(('describe', symbol), load)

    async def research_quote(self, symbol):
        meta = await self.describe(symbol)
        quote = await self.quote(meta['symbol'], meta['board'], meta['market'])
        quote['instrument'] = meta
        quote['price_unit'] = 'percent_of_face_value' if meta['asset_type'] == 'bond' else 'currency_per_unit'
        if meta['asset_type'] == 'index':quote['price_unit']='index_points'
        if meta['asset_type'] == 'bond':
            quote['bond_policy'] = 'LAST is clean price in % of face value; FACEVALUE and ACCRUEDINT are separate. No yield/total-return model.'
        return quote

    async def frame(self, symbol, start, end):
        first, last = date_range(start, end)
        meta = await self.describe(symbol)
        history = await self.history(meta['symbol'], first.isoformat(), last.isoformat(), meta['board'], meta['market'])
        frame = normalize_history(history['rows'])
        if frame.index[0].date() < first or frame.index[-1].date() > last:
            raise ValueError('MOEX returned observations outside the requested date range.')
        meta = {**meta, 'source': history['source'], 'retrieved_at_utc': history['retrieved_at_utc'], 'cache': history['cache'],
                'price_adjustment': 'unadjusted', 'history_sha256': hashlib.sha256(frame.to_csv().encode()).hexdigest(),
                'warnings': ['Unadjusted prices: dividend gaps, splits and trading suspensions can distort results.'],
                'price_unit': 'index_points' if meta['asset_type'] == 'index' else 'percent_of_face_value' if meta['asset_type'] == 'bond' else 'currency_per_unit'}
        meta['coverage'] = {'requested_start': first.isoformat(), 'requested_end': last.isoformat(),
                            'actual_start': str(frame.index[0].date()), 'actual_end': str(frame.index[-1].date())}
        if (frame.index[0].date() - first).days > 14:
            meta['coverage_warning'] = 'History on the selected primary board begins later than requested. Other boards were not stitched together.'
        if (last - frame.index[-1].date()).days > 14:
            meta['freshness_warning'] = 'Last historical observation is more than 14 calendar days before requested end; inspect trading status.'
        return frame, meta

    def frame_sync(self, symbol, start, end):
        return asyncio.run(self.frame(symbol, start, end))


@lru_cache(maxsize=1)
def get_engine():
    return DataEngine()


def require_equity(meta):
    if meta.get('asset_type') == 'index':
        raise ValueError('Индекс — ориентир, а не покупаемая бумага. Используйте историческое сравнение или выберите конкретный фонд.')
    if meta.get('asset_type') == 'bond':
        raise ValueError('Bond price is % of face value. Simulation/backtesting requires coupon, redemption and amortization schedules; unsupported in this MVP.')
    if meta.get('currency') not in {None, 'RUB', 'SUR'}:
        raise ValueError('Quantitative MVP supports RUB-quoted instruments. FX conversion and currency risk are not implemented.')
