"""Independent spot risk gate; all authoritative money/lot arithmetic is Decimal."""
from decimal import Decimal,ROUND_FLOOR
import math,time
from .costs import CostModel,estimate,scenario,basis
from .inventory import inventory,liquidation_at
D=lambda x:Decimal(str(x))
# Legacy compatibility exports; live calculations use CostModel.
FEE=D('0.001');SLIPPAGE=D('0.0005')
PROFILE={'trade_risk':.0075,'positions':3,'symbol':.25,'occupied':.75,'total_risk':.015,'day_loss':.03,'week_loss':.06,'reduce_dd':.08,'stop_dd':.12,'critical_dd':.15}
class RiskError(ValueError):pass

def floor_step(value,step):
    value,step=D(value),D(step)
    if not value.is_finite() or not step.is_finite() or step<=0:raise RiskError('Некорректная точность инструмента')
    return (value/step).to_integral_value(rounding=ROUND_FLOOR)*step

def quote_ok(q,now=None):
    now=time.time() if now is None else now
    try:
        return q.get('fresh') is True and all(-2<=now-q.get(k+'_ts',q.get('ts',0))<=15 for k in ('price','bid','ask')) and max(q.get(k+'_ts',q.get('ts',0)) for k in ('price','bid','ask'))-min(q.get(k+'_ts',q.get('ts',0)) for k in ('price','bid','ask'))<=5 and all(math.isfinite(float(q[k])) and float(q[k])>0 for k in ('price','bid','ask','ts')) and float(q['bid'])<=float(q['ask']) and -2<=now-q['ts']<=15
    except (KeyError,TypeError,ValueError,OverflowError,AttributeError):return False

def metrics(state,quotes,now=None,rules=None):
    cash=D(state['cash']);value=D(0);risk=D(0);unreal=D(0);missing=[];weights={}
    for sym,p in state['positions'].items():
        q=quotes.get(sym,{})
        if not quote_ok(q,now):missing.append(sym)
        mark=D(q.get('bid') or p['entry']);qty=D(p['qty']);v=qty*mark
        value+=v;unreal+=v-basis(p);weights[sym]=float(v)
        rule=(rules or {}).get(sym)
        valid_rule=bool(rule and 0<=(time.time() if now is None else now)-rule.get('retrieved',0)<=86400)
        stop_proceeds=liquidation_at(p,p['stop'],rule,CostModel.from_state(state))[1] if valid_rule else D(0) if rules is not None else estimate('SELL',qty,{'bid':p['stop']},CostModel.from_state(state)).cash_delta
        risk+=max(D(0),v-stop_proceeds)
    equity=cash+value;peak=max(D(state['peak']),equity)
    liquidation=value
    for sym,p in state['positions'].items():
        mark=D(quotes.get(sym,{}).get('bid') or p['entry'])
        rule=(rules or {}).get(sym)
        valid_rule=bool(rule and 0<=(time.time() if now is None else now)-rule.get('retrieved',0)<=86400)
        proceeds=liquidation_at(p,mark,rule,CostModel.from_state(state))[1] if valid_rule else D(0) if rules is not None else estimate('SELL',p['qty'],{'bid':mark},CostModel.from_state(state)).cash_delta
        liquidation+=proceeds-D(p['qty'])*mark
    return {'risk_decimal':str(risk),'occupied_decimal':str(value),'liquidation_equity':str(cash+liquidation),'equity_decimal':str(equity),'unrealized_decimal':str(unreal),'cash':float(cash),'equity':float(equity),'occupied':float(value),'risk':float(risk),'unrealized':float(unreal),'realized':float(D(state['realized'])),'drawdown':float((peak-equity)/peak) if peak>0 else 0,'weights':weights,'missing_quotes':missing}

