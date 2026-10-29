"""Unified local Streamlit terminal; all calculations delegate to shared Python modules."""
from __future__ import annotations
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from moex import metrics
from time_machine_core.moex_data import demo_daily
from time_machine_core.simulator import simulate, compare_scenarios
from time_machine_mcp import run_analysis
from .backtest import compare_backtest
from .config import Settings, configure_logging
from .data import get_engine, market_today, require_equity
from .portfolio import PortfolioStore, analyze_portfolio, ledger_state, stress_test, portfolio_curve
from .research import render_report

PAGES = ['Overview', 'Market Explorer', 'Time Machine', 'Strategy Lab', 'Portfolio', 'AI Research']
from .design import TOKENS
GREEN,BLUE,RED=TOKENS['gain'],TOKENS['accent'],TOKENS['loss']


def chart(fig,height=360,ytitle=None):
    from .design import chart_style
    return chart_style(fig,height,ytitle)


def line_figure(frame, names, ytitle=None, height=360):
    fig = go.Figure()
    for name, color in zip(names,[GREEN,BLUE,RED]):
        fig.add_trace(go.Scatter(x=frame.index, y=frame[name], name=name, line=dict(color=color,width=2)))
    return chart(fig,height,ytitle)


def source_caption(frame, meta):
    label = 'СИНТЕТИЧЕСКИЕ ДАННЫЕ' if meta.get('demo_data') else 'MOEX ISS · нескорректированные цены'
    st.caption(f"{label} · {meta['symbol']} / {meta['board']} · {len(frame)} наблюдений · {frame.index[0].date()} — {frame.index[-1].date()}")
    if meta.get('demo_data'): st.warning('Демонстрация: это искусственная история, а не котировки SBER.')
    else: st.caption(f"Загружено: {meta.get('retrieved_at_utc')} · кеш: {'да' if meta.get('cache',{}).get('hit') else 'нет'}. Время загрузки не является временем сделки.")
    if meta.get('coverage_warning'): st.warning('История выбранного режима торгов начинается позже запрошенной даты. Данные других режимов не объединялись автоматически.')
    if meta.get('freshness_warning'): st.warning('Последнее историческое наблюдение старше конца запрошенного периода более чем на 14 дней. Проверьте состояние торгов.')


def need_data(dataset):
    if dataset is None:
        st.info('Выберите источник и нажмите «Загрузить данные» слева. Демо работает без интернета.')
        return False
    return True


def overview(dataset):
    st.title('Обзор исследования')
    st.write('От рыночных данных к проверяемым гипотезам.')
    if not need_data(dataset):
        cols = st.columns(3)
        for col, title, text in zip(cols, ['01 / Данные','02 / Модели','03 / Проверка'],
            ['Исследуйте SBER, фонды и облигации с явным источником и датой.',
             'Сравнивайте траектории, издержки и хвостовые потери.',
             'Проверяйте стратегии на отложенном периоде и ведите виртуальный портфель.']):
            with col:
                with st.container(border=True): st.subheader(title); st.write(text)
        st.caption('Локальный аналитический терминал · только чтение · без торговых приказов')
        return
    frame, meta, quote = dataset
    source_caption(frame,meta)
    raw = {'rows':[{'TRADEDATE':str(day.date()),'CLOSE':float(v)} for day,v in frame.CLOSE.items()]}
    s = metrics(raw)
    cols = st.columns(4)
    cols[0].metric('Последнее закрытие', f"{frame.CLOSE.iloc[-1]:,.2f}")
    cols[1].metric('Изменение цены за период', f"{s['price_return_pct']:+.2f}%")
    cols[2].metric('Просадка по закрытиям', f"{s['max_close_drawdown_pct']:.2f}%")
    cols[3].metric('Историческая волатильность', f"{s['annualized_volatility_pct']:.2f}%")
    st.plotly_chart(line_figure(frame,['CLOSE'],'% номинала' if meta['asset_type']=='bond' else 'Цена за бумагу'), width='stretch')
    st.caption('Показатели цены выбранного инструмента. Это не индекс всего рынка и не полная доходность с выплатами.')
    if quote:
        st.caption(f"Последняя сделка LAST: {quote.get('last_price')} · валюта: {quote.get('currency')} · лот: {quote['security'].get('LOTSIZE')}. LAST может отличаться от исторического CLOSE.")
    if meta['asset_type']=='bond': st.warning('Облигация: график цены в процентах номинала. НКД, купоны, амортизация и погашение в доходность не включены.')


