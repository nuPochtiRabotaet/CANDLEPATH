"""Deterministic one-click investment research orchestration, independent of UI/LLM."""
from __future__ import annotations
from datetime import date, datetime, timezone, timedelta
import hashlib
import numpy as np
import pandas as pd
from .validation import finite, integer
from .data import get_engine, market_today
from .risk import assess, portfolio_impact
from .decision import decide
from time_machine_core.moex_data import demo_daily
from time_machine_core.simulator import simulate

VERSION='advisor-0.4.0'
PROFILE_FIELDS={'amount','horizon_months','max_drawdown_pct','risk_preference','needs_money_early'}


def validate_profile(profile):
    if profile is None or not PROFILE_FIELDS <= set(profile): return None
    p={key:profile[key] for key in PROFILE_FIELDS}
    p['amount']=finite(p['amount'],'amount',1,1e9)
    p['horizon_months']=integer(p['horizon_months'],'horizon_months',1,60)
    p['max_drawdown_pct']=finite(p['max_drawdown_pct'],'max_drawdown_pct',.1,100)
    if p['risk_preference'] not in {'low','medium','high'}:raise ValueError('Unknown risk preference.')
    if not isinstance(p['needs_money_early'],bool):raise ValueError('needs_money_early must be boolean.')
    return p


