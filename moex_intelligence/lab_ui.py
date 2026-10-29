"""Interactive Streamlit layer; hypothetical actions never call PortfolioStore writes."""
from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from .design import TOKENS
from moex import identifier
from .config import Settings
from .data import get_engine, market_today
from .dashboard import chart
from .laboratory import (manual_asset, preview_trade, concentration, stress_selected,
                         scenario_envelope, model_position, capital_goal, portfolio_health, position_stress)
from .lab_data import load_asset, QuoteSnapshots
from .persistence import ResearchStore
from .portfolio import ledger_state, analyze_portfolio
from .portfolio_ui import portfolio_store, instrument_picker, user_error
from . import portfolio_ui as portfolio_module

HORIZONS={'Неделя':5,'Месяц':21,'3 месяца':63,'Год':252}


def research_store():return ResearchStore(Settings.from_env().data_dir/'research.sqlite3')


@st.cache_data(ttl=60,max_entries=32,show_spinner=False)
def cached_asset(symbol,data_dir):
    return asyncio.run(load_asset(symbol,QuoteSnapshots(data_dir+'/market_snapshots')))


@st.cache_data(ttl=900,max_entries=16,show_spinner=False)
def cached_history(symbol,end_day):
    end=datetime.fromisoformat(end_day).date()
    try:
        async def get():
            async with asyncio.timeout(12):return await get_engine().frame(symbol,end-timedelta(days=1095),end)
        return {'data':asyncio.run(get()),'error':None}
    except (ValueError,KeyError,TypeError,TimeoutError) as exc:return {'data':None,'error':str(exc) or 'История MOEX не ответила за 12 секунд.'}


@st.cache_data(max_entries=16,show_spinner=False)
def cached_envelope(frame,meta,horizon):return scenario_envelope(frame,meta,horizon=horizon)


def _sync_slider(prefix):st.session_state[prefix+'qty']=int(st.session_state[prefix+'slider'])


def _sync_number(prefix,lot,maximum):
    qty=int(st.session_state[prefix+'qty'])
    if qty%lot==0 and qty<=maximum:st.session_state[prefix+'slider']=qty


def _step(prefix,change,lot,maximum):
    st.session_state[prefix+'qty']=max(0,min(100000000,int(st.session_state[prefix+'qty'])+change))
    _sync_number(prefix,lot,maximum)


def _reset():st.session_state.lab_reset=int(st.session_state.get('lab_reset',0))+1


def _topup(prefix):st.session_state[prefix+'funding']='topup'


def _overview_table(result,symbol):
    rows=[]
    before=result['before'];after=result['after']
    def values(snapshot,after_side=False):
        if snapshot is None:
            cash=result.get('cash_after') if after_side else result.get('known_cash')
            qty=result.get('known_after_quantity') if after_side else result.get('known_quantity')
            return ['—',f'{cash:,.2f} ₽' if cash is not None else '—',f'{qty} шт.' if qty is not None else '—','—','—']
        p=next((p for p in snapshot['positions'] if p['symbol']==symbol),None)
        return [f"{snapshot['equity']:,.2f} ₽",f"{snapshot['cash']:,.2f} ₽",f"{p['quantity'] if p else 0} шт.",
                f"{p['weight_pct'] if p else 0:.1f}%",f"{concentration(snapshot)['max_security_weight_pct']:.1f}%"]
    a,b=values(before),values(after,True)
    for name,x,y in zip(['Стоимость','Свободные деньги','Выбранная бумага','Доля выбранной бумаги','Самая крупная бумага'],a,b):rows.append({'Показатель':name,'До':x,'После эксперимента':y})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')


def _stress_chart(before,after,asset,shock):
    grid=np.arange(-50,51,5);fig=go.Figure()
    for snap,label,color,dash in [(before,'До',TOKENS['muted'],'dash'),(after,'После',TOKENS['accent'],'solid')]:
        if snap is None:continue
        vals=[stress_selected(snap,asset,float(v))['change_rub'] for v in grid]
        fig.add_trace(go.Scatter(x=grid,y=vals,name=label,line=dict(color=color,dash=dash),hovertemplate='%{x}%: %{y:,.2f} ₽<extra>%{fullData.name}</extra>'))
    fig.add_vline(x=shock,line_width=1,line_color=TOKENS['muted'])
    fig.update_xaxes(title='Гипотетическое изменение чистой цены, %' if asset['asset_type']=='bond' else 'Гипотетическое изменение цены, %')
    return chart(fig,300,'Сдвиг стоимости, ₽')