def explorer(dataset):
    st.title('Market Explorer')
    st.write('Инструмент, режим торгов и исходные данные.')
    query = st.text_input('Найти инструмент', 'SBER', key='search_query')
    if st.button('Поиск в MOEX ISS', key='search'):
        try: st.session_state.search_results = asyncio.run(get_engine().search(query,20))
        except ValueError as exc: st.error(str(exc))
    if 'search_results' in st.session_state:
        st.dataframe(pd.DataFrame(st.session_state.search_results['results']),hide_index=True,width='stretch')
        st.caption('Выберите SECID из результатов и введите его в поле «Тикер» слева.')
    if not need_data(dataset): return
    frame,meta,quote = dataset
    source_caption(frame,meta)
    if {'OPEN','HIGH','LOW'} <= set(frame.columns):
        tail = frame.tail(120)
        fig = go.Figure(go.Candlestick(x=tail.index,open=tail.OPEN,high=tail.HIGH,low=tail.LOW,close=tail.CLOSE,
            increasing_line_color=GREEN,decreasing_line_color=RED,name=meta['symbol']))
        fig.update_layout(xaxis_rangeslider_visible=False)
        st.plotly_chart(chart(fig,430,'Цена / единицы источника'),width='stretch')
    st.dataframe(frame.tail(30),width='stretch')
    st.download_button('История CSV', frame.to_csv().encode('utf-8-sig'),file_name=f"{meta['symbol']}_history.csv",mime='text/csv')
    with st.expander('Происхождение данных и карточка инструмента'): st.json(meta); st.json(quote or {})