def plan(state,quotes,symbol,quantity,stop,target,rules,risk_pct=.75,now=None,portfolio_rules=None):
    q=quotes.get(symbol,{})
    if not quote_ok(q,now):raise RiskError('Connection Lost / Stale Data: новая сделка недоступна')
    if not rules or not 0<=(time.time() if now is None else now)-rules.get('retrieved',0)<=86400:raise RiskError('Нет актуальных правил инструмента')
    qty=D(quantity);sl=D(stop);tp=D(target)
    if not all(x.is_finite() and x>0 for x in (qty,sl,tp)):raise RiskError('Количество и уровни должны быть положительными')
    if floor_step(qty,rules['step'])!=qty:raise RiskError('Количество не кратно шагу '+str(rules['step']))
    if floor_step(sl,rules['tick'])!=sl or floor_step(tp,rules['tick'])!=tp:raise RiskError('Цена не кратна шагу '+str(rules['tick']))
    model=CostModel.from_state(state);fill,cost=scenario(qty,q,sl,tp,model)
    prospective={'qty':str(fill.net_base),'cost_basis':str(cost['total'])}
    allocation=inventory(fill.net_base,q,rules,model,cost['total'])
    stop_allocation,stop_proceeds=liquidation_at(prospective,sl,rules,model)
    _,target_proceeds=liquidation_at(prospective,tp,rules,model)
    cost.update(loss=cost['total']-stop_proceeds,gain=target_proceeds-cost['total'])
    cost['rr']=cost['gain']/cost['loss'] if cost['loss']>0 else D(0)
    entry=fill.price;amount=fill.notional;fee=fill.fee_quote_value
    if not sl<D(q['bid'])<tp:raise RiskError('Нужны Stop < текущий Bid < Take Profit')
    if amount<D(rules['minimum']):raise RiskError('Сумма меньше минимальной')
    if rules.get('maximum') and qty>D(rules['maximum']):raise RiskError('Превышено максимальное количество')
    m=metrics(state,quotes,now,rules={**(portfolio_rules or {}),symbol:rules});eq=D(m['equity_decimal']);dd=m['drawdown'];errors=[]
    if m['missing_quotes']:errors.append('Нужны свежие котировки всех открытых позиций')
    if symbol in state['positions']:errors.append('Добавление к открытой позиции отключено; усреднение не применяется')
    if len(state['positions'])>=PROFILE['positions']:errors.append('Максимум 3 позиции')
    if cost['total']>D(state['cash']):errors.append('Недостаточно свободного баланса')
    factor=D('.5') if dd>=.08 else D(1)
    if dd>=.12:errors.append('Просадка ≥12%: новые сделки заблокированы')
    if dd>=.15:errors.append('Критический риск-бюджет: просадка ≥15%')
    if amount>eq*D('.25')*factor:errors.append('Лимит одного инструмента: 25% (вдвое меньше при DD≥8%)')
    if D(m['occupied_decimal'])+amount>eq*D('.75'):errors.append('Занятость капитала превышает 75%')
    if not math.isfinite(float(risk_pct)) or not 0<float(risk_pct)<=.75:raise RiskError('Риск сделки должен быть в диапазоне (0; 0,75%]')
    per_unit=cost['loss']/qty
    loss=cost['loss'];gain=cost['gain']
    if loss>eq*D(risk_pct)/100*factor:errors.append('Превышен риск на сделку')
    if loss+D(m['risk_decimal'])>eq*D('.015'):errors.append('Совокупный расчётный риск превышает 1,5%')
    for name,limit in [('day',.03),('week',.06)]:
        base=D(state[name+'_equity'])
        if base>0 and (base-eq)/base>=D(limit):errors.append('Лимит убытка: '+('день 3%' if name=='day' else 'неделя 6%'))
    budget=min(eq*D(risk_pct)/100*factor,max(D(0),eq*D('.015')-D(m['risk_decimal'])))
    recommended=floor_step(max(D(0),min(budget/per_unit,eq*D('.25')*factor/entry,max(D(0),eq*D('.75')-D(m['occupied_decimal']))/entry,D(state['cash'])/(cost['total']/qty))),rules['step'])
    return {'inventory':allocation,'stop_inventory':stop_allocation,'residue_risk_assumption':'zero recovery','exit_closeable':stop_allocation['fully_sellable'],'quantity':str(qty),'entry':float(entry),'amount':float(amount),'fee':float(fee),'cash_after':float(D(state['cash'])-cost['total']),'loss':float(loss),'gain':float(gain),'rr':float(gain/loss),'risk_pct':float(loss/eq*100),'recommended':str(recommended),'spread':float(D(q['ask'])-D(q['bid'])),'slippage_bps':float(model.execution.slippage_bps),'cost_model':model.snapshot(),'costs':{k:str(v) for k,v in cost.items()},'fill':fill.strings(),'total':float(cost['total']),'stop':str(sl),'target':str(tp),'allowed':not errors,'errors':errors}


