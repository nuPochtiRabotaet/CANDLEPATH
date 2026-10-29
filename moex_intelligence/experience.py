"""Shared product presentation, over existing financial services."""
from datetime import timedelta
from html import escape
import hashlib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from .config import Settings
from .portfolio import ledger_state,portfolio_curve
from .portfolio_ui import portfolio_store,current_portfolio,market_marks,open_research
from .dashboard import chart
from .data import market_today,get_engine
from .formatting import money,price,percent,quantity
from .provenance import describe_price,display_time
from .design import TOKENS,apply_theme,metrics_html,source_badge

ACCENT=TOKENS['accent']


def go_portfolio(tab='Позиции'):
    st.session_state.page='Portfolio';st.session_state.portfolio_target_tab=tab;st.session_state.show_settings=False


def go_history():
    st.session_state.page='Research';st.session_state.research_section='History';st.session_state.show_settings=False


def refresh_market():
    from .lab_ui import cached_asset
    cached_asset.clear();market_marks.clear();get_engine().clear_quotes()


def portfolio_summary(result):
    snapshot=result['snapshot'];state=result['state']
    market=result.get('market',{}).get('marks',{})
    statuses=[describe_price(m) for m in market.values()]
    if any(s['state']=='demo' for s in statuses):st.caption('УЧЕБНЫЕ ДАННЫЕ · не текущие цены MOEX')
    elif any(s['critical'] for s in statuses):st.caption('Есть сохранённые, устаревшие или неподтверждённые цены. Даты доступны в карточке.')
    total=money(snapshot['equity']) if snapshot else 'Не определена'
    pnl=money(snapshot['total_pnl'],signed=True) if snapshot and snapshot['total_pnl'] is not None else '—'
    note='Доходность: недостаточно истории' if not snapshot or not snapshot['history_complete'] else 'Взносы исключены из результата'
    st.html(metrics_html([('Стоимость портфеля',total,'По доступным оценкам' if snapshot else 'Нет сопоставимых цен всех позиций'),
       ('Свободные средства',money(state['cash']),'По журналу операций'),('Финансовый результат',pnl,note),
       ('Выплаты',money(snapshot['income'] if snapshot else state['income']),'Дивиденды и купоны из журнала')],capital=True))
    if not snapshot:
        st.warning('Полная оценка недоступна. '+', '.join(result['errors'])+': проверьте источник и даты цен.')


def portfolio_history(events,revision,key='overview'):
    digest=hashlib.sha256(str(events).encode()).hexdigest();saved=st.session_state.get('portfolio_valuation_history')
    if saved and saved['digest']!=digest:saved=None
    if not saved:
        st.html('<div class="history-empty"><div><strong>История портфеля пока не накоплена</strong><span>Текущая структура доступна. Для динамики нужны датированные оценки и денежные потоки.</span></div></div>')
        with st.popover('Загрузить историю'):
            st.caption('CSV: date и полные рублёвые цены тикеров. Нужны все даты операций; пропуски не заполняются.')
            f=st.file_uploader('История цен портфеля',type=['csv'],key=key+'_history_upload')
            if f:
                try:
                    prices=pd.read_csv(f,index_col=0,parse_dates=True);curve,stats=portfolio_curve(events,prices)
                    st.session_state.portfolio_valuation_history={'digest':digest,'curve':curve,'stats':stats,'source':f.name};st.rerun()
                except (ValueError,KeyError,TypeError,OverflowError) as exc:st.warning('Историю нельзя использовать: '+str(exc))
        return False
    curve=saved['curve'];h=st.segmented_control('Период',['1М','3М','6М','1Г','Всё'],default='Всё',key=key+'_horizon') or 'Всё'
    days={'1М':31,'3М':92,'6М':184,'1Г':366};tail=curve if h=='Всё' else curve.loc[curve.index>=curve.index[-1]-pd.Timedelta(days=days[h])]
    flows=st.toggle('Показать пополнения и выводы',value=True,key=key+'_flows')
    fig=go.Figure(go.Scatter(x=tail.index,y=tail.equity,name='Оценка портфеля',line_color=ACCENT))
    if flows:
        f=tail[tail.external_flow!=0]
        fig.add_trace(go.Scatter(x=f.index,y=f.equity,mode='markers',name='Внешний поток',customdata=f.external_flow,marker=dict(size=9,symbol='diamond',color=TOKENS['fund']),hovertemplate='Поток %{customdata:+,.2f} ₽<br>Оценка %{y:,.2f} ₽<extra></extra>'))
    st.plotly_chart(chart(fig,285,'Стоимость, ₽'),width='stretch',key=key+'_curve')
    st.caption('Источник: '+saved['source']+' · TWR всей загруженной истории '+percent(saved['stats']['time_weighted_return_pct'],2)+'. Изменение капитала и внешние потоки различаются.')
    return True