def time_machine(dataset):
    st.title('Time Machine')
    st.write('Распределение сценариев при заданных предположениях.')
    if not need_data(dataset): return
    frame,meta,_ = dataset
    source_caption(frame,meta)
    try: require_equity(meta)
    except ValueError as exc: st.warning(str(exc)); return
    with st.form('simulation_form'):
        cols = st.columns(4)
        horizon = cols[0].slider('Горизонт, торговых дней', 1,120,20,key='horizon')
        runs = cols[1].selectbox('Сценариев',[1000,5000,10000,20000],index=2,key='runs')
        target = cols[2].number_input('Цель по цене, %', .1,100.,8.,key='target')
        stop = cols[3].number_input('Стоп по цене, %', .1,90.,5.,key='stop')
        cols=st.columns(4)
        fee=cols[0].number_input('Комиссия за сторону, %',0.,3.,.05,.01,key='sim_fee')
        slip=cols[1].number_input('Проскальзывание за сторону, %',0.,3.,.05,.01,key='sim_slip')
        capital=cols[2].number_input('Условная позиция, ₽',100.,1e9,100000.,1000.,key='sim_capital')
        block=cols[3].slider('Блок истории, дней',1,20,5,key='block')
        seed=st.number_input('Seed',0,1000000,42,key='sim_seed')
        compare=st.checkbox('Сравнить три предположения о рынке',key='compare')
        submit=st.form_submit_button('Рассчитать сценарии',type='primary')
    if submit:
        st.session_state.pop('simulation',None)
        options=dict(horizon=horizon,runs=runs,target_pct=target,stop_pct=stop,commission_pct=fee,slippage_pct=slip,block=block,seed=seed)
        try:
            with st.spinner('Считаю сценарии…'):
                result=simulate(frame.CLOSE,**options)
                comparison=compare_scenarios(frame.CLOSE,**options) if compare else None
            st.session_state.simulation=(meta['history_sha256'],result,comparison,capital,options)
        except ValueError as exc: st.error(str(exc))
    saved=st.session_state.get('simulation')
    if not saved or saved[0]!=meta['history_sha256']: return
    _,result,comparison,capital,options=saved
    s=result.stats
    st.caption(f"Показан расчёт: {options['runs']:,} сценариев, {options['horizon']} дней, seed {options['seed']}. Изменения параметров применяются кнопкой расчёта.")
    with st.expander('Параметры показанного расчёта'): st.json(options)
    cols=st.columns(4)
    for col,label,val in zip(cols,['Цель первой · доля сценариев','Стоп первым · доля сценариев','Убыточный итог · доля','Медиана доходности'],[s['p_target'],s['p_stop'],s['p_loss'],s['median_return']]): col.metric(label,f'{val:.2%}')
    xs=np.arange(options['horizon']+1)
    quantiles=np.quantile(result.paths,[.05,.25,.5,.75,.95],axis=0)
    fig=go.Figure()
    for lo,hi,color,label in [(0,4,'rgba(107,159,255,.12)','5–95% траекторий'),(1,3,'rgba(107,159,255,.22)','25–75% траекторий')]:
        fig.add_trace(go.Scatter(x=xs,y=quantiles[lo],mode='lines',line_width=0,showlegend=False,hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=xs,y=quantiles[hi],mode='lines',line_width=0,fill='tonexty',fillcolor=color,name=label))
    for path in result.paths[:8]: fig.add_trace(go.Scatter(x=xs,y=path,line=dict(color='rgba(107,159,255,.15)',width=1),showlegend=False,hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=xs,y=quantiles[2],name='Медиана цены',line=dict(color=BLUE,width=3)))
    fig.add_hline(y=s['target_price'],line_dash='dash',line_color=GREEN,annotation_text='Цель')
    fig.add_hline(y=s['stop_price'],line_dash='dash',line_color=RED,annotation_text='Стоп')
    st.plotly_chart(chart(fig,420,'Модельная цена'),width='stretch')
    st.caption('Траектории цены продолжаются после выхода из позиции. Итог позиции фиксируется при первом пересечении по дневному закрытию.')
    left,right=st.columns([1.6,1])
    with left:
        fig=go.Figure(go.Histogram(x=result.net_returns*100,nbinsx=50,marker_color=BLUE,name='Сценарии'))
        fig.add_vline(x=0,line_color=RED)
        st.plotly_chart(chart(fig,300,'Количество сценариев'),width='stretch')
        st.caption('По горизонтали: доходность после комиссии и условного проскальзывания, %.')
    with right:
        st.metric('VaR 95% · модельный убыток',f"{s['var95_loss']:.2%}")
        st.metric('ES 95% · средний убыток хвоста',f"{s['es95_loss']:.2%}")
        st.metric('Медиана максимальной просадки позиции',f"{s['median_strategy_max_drawdown']:.2%}")
        st.caption('VaR/ES выражены как потери; отрицательное значение означает прибыль в модели. ES — среднее худших ceil(5% × N) исходов.')
    st.metric('Средний итог условной позиции',f"{capital*(1+s['mean_return']):,.0f} ₽")
    st.caption('Среднее по модели не является обещанием дохода. Денежный пересчёт допускает дробную позицию; реальные лоты здесь не моделируются.')
    if comparison:
        st.subheader('Чувствительность к предположениям')
        table=pd.DataFrame(comparison)[['scenario','drift_shift_pct','volatility_scale','mean_return','var95_loss','es95_loss','p_loss']]
        for col in ['mean_return','var95_loss','es95_loss','p_loss']: table[col] *= 100
        table['scenario'] = ['Исторические параметры','Негативное предположение','Позитивное предположение']
        table=table.rename(columns={'scenario':'Предположение','drift_shift_pct':'Сдвиг годового среднего, п.п.','volatility_scale':'Множитель волатильности','mean_return':'Средний итог, %','var95_loss':'VaR 95, %','es95_loss':'ES 95, %','p_loss':'Доля убыточных, %'})
        st.dataframe(table,hide_index=True,width='stretch')
        st.caption('Сдвиг годового среднего логарифмического изменения: −20 / 0 / +20 п.п.; множитель волатильности: 1.5 / 1 / 1. Это выбранные предположения, их вероятности не оценивались.')
    exports=pd.DataFrame({'net_return_pct':result.net_returns*100,'final_capital_rub':capital*(1+result.net_returns),'exit_day':result.exit_steps,
                          'outcome':np.where(result.hit_stop,'stop',np.where(result.hit_target,'target','horizon'))})
    st.download_button('Результаты CSV',exports.to_csv(index=False).encode('utf-8-sig'),file_name=f"{meta['symbol']}_simulation.csv",mime='text/csv')
    st.warning('Частоты внутри модели ≠ реальные вероятности. Дневные закрытия не отражают внутридневные касания. Налоги, дивиденды, сплиты, ликвидность и исполнение стопов не моделируются.')


