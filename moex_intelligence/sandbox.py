"""Validated presentation contract over the unchanged v0.6 financial engines.

The browser may preview light arithmetic. Python independently replays every
settled request. This module never imports PortfolioStore or writes trades.
"""
from __future__ import annotations
import copy
import hashlib
import json
from datetime import datetime, timezone
from .data import market_today
from .laboratory import preview_trade, concentration, position_stress, stress_selected, capital_goal
from .portfolio import ledger_state
from .validation import finite, integer
from .formatting import money,percent

METHOD_VERSION='lab-contract/0.7.1'


def context_id(asset,bundle,marks):
    body=json.dumps([asset,bundle['revision'],marks],sort_keys=True,ensure_ascii=False,default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:24]


def quote_status(asset):
    from .provenance import describe_price
    return describe_price(asset)


def default_state(asset,preferences=None,existing=False,mode='Сценарии'):
    prefs=preferences if isinstance(preferences,dict) else {}
    raw_fee=prefs.get('commission');fee=raw_fee if isinstance(raw_fee,dict) else {}
    raw_profile=prefs.get('profile');profile=raw_profile if isinstance(raw_profile,dict) else {}
    profile_valid=True
    try:
        months=integer(profile.get('horizon_months'),'Срок',1,600)
        loss=finite(profile.get('max_drawdown_pct'),'Потеря',.1,100)
        early=profile.get('needs_money_early')
        if not isinstance(early,bool):raise ValueError('Потребность в деньгах неизвестна.')
    except (ValueError,TypeError):months,loss,early,profile_valid=12,10,False,False
    fee_valid=bool(fee)
    try:rate=finite(fee.get('pct'),'Комиссия',0,10);minimum=finite(fee.get('minimum',0),'Минимум',0,1e9)
    except (ValueError,TypeError):rate,minimum,fee_valid=0,0,False
    return dict(quantity=0 if existing else asset['lot_size'],side='buy',funding='cash',unit='lots',
                fee_known=fee_valid,fee_pct=rate,minimum_fee=minimum,
                shock=0,horizon=21,show_model=False,mode=mode,months=months,
                max_loss=loss,early=early,profile_known=profile_valid,concentration_limit=40,concentration_known=False,scope='portfolio',seq=0)


def validate_state(value,asset,defaults):
    if not isinstance(value,dict):raise ValueError('Некорректное состояние сценария.')
    s={**defaults,**{k:v for k,v in value.items() if k in defaults}}
    for name,options in [('side',{'buy','sell'}),('funding',{'cash','topup'}),('unit',{'lots','shares'}),
                         ('mode',{'Оценить','Сценарии'}),('scope',{'portfolio','position'})]:
        if s[name] not in options:raise ValueError('Неизвестный параметр '+name)
    for k in ['fee_known','show_model','early','profile_known','concentration_known']:
        if not isinstance(s[k],bool):raise ValueError('Ожидается переключатель '+k)
    s['quantity']=integer(s['quantity'],'Количество',0,100000000)
    s['seq']=integer(s['seq'],'Номер сценария',0,1000000000)
    s['horizon']=integer(s['horizon'],'Горизонт',1,252)
    if s['horizon'] not in {5,21,63,252}:raise ValueError('Неизвестный горизонт модели.')
    s['months']=integer(s['months'],'Срок',1,600)
    for k,lo,hi in [('fee_pct',0,10),('minimum_fee',0,1e9),('shock',-50,50),('max_loss',.1,100),('concentration_limit',1,100)]:
        s[k]=finite(s[k],k,lo,hi)
    return s


