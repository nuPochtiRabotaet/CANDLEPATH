"""Warm, beginner-oriented local research workspace; shared deterministic engines."""
import asyncio
from datetime import timedelta
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from .design import TOKENS
from . import dashboard as legacy
from .advisor import evaluate, investigate, render_investment_report
from .config import Settings, configure_logging
from .workspace_mode import legacy_invest_enabled
from .data import get_engine, market_today
from .education import ASSETS, TERMS, NETWORK_HELP, network_message
from .persistence import ResearchStore
from .portfolio import PortfolioStore, ledger_state
from .portfolio_ui import portfolio_page, current_portfolio, show_summary
from .portfolio_service import advisor_context
from time_machine_core.moex_data import demo_daily
from time_machine_core.simulator import simulate, compare_scenarios

PAGES=['Overview','Portfolio','Laboratory','Research']
LABELS=dict(zip(PAGES,['Обзор','Портфель','Лаборатория','Исследования']))
RESEARCH=['Market Explorer','Strategy Lab','Time Machine','History','Investment Advisor','AI Research']
RESEARCH_LABELS=dict(zip(RESEARCH,['Исследовать актив','Проверить стратегию','Time Machine','История','Подробная оценка вложения','AI / MCP']))


def store():return ResearchStore(Settings.from_env().data_dir/'research.sqlite3')


def navigate(page):
    st.session_state.show_settings=False
    if page in RESEARCH:
        st.session_state.page='Research';st.session_state.research_section=page
    else:st.session_state.page=page


def close_settings():st.session_state.show_settings=False


def toggle_settings():st.session_state.show_settings=not st.session_state.get('show_settings',False)


def header(dataset,laboratory=False):
    left,right=st.columns([3,2])
    with left:st.markdown('**CandlePath**  /  исследовательское пространство')
    with right:
        if laboratory:st.caption('Песочница · журнал не меняется')
        elif dataset:
            frame,meta,_=dataset
            st.caption(('ДЕМО · ' if meta.get('demo_data') else 'ISS · загружено · ')+f"{meta['symbol']} / {frame.index[-1].date()}")
        else:st.caption('ISS · не проверен  /  актив не загружен')
    st.divider()


def helper(dataset):
    with st.container(border=True):
        st.markdown('**На что смотреть**')
        st.caption('Контекстная справка · без языковой модели')
        if dataset:
            meta=dataset[1];name,text=ASSETS.get(meta['asset_type'],('Инструмент','Характеристики требуют уточнения.'))
            st.write(f"**{meta['symbol']} · {name}**");st.caption(text)
        current=st.session_state.get('advisor_result')
        if current and dataset and current['instrument'].get('history_sha256')==dataset[1].get('history_sha256'):
            st.markdown('**Последний вывод**');st.write(current['verdict']['label']);st.caption(current['verdict']['main_reason'])
        term=st.selectbox('Объяснить термин',list(TERMS),key='help_term')
        st.caption(TERMS[term])
        with st.expander('Подключить ИИ'):
            st.caption('Встроенная LLM не подключена. Локальные расчёты работают без неё. Внешний MCP-клиент может вызвать evaluate_investment и объяснить результат по правилам.')
            st.code('python -m moex_intelligence.mcp_server',language='bash')


def profile_preferences(value):
    from .validation import finite,integer
    raw=value if isinstance(value,dict) else {};clean={}
    for key,lo,hi in [('amount',1,1e9),('max_drawdown_pct',.1,100)]:
        try:clean[key]=finite(raw.get(key),key,lo,hi)
        except (ValueError,TypeError):pass
    try:clean['horizon_months']=integer(raw.get('horizon_months'),'Срок',1,60)
    except (ValueError,TypeError):pass
    if raw.get('risk_preference') in ('low','medium','high'):clean['risk_preference']=raw['risk_preference']
    if isinstance(raw.get('needs_money_early'),bool):clean['needs_money_early']=raw['needs_money_early']
    return clean,len(clean)==5