def evaluate(frame, meta, quote=None, profile=None, portfolio=None, *, runs=2000, seed=42,
             commission_pct=.05, slippage_pct=.05, as_of=None):
    profile=validate_profile(profile)
    meta={**meta, 'history_sha256':hashlib.sha256(frame.to_csv().encode()).hexdigest()}
    integer(runs,'runs',100,5000);integer(seed,'seed',0,1000000)
    finite(commission_pct,'commission_pct',0,3);finite(slippage_pct,'slippage_pct',0,3)
    day=date.fromisoformat(as_of) if isinstance(as_of,str) else as_of or market_today()
    horizon=21*profile['horizon_months'] if profile else 20
    amount=profile['amount'] if profile else 5000.
    gaps=[];warnings=[];model_stats=[];sizing={};impact=None
    quality={'critical_gaps':gaps,'warnings':warnings,'history_points':len(frame),'as_of':str(day),
             'synthetic':bool(meta.get('demo_data')),'historical_drawdown_pct':None,'volatility_pct':None}
    valid=(isinstance(frame.index,pd.DatetimeIndex) and not frame.index.has_duplicates and frame.index.is_monotonic_increasing and not frame.index.hasnans and 'CLOSE' in frame)
    if valid:
        try: values=frame.CLOSE.to_numpy(dtype=float);valid=bool(np.isfinite(values).all() and (values>0).all())
        except (ValueError,TypeError):valid=False
    if not valid or len(frame)<2:gaps.append('История не содержит корректный непрерывный ряд дат и положительных цен.');frame=pd.DataFrame({'CLOSE':[]},index=pd.DatetimeIndex([]))
    historical={}
    if len(frame)>=2:
        close=frame.CLOSE.astype(float);returns=close.pct_change().dropna()
        quality['historical_drawdown_pct']=float(-(close/close.cummax()-1).min()*100)
        quality['volatility_pct']=float(returns.std(ddof=1)*np.sqrt(252)*100) if len(returns)>1 else 0.
        quality['first_observation']=str(frame.index[0].date());quality['last_observation']=str(frame.index[-1].date())
        age=(day-frame.index[-1].date()).days
        quality['age_calendar_days']=age
        if not meta.get('demo_data') and (age>7 or age<0):gaps.append('Последнее наблюдение старше 7 календарных дней либо находится в будущем. Это проверка возраста, не биржевой календарь.')
        for n in [21,63,126,252]:
            if len(close)>n:
                changes=close.pct_change(n).dropna()
                historical[str(n)]={'return_pct':float((close.iloc[-1]/close.iloc[-n-1]-1)*100),
                    'negative_period_frequency':float((changes<0).mean()),'windows':len(changes),'overlapping_windows':True}
        if returns.abs().max()>.25:warnings.append('Обнаружено дневное изменение более 25%: возможен гэп или корпоративное действие; данные не корректировались.')
    minimum=max(126,2*horizon+1)
    quality['minimum_history_required']=minimum
    if len(frame)<minimum:gaps.append(f'Для выбранного срока методика требует не менее {minimum} закрытий; получено {len(frame)}.')
    if horizon>252:gaps.append('Горизонт свыше 12 месяцев не поддерживается численной моделью v0.4; срок не сокращён автоматически.')
    if meta.get('asset_type') not in {'equity','fund'}:gaps.append('Для этого класса активов нет подходящей модели денежных потоков. Облигации требуют купонов, погашения и НКД.')
    if meta.get('currency') not in {'RUB','SUR'}:gaps.append('Валюта не подтверждена как рублёвая; FX-модель отсутствует.')
    for key in ['coverage_warning','freshness_warning']:
        if meta.get(key): warnings.append(meta[key])
    lot=(quote or {}).get('security',{}).get('LOTSIZE',1 if meta.get('demo_data') else None)
    if not isinstance(lot,int) or isinstance(lot,bool) or lot<1:gaps.append('Неизвестен корректный размер лота; доступность покупки не подтверждена.');lot=None
    if len(frame) and lot:
        price=float(frame.CLOSE.iloc[-1]);cost=(commission_pct+slippage_pct)/100
        qty=int(amount/(price*(1+cost)*lot))*lot
        invested=qty*price;entry_cost=invested*cost;allocated=invested+entry_cost
        sizing={'quantity':qty,'lot_size':lot,'indicative_price':price,'invested':invested,'entry_cost':entry_cost,
                'allocated_cash':allocated,'cash_remaining':amount-allocated,'roundtrip_cost_pct':(1-(1-cost)/(1+cost))*100,
                'price_basis':'Последнее историческое CLOSE, а не текущая цена исполнения.'}
        if profile: impact=portfolio_impact(portfolio,amount,invested,entry_cost)
    if len(frame)>=65 and horizon<=252 and meta.get('asset_type') in {'equity','fund'} and meta.get('currency') in {'RUB','SUR'}:
        for model in ['block_bootstrap','historical_bootstrap']:
            result=simulate(frame.CLOSE,horizon=horizon,runs=runs,seed=seed,model=model,exit_policy='horizon',
                            commission_pct=commission_pct,slippage_pct=slippage_pct)
            model_stats.append(result.stats)
            del result
    risk=assess(frame,meta,quote,profile,quality,model_stats,sizing,impact)
    verdict=decide(risk,profile is not None)
    scenarios=[]
    if model_stats and sizing:
        for key,label in [('p05_return','Плохой сценарий · 5-й процентиль'),('median_return','Базовый сценарий · медиана'),('p95_return','Хороший сценарий · 95-й процентиль')]:
            r=model_stats[0][key];pnl=sizing['allocated_cash']*r
            scenarios.append({'name':label,'return_pct':r*100,'change_rub':pnl,'final_capital_rub':amount+pnl,
                              'method':'block_bootstrap, hold to horizon, zero-interest remaining cash; no tax or dividends'})
    facts=[]
    if quality.get('age_calendar_days') is not None and not gaps:facts.append('История прошла проверки формата, длины и возраста по методике v0.4.')
    if sizing.get('quantity',0):facts.append(f"По последнему CLOSE бюджет позволяет условно купить {sizing['quantity']} бумаг с указанными издержками.")
    if impact is not None and impact['after_weight_pct']<20:facts.append('В рамках указанного состава портфеля доля тикера после покупки остаётся ниже 20%.')
    return {'model_version':VERSION,'computed_at_utc':datetime.now(timezone.utc).isoformat(),
            'instrument':meta,'quote_snapshot':quote,'profile':profile,'portfolio_context':portfolio,'parameters':{'runs':runs,'seed':seed,'horizon_trading_days':horizon,
            'commission_pct':commission_pct,'slippage_pct':slippage_pct,'exit_policy':'horizon','as_of':str(day)},
            'quality':quality,'historical':historical,'models':model_stats,'sizing':sizing,'portfolio_impact':impact,
            'risk':risk,'verdict':verdict,'scenarios':scenarios,'confirmed_factors':facts,
            'alternatives':[{'type':'Широкий фонд акций','status':'Нужно исследовать состав, концентрацию, расходы и историю; диверсификация не гарантирует прибыль.'},
                {'type':'ОФЗ с подходящим сроком погашения','status':'Автоматический подбор по дюрации не выполнен. Нужны цена с НКД, купоны, погашение и процентный риск.'},
                {'type':'Сохранить деньги доступными','status':'Рассмотреть, если они нужны скоро. Условия вклада/счёта, инфляция и ограничения отдельно не проверялись.'}],
            'before_buy':['Проверить актуальную цену, размер лота, доступность бумаги и тариф брокера.',
                          'Для акции — отчётность, долговую нагрузку и текущую оценку; для фонда — состав, концентрацию и расходы.',
                          'Сопоставить деньги, нужные для обязательных расходов, с риском потери всей позиции.'],
            'limitations':['Исследовательский вывод по внутренним правилам, не рекомендация лицензированного советника.',
                'Модельные частоты не являются реальными вероятностями; плохой сценарий не является максимальным убытком.',
                'Цены без дивидендных и сплитовых корректировок; нет налогов и гарантии исполнения.',
                'Нет фундаментального анализа, новостей, полного состава фондов и корреляций портфеля.']}