def evaluate_constraints(result,asset,state,envelope=None):
    """Three outcomes for selected scenario checks; never an investment endorsement."""
    checks=[];facts=[];actions=[]
    def add(code,label,status,detail,action=None):
        checks.append({'id':code,'label':label,'status':status,'detail':detail})
        if action and status!='passed':actions.append({'kind':action[0],'label':action[1]})
    order=result['order'];quantity=state['quantity'];after=result['after'];before=result['before']
    add('lot','Количество и лот','passed' if order['gross'] is not None else 'unknown',
        f"{quantity} бумаг, лот {asset['lot_size']}." if order['gross'] is not None else 'Исправьте количество без автоматического округления.',('quantity','Изменить количество'))
    add('fee','Издержки','passed' if order['fee'] is not None else 'unknown',
        'Операция не выбрана; новая комиссия не возникает.' if quantity==0 else 'Комиссия задана; дополнительные сборы и исполнение не оценены.' if order['fee'] is not None else 'Полная сумма неизвестна без проверенного тарифа.',('fee','Указать тариф'))
    cash_fail=state['side']=='buy' and state['funding']=='cash' and order['buy_total'] is not None and order['buy_total']>result['known_cash']+1e-7
    sell_fail=state['side']=='sell' and quantity>result['known_quantity']
    add('funding','Деньги и остаток','failed' if cash_fail or sell_fail else 'passed' if 'cash_after' in result else 'unknown',
        'Не хватает свободных средств.' if cash_fail else 'Продаётся больше бумаг, чем есть.' if sell_fail else 'Проверен денежный остаток после операции.' if 'cash_after' in result else 'Операция не может быть проверена.',('quantity','Изменить объём'))
    status=quote_status(asset)
    add('price','Источник цены','unknown' if status['critical'] else 'passed',status['label'],('refresh_price','Обновить цену'))
    add('portfolio','Оценка портфеля','passed' if after is not None else 'unknown',
        'Сопоставимые оценки всех позиций.' if after is not None else 'Нет полной проверенной оценки после операции.',('refresh_price','Обновить оценки'))
    if not state['profile_known']:
        add('profile','Условия эксперимента','unknown','Не подтверждены срок, допустимая потеря и потребность в деньгах.',('profile','Указать условия'))
    else:
        qty=result.get('known_after_quantity',result['known_quantity'])
        stress=position_stress(asset,qty,state['shock']);base=qty*asset['unit_price']
        loss=max(0,-stress['change_rub']/base*100) if base else 0
        add('loss','Потеря в заданном стрессе','failed' if loss>state['max_loss'] else 'passed',
            'Позиция: '+percent(loss)+' потери при пределе '+percent(state['max_loss'])+'. Это заданный стресс, не предел риска.',('stress','Изменить стресс'))
        add('horizon','Срок эксперимента','passed',f"Выбран срок {state['months']} мес.; инвестиционное соответствие сроку отдельно не установлено.")
        if state['early']:
            add('liquidity','Доступ к деньгам раньше срока','unknown','Продажа по приемлемой цене и ликвидность на нужную дату не подтверждены.',('profile','Уточнить условия'))
        else:add('liquidity','Потребность в деньгах','passed','Вы указали, что деньги раньше срока не потребуются.')
    if state['concentration_known']:
        weight=concentration(after)['max_security_weight_pct'] if after else None
        add('concentration','Предел концентрации','unknown' if weight is None else 'failed' if weight>state['concentration_limit'] else 'passed',
            'Доля неизвестна без полной оценки.' if weight is None else 'Крупнейшая позиция '+percent(weight)+' при пределе '+percent(state['concentration_limit'])+'.',('quantity','Изменить объём'))
    if state['show_model'] or envelope:
        available=envelope and not envelope.get('error') and state['horizon']<=envelope['horizon']
        if not available:add('model','Модельный исход','unknown',(envelope or {}).get('error') or 'Модель для этого горизонта пока недоступна.',('history','Проверить историю'))
        elif state['profile_known']:
            loss=max(0,(1-envelope['lo'][state['horizon']])*100)
            add('model','5-й процентиль модели','failed' if loss>state['max_loss'] else 'passed','В 5-м процентиле модели убыток '+percent(loss)+' на конец модельного срока при пределе '+percent(state['max_loss'])+'. Не историческая просадка и не гарантированная граница.',('horizon','Изменить горизонт'))
    if before and after:
        old=next((p['weight_pct'] for p in before['positions'] if p['symbol']==asset['symbol']),0.)
        new=next((p['weight_pct'] for p in after['positions'] if p['symbol']==asset['symbol']),0.)
        facts.append('Доля '+asset['symbol']+': '+percent(old)+' → '+percent(new)+' ('+percent(new-old,signed=True,points=True)+').')
        if order['fee'] and not result['topup']:facts.append('Комиссия уменьшает стоимость портфеля на '+money(order['fee'])+'; перераспределение денег само по себе не создаёт прибыль.')
    elif result.get('known_after_quantity') is not None:facts.append('Количество и деньги рассчитаны; полная стоимость портфеля неизвестна.')
    if result.get('topup'):facts.append('Условное пополнение '+money(result['topup'])+' — взнос, не инвестиционная прибыль.')
    failed=[c for c in checks if c['status']=='failed'];unknown=[c for c in checks if c['status']=='unknown']
    outcome='conflict' if failed else 'insufficient_data' if unknown else 'no_conflicts'
    labels={'conflict':'Обнаружен конфликт','insufficient_data':'Недостаточно данных для проверки сценария','no_conflicts':'По проверенным параметрам конфликтов не выявлено'}
    decisive=(failed or unknown);why=[c['detail'] for c in decisive]+facts
    if not why:why=['Выбранные проверки завершены без нарушений.']
    unique=[]
    for action in actions:
        if action not in unique:unique.append(action)
    return {'status':outcome,'label':labels[outcome],'scope':'scenario_only','investment_assessment':'not_assessed',
            'why':why[:3],'facts':facts,'checks':checks,'actions':unique[:3],
            'coverage':{'passed':sum(c['status']=='passed' for c in checks),'failed':len(failed),'unknown':len(unknown)},
            'check':['Это проверка выбранного сценария, а не рекомендация покупать или продавать.',
                     'Риски эмитента, полная ликвидность и инвестиционная пригодность не установлены.']}