def settings_page(onboarding=False):
    db=store();prefs=db.preferences();p,_=profile_preferences(prefs.get('profile'))
    st.subheader('Расскажите об условиях исследования' if onboarding else 'Ваши настройки')
    st.caption('Необязательно. Данные хранятся локально. Здесь не нужны имя, паспорт, доход или брокерские ключи.')
    with st.form('preferences_form'):
        experience=st.selectbox('Опыт',['Начинаю','Есть опыт'],index=0 if prefs.get('experience','Начинаю')=='Начинаю' else 1)
        goal=st.text_input('Для чего вы исследуете инвестиции?',prefs.get('goal','Понять риск перед первой покупкой'))
        a,b=st.columns(2)
        amount=a.number_input('Планируемая сумма, ₽',1.,1e9,float(p.get('amount',5000)))
        months=b.number_input('Срок, месяцев',1,60,int(p.get('horizon_months',12)))
        drawdown=a.number_input('Какое снижение готовы выдержать, %',.1,100.,float(p.get('max_drawdown_pct',10)))
        pref=b.selectbox('Предпочтительный риск',['low','medium','high'],index=['low','medium','high'].index(p.get('risk_preference','low')),format_func=lambda x:{'low':'Низкий','medium':'Умеренный','high':'Высокий'}[x])
        early=st.checkbox('Эти деньги могут понадобиться раньше окончания срока',value=p.get('needs_money_early',False))
        save=st.form_submit_button('Сохранить профиль',type='primary')
    if save:
        prefs.update(experience=experience,goal=goal,onboarding_done=True,profile={'amount':amount,'horizon_months':months,'max_drawdown_pct':drawdown,'risk_preference':pref,'needs_money_early':early})
        db.save_preferences(prefs);st.success('Профиль сохранён. Его можно менять перед каждым исследованием.')
    if onboarding and st.button('Пропустить знакомство',key='skip_onboarding'):
        prefs['onboarding_done']=True;db.save_preferences(prefs);st.rerun()
    if not onboarding:
        st.caption(f'Хранилище: {Settings.from_env().data_dir}. API-ключи не используются. Публичный сервер отключён.')
        with st.expander('О методике'):
            st.write('Условия проверяет Python Decision Engine. Неизвестный риск не считается низким. Нет проверенной фундаментальной оценки — нет положительного инвестиционного вывода только из истории цены.')
            st.caption('Пороговые значения — внутренняя консервативная методика v0.4, не норматив и не калиброванная вероятность.')


def overview(dataset):
    if PortfolioStore(Settings.from_env().data_dir/'portfolio.sqlite3').load():
        _,_,portfolio_result=current_portfolio()
        show_summary(portfolio_result)
    st.title('Мой капитал')
    st.write('Портфель, проверка предполагаемой покупки и эксперименты с ценой.')
    cols=st.columns(2)
    cols[0].button('Открыть портфель',on_click=navigate,args=('Portfolio',),type='primary',key='home_portfolio',width='stretch')
    cols[1].button('Проверить покупку / Сценарии',on_click=navigate,args=('Laboratory',),key='home_lab',width='stretch')
    if dataset:
        frame,meta,_=dataset;legacy.source_caption(frame,meta)
        st.plotly_chart(legacy.line_figure(frame,['CLOSE'],'Пункты' if meta['asset_type']=='index' else '% номинала' if meta['asset_type']=='bond' else 'Цена за бумагу'),width='stretch')
    with st.expander('Срез рынка · IMOEX и выбранные бумаги'):
        st.caption('По запросу; отдельные бумаги не заменяют индекс. Индекс нельзя купить напрямую.')
        if st.button('Обновить срез MOEX',key='snapshot'):
            rows=[]
            for ticker in ['IMOEX','SBER','SBMX']:
                try:
                    q=asyncio.run(get_engine().research_quote(ticker));md=q['marketdata']
                    rows.append({'Тикер':ticker,'Последнее значение':q['last_price'],'Единицы':q['price_unit'],'Биржевое время':md.get('SYSTIME') or md.get('UPDATETIME'), 'Загружено UTC':q['retrieved_at_utc']})
                except ValueError as exc:rows.append({'Тикер':ticker,'Ошибка':str(exc)})
            st.session_state.market_rows=rows
        if 'market_rows' in st.session_state:st.dataframe(pd.DataFrame(st.session_state.market_rows),hide_index=True,width='stretch')
    events=PortfolioStore(Settings.from_env().data_dir/'portfolio.sqlite3').load()
    if events:
        state=ledger_state(events)
        st.caption(f"Мой портфель: {len(state['positions'])} открытых позиций · свободные деньги {state['cash']:,.2f} ₽. Полная стоимость требует актуальных оценок.")
    recent=store().list(3)
    if recent:
        st.subheader('Последние исследования')
        st.dataframe(pd.DataFrame(recent)[['symbol','created']],hide_index=True,width='stretch')
        st.button('Открыть историю',on_click=navigate,args=('History',))
    with st.expander('Коротко об инвестициях'):
        for name,text in ASSETS.values():st.markdown(f'**{name}.** {text}')
        st.write(TERMS['Диверсификация']);st.write(TERMS['Историческая доходность'])
    if not store().preferences().get('onboarding_done'):
        with st.expander('Необязательное знакомство · настроить профиль'):settings_page(True)


