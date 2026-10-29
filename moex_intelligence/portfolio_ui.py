"""Existing Streamlit styling, thin UI for portfolio services. No financial math here."""
import asyncio
from datetime import date
import hashlib
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from .design import TOKENS
from .config import Settings
from .data import get_engine, market_today
from .portfolio import PortfolioStore, ledger_state, portfolio_curve, stress_test
from .portfolio_service import fetch_marks, value_portfolio, opening_event, resolve_symbols
from . import portfolio_import as importer
from .dashboard import chart, line_figure

LABELS={'deposit':'Пополнение','withdrawal':'Вывод денег','buy':'Покупка','sell':'Продажа',
        'dividend':'Дивиденд','coupon':'Купон','opening':'Начальные остатки'}
FIELD_LABELS={'date':'Дата','kind':'Операция','symbol':'Тикер','quantity':'Количество бумаг','price':'Цена за бумагу, ₽',
              'amount':'Сумма, ₽','fee':'Комиссия, ₽','currency':'Валюта','source':'Источник','external_id':'Номер операции'}


def user_error(exc):
    text=str(exc)
    if text.startswith('Insufficient cash on '):return 'После этого действия не хватает денег на '+text.split(' on ',1)[1].split(';',1)[0]+'. Проверьте предшествующие пополнения и покупки. Изменения не сохранены.'
    if 'cannot sell more units than held' in text:return text.split(':',1)[0]+': после изменения продаётся больше бумаг, чем есть. Проверьте последующие продажи. Изменения не сохранены.'
    if text.startswith('Dividend/coupon requires'):return 'Для дивиденда или купона укажите документ и дату выплаты.'
    if text.startswith('Invalid ticker'):return 'Укажите тикер MOEX либо найдите бумагу по названию или ISIN.'
    return text


def portfolio_store(): return PortfolioStore(Settings.from_env().data_dir/'portfolio.sqlite3')


MARKET_TIMEOUT_SECONDS=10


@st.cache_data(ttl=60,max_entries=32,show_spinner=False)
def _market_marks(symbols,data_dir):
    from .lab_data import load_asset,QuoteSnapshots
    async def load():
        semaphore=asyncio.Semaphore(4)
        async def one(symbol):
            cache=QuoteSnapshots(data_dir+'/market_snapshots')
            try:
                async with asyncio.timeout(MARKET_TIMEOUT_SECONDS):
                    async with semaphore:return symbol,await load_asset(symbol,cache)
            except TimeoutError:
                return symbol,{'asset':cache.load(symbol),'error':'Пакет котировок не завершён за отведённое время.'}
        return await asyncio.gather(*(one(s) for s in symbols))
    if len(symbols)>100:raise ValueError('Не более 100 открытых позиций.')
    results=asyncio.run(load());marks={};errors={};warnings={}
    for symbol,result in results:
        if result['asset']:
            asset=result['asset'];marks[symbol]={**asset['mark'],'saved_snapshot':asset.get('saved_snapshot',False),'manual':asset.get('manual',False),'demo_data':asset.get('demo_data',False),'market_observed_at':asset.get('observed_at'),'price_type':asset.get('price_type')}
            if result.get('error'):warnings[symbol]=result['error']
        else:errors[symbol]=result.get('error') or 'Нет цены.'
    return {'marks':marks,'errors':errors,'warnings':warnings}


def market_marks(symbols):return _market_marks(symbols,str(Settings.from_env().data_dir))
market_marks.clear=_market_marks.clear


def current_portfolio():
    db=portfolio_store();bundle=db.bundle();events=[r['event'] for r in bundle['records']]
    symbols=tuple(sorted(ledger_state(events)['positions']))
    market=market_marks(symbols) if symbols else {'marks':{},'errors':{}}
    result=value_portfolio(events,market);result['market']=market
    return db,bundle,result


def changed(message):
    st.session_state.portfolio_flash=message
    st.session_state.pop('portfolio_import_preview',None)
    for key in list(st.session_state):
        if key.startswith('portfolio_edit_context'):st.session_state.pop(key,None)
    # An old Advisor result must not look current after the ledger changes.
    st.session_state.pop('advisor_result',None)
    st.rerun()


