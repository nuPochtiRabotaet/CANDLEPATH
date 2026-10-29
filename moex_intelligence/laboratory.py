"""Read-only investment laboratory over the existing ledger/stress/simulation engines.

No store, broker connection or execution API is imported here. Every hypothetical
operation is replayed against a copied event list, never the persisted journal.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import numpy as np
import pandas as pd
from moex import identifier
from .data import market_today, require_equity
from .portfolio import analyze_portfolio, ledger_state, stress_test
from .portfolio_service import quote_mark
from .validation import finite, integer
from time_machine_core.simulator import simulate


def asset_from_quote(quote, mark=None):
    mark = copy.deepcopy(mark or quote_mark(quote))
    meta = quote['instrument'];sec=quote['security'];md=quote.get('marketdata',{})
    if (quote.get('currency') or meta.get('currency')) not in {'RUB','SUR'}:raise ValueError('Рублёвая валюта не подтверждена.')
    if meta.get('asset_type') not in {'equity','fund','bond'}:raise ValueError('Нужна акция, фонд или облигация.')
    lot=integer(sec.get('LOTSIZE'),'Размер лота MOEX',1,100000000)
    dirty=finite(mark['price'],'Полная цена в рублях',1e-8,1e12)
    accrued=finite(sec.get('ACCRUEDINT'),'НКД',0,1e12) if meta['asset_type']=='bond' else 0.
    face=finite(sec.get('FACEVALUE'),'Номинал',1e-8,1e12) if meta['asset_type']=='bond' else None
    clean=dirty-accrued
    if clean<=0:raise ValueError('Полная цена должна превышать НКД.')
    if meta['asset_type']=='bond' and sec.get('FACEUNIT') not in {'SUR','RUB'}:raise ValueError('Номинал облигации должен быть рублёвым.')
    return {'symbol':identifier(meta['symbol']),'name':meta['name'],'asset_type':meta['asset_type'],
            'board':meta.get('board'),'lot_size':lot,'unit_price':dirty,'clean_price':clean,
            'accrued_interest':accrued,'face_value':face,'quoted_pct':clean/face*100 if face else None,
            'currency':'RUB','mark':mark,'price_type':'daily_close' if mark.get('observed_as_of') else 'last_trade',
            'source':mark['source'],'retrieved_at_utc':mark['retrieved_at_utc'],
            'observed_at':mark.get('observed_as_of') or md.get('LASTTRADEDATE'),
            'market_update_at':md.get('SYSTIME') or md.get('UPDATETIME'),
            'liquidity':{'bid':md.get('BID'),'ask':md.get('OFFER'),'volume_units':md.get('VOLTODAY'),
                         'trades':md.get('NUMTRADES'),'trading_status':md.get('TRADINGSTATUS')},
            'demo_data':bool(meta.get('demo_data')),'manual':False,'saved_snapshot':False}


def manual_asset(symbol, kind, price, lot, source, *, face=None, accrued=0, as_of=None):
    """price is RUB/unit for shares; clean percent of face for a bond."""
    if kind not in {'equity','fund','bond'}:raise ValueError('Неподдерживаемый класс бумаги.')
    integer(lot,'Укажите подтверждённый размер лота',1,100000000)
    if not isinstance(source,str) or not source.strip():raise ValueError('Укажите источник и дату ручной цены.')
    clean=finite(price,'Цена',1e-8,1e12)
    if kind=='bond':
        face=finite(face,'Рублёвый номинал',1e-8,1e12);accrued=finite(accrued,'НКД',0,1e12)
        clean=clean/100*face
    else:face=None;accrued=0.
    mark={'price':clean+accrued,'as_of':market_today().isoformat(),'source':source.strip(),
          'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'observed_as_of':str(as_of or market_today()),
          'valuation_basis':'Ручная оценка пользователя, не подтверждённая MOEX'}
    return {'symbol':identifier(symbol),'name':identifier(symbol),'asset_type':kind,'board':'ручной ввод',
            'lot_size':lot,'unit_price':clean+accrued,'clean_price':clean,'accrued_interest':accrued,
            'face_value':face,'quoted_pct':clean/face*100 if face else None,'currency':'RUB','mark':mark,
            'price_type':'manual','source':source.strip(),'retrieved_at_utc':mark['retrieved_at_utc'],
            'observed_at':mark['observed_as_of'],'market_update_at':None,'liquidity':{},
            'manual':True,'saved_snapshot':False,'demo_data':False}


def order_cost(asset, quantity, fee_pct=None, minimum_fee=0.):
    qty=integer(quantity,'Количество бумаг',0,100000000)
    lot=integer(asset['lot_size'],'Размер лота',1,100000000)
    if qty%lot:raise ValueError(f'{qty} бумаг не кратны лоту {lot}. Количество не округляется автоматически.')
    price=finite(asset['unit_price'],'Полная цена',1e-8,1e12)
    gross=float(Decimal(str(price))*qty)
    fee=0. if qty==0 else None
    if fee_pct is not None:
        rate=finite(fee_pct,'Ставка комиссии, %',0,10)
        minimum=finite(minimum_fee,'Минимальная комиссия',0,1e9)
        raw=max(Decimal(str(gross))*Decimal(str(rate))/100,Decimal(str(minimum))) if qty else Decimal(0)
        fee=float(raw.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
    return {'quantity':qty,'lots':qty//lot,'gross':gross,'fee':fee,
            'buy_total':gross+fee if fee is not None else None,
            'sell_proceeds':gross-fee if fee is not None else None,
            'fee_policy':'User-supplied rate on full dirty consideration; nearest kopeck, minimum per hypothetical order.'}


def concentration(snapshot):
    return {'max_security_weight_pct':max((p['weight_pct'] for p in snapshot['positions']),default=0.),
            'security_hhi':sum(p['weight_pct']**2 for p in snapshot['positions']),
            'basis':'По тикерам относительно NAV; деньги исключены из HHI, сквозной состав фондов и эмитенты не разобраны.'}


def liquidity_check(asset,quantity):
    liq=asset.get('liquidity',{});bid=liq.get('bid');ask=liq.get('ask');volume=liq.get('volume_units')
    spread=None;participation=None;warnings=[]
    def positive(x):return isinstance(x,(float,int)) and not isinstance(x,bool) and np.isfinite(x) and x>0
    if positive(bid) and positive(ask) and ask>=bid:spread=(ask-bid)/((ask+bid)/2)*100
    if positive(volume):participation=quantity/volume*100
    if spread is None:warnings.append('Спред по доступному снимку неизвестен.')
    elif spread>1:warnings.append('Спред снимка превышает 1%; это внутренний порог внимания, не запрет покупки.')
    if participation is not None and participation>1:warnings.append('Количество превышает 1% дневного объёма снимка; оценка исполнения требует стакана.')
    if asset.get('saved_snapshot') or asset.get('manual') or asset.get('price_type')!='last_trade':warnings.append('Цена/ликвидность не подтверждены как текущие.')
    warnings.append('Последняя цена не гарантирует исполнение. Глубина стакана и проскальзывание не моделируются.')
    return {'spread_pct':spread,'order_share_of_reported_volume_pct':participation,'warnings':warnings,
            'trading_status':liq.get('trading_status'),'execution_confirmed':False}


def preview_trade(events,marks,asset,quantity,*,side='buy',funding='cash',fee_pct=None,minimum_fee=0.):
    if side not in {'buy','sell'} or funding not in {'cash','topup'}:raise ValueError('Неизвестный сценарий операции.')
    copied=copy.deepcopy(events);state=ledger_state(copied)
    cost=order_cost(asset,quantity,fee_pct,minimum_fee)
    valuations=copy.deepcopy(marks);valuations[asset['symbol']]=copy.deepcopy(asset['mark'])
    result={'asset':copy.deepcopy(asset),'order':cost,'before':None,'after':None,'topup':0.,'errors':[],
            'side':side,'funding':funding,'events_changed':False,'liquidity':liquidity_check(asset,quantity),
            'known_quantity':state['positions'].get(asset['symbol'],{}).get('quantity',0),'known_cash':state['cash']}
    try:result['before']=analyze_portfolio(copied,valuations)
    except (ValueError,KeyError,TypeError) as exc:result['errors'].append('Не хватает оценок для портфеля: '+str(exc))
    if cost['fee'] is None:
        result['errors'].append('Комиссия неизвестна. Полная сумма и состояние после операции не рассчитаны.');return result
    if quantity==0:
        result['after']=copy.deepcopy(result['before']);result['cash_after']=state['cash'];result['known_after_quantity']=result['known_quantity'];return result
    held=state['positions'].get(asset['symbol'],{}).get('quantity',0)
    if side=='sell' and quantity>held:
        result['errors'].append(f'Нельзя продать {quantity} бумаг: в портфеле {held}.');return result
    topup=max(0.,cost['buy_total']-state['cash']) if side=='buy' and funding=='topup' else 0.
    result['topup']=topup
    if side=='buy' and cost['buy_total']>state['cash']+topup+1e-7:
        result['errors'].append(f"Недостаточно денег: нужно {cost['buy_total']:,.2f} ₽, доступно {state['cash']:,.2f} ₽.");return result
    day=market_today().isoformat()
    # A future-dated ledger cannot be quietly simulated using today's marks.
    if any(e['date']>day for e in copied):result['errors'].append('Журнал содержит будущие операции; сегодняшняя оценка не подходит.');return result
    if topup:copied.append({'kind':'deposit','date':day,'amount':topup})
    copied.append({'kind':side,'date':day,'symbol':asset['symbol'],'quantity':quantity,'price':asset['unit_price'],'fee':cost['fee']})
    try:
        after_state=ledger_state(copied);result['cash_after']=after_state['cash']
        result['known_after_quantity']=after_state['positions'].get(asset['symbol'],{}).get('quantity',0)
        if result['before'] is not None:result['after']=analyze_portfolio(copied,valuations)
    except (ValueError,KeyError,TypeError) as exc:result['errors'].append(str(exc))
    return result


def position_stress(asset,quantity,shock_pct):
    integer(quantity,'Количество бумаг',0,100000000)
    change=finite(shock_pct,'Гипотетическое изменение цены, %',-50,50)
    price=asset['clean_price']*(1+change/100)+asset['accrued_interest']
    return {'unit_price':price,'value':quantity*price,'change_rub':quantity*asset['clean_price']*change/100}


def stress_selected(snapshot,asset,shock_pct):
    change=finite(shock_pct,'Гипотетическое изменение цены, %',-50,50)
    # Bonds: the slider changes CLEAN price, while accrued interest is frozen.
    effective=change*asset['clean_price']/asset['unit_price']
    held=next((p for p in snapshot['positions'] if p['symbol']==asset['symbol']),None)
    stressed=stress_test(snapshot,{asset['symbol']:effective} if held else {})
    return {**stressed,'position_value':(held['quantity'] if held else 0)*(asset['clean_price']*(1+change/100)+asset['accrued_interest']),
            'unit_price':asset['clean_price']*(1+change/100)+asset['accrued_interest'],
            'scenario_type':'user_hypothesis','other_assets':'fixed','accrued_interest':'fixed','exit_costs_included':False}


def scenario_envelope(frame,meta,*,horizon=252,runs=2000,seed=42):
    require_equity(meta)
    if meta.get('asset_type') not in {'equity','fund'}:raise ValueError('Модель доступна только для акций и фондов.')
    integer(horizon,'horizon',1,252);integer(runs,'runs',100,5000)
    minimum=max(126,2*horizon+1)
    if len(frame)<minimum:raise ValueError(f'Для горизонта {horizon} нужно не менее {minimum} закрытий; получено {len(frame)}.')
    result=simulate(frame.CLOSE,horizon=horizon,runs=runs,seed=seed,exit_policy='horizon',commission_pct=0.,slippage_pct=0.)
    ratios=result.paths/result.paths[:,0,None]
    qs=np.quantile(ratios,[.05,.5,.95],axis=0)
    return {'lo':qs[0].tolist(),'mid':qs[1].tolist(),'hi':qs[2].tolist(),'runs':runs,'horizon':horizon,'seed':seed,
            'history_sha256':hashlib.sha256(frame.to_csv().encode()).hexdigest(),
            'history_start':str(frame.index[0].date()),'history_end':str(frame.index[-1].date()),
            'model':'block_bootstrap','synthetic':bool(meta.get('demo_data')),
            'limits':['Нескорректированная история цен; без дивидендов, налогов и будущих издержек.',
                      'Модельные процентили не являются реальными вероятностями или гарантированными границами.',
                      'Прогностическое качество модели на этом активе не подтверждено.']}


def model_position(envelope,asset,quantity,horizon,snapshot=None):
    integer(quantity,'Количество',0,100000000);integer(horizon,'horizon',1,envelope['horizon'])
    base=quantity*asset['unit_price'];series={k:np.asarray(envelope[k][:horizon+1])*base for k in ['lo','mid','hi']}
    result={'position':{k:v.tolist() for k,v in series.items()},'horizon':horizon,'base_position_value':base}
    if snapshot is not None:
        rest=snapshot['equity']-base
        if rest < -1e-7:raise ValueError('Стоимость позиции превышает NAV выбранного портфеля.')
        result['conditional_portfolio']={k:(v+rest).tolist() for k,v in series.items()}
    return result


def capital_goal(initial,monthly,months,annual_return_pct,inflation_pct):
    initial=finite(initial,'Начальный капитал',0,1e12);monthly=finite(monthly,'Пополнение',0,1e9)
    integer(months,'Срок в месяцах',1,600)
    annual=finite(annual_return_pct,'Допущение доходности, %',-99,100)
    inflation=finite(inflation_pct,'Инфляция, %',-20,100)
    growth=(1+annual/100)**(1/12);deflator=(1+inflation/100)**(1/12)
    nominal=initial;rows=[{'month':0,'nominal':initial,'real':initial,'contributed':initial}]
    for month in range(1,months+1):
        nominal=nominal*growth+monthly
        rows.append({'month':month,'nominal':nominal,'real':nominal/deflator**month,'contributed':initial+monthly*month})
    return pd.DataFrame(rows).set_index('month')


def portfolio_health(snapshot,profile=None):
    mix={};warnings=[]
    for p in snapshot['positions']:mix[p['symbol']]=p['weight_pct']
    risk=concentration(snapshot);shock=stress_test(snapshot,{p['symbol']:-20 for p in snapshot['positions']})
    if risk['max_security_weight_pct']>40:warnings.append('Одна бумага занимает больше 40% капитала; это внутренний порог внимания к концентрации.')
    if not snapshot['history_complete']:warnings.append('История до переноса неизвестна: доходность всей истории не оценивается.')
    if profile and shock['change_pct'] < -profile.get('max_drawdown_pct',100):warnings.append('Заданный стресс −20% цен бумаг превышает введённый предел потерь. Это сценарий, не прогноз вероятности.')
    return {'equity':snapshot['equity'],'cash':snapshot['cash'],'positions':len(snapshot['positions']),
            'weights':mix,'concentration':risk,'uniform_price_stress':shock,'warnings':warnings,
            'limitations':['Это структурная проверка и заданный стресс, не полный инвестиционный вердикт.',
                           'Без полной истории оценок нет TWR/просадки. Корреляции и состав фондов здесь не угадываются.']}