async def investigate(symbol='SBER',profile=None,portfolio=None,*,demo=False,runs=2000,seed=42,commission_pct=.05,slippage_pct=.05):
    profile=validate_profile(profile)
    integer(runs,'runs',100,5000);integer(seed,'seed',0,1000000)
    if demo:
        frame,meta=demo_daily(days=756);quote=None
    else:
        end=market_today()-timedelta(days=1)
        frame,meta=await get_engine().frame(symbol,end-timedelta(days=1095),end)
        quote=await get_engine().research_quote(symbol)
    import asyncio
    result=await asyncio.to_thread(evaluate,frame,meta,quote,profile,portfolio,runs=runs,seed=seed,commission_pct=commission_pct,slippage_pct=slippage_pct)
    return result,frame


def render_investment_report(result):
    i=result['instrument'];v=result['verdict'];q=result['quality'];p=result['profile']
    lines=[f"# Investment Research Report · {i['symbol']}",f"\nДата расчёта: {result['computed_at_utc']} · модель: {result['model_version']}",
       '\n**ИСКУССТВЕННЫЕ ДАННЫЕ. Учебный вывод; не анализ реальной покупки.**' if q['synthetic'] else f"\nИсточник: {i.get('source')} · последнее наблюдение: {q.get('last_observation')}",
       f"\n## Вердикт: {v['label']}",v['main_reason'],f"Соответствие: {v['fit']}. Балл: {v['score'] if v['score'] is not None else 'не рассчитан'} (не вероятность).",
       f"\n## Условия\n{p if p else 'Профиль не заполнен. Персональное соответствие не оценено.'}",
       f"\n## Данные\n{q['history_points']} наблюдений. SHA-256: {i.get('history_sha256')}. Покрытие оценки рисков: частичное.",
       '\n## Исторические изменения цены']
    for n,h in result['historical'].items():lines.append(f"- {n} торговых дней: {h['return_pct']:+.2f}%. Доля отрицательных пересекающихся окон: {h['negative_period_frequency']:.1%}; окон {h['windows']}.")
    lines.append('\n## Проверка качества данных')
    lines += [f'- Критическое ограничение: {x}' for x in q['critical_gaps']]
    lines += [f'- Предупреждение: {x}' for x in q['warnings']]
    lines.append('\n## Воспроизводимость')
    lines.append(f"Правила: {v['rules_version']}. Параметры: {result['parameters']}. Размер позиции: {result['sizing']}.")
    lines.append(f"Контекст портфеля: {result['portfolio_context']}. Влияние: {result['portfolio_impact']}.")
    lines.append(f"Вычеты балла: {v['deductions']}. При конфликте балл ограничен {v['score_cap_if_conflict']}.")
    lines.append('\n## Модельные сценарии')
    for s in result['scenarios']:lines.append(f"- {s['name']}: {s['return_pct']:+.2f}%; изменение бюджета {s['change_rub']:+,.2f} ₽; итог {s['final_capital_rub']:,.2f} ₽.")
    lines.append('\n## Карта рисков')
    for f in result['risk']['factors']:lines.append(f"- **{f['name']} / {f['level']}**: {f['reason']} {f['limitations']}")
    lines+=['\n## Подтверждённые факторы']+[f'- {x}' for x in result['confirmed_factors']]
    lines+=['\n## Что может изменить вывод']+[f'- {x}' for x in v['what_can_change']]
    lines+=['\n## Альтернативы для исследования']+[f"- {x['type']}: {x['status']}" for x in result['alternatives']]
    lines+=['\n## Что проверить до покупки']+[f'- {x}' for x in result['before_buy']]
    lines+=['\n## Ограничения']+[f'- {x}' for x in result['limitations']]
    return '\n\n'.join(lines)
