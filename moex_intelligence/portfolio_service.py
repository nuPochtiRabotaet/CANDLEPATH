"""Portfolio use cases and market valuation. No Streamlit or visual dependencies."""
from __future__ import annotations
import asyncio
from datetime import timedelta
from moex import identifier
from .data import get_engine, market_today
from .portfolio import analyze_portfolio, ledger_state, validate_event
from .validation import finite


def quote_mark(quote, as_of=None):
    """No last->previous substitution, no nominal/FX guesses. Dirty RUB bond value."""
    meta = quote['instrument']; sec = quote['security']; md = quote.get('marketdata', {})
    if meta['asset_type'] == 'index': raise ValueError('Индекс нельзя добавить как бумагу.')
    currency = quote.get('currency') or meta.get('currency')
    if currency not in {'RUB', 'SUR'}: raise ValueError('Рублёвая валюта котировки не подтверждена.')
    price = finite(quote.get('last_price'), 'LAST: последняя цена MOEX', 1e-8, 1e12)
    if meta['asset_type'] == 'bond':
        if sec.get('FACEUNIT') not in {'RUB', 'SUR'}: raise ValueError('Рублёвый номинал облигации не подтверждён.')
        face = finite(sec.get('FACEVALUE'), 'FACEVALUE', 1e-8, 1e12)
        accrued = finite(sec.get('ACCRUEDINT'), 'ACCRUEDINT', 0, 1e12)
        price = price*face/100 + accrued
    return {'price':price, 'as_of':as_of or market_today().isoformat(), 'source':quote['source'],
            'name':meta['name'], 'asset_type':meta['asset_type'], 'retrieved_at_utc':quote['retrieved_at_utc'],
            'exchange_time':md.get('LASTTRADEDATE') or md.get('SYSTIME') or md.get('UPDATETIME'),
            'market_observed_at':md.get('LASTTRADEDATE') or md.get('SYSTIME'),
            'market_snapshot_at':md.get('SYSTIME'),'market_trade_at':md.get('LASTTRADEDATE'),
            'last_trade_clock':md.get('TIME'),
            'observation_kind':'trade_date' if md.get('LASTTRADEDATE') else 'snapshot' if md.get('SYSTIME') else 'unknown',
            'market_update_at':md.get('SYSTIME') or md.get('UPDATETIME'),
            'valuation_as_of':as_of or market_today().isoformat(),
            'price_type':'last_trade','demo_data':bool(meta.get('demo_data')), 
            'valuation_basis':'Последняя доступная сделка MOEX (возможна задержка)',
            'price_basis':'dirty_rub' if meta['asset_type']=='bond' else 'rub_per_unit'}


async def asset_market_data(symbol, engine=None):
    """One shared source for dated marks and the laboratory's full quote metadata."""
    engine=engine or get_engine()
    quote=await engine.research_quote(symbol)
    if quote.get('last_price') is not None:return {'quote':quote,'mark':quote_mark(quote)}
    end=market_today()-timedelta(days=1)
    frame,meta=await engine.frame(symbol,end-timedelta(days=21),end)
    last=frame.iloc[-1];observed=str(frame.index[-1].date())
    sec=dict(quote['security'])
    if meta['asset_type']=='bond':
        sec.update(FACEVALUE=float(last.get('FACEVALUE',float('nan'))),
                   ACCRUEDINT=float(last.get('ACCRUEDINT',float('nan'))))
    historical={**quote,'last_price':float(last['CLOSE']),'security':sec,'instrument':meta,
                'source':meta['source'],'retrieved_at_utc':meta['retrieved_at_utc'],
                'marketdata':{'LASTTRADEDATE':observed}}
    mark=quote_mark(historical)
    mark.update(valuation_basis='Дневное закрытие '+observed+'; не текущая котировка',observed_as_of=observed,market_observed_at=observed,market_trade_at=None,observation_kind='historical_close',price_type='daily_close')
    return {'quote':historical,'mark':mark}