def open_research(symbol,page):
    st.session_state.portfolio_selected_symbol=symbol
    st.session_state.symbol=symbol
    st.session_state.page='Laboratory'
    st.session_state.research_asset_query=symbol
    st.session_state.pop('research_asset_results',None);st.session_state.pop('research_asset_selected',None)
    st.session_state.lab_picker_query=symbol
    st.session_state.pop('lab_picker_results',None)
    st.session_state.pop('lab_picker_selected',None)
    st.session_state.lab_open_existing=page!='buy'
    st.session_state.lab_mode='Оценить' if page=='evaluate' else 'Сценарии'
    st.session_state.pop('sandbox_request',None)
    st.session_state.show_settings=False
    st.session_state.pop('dataset',None)
    st.session_state.pop('advisor_result',None)


def rows_table(records):
    return pd.DataFrame([{'ID':r['id'][:8], 'Дата':r['event']['date'], 'Операция':LABELS[r['event']['kind']],
       'Тикер':r['event'].get('symbol',''), 'Количество':r['event'].get('quantity'), 'Цена, ₽':r['event'].get('price'),
       'Сумма, ₽':r['event'].get('amount'), 'Комиссия, ₽':r['event'].get('fee',0)} for r in records])


def show_summary(result):
    from .experience import portfolio_summary
    portfolio_summary(result)


def _picker_context(prefix):
    from moex import identifier
    options=st.session_state.get(prefix+'_results',[])
    selected=st.session_state.get(prefix+'_selected') if options else None
    candidate=(selected.get('secid') or selected.get('SECID')) if selected else st.session_state.get(prefix+'_query','')
    try:symbol=identifier(candidate)
    except ValueError:return
    st.session_state.symbol=symbol
    other='research_asset' if prefix=='lab_picker' else 'lab_picker'
    st.session_state[other+'_query']=symbol
    st.session_state.pop(other+'_results',None);st.session_state.pop(other+'_selected',None)


def instrument_picker(prefix,default='SBER',compact=False):
    if prefix+'_query' not in st.session_state:st.session_state[prefix+'_query']=default
    if compact:
        a,b=st.columns([5,1],vertical_alignment='bottom')
        q=a.text_input('Название, тикер или ISIN',value=None,key=prefix+'_query',on_change=_picker_context if prefix in {'lab_picker','research_asset'} else None,args=(prefix,))
        search=b.button('Найти',key=prefix+'_search',width='stretch')
    else:
        q=st.text_input('Название, тикер или ISIN',value=None,key=prefix+'_query',on_change=_picker_context if prefix in {'lab_picker','research_asset'} else None,args=(prefix,))
        search=st.button('Найти бумагу',key=prefix+'_search')
    if search:
        try:
            result=asyncio.run(get_engine().search(q,10))
            st.session_state[prefix+'_results']=[r for r in result['results'] if r.get('secid') or r.get('SECID')]
        except (ValueError,TypeError) as exc: st.error(user_error(exc))
    options=st.session_state.get(prefix+'_results',[])
    if options:
        selected=st.selectbox('Результаты MOEX',options,format_func=lambda r:f"{r.get('shortname') or r.get('SHORTNAME') or r.get('name','')} · {r.get('secid') or r.get('SECID')}",key=prefix+'_selected',on_change=_picker_context if prefix in {'lab_picker','research_asset'} else None,args=(prefix,))
        return selected.get('secid') or selected.get('SECID')
    return q.strip().upper()


def event_fields(prefix,kind,original=None,symbol=None):
    e=original or {};cols=st.columns(2)
    day=cols[0].date_input('Дата операции',date.fromisoformat(e['date']) if e else market_today(),key=prefix+'_date')
    fee=cols[1].number_input('Комиссия операции, ₽',0.,1e9,float(e.get('fee',0)),key=prefix+'_fee')
    event={'date':str(day),'kind':kind,'fee':fee}
    if kind in {'buy','sell','dividend','coupon'}:
        event['symbol']=symbol or st.text_input('Тикер',e.get('symbol','SBER'),key=prefix+'_symbol').strip().upper()
    if kind in {'buy','sell'}:
        a,b=st.columns(2)
        event['quantity']=a.number_input('Количество бумаг, не лотов',1,100000000,int(e.get('quantity',1)),key=prefix+'_qty')
        event['price']=b.number_input('Цена за бумагу, ₽',.00000001,1e12,float(e.get('price',300)),format='%.6f',key=prefix+'_price')
        st.caption('Для облигаций: полная цена в рублях за одну бумагу, включая НКД. Проценты номинала сюда вводить нельзя.')
    else:
        event['amount']=st.number_input('Сумма, ₽',.01,1e12,float(e.get('amount',19000)),key=prefix+'_amount')
    if kind in {'dividend','coupon'}:
        event['source']=st.text_input('Документ и дата выплаты',e.get('source',''),key=prefix+'_source')
    return event


