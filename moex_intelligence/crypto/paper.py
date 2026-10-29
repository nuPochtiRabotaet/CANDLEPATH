"""Local, persisted virtual executions. No network order API is present."""
import copy,json,time,uuid,os
from datetime import datetime,timezone
from typing import Protocol
from .costs import CostModel,estimate,SimulatedFill,basis
from .risk import D,RiskError,plan,metrics,quote_ok,floor_step
from .inventory import inventory,validate_sale,position_revision
from .performance import record_equity

TRANSITIONS={'Created':{'Submitted','Cancelled'},'Submitted':{'Accepted','Rejected','Cancelled'},'Accepted':{'Partially Filled','Filled','Cancelled','Rejected'},'Partially Filled':{'Partially Filled','Filled','Cancelled'},'Filled':set(),'Rejected':set(),'Cancelled':set()}
def transition(order,status):
    if status not in TRANSITIONS[order['status']]:raise ValueError('Invalid order transition')
    order['status']=status;order['history'].append({'status':status,'time':time.time()})
class ExecutionAdapter(Protocol):
    def submit(self,request):...
    def reconcile(self,exchange_event):...
class LiveExecutionDisabled:
    def submit(self,request):raise RiskError('Real trading is disabled in v0.8')
    def reconcile(self,exchange_event):raise RiskError('Real trading is disabled in v0.8')

def periods(now=None):
    d=datetime.fromtimestamp(time.time() if now is None else now,timezone.utc)
    iso=d.isocalendar();return d.strftime('%Y-%m-%d'),f'{iso.year}-{iso.week}'
def new_state(capital):
    c=D(capital)
    if not c.is_finite() or not 0<c<=D('1000000000000'):raise RiskError('Некорректный виртуальный капитал')
    day,week=periods()
    return {'cash':str(c),'initial':str(c),'peak':str(c),'realized':'0','last_equity':str(c),'positions':{},'day':day,'week':week,'day_equity':str(c),'week_equity':str(c)}
