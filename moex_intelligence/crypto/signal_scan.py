"""Read-only scan completeness for Bybit Spot; never a trading decision.

Adapted idea: audit the requested universe before confirming candidates. Reuses
CandlePath's existing candle validator and strategies, with no NYSE calendar,
new thresholds, subscriptions, order methods or historical outcome scoring.
"""
import math
from collections import Counter
from .analysis import analyze
from .forecast_evaluation import _closed_rows
from .market import Bybit, seconds


def scan_candidates(snapshots, symbols, timeframe, *, now):
    """Count every requested symbol, including unavailable/excluded candidates.

    Snapshot data after the decision cutoff is never analyzed. Observation times
    are enforced when present; absent receipt logs are explicitly unknown. The
    freshness diagnostic allows at most two bar intervals since the last close;
    it does not replace the independent quote/rules/confirmation execution gate.
    """
    if not isinstance(snapshots, dict) or not isinstance(symbols, (list, tuple)) or not symbols or len(set(symbols)) != len(symbols):
        raise ValueError('Expected unique requested symbols and snapshot mapping')
    if isinstance(now, bool) or not isinstance(now, (int,float)) or not math.isfinite(now) or now <= 0:
        raise ValueError('Invalid scan cutoff')
    for symbol in symbols:
        Bybit.validate(symbol,timeframe)
    step=seconds(timeframe)
    candidates=[]; exclusions=[]; examined=0; forming=0; future=0
    for symbol in symbols:
        snapshot=snapshots.get(symbol)
        if not isinstance(snapshot,dict) or not snapshot.get('candles'):
            exclusions.append({'symbol':symbol,'code':'MISSING_HISTORY','reason':'Нет истории свечей'});continue
        rows=[];local_forming=0;local_future=0
        try:
            if snapshot.get('symbol',symbol)!=symbol or snapshot.get('interval',timeframe)!=timeframe:
                raise ValueError('Snapshot identity differs from requested market')
            for raw in snapshot['candles']:
                moment=raw['time']
                if type(moment) is not int or moment < 0 or moment % step:
                    raise ValueError('Invalid candle UTC boundary')
                if moment+step>now:
                    local_future+=1;continue
                if raw.get('closed') is False:
                    local_forming+=1
                    # An old bar still not confirmed is a gap, not a safe deletion.
                    if moment+step<=now-step:raise ValueError('Unconfirmed historical candle')
                    continue
                if raw.get('closed') is not True:raise ValueError('Invalid closed flag')
                for field in ('observed_at','available_at'):
                    if field in raw:
                        value=raw[field]
                        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<moment+step:
                            raise ValueError('Invalid candle availability')
                        if value>now:break
                else:
                    rows.append(raw);continue
                local_future+=1
            _closed_rows(rows,timeframe)  # existing OHLCV/continuity validator
            if len(rows)<56:
                exclusions.append({'symbol':symbol,'code':'INSUFFICIENT_SAMPLE','reason':'Для существующей аналитики нужно не менее 56 закрытых свечей'});continue
            if now-(rows[-1]['time']+step)>2*step:
                exclusions.append({'symbol':symbol,'code':'STALE_HISTORY','reason':'Последняя закрытая свеча устарела'});continue
            # No prefilter invents a second signal algorithm; stage two is the
            # existing causal analyzer on exactly the available closed prefix.
            result=analyze(rows,symbol,timeframe)
            signals=result['signals']
            if any(s['timestamp']>now or s['timestamp']!=s['candle_time']+step for s in signals):
                raise ValueError('Analyzer produced a signal before candle confirmation')
            candidates.append({'symbol':symbol,'closed_bars':len(rows),'last_close_at':rows[-1]['time']+step,
                'receipt_time_known':all('observed_at' in r and 'available_at' in r for r in rows),
                'signals':signals,'latest_signal_at':max((s['timestamp'] for s in signals),default=None)})
            examined+=1
        except (ValueError,TypeError,KeyError,ArithmeticError) as exc:
            exclusions.append({'symbol':symbol,'code':'INVALID_HISTORY','reason':str(exc)})
        finally:
            forming+=local_forming;future+=local_future
    requested=len(symbols)
    return {'status':'COMPLETE' if examined==requested else 'PARTIAL' if examined else 'INCOMPLETE',
        'cutoff':now,'timeframe':timeframe,'requested':requested,'scanned':examined,'excluded':len(exclusions),
        'forming_or_unavailable_bars':forming+future,'exclusion_counts':dict(Counter(x['code'] for x in exclusions)),
        'exclusions':exclusions,'candidates':candidates,'execution_authorized':False,
        'note':'Обнаружение исторических BUY/EXIT, не разрешение входа. Preview → Confirm и Risk Manager обязательны. Время получения без receipt log неизвестно.'}