def add_event(db,bundle):
    with st.expander('Добавить операцию',expanded=not bundle['records']):
        st.caption('Запись подтверждённой фактической операции. Для гипотетической покупки или продажи используйте лабораторию.')
        kind=st.selectbox('Операция',[k for k in LABELS if k!='opening'],format_func=LABELS.get,key='event_kind')
        symbol=instrument_picker('event_picker') if kind in {'buy','sell','dividend','coupon'} else None
        with st.form('ledger_form'):
            event=event_fields('event',kind,symbol=symbol)
            save=st.form_submit_button('Сохранить запись',type='primary')
        if save:
            try: db.append_many([event],expected_revision=bundle['revision']);changed('Операция добавлена. Портфель пересчитан.')
            except (ValueError,KeyError,TypeError) as exc: st.error(user_error(exc))


def correct_event(db,bundle,records,prefix='edit'):
    if not records:return
    ids=[r['id'] for r in records];by_id={r['id']:r['event'] for r in records}
    chosen=st.selectbox('Запись для исправления или удаления',ids,format_func=lambda i:f"{by_id[i]['date']} · {LABELS[by_id[i]['kind']]} · {by_id[i].get('symbol','')} · {i[:8]}",key=prefix+'_choice')
    context_key='portfolio_edit_context_'+prefix
    context=st.session_state.get(context_key)
    if not context or context['id']!=chosen:
        context={'id':chosen,'revision':bundle['revision'],'event':by_id[chosen]}
        st.session_state[context_key]=context
    if context['revision']!=bundle['revision']:
        st.warning('Журнал изменился после открытия формы. Обновите данные записи перед исправлением.')
        if st.button('Обновить форму',key=prefix+'_reload'):
            st.session_state.pop(context_key,None)
            for key in list(st.session_state):
                if key.startswith(prefix+'_'+chosen): del st.session_state[key]
            st.rerun()
        return
    original=context['event'];key=prefix+'_'+chosen
    corrected_kind=st.selectbox('Правильный тип операции',[k for k in LABELS if k!='opening'],
        index=[k for k in LABELS if k!='opening'].index(original['kind']),format_func=LABELS.get,key=key+'_kind') if original['kind']!='opening' else 'opening'
    st.caption('Исправление меняет ошибочную запись. Новая покупка или продажа при этом не создаётся. Удаление проверяет весь оставшийся журнал.')
    with st.form(key+'_form'):
        if original['kind']=='opening':
            day=st.date_input('Дата переноса',date.fromisoformat(original['date']),key=key+'_date')
            cash=st.number_input('Свободные деньги на дату переноса, ₽',0.,1e12,float(original['amount']),key=key+'_cash')
            edited=st.data_editor(pd.DataFrame(original['holdings'],columns=['symbol','quantity','price']),num_rows='dynamic',hide_index=True,key=key+'_holdings')
            replacement={'kind':'opening','date':str(day),'amount':cash,'holdings':edited.to_dict('records'),'fee':0}
            st.caption('quantity — целое количество бумаг, price — средняя учётная цена в рублях за бумагу.')
        else: replacement=event_fields(key,corrected_kind,original)
        save=st.form_submit_button('Сохранить исправление')
    if save:
        try:
            if replacement['kind']=='opening':
                for p in replacement['holdings']: p['quantity']=importer.quantity(p['quantity'])
            db.correct(chosen,replacement,expected_revision=context['revision'])
            st.session_state.pop(context_key,None);changed('Ошибочная запись исправлена. Портфель пересчитан.')
        except (ValueError,KeyError,TypeError) as exc: st.error(user_error(exc))
    confirm=st.checkbox('Это ошибочная запись — удалить её из журнала',key=key+'_confirm_delete')
    if st.button('Удалить ошибочную запись',disabled=not confirm,key=key+'_delete'):
        try:
            db.delete(chosen,expected_revision=context['revision'])
            st.session_state.pop(context_key,None);changed('Ошибочная запись удалена. Портфель пересчитан.')
        except ValueError as exc: st.error(user_error(exc))