def calculate(asset,bundle,marks,state):
    events=[r['event'] for r in bundle['records']]
    try:
        r=preview_trade(events,marks,asset,state['quantity'],side=state['side'],funding=state['funding'],
                        fee_pct=state['fee_pct'] if state['fee_known'] else None,minimum_fee=state['minimum_fee'])
    except ValueError as exc:
        r=preview_trade(events,marks,asset,0,fee_pct=0)
        r.update(after=None,errors=[str(exc)]);r.pop('cash_after',None);r.pop('known_after_quantity',None)
        r['order']={'quantity':state['quantity'],'gross':None,'fee':None,'buy_total':None,'sell_proceeds':None}
    r['constraints']=evaluate_constraints(r,asset,state)
    return r


def presentation_data(asset,bundle,marks,preferences=None,existing=False,mode='Сценарии'):
    state=default_state(asset,preferences,existing,mode)
    result=calculate(asset,bundle,marks,{**state,'quantity':0})
    events=[r['event'] for r in bundle['records']];ledger=ledger_state(events)
    return {'context':context_id(asset,bundle,marks),'asset':copy.deepcopy(asset),'initial':state,
            'before':result['before'],'cash':ledger['cash'],'held':result['known_quantity'],
            'future_ledger':any(e['date']>market_today().isoformat() for e in events),
            'price_status':quote_status(asset),'revision':bundle['revision'],'method':METHOD_VERSION,'valuation_errors':result['errors']}


def required_return(initial,monthly,months,target):
    """Effective annual nominal return solving the existing capital_goal formula."""
    finite(target,'Цель',.01,1e15)
    low,high=-99.,100.
    f=lambda rate:float(capital_goal(initial,monthly,months,rate,0).nominal.iloc[-1])
    if f(low)>target or f(high)<target:return None
    for _ in range(60):
        mid=(low+high)/2
        if f(mid)<target:low=mid
        else:high=mid
    return (low+high)/2