def strategy_lab(dataset):
    st.title('Strategy Lab')
    st.write('Сигнал по закрытию → исполнение на следующем открытии.')
    if not need_data(dataset): return
    frame,meta,quote=dataset
    source_caption(frame,meta)
    try: require_equity(meta)
    except ValueError as exc: st.warning(str(exc)); return
    with st.form('backtest_form'):
        cols=st.columns(3)
        strategy=cols[0].selectbox('Стратегия',['ma_cross','ema_cross','buy_hold','rsi'],format_func=lambda x:{'ma_cross':'SMA Crossover','ema_cross':'EMA Crossover','buy_hold':'Buy and Hold','rsi':'RSI / Wilder'}[x],key='strategy')
        capital=cols[1].number_input('Начальный капитал, ₽',100.,1e9,100000.,1000.,key='bt_capital')
        split=cols[2].slider('Доля истории до проверки',.2,.9,.7,.05,key='split')
        cols=st.columns(4)
        fast=cols[0].number_input('Короткая SMA',2,249,20,key='fast'); slow=cols[1].number_input('Длинная SMA',3,500,50,key='slow')
        fee=cols[2].number_input('Комиссия, %',0.,3.,.05,.01,key='bt_fee'); slip=cols[3].number_input('Проскальзывание, %',0.,3.,.05,.01,key='bt_slip')
        st.caption('RSI: Wilder 14, вход ≤30, выход ≥70. Параметры фиксированы до проверки. Повторный подбор по результату проверки делает этот период обучающим.')
        submit=st.form_submit_button('Проверить стратегию',type='primary')
    if submit:
        st.session_state.pop('backtest',None)
        try:
            lot=1 if meta.get('demo_data') else quote['security'].get('LOTSIZE')
            result=compare_backtest(frame,strategy,split,initial_cash=capital,commission_pct=fee,slippage_pct=slip,lot_size=lot,fast=fast,slow=slow)
            st.session_state.backtest=(meta['history_sha256'],result,strategy)
        except (ValueError,TypeError) as exc: st.error(str(exc))
    saved=st.session_state.get('backtest')
    if not saved or saved[0]!=meta['history_sha256']: return
    _,r,strategy=saved
    st.caption(f"Стратегия: {strategy} · начало отложенного периода: {r['split_date']} · лот: {r['test'].stats['lot_size']}")
    table=pd.DataFrame([{ 'Период':label,**r[key].stats} for key,label in [('train','До проверки'),('test','Отложенный период'),('benchmark','Buy & Hold / тот же период')]])[['Период','return_pct','max_drawdown_pct','annualized_volatility_pct','trades','fees']]
    table=table.rename(columns={'return_pct':'Доходность, %','max_drawdown_pct':'Просадка, %','annualized_volatility_pct':'Волатильность, %','trades':'Исполнений','fees':'Комиссии, ₽'})
    st.dataframe(table.round(2),hide_index=True,width='stretch')
    curve=pd.DataFrame({'Стратегия':r['test'].curve.equity,'Buy & Hold':r['benchmark'].curve.equity})
    st.plotly_chart(line_figure(curve,list(curve),'Стоимость, ₽'),width='stretch')
    st.plotly_chart(line_figure(r['test'].curve.assign(drawdown=r['test'].curve.drawdown*100),['drawdown'],'Просадка, %',220),width='stretch')
    with st.expander('Журнал исполнения'): st.dataframe(r['test'].trades,hide_index=True,width='stretch')
    st.download_button('Сделки бэктеста CSV',r['test'].trades.to_csv(index=False).encode('utf-8-sig'),file_name='backtest_trades.csv')
    st.warning('Без автоматического подбора параметров. История без корректировок: дивиденды и сплиты не учтены. Все позиции принудительно закрываются по последнему CLOSE с издержками. Шорты и плечо отсутствуют.')
    st.caption('Лот считается постоянным на всём периоде; исторические изменения размера лота не моделируются. Пользовательские стратегии: локальный Python API и examples/custom_strategy.py. Код из текстовых полей и MCP не исполняется.')