def explorer(dataset):
    if dataset:
        name,text=ASSETS.get(dataset[1]['asset_type'],('Инструмент','Описание недоступно.'))
        st.info(f'Что вы покупаете: {name.lower()}. {text}')
    legacy.explorer(dataset)
    if dataset and not dataset[1].get('demo_data'):
        with st.expander('Сравнить на одинаковых датах'):
            benchmark=st.selectbox('Ориентир',['SBMX','IMOEX'],key='benchmark')
            if st.button('Сравнить историю',key='compare_assets'):
                from .comparison import compare_instruments
                try:st.session_state.comparison=asyncio.run(compare_instruments(dataset[1]['symbol'],benchmark,st.session_state.lookback))
                except ValueError as exc:st.error(network_message(exc))
            r=st.session_state.get('comparison')
            if r and r['instruments'][0]['symbol']==dataset[1]['symbol']:
                st.caption(f"Общие даты: {r['first_date']} — {r['last_date']}; {r['observations']} наблюдений. Бета: {r['beta']}")
                st.dataframe(pd.DataFrame(r['stats']),hide_index=True,width='stretch')
                st.caption(' '.join(r['limitations']))


def _load_context_history(symbol):
    from .lab_ui import cached_history
    history=cached_history(symbol,str(market_today()-timedelta(days=1)))
    if history['data'] is None:
        st.session_state.research_context_error=str(history['error']);return
    frame,meta=history['data']
    st.session_state.context_dataset=(frame,meta,None)
    st.session_state.symbol=symbol
    st.session_state.mode='MOEX ISS'


def research_asset_page(dataset):
    from .experience import asset_card
    from .lab_ui import cached_asset
    from .portfolio_ui import instrument_picker,portfolio_store
    st.title('Исследовать актив')
    st.caption('Цена, история и глубокий анализ в контексте выбранной бумаги.')
    symbol=instrument_picker('research_asset',st.session_state.get('symbol','SBER'),compact=True)
    try:
        loaded=cached_asset(symbol,str(Settings.from_env().data_dir));asset=loaded['asset']
        if asset:
            quantity=ledger_state(portfolio_store().load())['positions'].get(symbol,{}).get('quantity',0)
            from .provenance import asset_mark
            from .portfolio_service import value_portfolio
            _,portfolio_bundle,current=current_portfolio()
            marks={**current.get('market',{}).get('marks',{}),symbol:asset_mark(asset)}
            scoped=value_portfolio([r['event'] for r in portfolio_bundle['records']],{'marks':marks,'errors':{}})
            position=next((p for p in scoped['snapshot']['positions'] if p['symbol']==symbol),None) if scoped['snapshot'] else None
            asset_card(symbol,quantity,asset_mark(asset),key='research_asset_card',position=position)
        else:st.warning('Цена недоступна: '+str(loaded.get('error')))
    except (ValueError,TypeError,KeyError) as exc:st.warning(str(exc))
    st.button('Загрузить историю выбранного актива для исследований',on_click=_load_context_history,args=(symbol,),key='research_load_selected')
    if st.session_state.get('research_context_error'):st.warning(st.session_state.pop('research_context_error'))
    selected_dataset=dataset if dataset and (dataset[1]['symbol']==symbol or dataset[1].get('demo_data')) else None
    with st.expander('Исходные данные, свечи и сравнение'):
        explorer(selected_dataset)


