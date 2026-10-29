"""Advisory policy, independent from regime, signals and execution permission."""
from dataclasses import dataclass,asdict
import math,time
from .risk import quote_ok
@dataclass(frozen=True)
class QualityPolicy:
    version:str='quality-v1'
    min_net_rr:float=1.0
    max_spread_bps:float=20.0
    def __post_init__(self):
        if not self.version or not math.isfinite(self.min_net_rr) or not 0<=self.min_net_rr<=10 or not math.isfinite(self.max_spread_bps) or not 0<self.max_spread_bps<=500:raise ValueError('Invalid quality policy')
def assess(regime,signal,preview,quote,error='',policy=None,now=None):
    policy=policy or QualityPolicy();now=time.time() if now is None else now
    codes=[];reasons=[];attention='Review Setup';stage=signal.get('state','NO_SIGNAL')
    def flag(code,reason,action='No Trade'):
        nonlocal attention
        codes.append(code);reasons.append(reason)
        if attention!='No Trade':attention=action
    if not quote_ok(quote,now):flag('STALE_QUOTE','Нет согласованного свежего Bid/Ask')
    if not preview:flag('INVALID_PLAN',error or 'Недостаточно данных для расчёта')
    elif not preview['allowed']:flag('RISK_REJECTED','; '.join(preview['errors']))
    if preview and not preview.get('exit_closeable',True):flag('EXIT_PRECISION','Правила допускают продажу лишь части остатка; локальная защита не покрывает весь актив')
    costs=(preview or {}).get('costs',{})
    if costs and float(costs['rr'])<policy.min_net_rr:flag('LOW_NET_RR','Net R/R ниже выбранного порога после издержек')
    if costs and float(costs['spread_bps'])>policy.max_spread_bps:flag('WIDE_SPREAD','Спред превышает выбранный порог')
    if stage in ('EXPIRED','INVALIDATED') or (signal.get('expiration') and now>=signal['expiration']):flag('SIGNAL_EXPIRED',signal.get('reason','Сигнал неактуален'))
    if signal.get('maximum_entry_price') and quote.get('price',0)>signal['maximum_entry_price']:flag('PRICE_DRIFT','Opportunity Missed: цена выше диапазона входа')
    if stage not in ('ACTIONABLE','CONFIRMED'):flag('AWAITING_CONFIRMATION','Нет текущего подтверждённого входа','Wait')
    codes.append('EDGE_NOT_VALIDATED');reasons.append('Statistical edge not validated')
    return {'regime':'Sideways' if regime=='Range' else regime,'signal':stage,'quality':'Poor Entry Conditions' if attention=='No Trade' else 'Within policy' if attention=='Review Setup' else 'Awaiting confirmation','attention':attention,'codes':codes,'reasons':reasons,'policy':asdict(policy),'calculated_at':now,'confirmed_at':signal.get('confirmed_at'),'age_seconds':max(0,now-signal['first_seen']) if signal.get('first_seen') else None,'costs':costs,'statistical_edge':None,'advisory_only':True}
