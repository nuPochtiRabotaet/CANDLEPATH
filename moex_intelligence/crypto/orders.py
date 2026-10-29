"""Manual LOCAL PAPER prepare/confirm gateway, no remote execution capabilities.

30s immutable previews; exact account/rule/profile revisions, <=10bps price drift,
<=2bps spread widening. Check and posting share Paper's BEGIN IMMEDIATE lock.
"""
import hashlib,json,time,uuid
from .paper import Paper
from .inventory import inventory,validate_sale
from .costs import CostModel,estimate as cost_estimate,budget_quantity,basis
from .risk import D,PROFILE,RiskError,plan,quote_ok,floor_step

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def revision(s):return digest({k:s.get(k) for k in ('cash','positions','realized','initial','day','week','day_equity','week_equity','cost_model')})
def rule_revision(r):return digest({k:v for k,v in r.items() if k!='retrieved'})
def spread(q):return (D(q['ask'])-D(q['bid']))/((D(q['ask'])+D(q['bid']))/2)*10000

def sell_preview(state,quotes,symbol,quantity,rules,dispose_sellable=False):
    q=quotes.get(symbol,{})
    if not quote_ok(q):raise RiskError('Stale Data: нет свежего Bid/Ask')
    if not rules or not 0<=time.time()-rules.get('retrieved',0)<=86400:raise RiskError('Нет актуальных правил')
    qty=D(quantity);p=state['positions'].get(symbol)
    if not qty.is_finite() or qty<=0 or floor_step(qty,rules['step'])!=qty:raise RiskError('Некорректное количество / шаг')
    if not p or qty>D(p['qty']):raise RiskError('Количество превышает позицию')
    model=CostModel.from_state(state);actual=cost_estimate('SELL',qty,q,model);fill=actual.price;remaining=D(p['qty'])-qty
    try:allocation=validate_sale(p,qty,q,rules,model,dispose_sellable)
    except ValueError as e:raise RiskError(str(e)) from e
    if fill*qty<D(rules['minimum']):raise RiskError('Сумма ниже минимума')
    if rules.get('maximum') and qty>D(rules['maximum']):raise RiskError('Количество выше максимума')
    fee=actual.fee_quote_value;proceeds=actual.cash_delta
    return {'inventory':allocation,'remaining_quantity':str(remaining),'remaining_basis':str(basis(p)-basis(p)*qty/D(p['qty'])),'fill':actual.strings(),'cost_model':model.snapshot(),'allowed':True,'quantity':str(qty),'entry':float(fill),'amount':float(fill*qty),'fee':float(fee),'cash_after':float(D(state['cash'])+proceeds),'total':float(proceeds),'stop':p['stop'],'target':p['target'],'loss':None,'risk_pct':None,'pnl':float(proceeds-basis(p)*qty/D(p['qty']))}