def show_verdict(result, archived=False):
    v=result['verdict'];q=result['quality']
    if q['synthetic']:st.warning('УЧЕБНЫЙ ВЫВОД · искусственные данные. Не оценка реальной покупки SBER.')
    if archived:st.info('Сохранённый снимок. История и вердикт не пересчитаны на сегодняшних данных.')
    st.caption(f"{result['instrument']['symbol']} · {result['computed_at_utc']} · {result['model_version']}")
    with st.container(border=True):
        st.subheader(v['label'])
        st.write(v['main_reason'])
        st.caption(f"Соответствие условиям: {v['fit']}")
        if result['profile']:st.write(f"Сумма: {result['profile']['amount']:,.0f} ₽ · срок: {result['profile']['horizon_months']} мес. · допустимое снижение: {result['profile']['max_drawdown_pct']}%")
        st.caption(f"Оценённый риск: {result['risk']['known_risk_level']} · покрытие рисков частичное. Неизвестные факторы перечислены ниже.")
    if q['critical_gaps']:
        for gap in q['critical_gaps']:st.warning(gap)
    cols=st.columns(3)
    for col,s in zip(cols,result['scenarios']):
        col.metric(s['name'],f"{s['final_capital_rub']:,.0f} ₽",f"{s['change_rub']:+,.0f} ₽")
    if result['scenarios']:st.caption('5-й процентиль / медиана / 95-й процентиль block bootstrap. Возможны исходы хуже «плохого». Это модель, не прогноз; остаток денег не приносит проценты.')
    with st.expander('Почему такой вывод?',expanded=True):
        for item in v['decisive_factors']:st.write('• '+item['reason'])
        if not result['profile']:st.write('Для личного соответствия нужны сумма, срок, допустимое снижение и потребность в деньгах.')
        if result['confirmed_factors']:
            st.markdown('**Что подтверждено**')
            for fact in result['confirmed_factors']:st.write('• '+fact)
    with st.expander('Карта рисков и ограничения данных'):
        for f in result['risk']['factors']:
            st.markdown(f"**{f['name']} · {f['level']}**")
            st.write(f['reason']);st.caption(f['limitations']+' '+f['effect'])
    with st.expander('Подробности балла и расчётов'):
        st.write(f"Балл: {v['score'] if v['score'] is not None else 'не рассчитывается'}. {v['score_label']}.")
        st.json({'rules_version':v['rules_version'],'deductions':v['deductions'],'cap_on_conflict':v['score_cap_if_conflict'],'priority':v['rule_order']})
        st.json({'quality':q,'historical':result['historical'],'model_parameters':result['parameters'],'models':result['models'],'sizing':result['sizing'],'portfolio_impact':result['portfolio_impact']})
    with st.expander('Альтернативы и что проверить до покупки'):
        for x in result['alternatives']:st.markdown(f"**{x['type']}** — {x['status']}")
        for x in result['before_buy']:st.write('• '+x)
        st.markdown('**Что может изменить вывод**')
        for x in v['what_can_change']:st.write('• '+x)
    st.download_button('Скачать исследование · Markdown',render_investment_report(result),file_name=f"{result['instrument']['symbol']}_research.md",mime='text/markdown',key='download_'+result['computed_at_utc'])
    st.caption('Исследовательский вывод по прозрачным правилам. Это не персональная рекомендация лицензированного советника. Решение остаётся за вами.')


