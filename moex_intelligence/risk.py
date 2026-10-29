"""Heuristic risk map; unknowns stay unknown. No averaging of critical limits."""
import math
import numpy as np
import pandas as pd
from .validation import finite

LEVELS=['низкий','умеренный','высокий','очень высокий']


def tier(value, thresholds): return sum(value>x for x in thresholds)


def portfolio_impact(context, amount, invested, entry_cost):
    if context is None: return None
    nav=finite(context.get('equity'),'portfolio equity',0,1e12)
    held=finite(context.get('asset_value'),'current asset value',0,nav)
    cash=finite(context.get('cash'),'portfolio cash',0,nav)
    if held+cash>nav+1e-7: raise ValueError('Asset value + cash cannot exceed portfolio equity.')
    funding=context.get('funding','new_money')
    if funding not in {'new_money','existing_cash'}:raise ValueError('Unknown funding source.')
    if funding=='existing_cash' and invested+entry_cost>cash+1e-7:raise ValueError('Недостаточно денег в портфеле для предполагаемой покупки.')
    after=nav+(amount if funding=='new_money' else 0)-entry_cost
    return {'before_weight_pct':held/nav*100 if nav else 0.,'after_weight_pct':(held+invested)/after*100 if after else 0.,
            'equity_after_costs':after,'asset_value_after':held+invested,'funding':funding,
            'limitations':'Only the selected ticker is combined. Other holdings of the same issuer, fund look-through, sectors and correlations are unknown.'}


