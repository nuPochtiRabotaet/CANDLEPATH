"""Fail-closed read-only 5m import; provenance cannot be upgraded by user text."""
import csv,hashlib,json
from pathlib import Path
from .forecast_evaluation import _closed_rows

# Original sealed interval; timestamps are boundaries, not scored prices.
ORIGINAL_SHA='3e93db2c4e06acd8f60134e398fb5ae93a9eac0a85fc65471f16cf3ee7c1d7d6'

def load_history(path, *, protected_interval=None):
    raw=Path(path).read_bytes();rows=[]
    for r in csv.DictReader(raw.decode('utf-8-sig').splitlines()):
        ms=int(r.get('timestamp_ms',r.get('open_time_ms')))
        if ms%300000:raise ValueError('Unaligned source milliseconds')
        if r.get('symbol','BTCUSDT')!='BTCUSDT' or r.get('timeframe','5') not in ('5','5m'):raise ValueError('Wrong market')
        rows.append(dict(time=ms//1000,**{k:float(r[k]) for k in ('open','high','low','close','volume')},closed=True))
    _closed_rows(rows,'5');end=len(rows)*80//100
    if end<200:raise ValueError('Insufficient development history')
    if protected_interval and any(protected_interval[0]<=r['time']<protected_interval[1] for r in rows[:end]):
        raise ValueError('Development would expose the original sealed holdout')
    seal=hashlib.sha256(json.dumps(rows[end:],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return rows,dict(sha256=hashlib.sha256(raw).hexdigest(),source='USER_SUPPLIED_CSV_UNVERIFIED',
        symbol='BTCUSDT',timeframe='5',rows=len(rows),development_end=end,sealed_sha256=seal,
        sealed_interval=[rows[end]['time'],rows[-1]['time']+300],sealed_evaluated=False)