def _model_view(asset,result,prefix):
    if asset['asset_type']=='bond':
        st.info('Облигационная модель требует купонов, амортизации и погашения. Для облигации доступен ценовой стресс выше с фиксированным НКД. Модель акции не подставляется.');return
    try:
        age=(market_today()-datetime.fromisoformat(str(asset.get('observed_at'))[:10]).date()).days
        if age>7 or age<0:st.warning('Цена старше 7 дней либо датирована будущим. Обновите её перед модельным исследованием.');return
    except ValueError:st.warning('Дата базовой цены неизвестна.');return
    horizon_name=st.segmented_control('Горизонт исследования',list(HORIZONS),default='Месяц',key=prefix+'model_horizon')
    horizon=HORIZONS.get(horizon_name,21)
    history=cached_history(asset['symbol'],str(market_today()-timedelta(days=1)))
    if history['data'] is None:st.warning('История недоступна: '+str(history['error']));return
    frame,meta=history['data']
    try:
        supported=[h for h in HORIZONS.values() if len(frame)>=max(126,2*h+1)]
        if not supported or horizon>max(supported):raise ValueError(f'Недостаточно истории для горизонта {horizon} торговых дней.')
        if not meta.get('demo_data') and (market_today()-frame.index[-1].date()).days>7:raise ValueError('История старше 7 календарных дней. Модель не рассчитывается.')
        with st.spinner('Модельные траектории…'):
            envelope=cached_envelope(frame,meta,max(supported))
        snap=result['after'] or result['before']
        held=next((p['quantity'] for p in snap['positions'] if p['symbol']==asset['symbol']),0) if snap else result.get('known_after_quantity',result.get('known_quantity',0))
        model=model_position(envelope,asset,held,horizon,snap)
    except (ValueError,KeyError,TypeError) as exc:st.warning(str(exc));return
    if envelope['synthetic']:st.warning('ИСКУССТВЕННАЯ ИСТОРИЯ. Это учебные сценарии, не прогноз реальной бумаги.')
    scope='после эксперимента' if result['after'] is not None or result.get('cash_after') is not None else 'текущая позиция; операция не применена'
    st.caption(f"{held} бумаг · {scope} · {horizon} торговых дней · {envelope['runs']} траекторий · качество прогноза на активе не подтверждено")
    cols=st.columns(3)
    for col,key,label in zip(cols,['lo','mid','hi'],['5-й процентиль','Медиана','95-й процентиль']):
        end=model['position'][key][-1];col.metric(label,f'{end:,.2f} ₽',f"{end-model['base_position_value']:+,.2f} ₽")
    xs=np.arange(horizon+1);p=model['position'];fig=go.Figure()
    fig.add_trace(go.Scatter(x=xs,y=p['lo'],line_width=0,name='5-й процентиль',showlegend=False))
    fig.add_trace(go.Scatter(x=xs,y=p['hi'],line_width=0,fill='tonexty',fillcolor=TOKENS['accent_fill'],name='5–95% модели'))
    fig.add_trace(go.Scatter(x=xs,y=p['mid'],line_color=TOKENS['accent'],name='Медиана'))
    fig.update_xaxes(title='Торговые дни')
    st.plotly_chart(chart(fig,310,'Стоимость позиции, ₽'),width='stretch',key=prefix+'model_chart')
    port=model.get('conditional_portfolio')
    if port:st.caption(f"Портфель при медианном исходе одной бумаги: {port['mid'][-1]:,.2f} ₽. Остальные бумаги и деньги фиксированы. Это не совместная модель всего портфеля.")
    else:st.caption('Приведены сценарии только выбранной позиции. Полная оценка портфеля недоступна.')
    for limit in envelope['limits']:st.caption(limit)
    if st.button('Сохранить сценарное исследование',key=prefix+'save_model'):
        study={'kind':'lab_scenarios','computed_at_utc':datetime.now(timezone.utc).isoformat(),'instrument':{'symbol':asset['symbol'],'name':asset['name']},
               'parameters':{'horizon':horizon,'quantity':held,'base_price':asset['unit_price'],'price_source':asset['source'],'price_type':asset['price_type'],
                             'quote_retrieved_at_utc':asset['retrieved_at_utc'],'seed':envelope['seed'],'model':envelope['model']},
               'model':model,'envelope':envelope,'synthetic':envelope['synthetic'],'portfolio_scope':scope,
               'limits':envelope['limits']}
        research_store().save(study,frame);st.success('Снимок сохранён в истории. Журнал портфеля не изменён.')


