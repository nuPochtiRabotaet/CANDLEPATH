"""Compact v2 component with local interactions and authoritative Python replay."""
from functools import lru_cache
from pathlib import Path
from datetime import datetime,timedelta,timezone
import streamlit as st
from plotly.offline import get_plotlyjs
from . import sandbox
from .config import Settings
from .data import market_today
from .laboratory import model_position,liquidity_check
from .design import TOKENS,css_vars

ASSETS=Path(__file__).with_name('components')


@lru_cache(maxsize=1)
def component():
    # Plotly is shipped by the existing Python dependency. No CDN, npm or build step.
    plotly='const __plotlyModule={exports:{}}; (function(module,exports){'+get_plotlyjs()+'})(__plotlyModule,__plotlyModule.exports);globalThis.__MOEXPlotly=__plotlyModule.exports;\n'
    return st.components.v2.component('moex_investment_sandbox_v071',html=(ASSETS/'lab.html').read_text(),
             css=css_vars(':host')+(ASSETS/'lab.css').read_text(),js=plotly+(ASSETS/'lab.js').read_text())


def prepare_model(asset):
    from .lab_ui import cached_history,cached_envelope
    if asset['asset_type']=='bond':return {'error':'Для облигации нет модели купонов, амортизации и погашения. Доступен ценовой стресс с фиксированным НКД.'}
    try:
        if not asset.get('observed_at'):raise ValueError('Время рыночного наблюдения неизвестно. Обновите базовую цену перед моделью.')
        age=(market_today()-datetime.fromisoformat(str(asset.get('observed_at'))[:10]).date()).days
        if age<0 or age>7:raise ValueError('Обновите базовую цену: дата старше 7 дней или находится в будущем.')
        loaded=cached_history(asset['symbol'],str(market_today()-timedelta(days=1)))
        if loaded['data'] is None:raise ValueError(loaded['error'])
        frame,meta=loaded['data']
        if not meta.get('demo_data') and meta.get('board')!=asset.get('board'):raise ValueError('Режим торгов истории отличается от котировки. Обновите историю; старый ряд не применяется.')
        if not meta.get('demo_data') and (market_today()-frame.index[-1].date()).days>7:raise ValueError('История старше 7 дней; модель не рассчитывается.')
        horizons=[h for h in [5,21,63,252] if len(frame)>=max(126,2*h+1)]
        if not horizons:raise ValueError('Для модели нужно не менее 126 закрытий.')
        return cached_envelope(frame,meta,max(horizons))
    except (ValueError,KeyError,TypeError) as exc:return {'error':str(exc)}


def advisor_transfer(asset,bundle,marks,state):
    """Transfer only assumptions representable by the existing purchase Advisor."""
    if not state['fee_known']:raise ValueError('Перед подробной оценкой подтвердите тариф: неизвестная комиссия не переносится как нулевая.')
    if state['fee_pct']>3:raise ValueError('Подробный Advisor поддерживает комиссию до 3%. Тариф не изменён; точная стоимость доступна в лаборатории.')
    if state['minimum_fee']>0:raise ValueError('Подробный Advisor не поддерживает минимальную комиссию в рублях. Точный расчёт с вашим тарифом остаётся в лаборатории; тариф не подменён процентным.')
    if state['side']=='sell' and state['quantity']:raise ValueError('Подробный Advisor оценивает вложение, а не продажу. Сценарий продажи доступен в лаборатории.')
    r=sandbox.calculate(asset,bundle,marks,state)
    existing=state['quantity']==0
    amount=r['known_quantity']*asset['unit_price'] if existing else r['order']['buy_total']
    if not amount or amount>1e9 or state['months']>60:raise ValueError('Подробный Advisor поддерживает ненулевую сумму до 1 млрд ₽ и срок до 60 месяцев.')
    fields={'adv_amount':float(amount),'adv_months':int(state['months']),'adv_loss':float(state['max_loss']),
            'adv_early':state['early'],'adv_filled':False,'adv_fee':float(state['fee_pct']),'adv_portfolio_known':False,
            'advisor_use_saved':not existing and state['funding']=='cash','adv_funding':'existing_cash'}
    notice='Перенесены актив, сумма, срок и ограничения эксперимента. Проверьте предпочтение риска, проскальзывание и источник средств, затем подтвердите полный профиль на этом экране; постоянный профиль не изменён.'
    if existing:notice+=' Анализируется сумма существующей позиции. Контекст новой покупки отключён, чтобы не прибавлять позицию к портфелю повторно.'
    elif state['funding']=='topup':notice+=' Пополнение только недостающей суммы не переносится как полное новое финансирование: контекст портфеля в Advisor отключён.'
    return {'symbol':asset['symbol'],'fields':fields,'notice':notice}