class OrderPreview:
    def __init__(self,store):self.store=store;self.paper=Paper(store)
    def get(self,ident):
        with self.store.connect() as db:r=db.execute('SELECT body FROM intents WHERE id=?',(ident,)).fetchone()
        if not r:raise RiskError('Предпросмотр не найден')
        return json.loads(r[0])
    def prepare(self,request,quotes,rules,owner):
        try:return self._prepare(request,quotes,rules,owner)
        except (RiskError,ValueError,ArithmeticError) as exc:
            with self.store.connect() as db:db.execute('INSERT INTO events(time,body) VALUES(?,?)',(time.time(),json.dumps({'message':'Preview blocked: '+str(exc)})))
            raise
    def _prepare(self,request,quotes,rules,owner):
        if not owner:raise RiskError('Нет сессии')
        rid=str(request['id']);uuid.UUID(rid)
        symbol=request['symbol'];side=request['side'];q=quotes.get(symbol,{})
        if side not in ('BUY','SELL'):raise RiskError('Только spot BUY / SELL')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT body FROM intents WHERE id=?',(rid,)).fetchone()
            if old:
                intent=json.loads(old[0])
                if intent['owner']!=owner or intent.get('kind','order')!='order':raise RiskError('Другая сессия / тип действия')
                return intent
            state=json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0]);Paper.refresh(state,quotes)
            rule=rules.get(symbol)
            if not quote_ok(q) or not rule:raise RiskError('Нет свежей котировки / правил')
            qty=D(request['quantity'])
            if request.get('input_mode')=='amount' and side=='BUY':
                budget=D(request['budget'])
                if not budget.is_finite() or budget<=0:raise RiskError('Некорректная сумма')
                qty=budget_quantity(budget,q,rule['step'],CostModel.from_state(state),request.get('budget_mode','notional'))
            payload={'id':rid,'symbol':symbol,'side':side,'quantity':str(qty),'reason':'manual confirmed preview'}
            if side=='BUY':
                payload.update(stop=str(request['stop']),target=str(request['target']),risk_pct=float(request.get('risk_pct',.75)))
                estimate=plan(state,quotes,symbol,qty,payload['stop'],payload['target'],rule,payload['risk_pct'],portfolio_rules=rules)
                if not estimate['allowed']:raise RiskError('; '.join(estimate['errors']))
                payload['protection_residue_limit']=estimate['stop_inventory']['remaining_after_sale']
                selected=None;sid=request.get('signal_id');timeframe=str(request.get('timeframe','unknown'))
                if timeframe not in ('unknown','1','5','15','30','60','240','D'):raise RiskError('Неверный таймфрейм')
                if sid:
                    row=db.execute('SELECT body FROM lifecycle WHERE id=?',(str(sid),)).fetchone()
                    if not row:raise RiskError('Выбранный сигнал не найден')
                    selected=json.loads(row[0])
                    if selected.get('symbol')!=symbol or selected.get('type')!='BUY' or selected.get('timeframe')!=timeframe:raise RiskError('Другой инструмент, таймфрейм или тип сигнала')
                notes=str(request.get('notes','')).strip()
                if len(notes)>500:raise RiskError('Заметка длиннее 500 символов')
                payload['signal_id']=sid
                payload['trade_metadata']={'signal_id':sid,'signal_state_at_preview':selected.get('state') if selected else None,
                    'strategy':selected.get('strategy') if selected else 'Manual / no signal','timeframe':timeframe,
                    'entry_reason':str(request.get('entry_reason','Manual decision'))[:200],'notes':notes,
                    'initial_risk':estimate['costs']['loss'],'planned_net_rr':estimate['costs']['rr'],
                    'signal_snapshot':selected,'recorded_at':time.time()}

                estimate['total']=estimate['amount']+estimate['fee'] if estimate['fill']['fee_currency']=='quote' else estimate['amount']
                if request.get('input_mode')=='amount' and request.get('budget_mode')=='total':payload['max_spend']=str(request['budget'])
            else:
                payload['dispose_sellable']=request.get('dispose_sellable') is True
                estimate=sell_preview(state,quotes,symbol,qty,rule,payload['dispose_sellable'])
            now=time.time()
            intent={'id':rid,'owner':owner,'status':'Prepared','created':now,'expires':now+30,'request':payload,
                'estimate':estimate,'balance':state['cash'],'rules':rule,'rule_revision':rule_revision(rule),
                'account_revision':revision(state),'profile':digest(PROFILE),'quote':q,'spread_bps':str(spread(q)),
                'history':[{'status':'Prepared','time':now}],'input_mode':request.get('input_mode','quantity'),
                'budget_mode':request.get('budget_mode','notional'),'budget':request.get('budget'),'source':'LOCAL PAPER · '+q.get('source','public Bybit quote'),'max_drift_bps':10}
            db.execute('INSERT INTO intents VALUES(?,?)',(rid,json.dumps(intent)))
            db.execute('INSERT INTO events(time,body) VALUES(?,?)',(now,json.dumps({'message':'Order preview prepared','intent':rid,'symbol':symbol})))
            return intent
    def cancel(self,ident,owner):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT body FROM intents WHERE id=?',(ident,)).fetchone()
            if not r:raise RiskError('Предпросмотр не найден')
            i=json.loads(r[0])
            if i['owner']!=owner:raise RiskError('Другая сессия')
            if i['status']=='Prepared':
                i['status']='Cancelled';i['history'].append({'status':'Cancelled','time':time.time()});db.execute('UPDATE intents SET body=? WHERE id=?',(json.dumps(i),ident))
            return i
    def confirm(self,ident,owner,quotes,rules,ack=False):
        if ack is not True:raise RiskError('Подтвердите осознанный риск')
        intent=self.get(ident)
        if intent['owner']!=owner or intent.get('kind','order')!='order':raise RiskError('Другая сессия / тип действия')
        def guard(db,state):
            i=json.loads(db.execute('SELECT body FROM intents WHERE id=?',(ident,)).fetchone()[0]);r=i['request'];symbol=r['symbol'];q=quotes.get(symbol,{})
            if i['status']!='Prepared':raise RiskError('Предпросмотр недоступен: '+i['status'])
            if time.time()>i['expires']:raise RiskError('Предпросмотр истёк. Создайте новый')
            if not quote_ok(q):raise RiskError('Stale Data: требуется новый предпросмотр')
            rule=rules.get(symbol)
            if not rule or not 0<=time.time()-rule.get('retrieved',0)<=86400 or rule_revision(rule)!=i['rule_revision']:raise RiskError('Правила изменились: нужен новый предпросмотр')
            if revision(state)!=i['account_revision'] or digest(PROFILE)!=i['profile']:raise RiskError('Баланс, позиция или риск-профиль изменились: нужен новый предпросмотр')
            sidekey='ask' if r['side']=='BUY' else 'bid'
            if abs(D(q[sidekey])/D(i['quote'][sidekey])-1)*10000>D(i['max_drift_bps']) or spread(q)>D(i['spread_bps'])+2:raise RiskError('Цена / спред изменились: нужен новый предпросмотр')
            if r['side']=='BUY':
                p=plan(state,quotes,symbol,r['quantity'],r['stop'],r['target'],rule,r['risk_pct'],portfolio_rules=rules)
                if not p['allowed']:raise RiskError('; '.join(p['errors']))
                if r.get('max_spend') and D(p['costs']['total'])>D(r['max_spend']):raise RiskError('All-inclusive maximum spend exceeded; prepare again')
            else:sell_preview(state,quotes,symbol,r['quantity'],rule,r.get('dispose_sellable',False))
            i['status']='Confirmed';i['history'].append({'status':'Confirmed','time':time.time()});db.execute('UPDATE intents SET body=? WHERE id=?',(json.dumps(i),ident))
        try:return self.paper.execute(intent['request'],quotes,rules,guard=guard)
        except (RiskError,ArithmeticError) as exc:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                i=json.loads(db.execute('SELECT body FROM intents WHERE id=?',(ident,)).fetchone()[0])
                if i['status']=='Prepared':
                    i.update(status='Expired',error=str(exc));i['history'].append({'status':'Expired','time':time.time()});db.execute('UPDATE intents SET body=? WHERE id=?',(json.dumps(i),ident))
                db.execute('INSERT INTO events(time,body) VALUES(?,?)',(time.time(),json.dumps({'message':'Order blocked: '+str(exc),'intent':ident})))
            raise
