"""Streamlit adapter. Public workers, analytical state and paper ledger are separate."""
import asyncio,math,time,uuid,os,sqlite3
from dataclasses import asdict
from .intelligence import RegimeSnapshot,DecisionContext,Forecast,ForecastHistory,format_forecast_scorecard_pct
from .forecast_baseline import HistoricalVolatilityBaseline,candle_stream_ready
from .market import seconds
from functools import lru_cache
from pathlib import Path
import streamlit as st
from .market import INTERVALS,SYMBOLS,MarketError
from .storage import Store
from .analysis import analyze
from .lifecycle import SignalLifecycle,provisional
from .paper import Paper
from .orders import OrderPreview
from .protection import ProtectionPreview
from .inventory import inventory,position_revision
from .preferences import load as load_preferences,save as save_preferences,DEFAULTS as OVERLAY_DEFAULTS
from .risk import D
from .costs import CostModel,FeeSchedule,ExecutionAssumptions,budget_quantity,estimate
from .quality import assess,QualityPolicy
from .risk import metrics,plan,protection_plan,RiskError,floor_step
from ..config import Settings
from ..workspace_mode import legacy_invest_enabled
from .runtime import hub, monitor
ASSETS=Path(__file__).resolve().parents[1]/'components'

@st.cache_data(max_entries=24,show_spinner=False)
def potential(rows,symbol,interval):return provisional(rows,symbol,interval)

@lru_cache(maxsize=1)
def component():
    return st.components.v2.component('moex_crypto_v08',html=(ASSETS/'trade.html').read_text(),css=(ASSETS/'trade.css').read_text(),js=(ASSETS/'vendor/lightweight-charts.js').read_text()+'\n'+(ASSETS/'trade.js').read_text())

@st.cache_data(max_entries=24,show_spinner=False)
def calculation(rows,symbol,interval):return analyze(rows,symbol,interval)

def collect(store,symbol,interval):
    state=Paper(store).state();symbols=set(state['positions'])|{symbol};snapshots={}
    pairs=[(s,interval if s==symbol else '15') for s in symbols]
    st.session_state.setdefault('crypto_owner',str(uuid.uuid4()))
    hub().retain(st.session_state.crypto_owner,pairs,store)
    for sym in symbols:
        snapshots[sym]=hub().get(sym,interval if sym==symbol else '15',store).snapshot()
    quotes={s:{**x['quote'],'fresh':x['fresh']} for s,x in snapshots.items()}
    rules={s:x['rules'] for s,x in snapshots.items()}
    return snapshots[symbol],quotes,rules