def portfolio_page():
    st.title('Виртуальный портфель')
    st.write('Ручной журнал, оценка капитала и сценарии риска. Только рубли.')
    store=PortfolioStore(Settings.from_env().data_dir/'portfolio.sqlite3')
    with st.expander('Добавить запись',expanded=True):
        with st.form('ledger_form'):
            cols=st.columns(3)
            kind=cols[0].selectbox('Операция',['deposit','buy','sell','withdrawal','dividend','coupon'],key='event_kind',
                format_func=lambda x:{'deposit':'Пополнение','buy':'Покупка','sell':'Продажа','withdrawal':'Вывод денег','dividend':'Дивиденд','coupon':'Купон'}[x])
            day=cols[1].date_input('Дата операции',market_today(),key='event_date')
            symbol=cols[2].text_input('Тикер операции','SBER',key='event_symbol')
            cols=st.columns(4)
            amount=cols[0].number_input('Сумма выплаты / пополнения, ₽',0.01,1e9,19000.,key='event_amount')
            qty=cols[1].number_input('Количество бумаг',1,100000000,10,key='event_qty')
            price=cols[2].number_input('Цена за бумагу, ₽',.01,1e9,300.,key='event_price')
            fee=cols[3].number_input('Комиссия операции, ₽',0.,1e9,0.,key='event_fee')
            source=st.text_input('Источник выплаты / примечание','',key='event_source',help='Для дивидендов/купонов укажите документ и дату. Источник не проверяется автоматически.')
            submit=st.form_submit_button('Сохранить запись')
        if submit:
            event={'kind':kind,'date':str(day),'symbol':symbol,'amount':amount,'quantity':qty,'price':price,'fee':fee,'source':source}
            try: store.append_many([event]); st.success('Запись сохранена.')
            except (ValueError,KeyError,TypeError) as exc: st.error(str(exc))
    events=store.load()
    if not events: st.info('Портфель пуст. Начните с пополнения; затем добавьте покупки.'); return
    state=ledger_state(events)
    st.dataframe(pd.DataFrame(events),hide_index=True,width='stretch')
    st.download_button('Экспорт журнала JSON',json.dumps(events,ensure_ascii=False,indent=2),file_name='virtual_portfolio.json',mime='application/json')
    st.caption('Цена сделки и оценки — рубли за одну бумагу. Для облигаций вводите полную цену с НКД, пересчитанную из процента номинала. Валютные активы пока не поддерживаются.')
    symbols=list(state['positions'])
    marks={}
    if symbols:
        st.subheader('Оценка открытых позиций')
        asof=st.date_input('Дата всех оценок',market_today(),key='mark_date')
        provenance=st.text_input('Источник оценок','Ручная оценка пользователя',key='mark_source')
        for sym in symbols:
            default=state['positions'][sym]['cost_basis']/state['positions'][sym]['quantity']
            price=st.number_input(f'{sym}: оценка одной бумаги, ₽',.0001,1e12,float(default),key=f'mark_{sym}')
            marks[sym]={'price':price,'as_of':str(asof),'source':provenance}
        st.caption('Начальное значение поля — средняя учётная стоимость, не текущая котировка. Введите актуальную оценку из выбранного источника.')
    try: snapshot=analyze_portfolio(events,marks)
    except (ValueError,KeyError) as exc: st.error(str(exc)); return
    cols=st.columns(4)
    for col,label,key in zip(cols,['Стоимость портфеля','Свободные деньги','P&L с учётом пополнений','Дивиденды и купоны'],['equity','cash','total_pnl','income']): col.metric(label,f"{snapshot[key]:,.2f} ₽")
    if snapshot['positions']:
        st.dataframe(pd.DataFrame(snapshot['positions']),hide_index=True,width='stretch')
        left,right=st.columns([1,1.2])
        with left:
            fig=go.Figure(go.Pie(labels=symbols+['Деньги'],values=[p['market_value'] for p in snapshot['positions']]+[snapshot['cash']],hole=.65,marker_colors=[BLUE,GREEN,RED,'#53657e']))
            st.plotly_chart(chart(fig,300),width='stretch')
        with right:
            shock=st.slider('Общий стресс цены активов, %',-100,100,-20,key='stress_shock')
            stressed=stress_test(snapshot,{sym:shock for sym in symbols})
            st.metric('Изменение при заданном стрессе',f"{stressed['change_rub']:+,.2f} ₽",f"{stressed['change_pct']:+.2f}%")
            st.caption('Изменение цены на один шаг; денежный остаток неизменен. Это предположение, не прогноз.')
            weight=st.slider('Альтернатива: доля денег, %',0,100,50,key='alternative_cash')
            st.metric('При альтернативной доле денег',f"{snapshot['equity']*(1-weight/100)*shock/100:+,.2f} ₽")
            st.caption('Остаток распределён между теми же активами пропорционально текущим долям. Издержки ребалансировки здесь не включены.')
    with st.expander('Доходность и просадка по истории оценок'):
        st.write('Загрузите CSV: первая колонка date, остальные — тикеры с полной рублёвой ценой за бумагу. Каждая дата операции должна присутствовать. Пропуски цен не заполняются.')
        uploaded=st.file_uploader('История оценок CSV',type=['csv'],key='valuations')
        if uploaded is not None:
            try:
                prices=pd.read_csv(uploaded,index_col=0,parse_dates=True)
                curve,stats=portfolio_curve(events,prices)
                st.json(stats)
                st.plotly_chart(line_figure(curve,['unit_nav'],'Индекс доходности'),width='stretch')
            except (ValueError,KeyError,TypeError) as exc: st.error(str(exc))
    st.caption('P&L снимка не является месячной доходностью. Для доходности и просадки нужна история оценок; денежные потоки считаются в начале дня.')