def assess(frame, meta, quote, profile, quality, model_stats, sizing, impact):
    hard=[]; unknown=[]; factors=[]
    def factor(key,name,level,reason,limits='',conflict=False,uncertain=False):
        item={'id':key,'name':name,'level':level,'reason':reason,'limitations':limits,
              'effect':'Обязательное ограничение' if conflict else 'Снижает определённость' if uncertain else 'Контекст'}
        factors.append(item)
        if conflict: hard.append(item)
        elif uncertain: unknown.append(item)
    hist_dd=quality.get('historical_drawdown_pct')
    vol=quality.get('volatility_pct')
    worst_dd=max([max(0.,-s['p05_strategy_max_drawdown']*100) for s in model_stats]+[0.])
    es=max([max(0.,s['es95_loss']*100) for s in model_stats]+[0.])
    observed=max(hist_dd or 0.,worst_dd,es)
    market_level=max(tier(hist_dd or 0.,[10,20,35]),tier(vol or 0.,[15,30,50]),tier(es,[5,15,30]))
    complete=profile is not None
    breach=complete and observed>profile['max_drawdown_pct']
    factor('drawdown','Рыночный риск',LEVELS[market_level],
        f'Историческая просадка {hist_dd:.1f}%, годовая волатильность {vol:.1f}%; модельный ES до {es:.1f}%, неблагоприятная просадка до {worst_dd:.1f}%.' if hist_dd is not None else 'Недостаточно цен для оценки рыночного риска.',
        'Максимум наблюдаемых оценок не является пределом будущего убытка. Потеря может достигать всей позиции.',conflict=breach)
    if breach:hard[-1]['reason']+=f" Это выше допустимых вами {profile['max_drawdown_pct']:.1f}%."
    if complete:
        deadline=profile['needs_money_early'] or profile['horizon_months']<=3
        factor('horizon','Срок и доступ к деньгам','высокий' if deadline else 'умеренный',
            'Деньги могут понадобиться до конца срока либо срок не превышает трёх месяцев; продажа может совпасть с падением.' if deadline else 'Даже на выбранном сроке нет гарантии восстановления цены.',conflict=deadline)
        preference=profile['risk_preference']=='low' and market_level>=2 or profile['risk_preference']=='medium' and market_level==3
        factor('preference','Предпочтительный риск',LEVELS[market_level],
            'Расчётный уровень риска выше выбранного предпочтения.' if preference else 'Уровень риска сопоставлен с выбранным предпочтением.',conflict=preference)
    if impact is None:
        factor('portfolio_unknown','Концентрация','неизвестно','Структура портфеля не указана: влияние покупки на общий капитал не оценено.',uncertain=True)
    else:
        w=impact['after_weight_pct']; fund=meta.get('asset_type')=='fund'
        limit=50 if fund else 35
        factor('concentration','Концентрация позиции',LEVELS[tier(w,[20,limit,65])],
            f"Доля тикера меняется с {impact['before_weight_pct']:.1f}% до {w:.1f}%.",
            ('Доля фонда не равна доле одного эмитента; состав фонда не проверен.' if fund else 'Другие бумаги того же эмитента и отрасли не объединены.')+' Корреляции и состав фондов неизвестны.',conflict=w>limit)
    turnover=None;estimated=False
    if 'VALUE' in frame:
        valid=pd.to_numeric(frame.VALUE,errors='coerce').tail(20)
    elif 'VOLUME' in frame:
        valid=(pd.to_numeric(frame.VOLUME,errors='coerce')*frame.CLOSE).tail(20);estimated=True
    else: valid=pd.Series(dtype=float)
    if len(valid)>=10 and np.isfinite(valid).all() and (valid>=0).all():turnover=float(valid.median())
    md=(quote or {}).get('marketdata',{})
    bid,ask=md.get('BID'),md.get('OFFER')
    spread=(ask-bid)/((bid+ask)/2)*100 if all(isinstance(x,(int,float)) and math.isfinite(x) and x>0 for x in (bid,ask)) and ask>=bid else None
    fraction=sizing.get('invested',0)/turnover*100 if turnover and turnover>0 else None
    liquidity_conflict=complete and (turnover==0 or fraction is not None and fraction>1 or spread is not None and spread>2)
    level='неизвестно' if turnover is None else 'высокий' if liquidity_conflict else 'умеренный'
    reason=('Оборот не определён.' if turnover is None else f'Медианный дневной оборот за последние 20 наблюдений: {turnover:,.0f} ₽'+(' (оценка CLOSE × VOLUME).' if estimated else '.'))
    reason+=f' Доля позиции в обороте: {fraction:.3f}%.' if fraction is not None else ''
    reason+=f' Наблюдаемый спред: {spread:.2f}%.' if spread is not None else ' Надёжный bid/ask не получен.'
    factor('liquidity','Ликвидность',level,reason,'Дневной оборот не гарантирует исполнение. Спред может быть отложенным; стакан и влияние заявки не моделируются.',conflict=liquidity_conflict,uncertain=turnover is None or spread is None)
    if len(model_stats)>=2:
        gap=max(s['p05_return'] for s in model_stats)-min(s['p05_return'] for s in model_stats)
        mismatch=gap*100>5
        factor('model_disagreement','Неопределённость модели','высокий' if mismatch else 'умеренный',f'Разница 5-х процентилей между моделями: {gap*100:.2f} п.п.',
               'Совпадение моделей не подтверждает правильность предположений. Обе используют одни исторические цены.',uncertain=mismatch)
    if sizing:
        cost=sizing.get('roundtrip_cost_pct',0)
        factor('costs','Издержки','высокий' if cost>1 else 'умеренный',f'Условный расход на полный оборот при неизменной цене: {cost:.2f}%.','Налоги и реальное влияние сделки на рынок не включены.',conflict=complete and cost>3,uncertain=1<cost<=3)
        if sizing.get('quantity')==0 and complete:
            hard.append({'id':'lot','reason':'Указанной суммы не хватает на один лот с учётом издержек.'})
    for warning in quality.get('warnings',[]):
        factor('history_warning','Ограничение истории','неизвестно',warning,uncertain=True)
    factor('fundamentals','Бизнес / состав фонда / текущая оценка','неизвестно',
        'Проверенной фундаментальной оценки компании или состава и расходов фонда нет. Рост цены не доказывает привлекательность покупки.',
        'Отчётность, новости, корпоративные и регуляторные события не проанализированы.',uncertain=True)
    factor('other_risks','Другие риски','неизвестно','Инфляция, изменение правил, события эмитента и неожиданные гэпы не оценены численно.',
           'Нельзя считать неизвестный риск низким.')
    overall=LEVELS[max([market_level]+[3 if f['level']=='очень высокий' else 2 if f['level']=='высокий' else 1 if f['level']=='умеренный' else 0 for f in factors])]
    return {'factors':factors,'known_risk_level':overall,'coverage':'частичная','hard_conflicts':hard,
            'uncertainties':unknown,'critical_gaps':quality['critical_gaps'],'drawdown_envelope_pct':observed,
            'aggregation':'Maximum assessed severity, never an average; unknown risks are listed separately.'}