def page():
    nav_col, symbol_col, tf_col, mode_col = st.columns([1.1,1.5,1.3,3])

    def navigate_workspace(workspace):
        st.session_state.workspace_mode = workspace

    if legacy_invest_enabled():
        nav_col.button('← Invest',key='return_invest',on_click=navigate_workspace,args=('Invest',))
    nav_col.button('Strategy Coliseum',key='open_coliseum',on_click=navigate_workspace,args=('Strategy Coliseum',))
    symbol=symbol_col.selectbox('Инструмент',SYMBOLS,key='crypto_symbol')
    tf=tf_col.selectbox('Таймфрейм',list(INTERVALS),index=2,key='crypto_tf')
    mode=mode_col.segmented_control('Режим',['Market Data','Paper Trading','Read Only'],default='Market Data',key='crypto_mode')
    dbpath=Settings.from_env().data_dir/'crypto-v08.sqlite3'
    try:
        monitor(dbpath)
    except RuntimeError as exc:
        st.error(str(exc))
        st.warning("Локальная Paper-база занята другим процессом; операции заблокированы.")
        return
    store=Store(dbpath)
    terminal(store,symbol,INTERVALS[tf],mode or 'Market Data')
    from .performance_ui import render as performance_view
    performance_view(store)
    with st.expander('Forecast · история проверенных исходов'):
        st.caption('Только реальные опубликованные экспериментальные прогнозы и последующие закрытые свечи. Показатели НЕ подтверждают доходность стратегии.')
        if st.button('Рассчитать точность завершённых прогнозов',key='forecast_scorecard_refresh'):
            try:
                report=ForecastHistory(store).scorecard(symbol,INTERVALS[tf])
                st.session_state.forecast_scorecard_cache=(symbol,INTERVALS[tf],report)
            except (sqlite3.Error,ValueError,ArithmeticError) as exc:
                st.error('Ошибка проверки журнала прогнозов: '+str(exc))
        cached=st.session_state.get('forecast_scorecard_cache')
        if cached and cached[:2]==(symbol,INTERVALS[tf]):
            report=cached[2]
            st.write('Опубликовано прогнозов:',report['forecasts'])
            if not report['horizons']:
                st.info('Пока нет прогнозов с подтверждёнными последующими свечами.')
            else:
                for horizon,row in report['horizons'].items():
                    st.write(f"+{horizon} свечей: {row['observations']} исходов · "
                             f"покрытие диапазона {row['empirical_coverage']*100:.1f}% · "
                             f"средняя абсолютная ошибка {format_forecast_scorecard_pct(row['mean_absolute_pct_error'])}"
                             +(f" · непредставимых ошибок: {row.get('unrepresentable_percentage_errors',0)}"
                               if row.get('unrepresentable_percentage_errors',0) else '')
                             +(' · мало наблюдений' if not row['sufficient_sample'] else ' · не является подтверждением торгового преимущества'))
    if mode=='Paper Trading':
        with st.expander('Paper · комиссии и Quality Policy'):
            current=CostModel.from_state(Paper(store).state());pol=Paper(store).state().get('quality_policy',{})
            with st.form('paper_cost_settings'):
                st.caption('LOCAL PAPER assumptions. Maker не применяется к Market. SELL/base запрещён. Изменение настроек аннулирует прежний preview; старые fills не пересчитываются.')
                maker=st.number_input('Maker % · только будущая модель',0.0,2.0,float(current.fees.maker)*100,step=.01)
                taker=st.number_input('Taker % · Market',0.0,2.0,float(current.fees.taker)*100,step=.01)
                currency=st.radio('Комиссия BUY',['quote','base'],key='cost_currency',index=0 if current.fees.buy_currency=='quote' else 1,horizontal=True,format_func=lambda x:'USDT (quote)' if x=='quote' else 'Актив (base)')
                slip=st.number_input('Slippage bps',0.0,100.0,float(current.execution.slippage_bps),step=1.0)
                rr=st.number_input('Advisory minimum Net R/R',0.0,10.0,float(pol.get('min_net_rr',1)),step=.1)
                spread_limit=st.number_input('Advisory maximum spread bps',1.0,500.0,float(pol.get('max_spread_bps',20)),step=1.0)
                if st.form_submit_button('Сохранить предположения Paper'):
                    model=CostModel(FeeSchedule(version='paper-'+str(uuid.uuid4()),maker=str(D(maker)/100),taker=str(D(taker)/100),buy_currency=currency),ExecutionAssumptions(str(slip)))
                    Paper(store).configure_costs(model,QualityPolicy(min_net_rr=rr,max_spread_bps=spread_limit));st.rerun()

    if mode=='Read Only':
        with st.expander('Приватный Bybit · только чтение'):
            st.caption('Ключи задаются переменными окружения на компьютере. Поддерживается глобальный V5 UNIFIED. Доступ зависит от платформы и региона; обход ограничений отсутствует.')
            if st.button('Проверить Read Only и загрузить данные',key='bybit_private'):
                from .private import ReadOnly
                try:
                    with st.spinner('Проверка прав и чтение аккаунта…'):st.session_state.private_view=asyncio.run(ReadOnly().snapshot())
                except MarketError as e:st.error(str(e));st.session_state.pop('private_view',None)
            if 'private_view' in st.session_state:st.json(st.session_state.private_view)
    with st.expander('Правила и ограничения симуляции'):
        st.write('LOCAL PAPER — локальные виртуальные исполнения, не Bybit Demo. Издержки задаются в настройках Paper: это предположения, не фактические тарифы аккаунта. Market использует Taker; Maker только параметр будущего исполнения. Bid/Ask учитывает спред один раз. При запуске через start.command локальный монитор стартует до открытия вкладки и работает только пока запущен процесс приложения. Прямой streamlit run запускает монитор лишь после открытия Trade. После сна Mac или сбоя данные могут устареть. При разрывах цена исполнения может быть хуже стопа. Реальные сделки технически отключены.')
        st.write('Риск: 0,75% на сделку, 1,5% совокупно; до 3 позиций, 25% на инструмент, 75% капитала. Дневной/недельный убыток 3%/6%; при просадке 8% размер новых позиций уменьшается вдвое, 12% блокирует входы, 15% — критический порог. Это проектные ограничения, а не оптимизированная стратегия.')

