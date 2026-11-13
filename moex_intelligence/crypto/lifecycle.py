"""Persistent causal signal lifecycle. No execution calls and no success probabilities."""
import copy,json,time,hashlib
from .analysis import analyze,PARAMS,VERSION
from .market import seconds
from .orders import sell_preview
from .risk import plan,floor_step,quote_ok
TTL_BARS={'Trend Following':1,'Mean Reversion':2,'Breakout Detection':1}
TERMINAL={'EXPIRED','INVALIDATED'}

def provisional(rows,symbol,interval,*,evaluated=None):
    if not rows or rows[-1]['closed']:return []
    # Same formulas, explicit provisional status; never fake a closed candle.
    evaluated=evaluated if evaluated is not None else analyze(rows,symbol,interval,include_forming=True,latest_only=True)
    signals=[dict(s,status='POTENTIAL') for s in evaluated['signals'] if s['candle_time']==rows[-1]['time']]
    if signals:return signals
    if evaluated['overlay']:
        o=evaluated['overlay'][-1];price=rows[-1]['close'];atr=(o['upper']-o['lower'])
        if atr>0 and o['fast']>o['slow'] and abs(price-o['fast'])<=atr*.5:
            key=f'{symbol}:{interval}:Trend Following:{VERSION}:{rows[-1]["time"]}:BUY'
            return [{'id':hashlib.sha256(key.encode()).hexdigest()[:24],'symbol':symbol,'timeframe':interval,'strategy':'Trend Following','strategy_version':VERSION,'type':'BUY','status':'WATCHING','candle_time':rows[-1]['time'],'timestamp':rows[-1]['time']+seconds(interval),'reference_price':price,'risk_estimates':{'stop':price-2*atr,'target':price+4*atr},'explanation':['Цена в пределах 0,5 ATR от EMA21; EMA21 выше EMA55. Полные условия BUY ещё не выполнены.']}]
    return []