def asset_card(symbol,quantity=0,mark=None,*,key='asset',actions=True,compact=False,position=None):
    status=describe_price(mark);kind=(mark or {}).get('asset_type','unknown');name=(mark or {}).get('name') or symbol
    label={'equity':'Акция','fund':'Биржевой фонд','bond':'Облигация'}.get(kind,'Класс не подтверждён')
    position=position or {};value=position.get('market_value');weight=position.get('weight_pct')
    if value is None and mark:value=quantity*mark['price']
    st.html('<div class="asset-summary"><div><div class="asset-head">'+escape(name)+'</div><div class="asset-sub">'+escape(symbol+' · '+label+' · '+str(quantity)+' шт.')+'</div>'+source_badge(status)+'</div><div><div class="financial-label">'+('Полная цена с НКД' if kind=='bond' else 'Цена за бумагу')+'</div><div class="asset-price">'+escape(price(mark['price']) if mark else '—')+'</div><div class="asset-meta">Наблюдение: '+escape(status.get('observed_display','неизвестно'))+'</div></div><div><div class="financial-label">Моя позиция</div><div class="asset-price">'+escape(money(value))+'</div><div class="asset-meta">'+escape(percent(weight)+' портфеля' if weight is not None else 'Доля неизвестна без полной оценки')+'</div></div></div>')
    if status['critical']:st.caption(status['label']+'. Расчёт использует только явно указанный источник.')
    if actions:
        with st.container(key=key+'_actions',horizontal=True):
            st.button('Оценить',on_click=open_research,args=(symbol,'evaluate'),key=key+'_evaluate',type='primary')
            st.button('Сценарии',on_click=open_research,args=(symbol,'existing'),key=key+'_scenarios')
            with st.popover('Изменить позицию'):
                st.caption('Эксперимент и запись фактической операции — отдельные действия.')
                st.button('Смоделировать покупку / продажу',on_click=open_research,args=(symbol,'buy'),key=key+'_trade')
                st.button('Внести подтверждённую операцию',on_click=_go_actual,args=(symbol,),key=key+'_actual')
    with st.expander('Источник и ограничения цены'):
        st.caption('Источник: '+str(status.get('source') or 'неизвестен'))
        st.caption('Рыночное наблюдение: '+status.get('observed_display','неизвестно')+' · получение: '+display_time(status.get('retrieved_at')))
        st.caption('Тип наблюдения: '+('снимок MOEX (SYSTIME), не дата последней сделки' if status.get('observation_kind')=='snapshot' else status.get('observation_kind','неизвестно'))+' · дата последней сделки: '+display_time(status.get('trade_at')))
        st.caption('Сохранение снимка: '+display_time(status.get('saved_at'))+' · дата оценки: '+display_time(status.get('valuation_as_of')))
        st.caption('Последняя сделка и закрытие не гарантируют цену исполнения. Время чтения кэша не является временем рынка.')
        if kind=='bond' and st.checkbox('Разобрать полную стоимость облигации',key=key+'_bond_parts'):
            from .lab_ui import cached_asset
            loaded=cached_asset(symbol,str(Settings.from_env().data_dir));asset=loaded['asset']
            if asset:
                st.write(f"{percent(asset['quoted_pct'],4)} × номинал {money(asset['face_value'])} + НКД {price(asset['accrued_interest'])} = {price(asset['unit_price'])}")
                st.caption('Погашение, оферта, купоны и чувствительность к ставкам требуют проверенных данных выпуска.')
            else:st.warning('Параметры выпуска недоступны.')
    with st.expander('График и показатели инструмента'):
        if st.checkbox('Загрузить историю цены',key=key+'_load_chart'):
            from .lab_ui import cached_history
            with st.spinner('История инструмента…'):loaded=cached_history(symbol,str(market_today()-timedelta(days=1)))
            if loaded['data'] is None:st.warning(str(loaded['error']))
            else:
                frame,meta=loaded['data'];h=st.segmented_control('Период цены',['1М','3М','1Г','Всё'],default='1Г',key=key+'_history_period') or '1Г'
                tail=frame if h=='Всё' else frame.tail({'1М':21,'3М':63,'1Г':252}[h])
                fig=go.Figure(go.Scatter(x=tail.index,y=tail.CLOSE,name='CLOSE',line_color=ACCENT))
                st.plotly_chart(chart(fig,240,'% номинала' if meta['asset_type']=='bond' else 'Цена, ₽'),width='stretch',key=key+'_history_chart')
                if meta['asset_type']!='bond':
                    from moex import metrics
                    m=metrics({'rows':[{'TRADEDATE':str(day.date()),'CLOSE':float(v)} for day,v in tail.CLOSE.items()]})
                    st.caption('Изменение '+percent(m['price_return_pct'],1,signed=True)+' · волатильность '+percent(m['annualized_volatility_pct'])+' · историческая просадка '+percent(m['max_close_drawdown_pct']))
                else:st.caption('Чистая котировка без выплат и НКД; не полная доходность.')
                st.caption(f"{meta['source']} · {meta['board']} · {frame.index[0].date()} — {frame.index[-1].date()}")
                st.download_button('История цены CSV',frame.to_csv(),file_name=symbol+'_history.csv',key=key+'_history_csv')