def ai_research(dataset):
    st.title('AI Research')
    st.write('Проверяемые численные результаты для вашего ИИ-ассистента.')
    st.info('Встроенного чата с языковой моделью пока нет. Подключите локальный MCP к совместимому клиенту: он сможет вызывать расчёты и интерпретировать результаты.')
    if dataset:
        frame,meta,_=dataset
        source_caption(frame,meta)
        if st.button('Сформировать отчёт по данным',key='report',type='primary'):
            try:
                result=run_analysis(symbol=meta['symbol'],scenarios=1000,history_loader=lambda *args:(frame,meta))
                st.session_state.research_result=(meta['history_sha256'],render_report(result),result)
            except ValueError as exc: st.error(str(exc))
        report=st.session_state.get('research_result')
        if report and report[0]==meta['history_sha256']:
            st.markdown(report[1]); st.download_button('Скачать отчёт Markdown',report[1],file_name='research_report.md')
            with st.expander('Численные данные отчёта'): st.json(report[2])
    with st.expander('Подключение MCP и доступные инструменты',expanded=dataset is None):
        st.code('python -m moex_intelligence.mcp_server\n# или локальный HTTP:\npython -m moex_intelligence.mcp_server --transport streamable-http',language='bash')
        st.write('Reader: search_security, get_quote, get_daily_history, analyze_history, get_market_snapshot.')
        st.write('Исследования: get_instrument, time_machine_simulate, time_machine_demo, strategy_backtest, compare_market_scenarios, portfolio_analyze, portfolio_stress, research_report.')
        st.caption('stdio не публикует сетевой порт. HTTP работает только на loopback. Облачный клиент не видит localhost вашего Mac; публичное подключение с авторизацией отложено.')
    st.code('Исследуй SBER: укажи дату, режим торгов, источник и ограничения.\nВызови симулятор и бэктест с издержками. Раздели факты,\nпредположения и модельные частоты. Не обещай доходность.',language=None)