@st.fragment
def trade_panel(asset,bundle,marks):
    latest=portfolio_store().bundle()
    if latest['revision']!=bundle['revision']:
        st.warning('Портфель изменён в другом окне. Обновите снимок перед продолжением эксперимента.')
        if st.button('Обновить снимок портфеля',key='lab_reload_bundle'):st.rerun()
        return
    prefix='lab_'+asset['symbol']+'_'+str(st.session_state.get('lab_reset',0))+'_'
    events=[r['event'] for r in bundle['records']];state=ledger_state(events);lot=asset['lot_size']
    held=state['positions'].get(asset['symbol'],{}).get('quantity',0)
    maximum=min(100000000,max(lot*20,int(np.ceil(held/lot))*lot))
    if st.session_state.get('lab_open_existing',False):
        task=st.segmented_control('Задача',['Позиция и сценарии','Изменить позицию'],default='Позиция и сценарии',key=prefix+'task')
        if task!='Изменить позицию':
            existing_position(asset,bundle,marks,prefix,held);return
    default_qty=lot
    st.caption(f"Песочница · снимок портфеля {bundle['revision']} · {asset['board']} · в лоте {lot} бумаг · в портфеле {held}")
    side=st.segmented_control('Предполагаемое действие',['buy','sell'],default='buy',format_func=lambda s:'Купить' if s=='buy' else 'Продать',key=prefix+'side') or 'buy'
    st.session_state.setdefault(prefix+'qty',default_qty);st.session_state.setdefault(prefix+'slider',default_qty)
    left,right=st.columns([1,1.2])
    with left:
        st.write('Количество бумаг')
        a,b,c=st.columns([1,3,1])
        a.button('−',key=prefix+'minus',on_click=_step,args=(prefix,-lot,lot,maximum))
        qty=b.number_input('Количество бумаг',0,100000000,step=lot,key=prefix+'qty',label_visibility='collapsed',on_change=_sync_number,args=(prefix,lot,maximum))
        c.button('+',key=prefix+'plus',on_click=_step,args=(prefix,lot,lot,maximum))
        st.slider('Количество с шагом в лот',0,maximum,step=lot,key=prefix+'slider',on_change=_sync_slider,args=(prefix,))
        st.caption(f'{qty//lot} целых лот.' if qty%lot==0 else 'Количество не кратно лоту — исправьте его без автоматического округления.')
    with right:
        funding=st.selectbox('Источник денег',['cash','topup'],format_func=lambda x:'Свободные деньги портфеля' if x=='cash' else 'Пополнить на недостающую сумму',disabled=side=='sell',key=prefix+'funding')
        st.caption(f"Свободные деньги по журналу: {state['cash']:,.2f} ₽")
    prefs=research_store().preferences();fee_pref=prefs.get('commission') or {}
    with st.expander('Комиссия и допущения',expanded=not bool(fee_pref)):
        known=st.checkbox('Я указываю проверенную ставку своего тарифа',value=bool(fee_pref),key=prefix+'fee_known')
        a,b=st.columns(2)
        rate=a.number_input('Комиссия, %',0.,10.,float(fee_pref.get('pct',0)),step=.01,key=prefix+'fee_rate')
        minimum=b.number_input('Минимальная комиссия за операцию, ₽',0.,1e9,float(fee_pref.get('minimum',0)),key=prefix+'fee_min')
        st.caption('Комиссия рассчитывается от полной суммы, включая НКД, с округлением до копейки. Проверьте базу расчёта по своему тарифу. Нулевую ставку тоже нужно подтвердить.')
        if st.button('Запомнить ставку',disabled=not known,key=prefix+'save_fee'):
            prefs['commission']={'pct':rate,'minimum':minimum};research_store().save_preferences(prefs);st.success('Ставка сохранена в настройках.')
    try:result=preview_trade(events,marks,asset,qty,side=side,funding=funding,fee_pct=rate if known else None,minimum_fee=minimum)
    except (ValueError,KeyError,TypeError) as exc:st.error(user_error(exc));return
    order=result['order'];total=order['buy_total'] if side=='buy' else order['sell_proceeds']
    st.metric('Стоимость покупки с комиссией' if side=='buy' else 'Выручка после комиссии',f'{total:,.2f} ₽' if total is not None else 'Комиссия неизвестна')
    st.caption(f"{qty} × {asset['unit_price']:,.6f} ₽ = {order['gross']:,.2f} ₽ · комиссия: "+(f"{order['fee']:,.2f} ₽" if order['fee'] is not None else 'не задана'))
    for error in result['errors']:st.warning(error)
    if any('Недостаточно денег' in e for e in result['errors']) and funding=='cash':
        st.button('Попробовать с пополнением недостающей суммы',key=prefix+'try_topup',on_click=_topup,args=(prefix,))
    if result['topup']>0:st.info(f"Гипотетическое пополнение: {result['topup']:,.2f} ₽. Это внесение денег, а не прибыль. Журнал не меняется.")
    _overview_table(result,asset['symbol'])
    st.subheader('Ваше изменение цены')
    shock=st.slider('Заданный стресс, не статистический прогноз, %',-50,50,0,key=prefix+'shock')
    selected=result['after'] or result['before']
    if selected is not None:
        stress=stress_selected(selected,asset,shock)
        a,b=st.columns(2);a.metric('Стоимость позиции при этой цене',f"{stress['position_value']:,.2f} ₽")
        b.metric('Стоимость портфеля при этой цене',f"{stress['equity_after']:,.2f} ₽",f"{stress['change_rub']:+,.2f} ₽")
        st.caption(('После эксперимента.' if result['after'] else 'Текущий портфель: операция не применена.')+f" Цена при стрессе: {stress['unit_price']:,.6f} ₽. Остальные активы и деньги неизменны; издержки будущего выхода не включены.")
        st.plotly_chart(_stress_chart(result['before'],result['after'],asset,shock),width='stretch',key=prefix+'stress_chart')
    else:
        held=result.get('known_after_quantity',result.get('known_quantity',0))
        one=position_stress(asset,held,shock)
        st.metric('Стоимость позиции при этой цене',f"{one['value']:,.2f} ₽",f"{one['change_rub']:+,.2f} ₽")
        st.caption('Это оценка только выбранной позиции. Полная стоимость портфеля неизвестна из-за недостающих цен других бумаг.')
    if asset['asset_type']=='bond':st.caption(f"Номинал {asset['face_value']:,.2f} ₽ · чистая котировка {asset['quoted_pct']:.6f}% · НКД {asset['accrued_interest']:,.6f} ₽. Стресс меняет только чистую цену; НКД фиксирован, амортизация и купоны не моделируются.")
    with st.expander('Ликвидность и ограничения'):
        liq=result['liquidity']
        st.write('Спред снимка: '+(f"{liq['spread_pct']:.3f}%" if liq['spread_pct'] is not None else 'неизвестен'))
        if liq['order_share_of_reported_volume_pct'] is not None:st.write(f"От дневного объёма снимка: {liq['order_share_of_reported_volume_pct']:.3f}%")
        for warning in liq['warnings']:st.caption(warning)
        st.caption('Концентрация сравнивается по тикерам. Сквозной состав фондов и совместная портфельная VaR не рассчитаны.')
    enabled=st.checkbox('Показать отдельные сценарии статистической модели',value=bool(st.session_state.get('lab_open_existing',False)),key=prefix+'model_enabled')
    if enabled:_model_view(asset,result,prefix)
    st.caption('Все действия в лаборатории — эксперименты. Кнопок записи сделок в журнал здесь нет.')