@st.fragment
def render_sandbox(asset,bundle,marks):
    from .portfolio_ui import portfolio_store
    from .lab_ui import research_store,cached_history
    if st.session_state.pop('lab_refresh_requested',False):
        from .lab_ui import cached_asset
        from .portfolio_ui import market_marks
        from .data import get_engine
        cached_asset.clear();market_marks.clear();get_engine().clear_quotes();st.session_state.pop('lab_manual_asset_'+asset['symbol'],None);st.rerun(scope='app')
    if st.session_state.get('navigation_request'):st.rerun(scope='app')
    if portfolio_store().bundle()['revision']!=bundle['revision']:
        st.warning('Портфель изменился в другом окне. Обновите снимок, чтобы продолжить.')
        if st.button('Обновить снимок',key='refresh_lab_revision'):st.rerun()
        return
    prefs=research_store().preferences()
    d=sandbox.presentation_data(asset,bundle,marks,prefs,st.session_state.get('lab_open_existing',False),st.session_state.get('lab_mode','Сценарии'))
    context=d['context'];saved=st.session_state.get('sandbox_request',{})
    defaults=d['initial'];state=defaults
    if saved.get('context')==context:
        try:state=sandbox.validate_state(saved.get('state'),asset,defaults)
        except ValueError:pass
    from .provenance import display_time
    d['tokens']=TOKENS
    for field,source in [('retrieved_display','retrieved_at'),('saved_display','saved_at'),('valuation_display','valuation_as_of')]:d['price_status'][field]=display_time(d['price_status'].get(source))
    rejected=st.session_state.get('sandbox_rejected',{})
    d['rejected_seq']=rejected.get('seq') if rejected.get('context')==context else None
    d['state']=state;d['classes']={s:m.get('asset_type','unknown') for s,m in marks.items()};d['classes'][asset['symbol']]=asset['asset_type']
    liq=liquidity_check(asset,state['quantity']);d['liquidity_text']=' '.join(liq['warnings'])
    if liq['spread_pct'] is not None:d['liquidity_text']=f"Спред снимка {liq['spread_pct']:.3f}%. "+d['liquidity_text']
    if liq['order_share_of_reported_volume_pct'] is not None:d['liquidity_text']+=f" От объёма дня: {liq['order_share_of_reported_volume_pct']:.3f}%."
    if state['show_model']:
        with st.spinner('Подготавливаю модель по истории…'):d['model']=prepare_model(asset)
    else:d['model']=None
    d['response']=sandbox.calculate(asset,bundle,marks,state)
    d['response']['constraints']=sandbox.evaluate_constraints(d['response'],asset,state,d.get('model'))
    st.session_state.sandbox_validated=d['response']
    d['notice']=st.session_state.pop('sandbox_notice',None)
    widget_key='investment_sandbox_'+context
    def receive():
        widget=st.session_state.get(widget_key,{})
        req=widget.get('request') if isinstance(widget,dict) else getattr(widget,'request',None)
        if req and req.get('context')==context:
            try:
                checked=sandbox.validate_state(req.get('state'),asset,defaults)
                latest=st.session_state.get('sandbox_request',{})
                if latest.get('context')==context and checked['seq']<latest.get('state',{}).get('seq',0):return
                st.session_state.sandbox_request={'context':context,'state':checked}
            except ValueError as exc:
                st.session_state.sandbox_notice=str(exc)
                st.session_state.sandbox_rejected={'context':context,'seq':req.get('state',{}).get('seq')}
    def action():
        widget=st.session_state.get(widget_key,{})
        req=widget.get('action') if isinstance(widget,dict) else getattr(widget,'action',None)
        if not req or req.get('context')!=context:return
        try:
            checked=sandbox.validate_state(req.get('state'),asset,defaults)
            latest=st.session_state.get('sandbox_request',{})
            if latest.get('context')==context and checked['seq']<latest.get('state',{}).get('seq',0):return
            if st.session_state.get('sandbox_last_action')==(context,checked['seq']):return
            st.session_state.sandbox_last_action=(context,checked['seq'])
            st.session_state.sandbox_request={'context':context,'state':checked}
            if req['kind']=='refresh_price':
                st.session_state.lab_refresh_requested=True
            elif req['kind']=='deep_advisor':
                st.session_state.navigation_request=advisor_transfer(asset,bundle,marks,checked)
            elif req['kind']=='save_fee':
                if not checked['fee_known']:raise ValueError('Сначала подтвердите тариф.')
                prefs['commission']={'pct':checked['fee_pct'],'minimum':checked['minimum_fee']};research_store().save_preferences(prefs)
                st.session_state.sandbox_notice='Тариф сохранён.'
            elif req['kind']=='save_model':
                envelope=prepare_model(asset)
                if envelope.get('error'):raise ValueError(envelope['error'])
                r=sandbox.calculate(asset,bundle,marks,checked)
                if r['errors']:raise ValueError('Сначала исправьте параметры операции: '+' '.join(r['errors']))
                qty=r.get('known_after_quantity',r['known_quantity']);snap=r['after'] or r['before']
                model=model_position(envelope,asset,qty,checked['horizon'],snap)
                loaded=cached_history(asset['symbol'],str(market_today()-timedelta(days=1)));frame,_=loaded['data']
                study={'kind':'lab_scenarios','computed_at_utc':datetime.now(timezone.utc).isoformat(),'instrument':{'symbol':asset['symbol'],'name':asset['name'],'board':asset['board']},
                       'parameters':{'horizon':checked['horizon'],'quantity':qty,'base_price':asset['unit_price'],'price_source':asset['source'],'price_type':asset['price_type'],'quote_retrieved_at_utc':asset['retrieved_at_utc'],'seed':envelope['seed'],'model':envelope['model']},
                       'model':model,'envelope':envelope,'synthetic':envelope['synthetic'],'portfolio_scope':'после эксперимента','limits':envelope['limits'],'method_version':sandbox.METHOD_VERSION}
                research_store().save(study,frame);st.session_state.sandbox_notice='Исследование сохранено. Журнал не изменён.'
        except (ValueError,KeyError,TypeError) as exc:st.session_state.sandbox_notice=str(exc)
    component()(key=widget_key,data=d,on_request_change=receive,on_action_change=action)