class Paper:
    def __init__(self,store,capital=None):
        self.store=store
        with store.connect() as db:db.execute('INSERT OR IGNORE INTO paper VALUES(1,?)',(json.dumps(new_state(capital if capital is not None else os.getenv('MOEX_PAPER_CAPITAL','10000'))),))
    def configure_costs(self,model,policy=None):
        if not isinstance(model,CostModel):raise RiskError('Invalid cost model')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');s=json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0]);s['cost_model']=model.snapshot()
            if policy:
                from dataclasses import asdict
                s['quality_policy']=asdict(policy)
            db.execute('UPDATE paper SET body=? WHERE id=1',(json.dumps(s),))
            db.execute('INSERT INTO events(time,body) VALUES(?,?)',(time.time(),json.dumps({'message':'Paper cost assumptions updated','cost_model':model.snapshot()})))
    def state(self):
        with self.store.connect() as db:return json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0])
    @staticmethod
    def refresh(s,quotes):
        m=metrics(s,quotes)
        # Never reset risk periods or high-water mark with incomplete market valuation.
        if not m['missing_quotes']:
            eq=D(m['equity_decimal']);s['peak']=str(max(D(s['peak']),eq))
            for key,p in zip(('day','week'),periods()):
                if s[key]!=p:s[key]=p;s[key+'_equity']=s.get('last_equity',str(eq))
            s['last_equity']=str(eq)
        return s
    def mark(self,quotes):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');s=json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0]);self.refresh(s,quotes);db.execute('UPDATE paper SET body=? WHERE id=1',(json.dumps(s),));record_equity(db,s,quotes)
        return s
    def execute(self,request,quotes,rules,*,guard=None):
        rid=str(request.get('id',''))
        try:uuid.UUID(rid)
        except ValueError:raise RiskError('Требуется уникальный ID действия')
        sym=request['symbol'];side=request['side'];q=quotes.get(sym,{})
        if side not in ('BUY','SELL'):raise RiskError('Только spot BUY / SELL')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT body FROM orders WHERE id=?',(rid,)).fetchone()
            if old:return json.loads(old[0])
            s=json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0]);self.refresh(s,quotes)
            if guard:guard(db,s)
            o={'id':rid,'symbol':sym,'side':side,'status':'Created','history':[{'status':'Created','time':time.time()}],'source':'LOCAL PAPER','time':time.time(),'reason':request.get('reason','manual')}
            transition(o,'Submitted')
            before_execution=copy.deepcopy(s)
            try:
                if not quote_ok(q):raise RiskError('Connection Lost / Stale Data')
                if request.get('protective_position'):
                    current=s['positions'].get(sym)
                    if not current or position_key(sym,current)!=request['protective_position']:raise RiskError('Защищаемая позиция уже закрыта или заменена')
                    if not (D(q['bid'])<=D(current['stop']) or D(q['bid'])>=D(current['target'])):raise RiskError('Защитное условие больше не выполнено')
                    rule_now=rules.get(sym)
                    if not rule_now:raise RiskError('Нет правил инструмента')
                    coverage=inventory(current['qty'],q,rule_now,CostModel.from_state(s))
                    if D(coverage['remaining_after_sale'])>D(current.get('protection_residue_limit','0')):raise RiskError('Правила изменили покрытие защиты: обновите правила или подтвердите новые уровни и остаток')
                    qty=D(coverage['sellable_quantity'])
                else:qty=D(request['quantity'])
                if not qty.is_finite() or qty<=0:raise RiskError('Некорректное количество')
                rule=rules.get(sym)
                if not rule or not 0<=time.time()-rule.get('retrieved',0)<=86400:raise RiskError('Нет актуальных правил')
                if floor_step(qty,rule['step'])!=qty:raise RiskError('Количество не кратно шагу')
                model=CostModel.from_state(s);actual=estimate(side,qty,q,model);fill=actual.price;fee=actual.fee_quote_value
                if side=='BUY':
                    p=plan(s,quotes,sym,qty,request['stop'],request['target'],rule,request.get('risk_pct',.75),portfolio_rules=rules)
                    if not p['allowed']:raise RiskError('; '.join(p['errors']))
                    if request.get('max_spend') and -actual.cash_delta>D(request['max_spend']):raise RiskError('All-inclusive maximum spend exceeded; prepare again')
                    meta=copy.deepcopy(request.get('trade_metadata',{}))
                    if meta.get('signal_id'):
                        row=db.execute('SELECT body FROM lifecycle WHERE id=?',(meta['signal_id'],)).fetchone()
                        current_signal=json.loads(row[0]) if row else {}
                        meta['signal_state']=current_signal.get('state','Unknown');meta['signal_at_fill']=current_signal
                    meta['filled_at']=time.time()
                    s['cash']=str(D(s['cash'])+actual.cash_delta)
                    s['positions'][sym]={'qty':str(actual.net_base),'entry':str(fill),'entry_fee':str(actual.fee_quantity if actual.fee_currency=='quote' else D(0)),
                        'protection_residue_limit':str(request.get('protection_residue_limit','0')),'cost_basis':str(-actual.cash_delta),'effective_entry':str(-actual.cash_delta/actual.net_base),'entry_cost_model':model.snapshot(),
                        'stop':p['stop'],'target':p['target'],'opened':time.time(),'position_id':rid,'signal_id':request.get('signal_id'),'trade_metadata':meta}
                    o['position_id']=position_key(sym,s['positions'][sym]);o['trade_metadata']=meta
                else:
                    if sym not in s['positions']:raise RiskError('Нет позиции для закрытия')
                    position=s['positions'][sym];held=D(position['qty'])
                    if qty>held:raise RiskError('Количество превышает позицию; short запрещён')
                    remaining=held-qty
                    allocation=validate_sale(position,qty,q,rule,model,request.get('dispose_sellable') is True or bool(request.get('protective_position')))
                    o['inventory_before']=allocation;o['remaining_quantity']=str(remaining)
                    if fill*qty<D(rule['minimum']):raise RiskError('Сумма закрытия меньше биржевого минимума')
                    if rule.get('maximum') and qty>D(rule['maximum']):raise RiskError('Превышен максимум заявки')
                    o['position_id']=position_key(sym,position);o['duration_seconds']=time.time()-position['opened'];o['signal_id']=position.get('signal_id')
                    entry_fee=D(position['entry_fee'])*qty/held
                    allocated=basis(position) if qty==held else basis(position)*qty/held
                    pnl=actual.cash_delta-allocated;o['allocated_basis']=str(allocated)
                    s['realized']=str(D(s['realized'])+pnl);s['cash']=str(D(s['cash'])+actual.cash_delta);o['realized']=str(pnl)
                    if qty==held:del s['positions'][sym]
                    else:
                        remaining_basis=basis(position)-allocated
                        position['qty']=str(held-qty);position['entry_fee']=str(D(position['entry_fee'])-entry_fee);position['cost_basis']=str(remaining_basis)
                o['execution']=SimulatedFill(actual,model).snapshot();o['execution']['quote']={k:q.get(k) for k in ('bid','ask','price','ts','bid_ts','ask_ts')};o['net_received']=str(actual.net_base if side=='BUY' else actual.cash_delta);o['cash_delta']=str(actual.cash_delta)
                transition(o,'Accepted');o.update(quantity=str(qty),fill=str(fill),fee=str(fee),filled_quantity=str(qty));transition(o,'Filled')
            except (ValueError,KeyError,ArithmeticError) as e:
                s=before_execution
                transition(o,'Rejected');o['error']=str(e)
            if o['status']=='Filled':record_equity(db,s,quotes,force=True)
            db.execute('INSERT INTO orders VALUES(?,?)',(rid,json.dumps(o,ensure_ascii=False)))
            db.execute('UPDATE paper SET body=? WHERE id=1',(json.dumps(s),))
            db.execute('INSERT INTO events(time,body) VALUES(?,?)',(time.time(),json.dumps({'order':rid,'symbol':sym,'status':o['status'],'message':o.get('error',side+' · LOCAL PAPER')},ensure_ascii=False)))
            if guard:
                row=db.execute('SELECT body FROM intents WHERE id=?',(rid,)).fetchone()
                intent=json.loads(row[0]);intent['status']=o['status'];intent['history']+=o['history'][1:]
                db.execute('UPDATE intents SET body=? WHERE id=?',(json.dumps(intent),rid))
        return o
    def protect(self,quotes,rules):
        now=time.time()
        state=self.state();model=CostModel.from_state(state)
        for sym,p in state['positions'].items():
            q=quotes.get(sym,{})
            if not quote_ok(q):continue
            if not (D(q['bid'])<=D(p['stop']) or D(q['bid'])>=D(p['target'])):continue
            obligation=position_key(sym,p);rule=rules.get(sym) or {}
            fingerprint=json.dumps({'rules':{k:rule.get(k) for k in ('step','tick','minimum','maximum')},
                'rules_valid':0<=now-rule.get('retrieved',0)<=86400,'quantity':p['qty'],'stop':p['stop'],'target':p['target'],
                'cost_model':model.snapshot(),'minimum_ok':estimate('SELL',p['qty'],q,model).notional>=D(rule.get('minimum','Infinity'))},sort_keys=True)
            # Claim an attempt atomically. A crashed in-flight attempt reuses its UUID after its lease.
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT body FROM protective WHERE id=?',(obligation,)).fetchone()
                a=json.loads(row[0]) if row else {'attempt':0,'status':'new','next_at':0,'fingerprint':''}
                if a['status']=='Filled' and fingerprint==a['fingerprint']:continue
                if a['status']=='pending' and now<a['next_at']:continue
                if a['status']!='pending':
                    if now<a['next_at'] and fingerprint==a['fingerprint']:continue
                    a['attempt']+=1;a['order_id']=str(uuid.uuid5(uuid.NAMESPACE_URL,obligation+':'+str(a['attempt'])))
                a.update(status='pending',next_at=now+30,fingerprint=fingerprint)
                db.execute('INSERT OR REPLACE INTO protective VALUES(?,?)',(obligation,json.dumps(a)))
            reason='virtual stop' if D(q['bid'])<=D(p['stop']) else 'virtual target'
            result=self.execute({'id':a['order_id'],'symbol':sym,'side':'SELL','quantity':p['qty'],
                'reason':reason,'protective_position':obligation},quotes,rules)
            with self.store.connect() as db:
                a.update(status=result['status'],last_error=result.get('error'),next_at=now+min(300,30*2**min(a['attempt']-1,4)))
                db.execute('UPDATE protective SET body=? WHERE id=?',(json.dumps(a),obligation))
        return self.protection_status()

    def protection_status(self):
        with self.store.connect() as db:return [dict(id=r[0],**json.loads(r[1])) for r in db.execute('SELECT id,body FROM protective')]

    def write_off_dust(self,symbol,request_id,confirmed=False,*,expected_position=None,quotes=None,rules=None):
        """Explicit local accounting loss, NEVER a simulated exchange fill."""
        if confirmed is not True:raise RiskError('Требуется явное подтверждение списания всего остатка в убыток')
        uuid.UUID(request_id)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT body FROM orders WHERE id=?',(request_id,)).fetchone()
            if previous:return json.loads(previous[0])
            s=json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0]);p=s['positions'].get(symbol)
            if not p:raise RiskError('Позиция отсутствует')
            if expected_position and position_revision(p)!=expected_position:raise RiskError('Позиция изменилась: подтвердите остаток заново')
            if quotes is not None and rules is not None:
                if not quote_ok(quotes.get(symbol,{})) or not rules.get(symbol) or not 0<=time.time()-rules[symbol].get('retrieved',0)<=86400:raise RiskError('Нужны свежие котировки и правила')
                if D(inventory(p['qty'],quotes[symbol],rules[symbol],CostModel.from_state(s))['sellable_quantity'])>0:raise RiskError('Сначала продайте доступное количество; это не dust')
            loss=basis(p)
            s['realized']=str(D(s['realized'])-loss);del s['positions'][symbol]
            o={'id':request_id,'symbol':symbol,'side':'WRITE_OFF','status':'Written Off','source':'LOCAL ACCOUNTING ONLY',
               'time':time.time(),'position_id':position_key(symbol,p),'duration_seconds':time.time()-p['opened'],'signal_id':p.get('signal_id'),'allocated_basis':str(loss),'cash_delta':'0','remaining_quantity':'0','quantity':p['qty'],'realized':str(-loss),'reason':'explicit zero-recovery write-off; NOT exchange execution'}
            record_equity(db,s,quotes or {},force=True)
            db.execute('INSERT INTO orders VALUES(?,?)',(request_id,json.dumps(o)))
            db.execute('UPDATE paper SET body=? WHERE id=1',(json.dumps(s),))
            db.execute('INSERT INTO events(time,body) VALUES(?,?)',(time.time(),json.dumps({'message':o['reason'],'symbol':symbol})))
            return o