def existing_position(asset,bundle,marks,prefix,held):
    st.caption(f'Текущая позиция: {held} бумаг · количество из журнала, повторный ввод не нужен')
    st.metric('Текущая стоимость выбранной позиции',f"{held*asset['unit_price']:,.2f} ₽")
    events=[r['event'] for r in bundle['records']]
    try:snapshot=analyze_portfolio(events,marks)
    except (ValueError,KeyError,TypeError):snapshot=None
    st.subheader('Ваше изменение цены')
    shock=st.slider('Заданный стресс, не статистический прогноз, %',-50,50,0,key=prefix+'existing_shock')
    one=position_stress(asset,held,shock)
    a,b=st.columns(2);a.metric('Стоимость позиции при этой цене',f"{one['value']:,.2f} ₽",f"{one['change_rub']:+,.2f} ₽")
    if snapshot:
        stressed=stress_selected(snapshot,asset,shock)
        b.metric('Стоимость портфеля при этой цене',f"{stressed['equity_after']:,.2f} ₽",f"{stressed['change_rub']:+,.2f} ₽")
        st.plotly_chart(_stress_chart(snapshot,None,asset,shock),width='stretch',key=prefix+'existing_chart')
    else:b.caption('Полная стоимость портфеля неизвестна: нет оценок остальных позиций.')
    st.caption(f"Цена при заданном стрессе: {one['unit_price']:,.6f} ₽. Это гипотеза пользователя. Остальные активы фиксированы; для облигаций фиксирован НКД.")
    enabled=st.checkbox('Показать отдельные сценарии статистической модели',value=True,key=prefix+'model_enabled')
    if enabled:_model_view(asset,{'before':snapshot,'after':None,'known_quantity':held},prefix)
    st.caption('Сохранённые операции и позиции не меняются.')