def quick_transfer(db,bundle):
    st.subheader('Перенести текущие позиции')
    if bundle['records']:
        st.info('Быстрый перенос доступен для пустого журнала. Уже сохранённые начальные остатки можно исправить во вкладке «Операции». Накладывать второй остаток на существующие сделки нельзя.')
        return
    st.caption('Это начальные остатки, а не вымышленные покупки. Историческая доходность до переноса неизвестна.')
    symbol=instrument_picker('opening_picker')
    with st.form('opening_position'):
        a,b=st.columns(2)
        qty=a.number_input('Количество переносимых бумаг',1,100000000,1,key='opening_qty')
        price=b.number_input('Средняя цена покупки, ₽ за бумагу',.00000001,1e12,300.,format='%.6f',key='opening_price')
        add=st.form_submit_button('Добавить в список переноса')
    holdings=st.session_state.setdefault('opening_holdings',[])
    if add:
        try:
            candidate=holdings+[{'symbol':symbol,'quantity':qty,'price':price}]
            opening_event(market_today(),candidate,0)
            st.session_state.opening_holdings=candidate;st.rerun()
        except (ValueError,KeyError,TypeError) as exc: st.error(user_error(exc))
    holdings=st.session_state.opening_holdings
    if holdings:
        st.dataframe(pd.DataFrame(holdings).rename(columns={'symbol':'Тикер','quantity':'Количество','price':'Средняя цена, ₽'}),hide_index=True,width='stretch')
        remove=st.selectbox('Убрать из списка',range(len(holdings)),format_func=lambda i:holdings[i]['symbol'],key='opening_remove')
        if st.button('Убрать позицию',key='opening_remove_button'):
            st.session_state.opening_holdings=[p for i,p in enumerate(holdings) if i!=remove];st.rerun()
    with st.form('opening_save'):
        day=st.date_input('Дата переноса',market_today(),key='opening_day')
        cash=st.number_input('Свободные деньги, ₽',0.,1e12,0.,key='opening_cash')
        ack=st.checkbox('Проверены количество, средняя цена и деньги. Для облигаций указана цена с НКД.',key='opening_ack')
        save=st.form_submit_button('Сохранить начальные остатки')
    if save:
        if not ack: st.error('Проверьте и подтвердите начальные остатки.');return
        try:
            db.append_many([opening_event(day,holdings,cash)],expected_revision=bundle['revision'])
            st.session_state.opening_holdings=[];changed('Начальные остатки сохранены. Котировки и аналитика обновлены.')
        except (ValueError,KeyError,TypeError) as exc: st.error(user_error(exc))


