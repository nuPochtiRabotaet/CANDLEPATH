"""Read-only MOEX ISS client. No broker credentials or trading operations."""
import asyncio
import math
import re
import statistics
from datetime import date, datetime, timezone
import httpx
import logging

BASE = 'https://iss.moex.com/iss'
NOTICE = 'Public ISS data may be delayed (normally 15 minutes). Retrieval time is not trade time. Prices are not dividend/split-adjusted. No guaranteed forecasts.'

def identifier(value):
    if not isinstance(value, str):
        raise ValueError('Ticker/board must be a string.')
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9_-]{1,32}', value):
        raise ValueError('Invalid ticker or board: use 1–32 letters, digits, underscore or hyphen.')
    return value

def rows(data, key):
    block = data.get(key)
    if not isinstance(block, dict) or not isinstance(block.get('columns'), list) or not isinstance(block.get('data'), list):
        raise ValueError(f'MOEX response is missing table {key}')
    if (any(not isinstance(c, str) for c in block['columns']) or
        len(set(block['columns'])) != len(block['columns']) or
        any(not isinstance(r, list) or len(r) != len(block['columns']) for r in block['data'])):
        raise ValueError(f'Malformed MOEX table {key}')
    return [dict(zip(block['columns'], r)) for r in block['data']]

def envelope(data, url):
    return {'source': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'notice': NOTICE, **data}

class ISS:
    def __init__(self, transport=None):
        self.transport = transport

    async def get(self, path, params=None):
        url = BASE + path + '.json'
        async with httpx.AsyncClient(timeout=20, transport=self.transport, follow_redirects=False) as client:
            for attempt in range(3):
                try:
                    r = await client.get(url, params={'iss.meta': 'off', **(params or {})})
                    if r.status_code in (429, 502, 503, 504) and attempt < 2:
                        logging.getLogger('moex_intelligence.iss').info('retry status=%s attempt=%s', r.status_code, attempt + 1)
                        await asyncio.sleep(0.5 * 2**attempt)
                        continue
                    r.raise_for_status()
                    data = r.json()
                    if not isinstance(data, dict):
                        raise ValueError('Unexpected MOEX JSON format')
                    return data, str(r.url)
                except httpx.TransportError as exc:
                    if attempt == 2:
                        raise ValueError('MOEX unavailable after 3 attempts; no substitute prices used.') from exc
                    await asyncio.sleep(0.5 * 2**attempt)
                except (httpx.HTTPStatusError, ValueError) as exc:
                    raise ValueError(f'MOEX request failed: {type(exc).__name__}; no substitute prices used.') from exc

    async def search(self, query, limit=10):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100 or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError('Query length 1–100; limit 1–50')
        data, url = await self.get('/securities', {'q': query.strip(), 'limit': limit})
        return envelope({'results': rows(data, 'securities')[:limit], 'scope': 'Search includes other asset classes; quote/history tools support stock market shares only.'}, url)

    async def quote(self, ticker, board='TQBR', market='shares'):
        if market not in {'shares', 'bonds', 'index'}:
            raise ValueError('Only shares, bonds and index markets are supported.')
        ticker, board = identifier(ticker), identifier(board)
        data, url = await self.get(f'/engines/stock/markets/{market}/boards/{board}/securities/{ticker}', {'iss.only': 'securities,marketdata'})
        securities, marketdata = rows(data, 'securities'), rows(data, 'marketdata')
        if not securities:
            raise ValueError('Security not found on this board. Check ticker/primary_boardid with search_security.')
        sec = securities[0]
        md = marketdata[0] if marketdata else {}
        last = md.get('LAST')
        if last is not None and (isinstance(last, bool) or not isinstance(last, (int, float)) or not math.isfinite(last) or last <= 0):
            raise ValueError('Invalid LAST returned by MOEX; no substitute price used.')
        return envelope({'ticker': ticker, 'board': board, 'security': sec, 'marketdata': md,
            'last_price': md.get('LAST'), 'currency': sec.get('CURRENCYID'),
            'last_price_missing': md.get('LAST') is None,
            'price_policy': 'LAST only; PREVPRICE is not substituted. Check SYSTIME, UPDATETIME, TIME and TRADINGSTATUS in marketdata.'}, url)

    async def history(self, ticker, start, end, board='TQBR', market='shares'):
        if market not in {'shares', 'bonds', 'index'}:
            raise ValueError('Only shares, bonds and index markets are supported.')
        ticker, board = identifier(ticker), identifier(board)
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first > last or (last-first).days > 3660:
            raise ValueError('Date range must be ordered and no longer than 3660 days.')
        path = f'/history/engines/stock/markets/{market}/boards/{board}/securities/{ticker}'
        result = []
        for _ in range(40):
            data, url = await self.get(path, {'from': first.isoformat(), 'till': last.isoformat(), 'start': len(result)})
            page = rows(data, 'history')
            if not page:
                return envelope({'ticker': ticker, 'board': board, 'start': start, 'end': end, 'rows': result, 'count': len(result), 'complete': True}, url)
            dates = [r.get('TRADEDATE') for r in page]
            try:
                parsed = [date.fromisoformat(d) for d in dates]
            except (ValueError, TypeError) as exc:
                raise ValueError('Malformed history date in pagination') from exc
            if any(b <= a for a, b in zip(parsed, parsed[1:])):
                raise ValueError('Unordered history pagination')
            if result and page[0].get('TRADEDATE') <= result[-1].get('TRADEDATE'):
                raise ValueError('Non-advancing or unordered history pagination')
            result.extend(page)
        raise ValueError('History page limit reached; request a shorter range.')

    async def snapshot(self, tickers, board='TQBR'):
        if not 1 <= len(tickers) <= 10:
            raise ValueError('Supply 1–10 tickers')
        result = []
        for ticker in tickers:
            try:
                result.append(await self.quote(ticker, board))
            except ValueError as exc:
                result.append({'ticker': ticker, 'error': str(exc)})
        return {'results': result, 'notice': 'Sequential snapshots are not simultaneous. A selected basket is not the whole market.'}

def metrics(history):
    items = history['rows']
    closes = [r.get('CLOSE') for r in items]
    if len(closes) < 2 or any(isinstance(x, bool) or not isinstance(x, (int,float)) or not math.isfinite(x) or x <= 0 for x in closes):
        raise ValueError('At least 2 consecutive valid positive daily closes required; missing closes are not silently skipped.')
    returns = [b/a-1 for a,b in zip(closes, closes[1:])]
    peak, drawdown = closes[0], 0.0
    for price in closes:
        peak = max(peak, price)
        drawdown = min(drawdown, price/peak-1)
    return {'observations': len(closes), 'first_date': items[0]['TRADEDATE'], 'last_date': items[-1]['TRADEDATE'],
        'price_return_pct': (closes[-1]/closes[0]-1)*100,
        'max_close_drawdown_pct': drawdown*100,
        'annualized_volatility_pct': statistics.stdev(returns)*math.sqrt(252)*100 if len(returns)>1 else None,
        'sma20': statistics.mean(closes[-20:]) if len(closes)>=20 else None,
        'sma50': statistics.mean(closes[-50:]) if len(closes)>=50 else None,
        'method': 'Close-to-close simple returns; sample standard deviation × sqrt(252). Daily-close drawdown only.',
        'limitations': 'Descriptive history, not a forecast. No dividends, fees, taxes or corporate-action adjustment; splits can distort results.'}