def _manual_quote(symbol):
    with st.expander('Задать цену вручную',expanded=True):
        st.caption('Это явно ручная цена, не ответ MOEX. Нужны подтверждённые единицы, дата и размер лота.')
        with st.form('lab_manual_quote'):
            kind=st.selectbox('Класс бумаги',['equity','fund','bond'],format_func=lambda k:{'equity':'Акция','fund':'Фонд','bond':'Облигация'}[k],key='lab_manual_kind')
            # All fields remain explicit in this fallback; irrelevant bond fields are ignored.
            a,b=st.columns(2)
            price=a.number_input('Цена: ₽ за бумагу; для облигации — % номинала',0.,1e12,0.,format='%.6f',key='lab_manual_price')
            lot=b.number_input('Подтверждённый размер лота',0,100000000,0,key='lab_manual_lot')
            face=a.number_input('Рублёвый номинал облигации',0.,1e12,0.,key='lab_manual_face')
            accrued=b.number_input('НКД за облигацию, ₽',0.,1e12,0.,format='%.6f',key='lab_manual_accrued')
            day=st.date_input('Дата цены',market_today(),max_value=market_today(),key='lab_manual_date')
            source=st.text_input('Документ / источник цены',key='lab_manual_source')
            ack=st.checkbox('Проверены валюта RUB, единицы цены, НКД и размер лота',key='lab_manual_ack')
            save=st.form_submit_button('Использовать ручную цену только в песочнице')
        if save:
            if not ack:st.error('Подтвердите проверку единиц и лота.');return
            try:
                st.session_state['lab_manual_asset_'+symbol]=manual_asset(symbol,kind,price,lot,source,face=face,accrued=accrued,as_of=day)
                st.rerun()
            except (ValueError,KeyError,TypeError) as exc:st.error(str(exc))


