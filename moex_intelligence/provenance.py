"""Shared price provenance. Reading a cache never creates a market observation."""
from datetime import datetime,date
from zoneinfo import ZoneInfo
from .data import market_today

MOSCOW=ZoneInfo('Europe/Moscow')


def display_time(value):
    if not value:return 'неизвестно'
    raw=str(value)
    try:
        if len(raw)==10:return date.fromisoformat(raw).strftime('%d.%m.%Y')
        stamp=datetime.fromisoformat(raw.replace('Z','+00:00'))
        if stamp.tzinfo:return stamp.astimezone(MOSCOW).strftime('%d.%m.%Y %H:%M МСК')
        return stamp.strftime('%d.%m.%Y %H:%M')+' (пояс не сообщён)'
    except ValueError:return raw


def describe_price(value):
    if not value:return {'state':'missing','kind':'missing','label':'Цена не получена','short':'Нет цены','critical':True,'observed_at':None,'age_days':None,'retrieved_at':None,'saved_at':None,'valuation_as_of':None}
    mark=value.get('mark',value)
    explicit_asset_time='mark' in value and 'observed_at' in value
    observed=value['observed_at'] if explicit_asset_time else mark.get('market_observed_at') or mark.get('observed_as_of')
    # Legacy exchange_time may be an update rather than a trade. Never substitute as_of/retrieval.
    if not observed and not explicit_asset_time and 'market_observed_at' not in mark:observed=mark.get('exchange_time')
    saved=bool(value.get('saved_snapshot') or mark.get('saved_snapshot'))
    manual=bool(value.get('manual') or mark.get('manual'))
    synthetic=bool(value.get('demo_data') or mark.get('demo_data'))
    price_type=value.get('price_type') or mark.get('price_type') or ('daily_close' if mark.get('observed_as_of') else 'unknown')
    age=None
    try:age=(market_today()-date.fromisoformat(str(observed)[:10])).days
    except (ValueError,TypeError):pass
    kind='demo' if synthetic else 'manual' if manual else 'saved' if saved else 'historical' if price_type=='daily_close' else 'delayed'
    state=kind
    if not (synthetic or manual or saved):
        if age is None:state='unknown_age'
        elif age<0 or age>7:state='stale'
    names={'demo':'Учебные данные','manual':'Ручная сценарная цена','saved':'Сохранённая цена','historical':'Историческое закрытие','delayed':'Последняя доступная цена MOEX · возможна задержка','unknown_age':'Время наблюдения неизвестно','stale':'Устаревшая цена'}
    label=names[state]
    if saved and age is not None and (age<0 or age>7):label+=' · устарела'
    return {'state':state,'kind':kind,'label':label,'short':label,'critical':state in {'missing','manual','saved','stale','unknown_age'},
            'observed_at':observed,'observed_display':display_time(observed),'age_days':age,
            'retrieved_at':value.get('retrieved_at_utc') or mark.get('retrieved_at_utc'),
            'saved_at':value.get('snapshot_saved_at_utc') or mark.get('snapshot_saved_at_utc'),
            'valuation_as_of':mark.get('valuation_as_of') or mark.get('as_of'),
            'source':value.get('source') or mark.get('source'),'price_type':price_type,
            'observation_kind':value.get('observation_kind') or mark.get('observation_kind','unknown'),
            'trade_at':mark.get('market_trade_at'),'trade_clock':mark.get('last_trade_clock'),
            'snapshot_at':mark.get('market_snapshot_at')}


def asset_mark(asset):
    """Compatibility mark for the unchanged ledger, with explicit price provenance."""
    return {**asset['mark'],'manual':bool(asset.get('manual')),'saved_snapshot':bool(asset.get('saved_snapshot')),
            'demo_data':bool(asset.get('demo_data')),'price_type':asset.get('price_type','unknown'),
            'market_observed_at':asset.get('observed_at'),'observation_kind':asset.get('observation_kind') or asset['mark'].get('observation_kind','unknown'),'snapshot_saved_at_utc':asset.get('snapshot_saved_at_utc')}