def import_page(db,bundle):
    st.subheader('Импорт с предварительной проверкой')
    st.caption('CSV и XLSX: выберите лист, начало таблицы и сопоставьте колонки. JSON: восстановление нашего журнала в пустой счёт. PDF и старый XLS не поддерживаются. Все разделы сложного отчёта Альфы автоматически не объединяются; совместимость с вашим файлом ещё не подтверждена.')
    uploaded=st.file_uploader('Отчёт или журнал',type=['csv','xlsx','json'],key='portfolio_upload')
    if uploaded is None:return
    data=uploaded.getvalue();filename=uploaded.name
    events=[r['event'] for r in bundle['records']]
    try:
        is_json=filename.lower().endswith('.json')
        if is_json:
            if events: st.warning('Восстановление JSON возможно только в пустой счёт, чтобы не удвоить журнал.');return
            candidate_events=importer.preview_json(data)
            controls={'file':hashlib.sha256(data).hexdigest(),'json':True}
        else:
            tables=importer.read_tables(data,filename)
            sheet=st.selectbox('Лист таблицы',list(tables),key='import_sheet')
            grid=tables[sheet]
            st.dataframe(pd.DataFrame(grid[:12]).astype(str),hide_index=True,width='stretch')
            header=st.number_input('Номер строки с заголовками',1,max(1,len(grid)),1,key='import_header')
            columns,raw_rows=importer.table_rows(grid,header-1)
            mode=st.radio('Содержимое таблицы',['operations','positions'],format_func=lambda s:'Операции' if s=='operations' else 'Текущие позиции (начальные остатки)',key='import_mode')
            if mode=='positions' and events:st.warning('Начальные остатки можно импортировать только в пустой журнал.');return
            suggested=importer.infer_mapping(columns);mapping={}
            with st.expander('Сопоставление колонок',expanded=True):
                for field in importer.FIELDS:
                    options=['']+columns
                    mapping[field]=st.selectbox(FIELD_LABELS[field],options,index=options.index(suggested.get(field,'')),key='mapping_'+sheet+'_'+field,format_func=lambda c:c or 'Не задано')
            day=st.date_input('Дата начальных остатков',market_today(),key='import_opening_day') if mode=='positions' else None
            cash=st.number_input('Денежный остаток на эту дату, ₽',0.,1e12,0.,key='import_opening_cash') if mode=='positions' else 0
            st.caption('Количество — в бумагах, не лотах. Цена — рубли за бумагу; для облигаций полная цена с НКД. Пополнения/выводы должны быть отдельными строками. Остаток денег вычисляется из операций; итог из сложного отчёта не подставляется незаметно.')
            controls={'file':hashlib.sha256(data).hexdigest(),'sheet':sheet,'header':header,'mapping':mapping,'mode':mode,'day':str(day),'cash':cash}
        fingerprint=hashlib.sha256(json.dumps(controls,sort_keys=True).encode()).hexdigest()
        if st.button('Подготовить предпросмотр',key='import_preview'):
            if is_json:result={'json_events':candidate_events}
            else:
                raw_symbols=[str(row.get(mapping.get('symbol',''),'')).strip() for _,row in raw_rows]
                with st.spinner('Проверяю идентификаторы бумаг в MOEX…'):resolution=asyncio.run(resolve_symbols(raw_symbols))
                symbol_map={v:m['symbol'] for v,m in resolution['resolved'].items()}
                result=importer.preview(raw_rows,mapping,filename,data,events,db.imported_keys(),mode=mode,opening_date=day,opening_cash=cash,symbol_map=symbol_map)
                result['resolution']=resolution
            st.session_state.portfolio_import_preview={'fingerprint':fingerprint,'revision':bundle['revision'],'result':result}
        saved=st.session_state.get('portfolio_import_preview')
        if not saved or saved['fingerprint']!=fingerprint:return
        if saved['revision']!=bundle['revision']:
            st.warning('Журнал изменился. Подготовьте предпросмотр заново.');return
        result=saved['result'];exclude=[];possible=False
        if is_json: st.dataframe(pd.DataFrame(result['json_events']),hide_index=True,width='stretch')
        else:
            resolution=result.get('resolution',{'resolved':{},'errors':{}})
            if resolution['resolved']:
                st.dataframe(pd.DataFrame([{'В файле':v,'Тикер MOEX':m['symbol'],'Название':m['name']} for v,m in resolution['resolved'].items()]),hide_index=True,width='stretch')
            for value,error in resolution['errors'].items():st.warning(f'Идентификатор {value} не проверен: {error}. Сохранение допустимо только после самостоятельной проверки тикера.')
            st.dataframe(pd.DataFrame([{'Строка':c['line'],'Статус':'Уже импортирована' if c['duplicate'] else 'Возможный повтор' if c['possible_duplicate'] else 'Новая',**c['event']} for c in result['candidates']]),hide_index=True,width='stretch')
            for error in result['errors']:st.error(f"Строка {error['line']}: {error['error']}")
            for warning in result['warnings']:st.warning(warning)
            exclude=st.multiselect('Исключить строки из импорта',[c['line'] for c in result['candidates'] if not c['duplicate']],key='import_exclude')
            if any(c['possible_duplicate'] for c in result['candidates']):possible=st.checkbox('Возможные повторы проверены: выбранные строки являются отдельными реальными операциями',key='import_possible_ack')
        selected=None
        try:
            selected=result['json_events'] if is_json else importer.selected_events(result,exclude,possible)
            state=ledger_state(events+selected)
            st.write(f"После сохранения: {len(selected)} новых записей · денег {state['cash']:,.2f} ₽ · открытых позиций {len(state['positions'])}.")
            if state['positions']:st.dataframe(pd.DataFrame([{'Тикер':s,**p} for s,p in state['positions'].items()]),hide_index=True,width='stretch')
        except (ValueError,KeyError,TypeError) as exc:
            # The import engine deliberately rejects an empty write. In a preview
            # of already imported rows this is an informational UI state.
            if isinstance(exc,ValueError) and str(exc)=='Нет новых выбранных записей.':selected=[]
            else:st.error(user_error(exc));selected=None
        ack=st.checkbox('Проверены все операции, валюты, единицы цены и денежный остаток',key='import_ack')
        if selected==[]:st.info('Новых операций нет: распознанные записи уже импортированы либо исключены.')
        if st.button('Сохранить импорт',disabled=not ack or not selected,key='import_save'):
            db.append_many(selected,expected_revision=saved['revision']);changed('Импорт сохранён целиком. Портфель пересчитан.')
    except (ValueError,KeyError,TypeError,OverflowError) as exc:st.error(user_error(exc))