@st.fragment(run_every=1)
def terminal(store,symbol,interval,mode):
    paper=Paper(store)
    try:snap,quotes,rules=collect(store,symbol,interval)
    except MarketError as e:st.error(str(e));return
    result=calculation(snap['candles'],symbol,interval)
    signals=[s for s in store.signals(symbol,interval) if s['detected_at']<=snap.get('snapshot_at',time.time())]
    state=paper.mark(quotes);m=metrics(state,quotes,rules=rules)
    key='crypto_terminal'
    context=symbol+':'+interval
    saved=st.session_state.get('crypto_inputs',{})
    price=snap['quote'].get('price',0);rule=snap['rules'];tick=rule['tick'] if rule else '.01'
    atr=result.get('atr') or price*.01
    defaults={'quantity':str(floor_step(1000/price,rule['step'])) if rule and price else '0','stop':str(floor_step(max(float(tick),price-2*atr),tick)),'target':str(floor_step(price+4*atr,tick)),'risk_pct':.75,'seq':0,'input_mode':'amount','budget':'25','budget_mode':'notional'}
    if saved.get('context')!=context and price and rule:
        saved={'context':context,'inputs':defaults};st.session_state.crypto_inputs=saved
    inputs=saved.get('inputs',defaults) if saved.get('context')==context else defaults
    inputs=dict(inputs)
    if inputs.get('input_mode')=='amount' and price and rule:
        try:inputs['quantity']=str(budget_quantity(inputs.get('budget','25'),snap['quote'],rule['step'],CostModel.from_state(state),inputs.get('budget_mode','notional')))
        except (ValueError,ArithmeticError):inputs['quantity']='0'
    preview=None;error=''
    if price and rule:
        try:preview=plan(state,quotes,symbol,inputs['quantity'],inputs['stop'],inputs['target'],rule,inputs['risk_pct'],portfolio_rules=rules)
        except (ValueError,ArithmeticError,TypeError,KeyError) as e:error=str(e)
    life=SignalLifecycle(store).update([],[],symbol,interval,quotes[symbol],result['regime'],state,rule,inputs['quantity'],inputs['risk_pct'],candle_fresh=snap.get('readiness',{}).get('forecast_feed_ready',False),portfolio_quotes=quotes,portfolio_rules=rules,observe=False,as_of=snap.get('snapshot_at'))
    quality=assess(result['regime'],life['active'],preview,quotes[symbol],error,QualityPolicy(**state.get('quality_policy',{})))
    protection=monitor(str(store.path)).status()
    allocations={}
    for sym,position in state['positions'].items():
        try:
            allocations[sym]=inventory(position['qty'],quotes[sym],rules[sym],CostModel.from_state(state),position.get('cost_basis',str(D(position['entry'])*D(position['qty'])+D(position['entry_fee']))))
        except (ValueError,KeyError,TypeError,ArithmeticError):pass
    edit_preview=None;edit_error=''
    if symbol in state['positions']:
        try:edit_preview=protection_plan(state,quotes,symbol,inputs['stop'],inputs['target'],rule,rules)
        except (ValueError,KeyError,TypeError,ArithmeticError) as exc:edit_error=str(exc)
    research_as_of=max((c['time']+seconds(interval) for c in snap['candles'] if c['closed']),default=0)
    if candle_stream_ready(snap):
        forecast=HistoricalVolatilityBaseline().forecast(tuple(snap['candles']),symbol,interval,time.time())
    else:
        forecast=Forecast('unavailable',symbol,interval,time.time(),research_as_of,
                          HistoricalVolatilityBaseline.version,'UNAVAILABLE',
                          reason='Нет актуального потока закрытых свечей; прогноз скрыт')
    # A forecast is visible only after an immutable first publication succeeds.
    # Repeated UI reruns must never create conflicting forecasts for the same candle.
    if forecast.status=='EXPERIMENTAL':
        try:
            history=ForecastHistory(store)
            history.publish(forecast)
            reconcile_key='forecast_reconciled_'+symbol+'_'+interval
            if st.session_state.get(reconcile_key)!=research_as_of:
                history.reconcile()
                st.session_state[reconcile_key]=research_as_of
        except (ValueError,sqlite3.Error):
            forecast=Forecast('unavailable',symbol,interval,time.time(),research_as_of,
                              HistoricalVolatilityBaseline.version,'UNAVAILABLE',
                              reason='Не удалось безопасно сохранить прогноз в журнале')
    decision=DecisionContext(symbol,interval,time.time(),RegimeSnapshot(symbol,interval,research_as_of,result['regime']),life['active'].get('id'),life['active']['state'],quality['quality'],quality['attention'],bool(preview and preview['allowed']),tuple((preview or {}).get('errors',[])),forecast)
    d={**snap,'ui_payload_at':time.time(),'intelligence':asdict(decision),'overlay_settings':load_preferences(store),'overlay_defaults':OVERLAY_DEFAULTS,'inventory':allocations,'protection_preview':edit_preview,'protection_error':edit_error,'quality_assessment':quality,'cost_model':CostModel.from_state(state).snapshot(),'lifecycle':life,'protection':protection,'context':context,'mode':mode,'analysis':result,'signals':signals,'account':m,'state':state,'orders':store.orders(),'journal':store.events(),'inputs':inputs,'preview':preview,'input_error':error,'notice':st.session_state.get('crypto_notice',''),'pending':st.session_state.get('crypto_pending')}
    def read_event(name):
        widget=st.session_state.get(key,{})
        return widget.get(name) if isinstance(widget,dict) else getattr(widget,name,None)
    def validate(req):
        if not req or req.get('context')!=context:return None
        raw=req.get('inputs',{});out={k:str(raw[k]) for k in ('quantity','stop','target')};out['risk_pct']=float(raw['risk_pct']);out['seq']=int(raw['seq'])
        if not all(math.isfinite(float(out[k])) for k in ('quantity','stop','target','risk_pct')):raise RiskError('Некорректное число')
        out['budget_mode']=raw.get('budget_mode','notional')
        if out['budget_mode'] not in ('notional','total'):raise RiskError('Неверный режим суммы')
        out['input_mode']=raw.get('input_mode','quantity');out['budget']=str(raw.get('budget','25'))
        if out['input_mode'] not in ('quantity','amount') or not D(out['budget']).is_finite():raise RiskError('Некорректная сумма')
        prior=st.session_state.get('crypto_inputs',{})
        if prior.get('context')==context and out['seq']<prior['inputs']['seq']:return None
        st.session_state.crypto_inputs={'context':context,'inputs':out};return out
    def receive():
        try:validate(read_event('request'))
        except (ValueError,KeyError,TypeError) as e:st.session_state.crypto_notice=str(e)
    def action():
        try:
            req=read_event('action')
            if not req or req.get('context')!=context:return
            gateway=OrderPreview(store);owner=st.session_state.crypto_owner
            if req.get('stage')=='cancel':
                gateway.cancel(req['id'],owner);st.session_state.pop('crypto_pending',None);return
            if mode!='Paper Trading':raise RiskError('Выберите режим Paper Trading')
            _,latest,latest_rules=collect(store,symbol,interval)
            if req.get('stage')=='confirm_protection':
                changed=ProtectionPreview(store).confirm(req['id'],owner,latest,latest_rules,req.get('ack') is True)
                st.session_state.crypto_notice='LOCAL PAPER · '+changed['status']+' · Stop/Target сохранены'
                st.session_state.pop('crypto_pending',None)
            elif req.get('stage')=='prepare_protection':
                checked=validate(req)
                if checked is None:return
                st.session_state.crypto_pending=ProtectionPreview(store).prepare({'id':req['id'],'symbol':symbol,**checked},latest,latest_rules,owner)
            elif req.get('stage')=='confirm':
                order=gateway.confirm(req['id'],owner,latest,latest_rules,req.get('ack') is True)
                st.session_state.crypto_notice='LOCAL PAPER · '+order['status']+(' · '+order['error'] if order.get('error') else '')
                st.session_state.pop('crypto_pending',None)
            elif req.get('stage')=='prepare':
                checked=validate(req)
                if checked is None:return
                st.session_state.crypto_pending=gateway.prepare({'id':req['id'],'symbol':symbol,'side':req['side'],'dispose_sellable':req.get('dispose_sellable') is True,'timeframe':interval,'signal_id':req.get('signal_id'),'notes':req.get('notes',''),**checked},latest,latest_rules,owner)
                st.session_state.crypto_notice='Предпросмотр создан. Заявка ещё не исполнена.'
            else:raise RiskError('Требуется Prepare → Confirm')
        except (ValueError,KeyError,TypeError,ArithmeticError) as e:
            st.session_state.crypto_notice=str(e)
            if st.session_state.get('crypto_pending'):st.session_state.crypto_pending['error']=str(e)
    def preferences():
        try:save_preferences(store,read_event('preferences'))
        except (ValueError,TypeError) as exc:st.session_state.crypto_notice=str(exc)
    component()(key=key,data=d,on_request_change=receive,on_action_change=action,on_preferences_change=preferences)
    if mode=='Paper Trading' and symbol in state['positions']:
        with st.expander('Полное закрытие / старые остатки'):
            held=state['positions'][symbol];allocation=allocations.get(symbol)
            st.caption('Фактический остаток '+held['qty']+' '+symbol+'. Продажа доступного количества оставляет дробную часть и её себестоимость в портфеле.')
            if allocation:
                st.write({'Доступно для одной продажи':allocation['sellable_quantity'],'Неторгуемый остаток':allocation['non_sellable_residue'],'Стоимость остатка по Bid':allocation['residue_value'],'Себестоимость остатка':allocation['residue_basis'],'Нереализованный P&L остатка':allocation['residue_unrealized']})
            if allocation and D(allocation['sellable_quantity'])==0:
                st.warning('Нет доступного для продажи количества. Учётное списание ниже — убыток с нулевым денежным поступлением, не биржевая продажа.')
                expected=position_revision(held)
                consent=st.checkbox('Списать весь остаток в убыток без возврата денег',key='dust_consent_'+symbol+'_'+expected)
                if st.button('Учётное списание · не продажа',disabled=not consent,key='writeoff_'+symbol):
                    try:
                        _,fresh_quotes,fresh_rules=collect(store,symbol,interval)
                        paper.write_off_dust(symbol,str(uuid.uuid4()),confirmed=True,expected_position=expected,quotes=fresh_quotes,rules=fresh_rules)
                        st.rerun(scope='fragment')
                    except (ValueError,ArithmeticError) as exc:st.error(str(exc))
    with st.expander('Что ограничивает размер Paper-заявки'):
        if preview and preview.get('sizing_diagnostics'):
            diagnostics=preview['sizing_diagnostics']
            st.caption(diagnostics['note'])
            st.dataframe([{'Ограничение':row['label'],'Количество, не более':row['quantity_cap'],
                           'Определяет размер':row['code'] in diagnostics['binding_limits']}
                          for row in diagnostics['limits']],hide_index=True,width='stretch')
            st.write('Расчётное количество:',preview['recommended'])
            st.write('Minimum notional / quantity step / tick size:',
                     diagnostics['rules']['minimum_notional'],diagnostics['rules']['quantity_step'],diagnostics['rules']['price_tick'])
            st.write('Издержки полного круга:',diagnostics['costs']['round_trip_cost'])
            if not preview['allowed']:st.warning('; '.join(preview['errors']))
        else:
            st.info(error or 'Для расчёта нужны свежая котировка и правила инструмента.')
    with st.expander('Signal scan · полнота текущего инструмента'):
        st.caption('Проверяется только выбранный инструмент, не весь рынок. Сигнал отделён от разрешения на сделку.')
        if st.button('Проверить закрытые свечи',key='signal_scan_refresh'):
            from .signal_scan import scan_candidates
            report=scan_candidates({symbol:snap},[symbol],interval,now=time.time())
            st.session_state.signal_scan_report=(context,report)
        scanned=st.session_state.get('signal_scan_report')
        if scanned and scanned[0]==context:
            report=scanned[1]
            st.write(f"{report['status']} · проверено {report['scanned']} из {report['requested']} · исключено {report['excluded']}")
            st.caption('Срез UTC: '+str(report['cutoff'])+'. Результат последней ручной проверки; не обновляется автоматически.')
            if report['exclusions']:st.dataframe(report['exclusions'],hide_index=True,width='stretch')
            for candidate in report['candidates']:
                st.write(candidate['symbol'], '· закрытых свечей:',candidate['closed_bars'], '· исторических BUY/EXIT:',len(candidate['signals']))
            st.caption(report['note'])
    with st.expander('Security Center Preview · данные и защита'):
        from .risk import PROFILE
        st.write('Режим: '+mode+' · Live / Autonomous: технически отключены · withdraw API отсутствует')
        st.json(PROFILE)
        st.write('Лимит одного инструмента до 25% equity (12,5% при DD ≥8%); индивидуальный максимум также ограничен cash, занятостью и риском стопа.')
        st.write('Защита: '+protection.get('state','QA / Unknown')+' · последний успешный цикл: '+str(protection.get('last_success','не подтверждён')))
        st.caption('Loopback по умолчанию; XSRF и CORS включены. Права аккаунта не проверены до отдельной Read Only-проверки. Keychain/IP allowlist не реализованы.')
        st.json(snap.get('readiness',{}));st.write(protection['message'])
        st.json(paper.protection_status())
        st.dataframe(life['notifications'],hide_index=True,width='stretch')