@st.fragment
def goal_panel(default_initial=5000.):
    from .experience import money
    st.subheader('Финансовая цель')
    target=st.number_input('Капитал, который хочу накопить, ₽',.01,1e15,1000000.,step=10000.,key='goal_target')
    st.caption('Допущения о доходности и инфляции, не прогноз рынка. Пополнения фиксированы в рублях и поступают в конце месяца.')
    a,b=st.columns(2)
    initial=a.number_input('Первоначальный капитал, ₽',0.,1e12,float(default_initial),key='goal_initial')
    monthly=b.number_input('Ежемесячное пополнение, ₽',0.,1e9,5000.,step=1000.,key='goal_monthly')
    months=st.slider('Горизонт накопления, месяцев',1,600,60,key='goal_months')
    a,b=st.columns(2)
    annual=a.slider('Допущение доходности в год, %',-50.,50.,10.,.5,key='goal_return')
    inflation=b.slider('Допущение инфляции в год, %',-10.,30.,5.,.5,key='goal_inflation')
    real=st.toggle('Показать в покупательной способности сегодняшних рублей',value=True,key='goal_real')
    main=capital_goal(initial,monthly,months,annual,inflation);column='real' if real else 'nominal'
    fig=go.Figure()
    for delta,label,dash in [(-5,'Доходность на 5 п.п. ниже','dot'),(0,'Ваше допущение','solid'),(5,'Доходность на 5 п.п. выше','dash')]:
        curve=capital_goal(initial,monthly,months,annual+delta,inflation)
        fig.add_trace(go.Scatter(x=curve.index,y=curve[column],name=label,line=dict(dash=dash)))
    no_return=capital_goal(initial,monthly,months,0.,inflation)
    fig.add_trace(go.Scatter(x=main.index,y=no_return[column],name='Без доходности, та же инфляция',line=dict(color=TOKENS['muted'],dash='dashdot')))
    fig.update_xaxes(title='Месяцы')
    st.plotly_chart(chart(fig,350,'Сегодняшние ₽' if real else 'Номинальные ₽'),width='stretch',key='goal_chart')
    a,b,c=st.columns(3)
    a.metric('Внесено за весь срок',money(main.contributed.iloc[-1],0))
    b.metric('Номинальный капитал',money(main.nominal.iloc[-1],0))
    c.metric('В сегодняшних рублях',money(main.real.iloc[-1],0))
    from .sandbox import required_return
    needed=required_return(initial,monthly,months,target)
    st.metric('Требуемая средняя доходность в год',f'{needed:.2f}%' if needed is not None else 'За пределами диапазона −99…100%')
    st.caption('Обратный расчёт при постоянной номинальной доходности, без гарантии достижимости. Цель в номинальных рублях.')
    a,b=st.columns(2)
    a.metric('Если пополнять на 1 000 ₽ больше',money(capital_goal(initial,monthly+1000,months,annual,inflation).nominal.iloc[-1],0))
    b.metric('Если копить на год дольше',money(capital_goal(initial,monthly,min(600,months+12),annual,inflation).nominal.iloc[-1],0))
    st.caption('±5 п.п. — выбранные допущения чувствительности, не процентили и не реальные вероятности. Без налогов, комиссий и гарантий доходности.')


def laboratory_page():
    view=st.segmented_control('Эксперимент',['Покупка и цена','Финансовая цель'],default='Покупка и цена',key='lab_view',label_visibility='collapsed')
    db=portfolio_store();bundle=db.bundle()
    if view=='Финансовая цель':
        _,_,current=portfolio_module.current_portfolio()
        initial=current['snapshot']['equity'] if current['snapshot'] is not None and bundle['records'] else 5000.
        goal_panel(initial);return
    a,b=st.columns([5,1],vertical_alignment='bottom')
    with a:symbol=instrument_picker('lab_picker',st.session_state.get('symbol','SBER'),compact=True)
    with b:
        if st.button('Обновить цену',key='lab_refresh_price'):
            cached_asset.clear();portfolio_module.market_marks.clear();get_engine().clear_quotes()
            st.session_state.pop('lab_manual_asset_'+symbol,None)

    try:
        symbol=identifier(symbol)
        with st.spinner('Получаю цену, единицы и лот…'):loaded=cached_asset(symbol,str(Settings.from_env().data_dir))
    except (ValueError,KeyError,TypeError) as exc:st.warning(str(exc));return
    asset=st.session_state.get('lab_manual_asset_'+symbol) or loaded['asset']
    if loaded.get('error'):
        st.caption('Источник сейчас недоступен. '+('Доступна сохранённая оценка.' if asset else 'Подходящая цена не получена.'))
    if asset is None:
        _manual_quote(symbol);return
    from .provenance import asset_mark
    asset={**asset,'mark':asset_mark(asset)}
    if asset.get('manual'):st.warning('Ручная оценка пользователя. Ликвидность и доступность лота не проверены биржей.')
    elif asset.get('saved_snapshot'):st.warning('MOEX недоступна: используется сохранённый снимок. Цена и торговые условия могут устареть.')
    from .sandbox import quote_status
    status=quote_status(asset)
    if status['state'] in {'stale','unknown_age'}:st.warning(status['label'])
    symbols=tuple(sorted(ledger_state([r['event'] for r in bundle['records']])['positions']))
    market=portfolio_module.market_marks(symbols) if symbols else {'marks':{},'errors':{}}
    marks=copy.deepcopy(market['marks']);marks[symbol]=asset['mark']
    missing=[s for s in symbols if s not in marks]
    if missing:
        with st.expander('Недостающие оценки других позиций',expanded=True):
            st.caption('Без них полная стоимость и сравнение портфеля недоступны. Можно задать явно ручные цены только для этого эксперимента.')
            source=st.text_input('Источник ручных оценок остальных бумаг',key='lab_other_source')
            for s in missing:
                price=st.number_input(s+': полная цена, ₽ за бумагу (для облигации с НКД)',0.,1e12,0.,format='%.6f',key='lab_other_'+s)
                if price>0 and source.strip():marks[s]={'price':price,'as_of':str(market_today()),'source':source+' (ручная оценка для песочницы)'}
    from .interactive_lab import render_sandbox
    render_sandbox(asset,bundle,marks)
    from .experience import asset_card
    with st.expander('Карточка инструмента и история цены'):
        held=ledger_state([r['event'] for r in bundle['records']])['positions'].get(symbol,{}).get('quantity',0)
        asset_card(symbol,held,asset['mark'],key='lab_asset',actions=False)