def position_key(symbol,position):
    return symbol+':'+str(position.get('position_id',position['opened']))


def reconcile_order(order,event):
    """Pure future adapter boundary: exchange acknowledgement is not a fill.

    Financial posting is deliberately not connected to a live adapter in v0.8.
    Cumulative executed quantity is monotone; duplicate events are idempotent.
    """
    import copy
    out=copy.deepcopy(order)
    if event['order_id']!=order['id']:raise RiskError('Order ID mismatch')
    if event['event_id'] in order.get('event_ids',[]):return out
    old=D(order.get('filled_quantity','0'));filled=D(event.get('filled_quantity',old));total=D(order['quantity'])
    if not filled.is_finite() or not old<=filled<=total:raise RiskError('Invalid cumulative fill quantity')
    status=event['status']
    if status=='Filled' and filled!=total:raise RiskError('Filled status without full execution')
    if status=='Partially Filled' and not 0<filled<total:raise RiskError('Invalid partial execution')
    if status in ('Created','Submitted','Accepted','Rejected') and filled!=0:raise RiskError('Acknowledgement is not an execution')
    if status!=out['status']:transition(out,status)
    elif status not in ('Accepted','Partially Filled'):raise RiskError('Terminal order cannot change')
    out['filled_quantity']=str(filled);out.setdefault('event_ids',[]).append(event['event_id']);return out
