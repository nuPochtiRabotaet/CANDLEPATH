"""Versioned transparent rules, not a trained predictor or licensed advice."""
VERSION = 'rules-0.4.0'
CATEGORIES = {'consider':'Скорее стоит рассмотреть','study':'Лучше дополнительно изучить',
              'unsuitable':'Скорее не подходит','insufficient':'Недостаточно данных'}


def decide(risk, profile_complete):
    hard = risk['hard_conflicts']; gaps = risk['critical_gaps']; unknown = risk['uncertainties']
    score = None
    deductions = []
    if profile_complete and not gaps:
        weights = {'drawdown':40,'horizon':25,'concentration':25,'liquidity':20,'costs':10,'preference':15,
                   'model_disagreement':10,'fundamentals':10,'portfolio_unknown':10,'history_warning':10}
        for item in hard + unknown:
            if item['id'] in weights and not any(d['id']==item['id'] for d in deductions):
                deductions.append({'id':item['id'],'points':weights[item['id']],'reason':item['reason']})
        score = max(0,100-sum(x['points'] for x in deductions))
        if hard: score = min(score,40)
    if not profile_complete:
        key='insufficient'; fit='Невозможно оценить'; reason='Профиль не заполнен: нельзя оценить соответствие вложения вашим условиям.'
    elif hard:
        key='unsuitable'; fit='Не соответствует'; reason=hard[0]['reason']
    elif gaps:
        key='insufficient'; fit='Невозможно оценить'; reason=gaps[0]
    elif unknown:
        key='study'; fit='Частично соответствует'; reason=unknown[0]['reason']
    else:
        key='consider'; fit='Соответствует проверенным ограничениям'; reason='В пределах проверенных данных конфликтов с заданными условиями не найдено; это не оценка справедливой цены.'
    return {'category':key,'label':CATEGORIES[key],'fit':fit,'main_reason':reason,'score':score,
            'score_label':'Внутренний балл соответствия правилам, не вероятность успеха',
            'deductions':deductions,'score_cap_if_conflict':40,'rules_version':VERSION,
            'rule_order':['missing_profile','hard_conflicts','critical_data_gaps','uncertainties','consider'],
            'decisive_factors':hard if hard else ([{'id':'data','reason':g} for g in gaps] or unknown),
            'what_can_change':['Изменение срока, допустимых потерь или потребности в деньгах — только если это действительно соответствует вашей ситуации.',
                               'Проверенные актуальные данные, состав портфеля и оценка бизнеса / состава фонда.',
                               'Меньший размер позиции может уменьшить концентрацию, но не риск самой бумаги.']}