def show_health(snapshot):
    prefs=research_store().preferences();health=portfolio_health(snapshot,prefs.get('profile'))
    st.subheader('Структура и стресс портфеля')
    st.write(f"{health['positions']} открытых позиций. Самая крупная бумага: {health['concentration']['max_security_weight_pct']:.1f}% капитала. Свободные деньги: {health['cash']:,.2f} ₽.")
    for warning in health['warnings']:st.warning(warning)
    stress=health['uniform_price_stress']
    st.metric('Заданный стресс: все бумаги −20%',f"{stress['change_rub']:+,.2f} ₽",f"{stress['change_pct']:+.2f}%")
    for limitation in health['limitations']:st.caption(limitation)


def show_saved_scenarios(result,history_csv):
    st.info('Сохранённый снимок сценарного исследования. Он не пересчитывается вслед за текущими настройками или портфелем.')
    if result.get('synthetic'):st.warning('Искусственная история: учебные сценарии, не прогноз реальной бумаги.')
    p=result['parameters'];model=result['model'];series=model['position'];h=p['horizon']
    st.write(f"{result['instrument']['symbol']} · {p['quantity']} бумаг · {h} торговых дней · {result['computed_at_utc']}")
    fig=go.Figure()
    for key,label in [('lo','5-й процентиль'),('mid','Медиана'),('hi','95-й процентиль')]:fig.add_trace(go.Scatter(x=list(range(h+1)),y=series[key],name=label))
    fig.update_xaxes(title='Торговые дни')
    st.plotly_chart(chart(fig,330,'Стоимость позиции, ₽'),width='stretch')
    for limit in result['limits']:st.caption(limit)
    if st.button('Сравнить с фактическими закрытиями после снимка',disabled=bool(result.get('synthetic')),key='compare_saved_lab'):
        try:
            start=datetime.fromisoformat(result['computed_at_utc']).astimezone(ZoneInfo('Europe/Moscow')).date()+timedelta(days=1)
            end=market_today()-timedelta(days=1)
            if start>end:st.info('После снимка ещё нет доступных завершённых торговых дней.');return
            frame,meta=get_engine().frame_sync(result['instrument']['symbol'],start,end)
            if len(frame)<h:st.info(f'Доступно {len(frame)} закрытий после снимка, требуется {h}. Сравнение срока ещё не готово.');return
            actual=float(frame.CLOSE.iloc[h-1])*p['quantity']
            st.metric('Фактическая стоимость позиции на выбранном сроке',f'{actual:,.2f} ₽')
            st.caption(f"Дата: {frame.index[h-1].date()}. Цена CLOSE, без выплат и корпоративных корректировок. Это проверка одного исхода, не доказательство качества модели.")
        except (ValueError,KeyError,TypeError) as exc:st.warning(str(exc))
    st.download_button('Скачать снимок сценариев JSON',json.dumps(result,ensure_ascii=False,indent=2),file_name='lab_scenario_snapshot.json',mime='application/json')
    st.download_button('Исходная история CSV',history_csv,file_name='lab_history.csv',mime='text/csv')