def advisor_page(dataset):
    st.title('Подробная оценка вложения')
    st.caption('Риски, модели и соответствие условиям · '+st.session_state.get('symbol','SBER'))
    if st.session_state.get('advisor_bridge_notice'):st.info(st.session_state.pop('advisor_bridge_notice'))
    prefs=store().preferences();p,profile_complete=profile_preferences(prefs.get('profile'))
    saved_context=None
    if PortfolioStore(Settings.from_env().data_dir/'portfolio.sqlite3').load():
        _,_,saved_portfolio=current_portfolio()
        saved_context=advisor_context(saved_portfolio['snapshot'],st.session_state.symbol)
        if st.session_state.mode.startswith('Демо'):saved_context=None
        use_saved=st.checkbox('Использовать мой портфель при оценке покупки',value=True,key='advisor_use_saved',disabled=saved_context is None)
        if saved_context is None:st.warning('Для автоматического контекста портфеля нужны котировки всех его позиций.')
    else:use_saved=False
    with st.form('advisor_form'):
        a,b,c=st.columns(3)
        amount=a.number_input('Хочу вложить, ₽',1.,1e9,float(p.get('amount',5000)),key='adv_amount')
        months=b.number_input('На сколько месяцев',1,60,int(p.get('horizon_months',12)),key='adv_months')
        loss=c.number_input('Допустимое снижение, %',.1,100.,float(p.get('max_drawdown_pct',10)),key='adv_loss',help='Какое временное или окончательное снижение суммы вы готовы выдержать. Это ограничение, а не гарантия модели.')
        a,b=st.columns(2)
        pref=a.selectbox('Предпочтительный риск',['low','medium','high'],index=['low','medium','high'].index(p.get('risk_preference','low')),format_func=lambda x:{'low':'Низкий','medium':'Умеренный','high':'Высокий'}[x],key='adv_risk')
        early=b.checkbox('Деньги могут понадобиться раньше',value=p.get('needs_money_early',False),key='adv_early')
        filled=st.checkbox('Это мои условия — оценить соответствие профилю',value=profile_complete,key='adv_filled')
        with st.expander('Как покупка изменит портфель?'):
            if use_saved and saved_context:
                st.caption(f"Из журнала: капитал {saved_context['equity']:,.2f} ₽ · деньги {saved_context['cash']:,.2f} ₽ · выбранный тикер {saved_context['asset_value']:,.2f} ₽. После правок портфеля используется новый снимок.")
            known=st.checkbox('Я укажу текущую структуру',key='adv_portfolio_known',disabled=bool(use_saved and saved_context))
            a,b,c=st.columns(3)
            total=a.number_input('Стоимость портфеля до покупки, ₽',0.,1e12,0.,key='adv_total',disabled=bool(use_saved and saved_context))
            held=b.number_input('В нём уже есть этот тикер, ₽',0.,1e12,0.,key='adv_held',disabled=bool(use_saved and saved_context))
            cash=c.number_input('Свободные деньги в портфеле, ₽',0.,1e12,0.,key='adv_cash',disabled=bool(use_saved and saved_context))
            funding=st.selectbox('Источник покупки',['new_money','existing_cash'],format_func=lambda x:'Новые деньги' if x=='new_money' else 'Деньги внутри портфеля',key='adv_funding')
            st.caption('Ручные оценки используйте на одну дату. Свободные деньги входят в общую стоимость. «Новые деньги» увеличивают капитал, «Деньги внутри портфеля» используют доступный остаток.')
        with st.expander('Параметры исследования'):
            runs=st.selectbox('Сценариев в каждой модели',[1000,2000,5000],index=1,key='adv_runs')
            seed=st.number_input('Seed исследования',0,1000000,42,key='adv_seed')
            a,b=st.columns(2)
            fee=a.number_input('Комиссия на сторону, %',0.,3.,.05,.01,key='adv_fee')
            slip=b.number_input('Проскальзывание на сторону, %',0.,3.,.05,.01,key='adv_slip')
            st.caption('Block bootstrap и независимый historical bootstrap. Удержание до конца срока без автоматического выхода по стопу. Горизонт модели — до 12 месяцев, без скрытого сокращения более длинного срока.')
        submit=st.form_submit_button('Проанализировать инвестицию',type='primary')
    if submit:
        st.session_state.pop('advisor_result',None)
        profile={'amount':amount,'horizon_months':months,'max_drawdown_pct':loss,'risk_preference':pref,'needs_money_early':early} if filled else None
        portfolio={**saved_context,'funding':funding} if use_saved and saved_context else {'equity':total,'asset_value':held,'cash':cash,'funding':funding} if known else None
        try:
            with st.spinner('Проверяю данные и сопоставляю риски с условиями…'):
                if dataset:
                    frame,meta,quote=dataset
                    result=evaluate(frame,meta,quote,profile,portfolio,runs=runs,seed=seed,commission_pct=fee,slippage_pct=slip)
                else:
                    result,frame=asyncio.run(investigate(st.session_state.symbol,profile,portfolio,demo=st.session_state.mode.startswith('Демо'),runs=runs,seed=seed,commission_pct=fee,slippage_pct=slip))
                study_id=store().save(result,frame)
            st.session_state.advisor_result=result
            st.session_state.advisor_selection=(st.session_state.mode,st.session_state.symbol,st.session_state.lookback)
            st.success('Исследование сохранено в истории.')
        except (ValueError,TypeError,KeyError) as exc:st.error(network_message(exc));st.caption(NETWORK_HELP)
    result=st.session_state.get('advisor_result')
    selection=(st.session_state.mode,st.session_state.symbol,st.session_state.lookback)
    if result and st.session_state.get('advisor_selection')==selection:
        show_verdict(result)
        st.caption('Показан последний сохранённый расчёт. Изменённые поля применяются только после нового нажатия «Проанализировать инвестицию».')