class SignalLifecycle:
    def __init__(self,store):self.store=store
    def observe(self,confirmed,potential,symbol,interval,*,now=None,fresh=True,source=None,event_time=None):
        """Feed-side observation only: no portfolio access or risk/execution calls."""
        return self.update(confirmed,potential,symbol,interval,{},'Uncertain',{},None,'0',
                           now=now,candle_fresh=fresh,observe_only=True,
                           source=source,event_time=event_time)
    def update(self,confirmed,potential,symbol,interval,quote,regime,state,rules,quantity,risk_pct=.75,now=None,candle_fresh=True,portfolio_quotes=None,portfolio_rules=None,observe_only=False,observe=True,source=None,event_time=None,as_of=None):
        now=time.time() if now is None else now;duration=seconds(interval)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            records={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,body FROM lifecycle')}
            def event(rec,status,reason):
                if rec.get('state')!=status:
                    rec['state']=status;rec['reason']=reason;rec['changed_at']=now
                    rec['transitions']=(rec.get('transitions',[])+[{'state':status,'at':now,'reason':reason}])[-32:]
                    if status=='INVALIDATED' and rec.get('confirmed_at') is None:
                        rec['preliminary_cancellations']=rec.get('preliminary_cancellations',0)+1
                    # At most one notification per state per candle/strategy, including flicker.
                    nid=rec['id']+':'+status
                    if not rec.get('historical'):
                        db.execute('INSERT OR IGNORE INTO notifications VALUES(?,?,?)',(nid,now,json.dumps({'id':nid,'symbol':symbol,'timeframe':interval,'state':status,'type':rec['type'],'message':reason},ensure_ascii=False)))
                else:rec['reason']=reason
            seen=set()
            for sig in (potential+confirmed if observe else []):
                if sig['symbol']!=symbol or sig['timeframe']!=interval:continue
                is_confirmed=sig.get('status')=='confirmed'
                if is_confirmed and (sig['timestamp']>now or sig['timestamp']!=sig['candle_time']+duration):continue
                if not is_confirmed and not candle_fresh:continue
                if not is_confirmed and not sig['candle_time']<=now<sig['candle_time']+duration:continue
                seen.add(sig['id']);rec=records.get(sig['id'])
                if rec is not None and now<rec.get('last_validated_at',0):continue
                if rec is None:
                    rec={**sig,'state':'NO_SIGNAL','first_seen':now,'historical':is_confirmed and now-sig['timestamp']>60,'confirmed_at':None}
                    records[sig['id']]=rec
                if rec['confirmed_at'] is None:
                    rec.update({k:v for k,v in sig.items() if k not in ('state','first_seen')})
                    if source:rec['source']=source
                    rec['observed_at']=now;rec['observed_price']=sig.get('reference_price')
                    rec['source_event_at']=event_time
                    if sig.get('status')=='POTENTIAL' and rec.get('potential_detected_at') is None:
                        rec['potential_detected_at']=now
                        rec['first_potential_price']=sig.get('reference_price')
                    if is_confirmed:
                        rec['confirmed_at']=now;rec['available_at']=now
                        atr=max(0,(sig['reference_price']-sig['risk_estimates']['stop'])/2)
                        rec.update(expiration=sig['timestamp']+duration*TTL_BARS[sig['strategy']],maximum_entry_price=sig['reference_price']+.5*atr,
                                   minimum_entry_price=sig['reference_price']-.25*atr,invalidation_price=sig['risk_estimates']['stop'])
                        event(rec,'CONFIRMED','Условия подтверждены закрытой свечой; обнаружено сейчас')
                    else:event(rec,sig['status'],'Potential '+sig['type']+' — Awaiting Confirmation' if sig['status']=='POTENTIAL' else 'Наблюдение: условия стратегии приближаются')
            relevant=[]
            for rec in records.values():
                if rec['symbol']!=symbol or rec['timeframe']!=interval:continue
                if as_of is not None and rec.get('observed_at',rec.get('first_seen',0))>as_of:continue
                if now<rec.get('last_validated_at',0):continue
                rec['last_validated_at']=now
                if rec['confirmed_at'] is None:
                    if observe and rec['id'] not in seen:event(rec,'INVALIDATED','Предварительные условия исчезли; подтверждения нет')
                    elif not candle_fresh or now>=rec['timestamp']:event(rec,'INVALIDATED','Нет свежей текущей свечи; предварительный сигнал снят')
                elif not observe_only and rec['state'] not in TERMINAL:
                    price=quote.get('price',0);ref=rec['reference_price'];rec['price_drift']=price/ref-1 if price and ref else None
                    if now>=rec['expiration'] or rec.get('historical'):event(rec,'EXPIRED','Исторический сигнал / истёк срок входа')
                    elif not quote_ok(quote,now) or not candle_fresh:event(rec,'CONFIRMED','Ожидание свежего рынка; Actionable запрещён')
                    elif rec['type']=='EXIT':
                        held=state['positions'].get(symbol)
                        if not held:
                            event(rec,'CONFIRMED','Потенциальный выход; позиция отсутствует')
                        else:
                            try:
                                # Readiness is for the selected manual quantity, not
                                # gross holdings. Reuse Paper's read-only sale gate;
                                # never prepare or execute an order from a signal.
                                sell_preview(state,{symbol:quote},symbol,quantity,rules,now=now)
                                event(rec,'ACTIONABLE','Выход выбранным количеством проверен; требуется Paper Preview → Confirm. Продажа не исполнена')
                            except (ValueError,ArithmeticError,KeyError,TypeError) as exc:
                                event(rec,'REJECTED_BY_RISK',str(exc))
                    elif price<=rec['invalidation_price']:event(rec,'INVALIDATED','Нарушен уровень отмены гипотезы')
                    elif price>rec['maximum_entry_price']:event(rec,'EXPIRED','Opportunity Missed — цена выше диапазона входа')
                    elif regime in ('Bearish','High Volatility') or (rec['strategy']=='Mean Reversion' and regime!='Range'):event(rec,'INVALIDATED','Режим рынка несовместим с гипотезой')
                    elif price<rec['minimum_entry_price']:event(rec,'CONFIRMED','Цена вне диапазона входа; ожидание')
                    else:
                        try:
                            if not rules:raise ValueError('Нет правил инструмента')
                            result=plan(state,portfolio_quotes or {symbol:quote},symbol,quantity,floor_step(rec['risk_estimates']['stop'],rules['tick']),floor_step(rec['risk_estimates']['target'],rules['tick']),rules,risk_pct,now,portfolio_rules=portfolio_rules)
                            rec['quality']=result
                            event(rec,'ACTIONABLE' if result['allowed'] else 'REJECTED_BY_RISK','Риск выбранного количества проверен' if result['allowed'] else '; '.join(result['errors']))
                        except (ValueError,ArithmeticError,KeyError,TypeError) as exc:event(rec,'REJECTED_BY_RISK',str(exc))
                db.execute('INSERT OR REPLACE INTO lifecycle VALUES(?,?)',(rec['id'],json.dumps(rec,ensure_ascii=False,allow_nan=False)))
                relevant.append(rec)
            rank={'ACTIONABLE':5,'POTENTIAL':4,'WATCHING':3,'CONFIRMED':2,'REJECTED_BY_RISK':2,'EXPIRED':0,'INVALIDATED':0}
            relevant.sort(key=lambda x:(rank.get(x['state'],0),x['candle_time']))
            active=relevant[-1] if relevant else {'state':'NO_SIGNAL','reason':'Подходящих условий нет','type':None}
            notifications=[dict(time=t,**json.loads(body)) for t,body in db.execute('SELECT time,body FROM notifications ORDER BY time DESC LIMIT 100')]
        return {'active':active,'notifications':notifications,'records':relevant[-100:],'diagnostics':{'observed_preliminaries':sum(r.get('potential_detected_at') is not None for r in relevant),'cancelled_preliminaries':sum(r.get('preliminary_cancellations',0) for r in relevant)}}