def analysis_page(events,result):
    snapshot=result['snapshot']
    if snapshot and snapshot['positions']:
        symbols=[p['symbol'] for p in snapshot['positions']]
        grouping=st.segmented_control('Структура портфеля',['По бумагам','По классам','По эмитентам','По отраслям'],default='По бумагам',key='portfolio_grouping') or 'По бумагам'
        marks=market_marks(tuple(sorted(symbols)))['marks']
        groups={};members={}
        field={'По эмитентам':'issuer','По отраслям':'sector'}.get(grouping)
        for p in snapshot['positions']:
            name=p['symbol'] if grouping=='По бумагам' else {'equity':'Акции','fund':'Фонды','bond':'Облигации'}.get(marks.get(p['symbol'],{}).get('asset_type'),'Класс неизвестен') if grouping=='По классам' else marks.get(p['symbol'],{}).get(field)
            if name:groups[name]=groups.get(name,0)+p['market_value'];members.setdefault(name,[]).append(p['symbol'])
        if field and sum(groups.values()) < sum(p['market_value'] for p in snapshot['positions'])-1e-7:
            st.info('Нет проверенной классификации '+('эмитентов' if field=='issuer' else 'отраслей')+' для всех позиций. Она не угадывается по названию. Выберите бумаги или классы. Сквозной состав фондов неизвестен.')
        else:
            groups['Деньги']=snapshot['cash']
            fig=go.Figure(go.Bar(x=list(groups.values()),y=list(groups),orientation='h',text=[f'{v/snapshot["equity"]:.1%}' if snapshot['equity'] else '0%' for v in groups.values()],textposition='auto',marker_color=TOKENS['accent']))
            selected=st.plotly_chart(chart(fig,280,'Категория'),width='stretch',on_select='rerun',selection_mode='points',key='portfolio_allocation')
            points=selected.selection.points
            if points:
                candidates=members.get(points[0].get('y'),[])
                if candidates:
                    selected_symbol=st.selectbox('Позиции категории',candidates,key='portfolio_group_members')
                    from .experience import asset_card
                    asset_card(selected_symbol,ledger_state(events)['positions'][selected_symbol]['quantity'],marks.get(selected_symbol),key='group_asset')
        shock=st.slider('Общий стресс цены активов, %',-100,100,-20,key='stress_shock')
        stressed=stress_test(snapshot,{s:shock for s in symbols})
        st.metric('Изменение при заданном стрессе',f"{stressed['change_rub']:+,.2f} ₽",f"{stressed['change_pct']:+.2f}%")
        weight=st.slider('Альтернатива: доля денег, %',0,100,50,key='alternative_cash')
        st.metric('При альтернативной доле денег',f"{snapshot['equity']*(1-weight/100)*shock/100:+,.2f} ₽")
        st.caption('Мгновенный заданный стресс, не прогноз. Деньги не меняются. Альтернатива сохраняет пропорции бумаг; издержки ребалансировки не включены.')
    with st.expander('Доходность и просадка по истории оценок'):
        st.caption('CSV: первая колонка date, остальные — тикеры с полной рублёвой ценой за бумагу. На каждую дату операции нужна строка. Пропуски не заполняются. При начальных остатках первый день задаёт рыночную базу: прибыли до переноса здесь нет.')
        uploaded=st.file_uploader('История оценок CSV',type=['csv'],key='valuations')
        if uploaded is not None:
            try:
                prices=pd.read_csv(uploaded,index_col=0,parse_dates=True)
                curve,stats=portfolio_curve(events,prices);st.json(stats)
                st.session_state.portfolio_valuation_history={'digest':hashlib.sha256(str(events).encode()).hexdigest(),'curve':curve,'stats':stats,'source':uploaded.name}
                st.plotly_chart(line_figure(curve,['unit_nav'],'Индекс доходности'),width='stretch')
            except (ValueError,KeyError,TypeError) as exc:st.error(user_error(exc))