def history_page():
    st.title('История исследований')
    entries=store().list()
    if not entries:st.info('Сохранённых исследований пока нет. Начните с оценки вложения.');return
    selected=st.selectbox('Открыть снимок',entries,format_func=lambda x:f"{x['symbol']} · {x['created']}",key='history_selected')
    payload=store().load(selected['id']);result=payload['result']
    if result.get('kind')=='lab_scenarios':
        from .lab_ui import show_saved_scenarios
        show_saved_scenarios(result,payload['history_csv']);return
    if st.button('Повторить анализ с новыми данными',key='rerun_study'):
        try:
            with st.spinner('Создаю новое исследование; старое останется в истории…'):
                par=result['parameters']
                fresh,frame=asyncio.run(investigate(result['instrument']['symbol'],result['profile'],result.get('portfolio_context'),
                    demo=result['quality']['synthetic'],runs=par['runs'],seed=par['seed'],commission_pct=par['commission_pct'],slippage_pct=par['slippage_pct']))
                store().save(fresh,frame)
            st.success('Новое исследование сохранено. Выберите его в списке после обновления страницы.')
        except ValueError as exc:st.error(network_message(exc))
    show_verdict(result,True)
    st.download_button('Исходные цены снимка CSV',payload['history_csv'],file_name='research_history.csv',mime='text/csv')


def scenarios_page(dataset):
    st.title('Сценарии будущего')
    if not legacy.need_data(dataset):return
    frame,meta,_=dataset;legacy.source_caption(frame,meta)
    from .data import require_equity
    try:require_equity(meta)
    except ValueError as exc:st.warning(str(exc));return
    if meta['asset_type']=='index':st.info('Индекс доступен для исторического сравнения, но не для моделирования покупки.');return
    with st.form('simulation_form'):
        a,b=st.columns(2)
        capital=a.number_input('Условная сумма, ₽',100.,1e9,100000.,key='sim_capital')
        horizon=b.slider('Горизонт, торговых дней',1,120,20,key='horizon')
        with st.expander('Параметры модели и выхода'):
            a,b,c=st.columns(3)
            runs=a.selectbox('Сценариев',[1000,5000,10000,20000],index=2,key='runs')
            target=b.number_input('Цель по цене, %',.1,100.,8.,key='target')
            stop=c.number_input('Стоп по цене, %',.1,90.,5.,key='stop')
            model=st.selectbox('Модель',['block_bootstrap','historical_bootstrap','gbm'],format_func=lambda x:{'block_bootstrap':'Блоки исторических изменений','historical_bootstrap':'Независимые исторические изменения','gbm':'Геометрическое броуновское движение'}[x],key='sim_model')
            policy=st.selectbox('Правило выхода',['barriers','horizon'],format_func=lambda x:'По цели/стопу на дневном закрытии' if x=='barriers' else 'Удерживать до конца срока',key='exit_policy')
            a,b,c=st.columns(3)
            fee=a.number_input('Комиссия за сторону, %',0.,3.,.05,.01,key='sim_fee')
            slip=b.number_input('Проскальзывание за сторону, %',0.,3.,.05,.01,key='sim_slip')
            block=c.slider('Блок истории, дней',1,20,5,key='block')
            seed=st.number_input('Seed',0,1000000,42,key='sim_seed')
            compare=st.checkbox('Сравнить три предположения о рынке',key='compare')
            st.caption('GBM предполагает нормальные независимые лог-изменения с постоянными параметрами и может недооценивать гэпы. Bootstrap зависит от выбранной истории.')
        submit=st.form_submit_button('Рассчитать сценарии',type='primary')
    if submit:
        st.session_state.pop('simulation',None)
        options=dict(horizon=horizon,runs=runs,target_pct=target,stop_pct=stop,commission_pct=fee,slippage_pct=slip,block=block,seed=seed,model=model,exit_policy=policy)
        try:
            result=simulate(frame.CLOSE,**options)
            compared=compare_scenarios(frame.CLOSE,**options) if compare else None
            st.session_state.simulation=(meta['history_sha256'],result,compared,capital,options)
        except ValueError as exc:st.error(str(exc))
    saved=st.session_state.get('simulation')
    if not saved or saved[0]!=meta['history_sha256']:return
    _,r,compared,capital,options=saved;s=r.stats
    st.caption(f"Последний расчёт: {options['runs']} сценариев, {options['horizon']} дней, {options['model']}, seed {options['seed']}. Режим интерфейса не меняет числа.")
    cols=st.columns(3)
    for col,label,key in zip(cols,['Плохой · 5-й процентиль','Базовый · медиана','Хороший · 95-й процентиль'],['p05_return','median_return','p95_return']):col.metric(label,f"{capital*(1+s[key]):,.0f} ₽",f"{s[key]*100:+.2f}%")
    st.caption('Это три точки модельного распределения. Медиана не названа наиболее вероятным будущим, а 5-й процентиль не ограничивает возможный убыток.')
    q=np.quantile(r.paths,[.05,.5,.95],axis=0);xs=np.arange(options['horizon']+1)
    fig=go.Figure([go.Scatter(x=xs,y=q[0],line_width=0,showlegend=False),go.Scatter(x=xs,y=q[2],line_width=0,fill='tonexty',fillcolor=TOKENS['accent_fill'],name='5–95%'),go.Scatter(x=xs,y=q[1],line_color=TOKENS['accent'],name='Медиана цены')])
    st.plotly_chart(legacy.chart(fig,350,'Модельная цена'),width='stretch')
    cols=st.columns(3)
    cols[0].metric('VaR 95% · модельный убыток',f"{s['var95_loss']:.2%}",help=TERMS['VaR'])
    cols[1].metric('ES 95% · средний хвостовой убыток',f"{s['es95_loss']:.2%}",help=TERMS['Expected Shortfall'])
    cols[2].metric('Убыточных сценариев',f"{s['p_loss']:.1%}",help=TERMS['Модельные сценарии'])
    with st.expander('Частоты выходов, просадки и распределение'):
        st.json(s)
        st.plotly_chart(legacy.chart(go.Figure(go.Histogram(x=r.net_returns*100,nbinsx=50,marker_color=TOKENS['fund'])),260,'Сценарии'),width='stretch')
        if compared:st.dataframe(pd.DataFrame(compared),hide_index=True,width='stretch')
        st.caption('Ценовые траектории продолжаются после условного выхода; прибыль/убыток позиции после выхода фиксируется. Стоп и цель проверяются только по дневному CLOSE, не по внутридневным касаниям. VaR/ES отрицательны, если соответствующий хвост дал прибыль.')
    table=pd.DataFrame({'net_return_pct':r.net_returns*100,'final_capital_rub':capital*(1+r.net_returns),'exit_day':r.exit_steps,'outcome':np.where(r.hit_stop,'stop',np.where(r.hit_target,'target','horizon'))})
    st.download_button('Результаты CSV',table.to_csv(index=False),file_name='simulation.csv',mime='text/csv')
    st.caption('Синтетические частоты не равны реальным вероятностям. Нет налогов, дивидендов, сплитов и гарантии исполнения. Денежный пересчёт здесь допускает дробную позицию; Advisor отдельно проверяет лоты.')