async def fetch_marks(symbols, engine=None):
    engine=engine or get_engine()
    if len(symbols)>100:raise ValueError('Не более 100 открытых позиций.')
    semaphore=asyncio.Semaphore(4)
    async def one(symbol):
        try:
            async with asyncio.timeout(8):
                async with semaphore:
                    result=await asset_market_data(symbol,engine)
                    return symbol,result['mark'],None
        except (ValueError,KeyError,TypeError,TimeoutError) as exc:
            return symbol,None,str(exc) or 'MOEX не ответила за 8 секунд.'
    result=await asyncio.gather(*(one(s) for s in symbols))
    return {'marks':{s:m for s,m,e in result if m is not None},'errors':{s:e for s,m,e in result if e}}


async def resolve_symbols(values, engine=None):
    """Resolve identifiers/ISINs/exact names only. Never choose a fuzzy first hit."""
    values=sorted(set(v.strip() for v in values if v.strip()))
    if len(values)>100:raise ValueError('Не более 100 разных инструментов.')
    engine=engine or get_engine();semaphore=asyncio.Semaphore(4)
    def canonical(meta):
        return {**meta,'symbol':identifier(meta.get('description',{}).get('SECID') or meta['symbol'])}
    async def one(value):
        try:
            async with asyncio.timeout(8):
                async with semaphore:
                    try:
                        meta=await engine.describe(identifier(value))
                        if meta['asset_type']=='index':raise ValueError('Индекс не является бумагой.')
                        return value,canonical(meta),None
                    except ValueError:pass
                    result=await engine.search(value,50)
                    exact=[]
                    for record in result['results']:
                        r={str(k).lower():v for k,v in record.items()}
                        if any(str(r.get(k,'')).strip().casefold()==value.casefold() for k in ['secid','isin','shortname','name']):
                            if r.get('secid') and r.get('is_traded',1):exact.append(r['secid'])
                    candidates=set(exact)
                    if len(candidates)!=1:raise ValueError('Нет однозначного совпадения MOEX. Укажите точный тикер.')
                    meta=await engine.describe(candidates.pop())
                    if meta['asset_type']=='index':raise ValueError('Индекс не является бумагой.')
                    return value,canonical(meta),None
        except (ValueError,KeyError,TypeError,TimeoutError) as exc:
            return value,None,str(exc) or 'MOEX не ответила за 8 секунд.'
    result=await asyncio.gather(*(one(v) for v in values))
    return {'resolved':{v:m for v,m,e in result if m is not None},'errors':{v:e for v,m,e in result if e}}


def value_portfolio(events, market):
    state = ledger_state(events)
    missing = set(state['positions'])-set(market['marks'])
    if missing:
        return {'state':state, 'snapshot':None, 'errors':{s:market.get('errors',{}).get(s,'Нет котировки.') for s in missing}}
    try:snapshot=analyze_portfolio(events,market['marks'])
    except (ValueError,KeyError,TypeError) as exc:
        return {'state':state,'snapshot':None,'errors':{s:'Оценки несопоставимы по датам: '+str(exc) for s in state['positions']}}
    return {'state':state,'snapshot':snapshot,'errors':{},'warnings':market.get('warnings',{})}


def opening_event(day, holdings, cash):
    return validate_event({'date':str(day), 'kind':'opening', 'holdings':holdings, 'amount':cash, 'fee':0})


def advisor_context(snapshot, symbol, funding='existing_cash'):
    if snapshot is None: return None
    return {'equity':snapshot['equity'], 'cash':snapshot['cash'], 'funding':funding,
            'asset_value':sum(p['market_value'] for p in snapshot['positions'] if p['symbol']==symbol)}


def preview_change(records, event_id, replacement):
    if not any(r['id']==event_id for r in records): raise ValueError('Запись не найдена.')
    return ledger_state([replacement if r['id']==event_id else r['event'] for r in records if r['id']!=event_id or replacement is not None])