def portfolio_page():
    st.title('Мой портфель')
    if st.session_state.get('portfolio_flash'):st.success(st.session_state.pop('portfolio_flash'))
    with st.spinner('Проверяю портфель и котировки…'):db,bundle,result=current_portfolio()
    events=[r['event'] for r in bundle['records']]
    show_summary(result)
    target=st.session_state.pop('portfolio_target_tab',None)
    if target:st.session_state.portfolio_active_tab=target
    positions,operations,payouts,analysis,imports=st.tabs(['Позиции','Операции','Выплаты','Анализ','Импорт'],key='portfolio_active_tab',on_change='rerun')
    with positions:
        state=result['state'];snapshot=result['snapshot']
        if state['positions']:
            from .positions_view import positions_list
            market=market_marks(tuple(sorted(state['positions'])))
            symbol,values=positions_list(state,snapshot,market['marks'],bundle['revision'])
            from .experience import asset_card
            from .formatting import price
            with st.container(key='position_detail'):
                mark=market['marks'].get(symbol)
                asset_card(symbol,state['positions'][symbol]['quantity'],mark,key='position',position=values.get(symbol))
                with st.expander('Учётная цена и операции позиции'):
                    held=state['positions'][symbol]
                    st.caption('Средняя учётная цена: '+price(held['cost_basis']/held['quantity'])+'. При переносе это введённая база, а не восстановленная история.')
                    own=[r for r in bundle['records'] if r['event'].get('symbol')==symbol or r['event']['kind']=='opening']
                    if own:st.dataframe(rows_table(own),hide_index=True,width='stretch')
        else:st.info('Открытых позиций нет. Добавьте операции или перенесите текущие бумаги.')
        with st.expander('Быстрый перенос без истории сделок'):quick_transfer(db,bundle)
    with operations:
        add_event(db,bundle)
        if bundle['records']:
            st.dataframe(rows_table(bundle['records']),hide_index=True,width='stretch')
            correct_event(db,bundle,bundle['records'])
            st.download_button('Экспорт журнала JSON',json.dumps(events,ensure_ascii=False,indent=2),file_name='virtual_portfolio.json',mime='application/json')
            with st.expander('История исправлений'):
                st.dataframe(pd.DataFrame(db.audit()),hide_index=True,width='stretch')
    with payouts:
        income=[r for r in bundle['records'] if r['event']['kind'] in {'dividend','coupon'}]
        if income:
            st.dataframe(rows_table(income),hide_index=True,width='stretch');correct_event(db,bundle,income,'income_edit')
        else:st.info('Выплат в журнале пока нет. Добавьте дивиденды или купоны во вкладке «Операции» либо импортируйте их из отчёта.')
        st.caption('Выплаты учитываются только по введённым документам. Будущие дивиденды, купоны и налоги автоматически не начисляются.')
    with analysis:
        with st.expander('Структура и ограничения портфеля'):
            if st.button('Проанализировать мой портфель',disabled=result['snapshot'] is None,key='portfolio_health'):
                st.session_state.health_revision=bundle['revision']
            if st.session_state.get('health_revision')==bundle['revision'] and result['snapshot'] is not None:
                from .lab_ui import show_health
                show_health(result['snapshot'])
        if analysis.open:analysis_page(events,result)
    with imports:
        if imports.open:import_page(db,bundle)