def main():
    st.set_page_config(page_title='CandlePath',page_icon='◈',layout='wide',initial_sidebar_state='expanded')
    legacy_invest = legacy_invest_enabled()
    workspaces = ['Invest', 'Trade', 'Strategy Coliseum'] if legacy_invest else ['Trade', 'Strategy Coliseum']
    if st.session_state.get('workspace_mode') not in workspaces:
        st.session_state.workspace_mode = workspaces[0]
    workspace = st.session_state.workspace_mode
    if workspace != 'Trade':
        workspace = st.sidebar.segmented_control('Рабочее пространство', workspaces, default=workspace) or workspace
        st.session_state.workspace_mode = workspace
    if workspace == 'Strategy Coliseum':
        from .crypto.coliseum_ui import page
        page()
        return
    configure_logging()
    from .upgrades import ensure_v081_backup
    try:ensure_v081_backup(Settings.from_env().data_dir)
    except Exception as exc:
        st.error('Не удалось создать резервную копию перед обновлением. Данные не изменены: '+str(exc));return
    from .experience import apply_theme,overview_page
    apply_theme()
    if workspace=='Trade':
        st.markdown('<style>[data-testid="stSidebar"]{display:none!important}[data-testid="stMainBlockContainer"]{max-width:100%;padding:1rem 1.25rem}header[data-testid="stHeader"]{height:0}</style>',unsafe_allow_html=True)
        from .crypto.ui import page as trade_page
        trade_page();return
    prefs=store().preferences()
    if st.session_state.get('research_section')=='Laboratory':st.session_state.research_section='Market Explorer'
    old_page=st.session_state.get('page','Overview')
    if old_page=='History':navigate('History')
    elif old_page in RESEARCH and old_page not in PAGES:navigate(old_page)
    elif old_page=='Settings':st.session_state.page='Overview';st.session_state.show_settings=True
    pending=st.session_state.pop('navigation_request',None)
    if pending:
        st.session_state.page='Research';st.session_state.research_section='Investment Advisor'
        st.session_state.symbol=pending['symbol'];st.session_state.show_settings=False
        for key,value in pending['fields'].items():st.session_state[key]=value
        st.session_state.advisor_bridge_notice=pending['notice']
    st.session_state.setdefault('page','Overview')
    st.html('<style>.st-key-nav_'+st.session_state.page+' button{background:var(--accent)!important;color:var(--bg)!important}</style>')
    with st.sidebar:
        st.markdown('**CandlePath**')
        with st.container(key='app_navigation'):
            for target in PAGES:
                st.button(LABELS[target],key='nav_'+target,width='stretch',type='primary' if st.session_state.page==target else 'secondary',on_click=navigate,args=(target,))
        page=st.session_state.page
        section=st.selectbox('Задача исследования',RESEARCH[:4],format_func=lambda x:RESEARCH_LABELS[x],key='research_section') if page=='Research' and st.session_state.get('research_section') not in RESEARCH[4:] else st.session_state.get('research_section','Market Explorer') if page=='Research' else None
        with st.expander('Данные исследования'):
            mode=st.radio('Источник',['MOEX ISS','Демо · искусственные данные'],key='mode')
            st.session_state.setdefault('symbol','SBER')
            symbol=(st.text_input('Тикер',value=None,disabled=mode.startswith('Демо'),key='symbol') or '').strip().upper()
            lookback=st.selectbox('История, календарных дней',[365,730,1095],index=2,key='lookback')
            fingerprint=(mode,symbol,lookback)
            if st.button('Загрузить данные',type='primary',key='load_history',width='stretch'):
                st.session_state.pop('dataset',None)
                st.session_state.pop('context_dataset',None)
                try:
                    with st.spinner('Запрашиваю историю…'):
                        if mode.startswith('Демо'):frame,meta=demo_daily(days=756);quote=None
                        else:
                            last=market_today()-timedelta(days=1)
                            frame,meta=get_engine().frame_sync(symbol,last-timedelta(days=lookback),last)
                            quote=asyncio.run(get_engine().research_quote(symbol))
                    st.session_state.dataset=(fingerprint,(frame,meta,quote))
                except (ValueError,TypeError,KeyError) as exc:st.error(network_message(exc));st.caption(NETWORK_HELP)
            st.caption('Эти настройки нужны для подробных исследований. Лаборатория сама запрашивает реальные цены; демо туда не подставляется.')

    saved=st.session_state.get('dataset');dataset=saved[1] if saved and saved[0]==fingerprint else None
    context=st.session_state.get('context_dataset')
    if context and context[1]['symbol']==symbol and mode=='MOEX ISS':dataset=context
    from .experience import refresh_market
    with st.container(key='workspace_header',horizontal=True,vertical_alignment='center'):
        st.markdown('**CandlePath** / '+LABELS[page],width='stretch')
        st.button('Обновить цены',icon=':material/refresh:',help='Обновить котировки; историю заново не загружаем',key='header_refresh',on_click=refresh_market,width=44)
        st.button('Настройки',icon=':material/settings:',help='Профиль и настройки приложения',key='open_settings',on_click=toggle_settings,width=44)
    if st.session_state.get('show_settings'):settings_page();return
    if page=='Overview':overview_page()
    elif page=='Portfolio':portfolio_page()
    elif page=='Laboratory':
        from .lab_ui import laboratory_page
        laboratory_page()
    else:
        if section in RESEARCH[4:]:
            with st.container(horizontal=True):
                st.button('К карточке актива',on_click=navigate,args=('Market Explorer',),key='back_asset_top')
                st.button('Вернуться в портфель',on_click=navigate,args=('Portfolio',),key='back_portfolio_top')
        if section=='History':history_page()
        elif section=='Market Explorer':
            research_asset_page(dataset)
        elif section=='Investment Advisor':advisor_page(dataset)
        elif section=='Time Machine':scenarios_page(dataset)
        elif section=='Strategy Lab':legacy.strategy_lab(dataset)
        else:legacy.ai_research(dataset)
        with st.expander('AI, MCP и подробная оценка'):
            a,b=st.columns(2)
            a.button('Подробный Advisor',on_click=navigate,args=('Investment Advisor',),key='deep_advisor')
            b.button('AI Research / MCP',on_click=navigate,args=('AI Research',),key='deep_ai')
            helper(dataset)
            if section in RESEARCH[4:]:st.button('Вернуться к исследованию актива',on_click=navigate,args=('Market Explorer',),key='back_research')