def _go_actual(symbol):
    st.session_state.event_picker_query=symbol
    st.session_state.pop('event_picker_results',None);st.session_state.pop('event_picker_selected',None)
    st.session_state.event_kind='buy';go_portfolio('Операции')


def overview_page():
    with st.spinner('Оцениваю портфель…'):db,bundle,result=current_portfolio()
    events=[r['event'] for r in bundle['records']];snap=result['snapshot'];state=result['state']
    if not events:
        st.title('Ваш первый портфель')
        st.write('Импортируйте отчёт или добавьте операцию. Лаборатория доступна без изменения журнала.')
        with st.container(horizontal=True):
            st.button('Импортировать отчёт',on_click=go_portfolio,args=('Импорт',),key='empty_import',type='primary')
            st.button('Добавить операцию',on_click=go_portfolio,args=('Операции',),key='empty_add')
            st.button('Открыть лабораторию',on_click=_go_lab,key='empty_lab')
        return
    portfolio_summary(result)
    with st.container(horizontal=True):
        st.button('Мой портфель',on_click=go_portfolio,key='overview_portfolio')
        st.button('Проверить покупку',on_click=_go_lab,key='overview_lab',type='primary')
        st.button('История исследований',on_click=go_history,key='overview_history')
    has_history=portfolio_history(events,bundle['revision'])
    if snap and snap['positions'] and not has_history:
        fig=go.Figure(go.Bar(x=[p['market_value'] for p in snap['positions']]+[snap['cash']],y=[p['symbol'] for p in snap['positions']]+['Деньги'],orientation='h',text=[percent(p['weight_pct']) for p in snap['positions']]+[percent(snap['cash']/snap['equity']*100 if snap['equity'] else 0)],textposition='auto',marker_color=ACCENT))
        fig.update_yaxes(autorange='reversed');fig.update_xaxes(title='Стоимость, ₽');st.plotly_chart(chart(fig,170,None),width='stretch',key='overview_structure')
    st.subheader('Что требует внимания')
    insights=[]
    if result['errors']:insights.append(('Цены: '+str(len(result['errors']))+' недоступны','Полная оценка портфеля ограничена.','Проверить',go_portfolio,('Позиции',)))
    if snap and snap['positions']:
        p=max(snap['positions'],key=lambda p:p['weight_pct'])
        if p['weight_pct']>40:insights.append(('Концентрация: '+p['symbol']+' — '+percent(p['weight_pct']),'Порог внимания 40% — внутренний ориентир, не инвестиционный вердикт.','Сценарий',open_research,(p['symbol'],'existing')))
    marks=market_marks(tuple(sorted(state['positions'])))['marks'] if state['positions'] else {}
    stale=[s for s,m in marks.items() if describe_price(m)['critical']]
    if stale:insights.append(('Источник: '+str(len(stale))+' позиций требуют проверки',', '.join(stale)+'. Сохранённая цена не считается текущей.','Проверить',go_portfolio,('Позиции',)))
    if not state['history_complete']:insights.append(('Доходность: нет полной истории','Начальные остатки не восстанавливают прошлый инвестиционный результат.','Журнал',go_portfolio,('Операции',)))
    if not insights:st.caption('По текущему снимку нет отмеченных ограничений данных и концентрации. Полный анализ риска отдельно не выполнялся.')
    with st.container(key='insights'):
        for i,(title,body,label,callback,args) in enumerate(insights[:3]):
            left,right=st.columns([5,1],vertical_alignment='center')
            left.html('<div class="insight-title">'+escape(title)+'</div><div class="insight-detail">'+escape(body)+'</div>')
            right.button(label,key='insight_'+str(i),on_click=callback,args=args)
    if snap and snap['positions']:
        st.subheader('Позиции')
        for p in sorted(snap['positions'],key=lambda x:-x['market_value'])[:3]:
            left,right=st.columns([5,1],vertical_alignment='center')
            left.write(f"**{p['symbol']}** · {money(p['market_value'])} · {percent(p['weight_pct'])}")
            right.button('Оценить',key='top_'+p['symbol'],on_click=open_research,args=(p['symbol'],'evaluate'))


def _go_lab():
    st.session_state.page='Laboratory';st.session_state.show_settings=False