def protection_plan(state, quotes, symbol, stop, target, rules, portfolio_rules=None):
    """Risk preview for an existing long; unexecutable residue has zero recovery."""
    q = quotes.get(symbol, {})
    if not quote_ok(q):
        raise RiskError('Stale Data: изменение защиты недоступно')
    if not rules or not 0 <= time.time() - rules.get('retrieved', 0) <= 86400:
        raise RiskError('Нет актуальных правил')
    position = state['positions'].get(symbol)
    if not position:
        raise RiskError('Позиция закрыта или отсутствует')
    sl, tp = D(stop), D(target)
    if not all(x.is_finite() and x > 0 for x in (sl, tp)):
        raise RiskError('Некорректные уровни')
    if floor_step(sl, rules['tick']) != sl or floor_step(tp, rules['tick']) != tp:
        raise RiskError('Уровни не кратны tick size')
    if not sl < D(q['bid']) < tp:
        raise RiskError('Нужны Stop < Bid < Target')
    if D(q['bid']) <= D(position['stop']) or D(q['bid']) >= D(position['target']):
        raise RiskError('Действующая защита уже сработала: изменение недоступно')
    model = CostModel.from_state(state)
    held, cost = D(position['qty']), basis(position)
    mark = held * D(q['bid'])
    allocation, stop_proceeds = liquidation_at(position, sl, rules, model)
    _, old_proceeds = liquidation_at(position, D(position['stop']), rules, model)
    _, target_proceeds = liquidation_at(position, tp, rules, model)
    m = metrics(state, quotes)
    eq = D(m['equity_decimal'])
    if m['missing_quotes'] or eq <= 0:
        raise RiskError('Нужна полная свежая оценка портфеля')
    old_risk, new_risk = max(D(0), mark - old_proceeds), max(D(0), mark - stop_proceeds)
    other_risk = D(0)
    for sym, pos in state['positions'].items():
        if sym == symbol:
            continue
        rule = (portfolio_rules or {}).get(sym)
        proceeds = liquidation_at(pos, pos['stop'], rule, model)[1] if rule and 0 <= time.time()-rule.get('retrieved',0) <= 86400 else D(0)
        other_risk += max(D(0), D(pos['qty']) * D(quotes[sym]['bid']) - proceeds)
    errors = []
    factor = D('.5') if m['drawdown'] >= PROFILE['reduce_dd'] else D(1)
    if new_risk > old_risk:
        if m['drawdown'] >= PROFILE['stop_dd'] or new_risk > eq * D(PROFILE['trade_risk']) * factor or new_risk + other_risk > eq * D(PROFILE['total_risk']):
            errors.append('Увеличение риска превышает лимит; уменьшите риск или сократите позицию')
    loss, gain = max(D(0), cost - stop_proceeds), target_proceeds - cost
    return {'stop': str(sl), 'target': str(tp), 'old_stop': position['stop'], 'old_target': position['target'],
            'quantity': str(held), 'inventory': allocation, 'old_risk': str(old_risk), 'new_risk': str(new_risk),
            'risk_delta': str(new_risk-old_risk), 'loss': str(loss), 'gain': str(gain),
            'rr': str(gain/loss) if loss else None, 'stop_distance': str(D(q['bid'])-sl),
            'target_distance': str(tp-D(q['bid'])), 'risk_pct': str(new_risk/eq*100),
            'cost_model': model.snapshot(), 'allowed': not errors, 'errors': errors,
            'residue_assumption': 'Zero recovery for non-executable quantity in risk estimate'}