def legacy_main():
    st.set_page_config(page_title='MOEX Intelligence',page_icon='◈',layout='wide')
    configure_logging()
    st.markdown('''<style>
    .block-container{max-width:1440px;padding-top:2.1rem;padding-bottom:3rem}
    h1{font-size:2rem!important;letter-spacing:-.035em} h2,h3{letter-spacing:-.02em}
    [data-testid="stSidebar"]{border-right:1px solid #223047}
    [data-testid="stMetric"]{background:#131d2b;border:1px solid #223047;border-radius:12px;padding:16px}
    [data-testid="stMetricValue"]{font-size:1.65rem} .stCaption{color:#96a8be}
    </style>''',unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('### ◈ MOEX Intelligence')
        st.caption('RESEARCH TERMINAL / 0.3.0')
        page=st.radio('Раздел',PAGES,key='page',label_visibility='collapsed')
        st.divider()
        mode=st.radio('Источник',['MOEX ISS','Демо · искусственные данные'],key='mode')
        symbol=st.text_input('Тикер','SBER',disabled=mode.startswith('Демо'),key='symbol').strip().upper()
        lookback=st.selectbox('История, календарных дней',[365,730,1095],index=1,key='lookback')
        fingerprint=(mode,symbol,lookback)
        if st.button('Загрузить данные',type='primary',key='load_history',width='stretch'):
            st.session_state.pop('dataset',None)
            try:
                with st.spinner('Загрузка…'):
                    if mode.startswith('Демо'): frame,meta=demo_daily(); quote=None
                    else:
                        last=market_today()-timedelta(days=1)
                        frame,meta=get_engine().frame_sync(symbol,last-timedelta(days=lookback),last)
                        quote=asyncio.run(get_engine().research_quote(symbol))
                st.session_state.dataset=(fingerprint,(frame,meta,quote))
            except (ValueError,TypeError,KeyError) as exc: st.error(f'Загрузка не выполнена: {exc}')
        st.caption('Последние дневные данные — до вчерашней даты по Москве. Ошибка API не включает демо автоматически.')
        st.divider(); st.caption('Локально · без брокерского счёта\n\nМодели помогают исследовать риск, но не гарантируют прибыль.')
    saved=st.session_state.get('dataset')
    dataset=saved[1] if saved and saved[0]==fingerprint else None
    if page=='Overview': overview(dataset)
    elif page=='Market Explorer': explorer(dataset)
    elif page=='Time Machine': time_machine(dataset)
    elif page=='Strategy Lab': strategy_lab(dataset)
    elif page=='Portfolio': portfolio_page()
    else: ai_research(dataset)


def main():
    from .workbench import main as run
    run()
