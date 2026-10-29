"""Market snapshots for the read-only lab; disk cache contains no portfolio events."""
from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import tempfile
from moex import identifier
from .data import get_engine, market_today
from .portfolio_service import asset_market_data
from .laboratory import asset_from_quote


class QuoteSnapshots:
    def __init__(self,directory):self.directory=Path(directory)
    def save(self,asset):
        if asset.get('manual') or asset.get('demo_data'):return
        self.directory.mkdir(parents=True,exist_ok=True)
        path=self.directory/(identifier(asset['symbol'])+'.json')
        asset=copy.deepcopy(asset)
        asset['snapshot_saved_at_utc']=datetime.now(timezone.utc).isoformat()
        asset['mark']['snapshot_saved_at_utc']=asset['snapshot_saved_at_utc']
        payload=json.dumps(asset,ensure_ascii=False,allow_nan=False,sort_keys=True)
        body=json.dumps({'asset':asset,'sha256':hashlib.sha256(payload.encode()).hexdigest()},ensure_ascii=False,allow_nan=False)
        if len(body)>64000:raise ValueError('Слишком большой снимок котировки.')
        fd,name=tempfile.mkstemp(prefix='.quote-',dir=self.directory)
        try:
            with os.fdopen(fd,'w') as f:f.write(body)
            os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)
    def load(self,symbol):
        path=self.directory/(identifier(symbol)+'.json')
        try:
            if path.stat().st_size>64000:return None
            stored=json.loads(path.read_text());value=stored['asset']
            payload=json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True)
            if hashlib.sha256(payload.encode()).hexdigest()!=stored.get('sha256'):return None
            if value.get('symbol')!=identifier(symbol) or value.get('manual') or value.get('demo_data'):return None
            # Revalidate all monetary fields and lot before offering cached content.
            from .laboratory import order_cost
            order_cost(value,0,0)
            stamp=datetime.fromisoformat(value['retrieved_at_utc'])
            if stamp.tzinfo is None or (stamp-datetime.now(timezone.utc)).total_seconds()>300:return None
            from .validation import finite
            if value.get('currency')!='RUB' or value.get('asset_type') not in {'equity','fund','bond'}:return None
            clean=finite(value['clean_price'],'clean',1e-8,1e12);accrued=finite(value['accrued_interest'],'accrued',0,1e12)
            if abs(value['unit_price']-clean-accrued)>max(1e-8,abs(clean)*1e-10):return None
            if value['asset_type']=='bond':finite(value['face_value'],'face',1e-8,1e12)
            if not value.get('source') or abs(value['mark']['price']-value['unit_price'])>1e-8:return None
            value=copy.deepcopy(value);value['saved_snapshot']=True
            # Preserve original valuation date, market time, retrieval and save time.
            value['mark']['saved_snapshot']=True
            value['mark']['price_type']=value.get('price_type','unknown')
            value['mark']['market_observed_at']=value.get('observed_at')
            value['mark']['valuation_basis']='Сохранённый снимок: '+value['retrieved_at_utc']+'; не текущая котировка'
            return value
        except (OSError,ValueError,KeyError,TypeError):return None


async def load_asset(symbol,cache=None,engine=None):
    symbol=identifier(symbol)
    try:
        async with asyncio.timeout(10):result=await asset_market_data(symbol,engine or get_engine())
        asset=asset_from_quote(result['quote'],result['mark'])
        # SYSTIME is an observed exchange snapshot time, not a fabricated trade date.
        asset['observation_kind']=result['mark'].get('observation_kind','unknown')
        if asset.get('observed_at') is None and asset['observation_kind']=='snapshot':
            asset['observed_at']=result['mark'].get('market_snapshot_at')
        if cache:
            try:cache.save(asset)
            except (OSError,ValueError):pass  # A cache write cannot invalidate valid live data.
        return {'asset':asset,'error':None}
    except (ValueError,KeyError,TypeError,TimeoutError) as exc:
        error=str(exc) or 'MOEX не ответила за 10 секунд.'
        cached=cache.load(symbol) if cache else None
        return {'asset':cached,'error':error,'using_saved_snapshot':cached is not None}
