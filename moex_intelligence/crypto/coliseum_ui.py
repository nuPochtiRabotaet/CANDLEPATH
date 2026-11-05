"""Read-only saved research display plus explicit isolated offline job controls."""
import json
import gzip
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from scripts.coliseum_v02_cost_audit import analyze as cost_audit
from .coliseum_jobs import research_root,register_csv,start,pause,status,ROOT


def load_report(folder):
    folder=Path(folder)
    limit=100*1024*1024
    mpath=folder/'manifest.json';rpath=folder/'result.json'
    if not rpath.exists():rpath=folder/'result.json.gz'
    if mpath.stat().st_size>limit or rpath.stat().st_size>limit:raise ValueError('Report too large')
    m=json.loads(mpath.read_text())
    opener=gzip.open if rpath.suffix=='.gz' else open
    with opener(rpath,'rb') as stream:payload=stream.read(limit+1)
    if len(payload)>limit:raise ValueError('Expanded report too large')
    r=json.loads(payload)
    return m,r,cost_audit(m,r)

def page():
    st.title('Strategy Coliseum')
    st.caption('Офлайн-исследования. Результаты отдельных экспериментов — не единый портфель. Торговля не подключена.')
    committed=ROOT/'docs/research/coliseum_v02'
    saved=[committed]
    enriched=ROOT/'docs/research/coliseum_completed'
    if (enriched/'result.json').exists() or (enriched/'result.json.gz').exists():saved.insert(0,enriched)
    saved+=sorted(p.parent for p in research_root().glob('*/study/result.json'))
    selected=st.selectbox('Сохранённое исследование',saved,format_func=lambda p:'Архив '+p.name if 'docs' in p.parts else p.parent.name[:12])
    with st.expander('Запуск и возобновление офлайн-исследования'):
        st.caption('Фиксированные 100 кандидатов, три сценария издержек. CSV BTCUSDT 5m; последние 20% закрыты. Файл не подтверждает биржевое происхождение.')
        uploaded=st.file_uploader('История CSV',type=['csv'])
        if uploaded is not None and st.button('Проверить и зарегистрировать CSV'):
            try:
                folder,quality=register_csv(uploaded.getvalue());st.session_state.coliseum_job=str(folder);st.json(quality)
            except (ValueError,OSError,KeyError) as exc:st.error(str(exc))
        folders=sorted(p.parent for p in research_root().glob('*/source.csv'))
        if folders:
            job=st.selectbox('Локальное исследование',folders,format_func=lambda p:p.name[:12])
            a,b=st.columns(2)
            if a.button('Запустить / возобновить'):
                try:start(job)
                except (ValueError,OSError) as exc:st.error(str(exc))
            if b.button('Приостановить после текущего кандидата'):pause(job)
            state=status(job);st.progress(min(state['completed']/300,1.0),text=f"Завершено испытаний: {state['completed']}/300 · {'Выполняется' if state['running'] else 'Остановлено / завершено'}")
            st.button('Обновить прогресс')
            if state['log']:st.code(state['log'],language=None)
    try:m,r,audit=load_report(selected)
    except (OSError,ValueError,KeyError,TypeError) as exc:st.error('Исследование не прошло проверку целостности: '+str(exc));return
    stats=r.get('statistics',{});judged=r['judge'];paper=r['study']['results']['PAPER'];roster={c['id']:c for c in m['roster']}
    cols=st.columns(5)
    for col,label,value in zip(cols,['Кандидатов','Испытаний','Отклонено','Для независимой проверки','Независимо подтверждено'],
            [len(roster),sum(len(x) for x in r['study']['results'].values()),sum(not x['shortlisted'] for x in judged['standings']),judged['qualified_count'],0]):col.metric(label,value)
    st.info('Статистика: '+stats.get('status','NOT EXECUTED')+' · Источник: '+r['study']['source']+' · Holdout: SEALED, не оценивался')
    rows=[];ids=stats.get('candidate_ids',[]);groups=stats.get('dependence',{}).get('groups',[])
    for row in judged['standings']:
        cid=row['candidate_id'];metric=paper[cid];cost=audit['candidates']['PAPER'][cid]
        rows.append(dict(candidate=cid,family=roster[cid]['family'],net=float(metric['net_pnl']),gross=float(cost['gross_pnl']),
            drawdown=float(metric['max_drawdown']),trades=metric['trades'],group=str(groups[ids.index(cid)]) if groups else 'UNAVAILABLE',
            reasons=', '.join(row['rejection_reasons']),statistical_status=stats.get('status','NOT EXECUTED')))
    table=pd.DataFrame(rows);x,y,z=st.columns(3)
    family=x.multiselect('Семейства',sorted(table.family.unique()))
    mintrades=y.number_input('Минимум сделок',min_value=0,value=0)
    sort=z.selectbox('Сортировка',['net','gross','drawdown','trades','group'])
    maxdd=st.number_input('Максимальная просадка, %',min_value=0.,max_value=100.,value=100.)
    group_filter=st.multiselect('Корреляционная группа',sorted(table.group.unique()))
    status_filter=st.multiselect('Статистический статус',sorted(table.statistical_status.unique()))
    sign=st.selectbox('Прибыльность',['Все','Валовой > 0','Чистый > 0','Чистый ≤ 0'])
    view=table[(table.trades>=mintrades)&(table.drawdown<=maxdd)]
    if group_filter:view=view[view.group.isin(group_filter)]
    if status_filter:view=view[view.statistical_status.isin(status_filter)]
    if family:view=view[view.family.isin(family)]
    if sign=='Валовой > 0':view=view[view.gross>0]
    if sign=='Чистый > 0':view=view[view.net>0]
    if sign=='Чистый ≤ 0':view=view[view.net<=0]
    st.dataframe(view.sort_values(sort,ascending=sort in ('drawdown','group')),hide_index=True)
    st.plotly_chart(px.histogram(table,x='net',title='Распределение net P&L отдельных кандидатов, USDT'),width='stretch')
    cid=st.selectbox('Карточка стратегии',list(roster));spec=roster[cid];st.json(spec)
    comparison=[]
    for scenario in ('LOW','PAPER','STRESS'):
        cost=audit['candidates'][scenario][cid]
        comparison.append(dict(scenario=scenario,**{k:float(cost[k]) for k in ('gross_pnl','fee_cost','spread_cost','slippage_cost','net_pnl')}))
    comp=pd.DataFrame(comparison);st.dataframe(comp,hide_index=True)
    st.plotly_chart(px.bar(comp,x='scenario',y=['gross_pnl','fee_cost','spread_cost','slippage_cost','net_pnl'],barmode='group',title='Валовой P&L, модельные издержки и net'),width='stretch')
    st.write('Причины отклонения:',table.loc[table.candidate==cid,'reasons'].iloc[0])
    details=r.get('diagnostics',{}).get(cid)
    if details:
        day=pd.DataFrame(details['daily']);day['equity']=day.groupby('fold').net_pnl.transform(lambda s:10000+s.astype(float).cumsum())
        st.plotly_chart(px.line(day,x='day',y='equity',color=day.fold.astype(str),title='Дневной капитал: отдельные периоды с начальным капиталом 10 000'),width='stretch')
        regimes=pd.DataFrame([dict(regime=k,**v) for k,v in details['regimes'].items()]);regimes['net_pnl']=regimes.net_pnl.astype(float)
        st.plotly_chart(px.bar(regimes,x='regime',y='net_pnl',title='P&L сделок по режиму при входе; тренд и волатильность перекрываются'),width='stretch')
        st.caption(details['limitations'])
        st.caption(details.get('trade_details','Полный журнал сохранённого исследования'))
        trades=details['trades']
        key=digest([digest(m),spec['spec_sha256'],'PAPER']);trial=selected/(key+'.json')
        if trial.exists() and st.checkbox('Открыть полный журнал сделок'):
            envelope=json.loads(trial.read_text())
            if envelope.get('key')!=key or envelope.get('sha256')!=digest(envelope['result']):
                st.error('Повреждён журнал испытания');return
            trades=envelope['result']['diagnostics']['trades']
        st.dataframe(pd.DataFrame(trades),hide_index=True)
    else:st.info('Временные ряды, MFE/MAE и режимы отсутствуют в этом архиве; графики не восстановлены из сумм.')
    if groups:
        st.plotly_chart(px.imshow(stats['dependence']['correlation'],x=ids,y=ids,zmin=-1,zmax=1,color_continuous_scale='RdBu',title='Корреляции синхронных дневных результатов'),width='stretch')
        intervals=[]
        for test in stats['tests']:
            if 'lower' in test:
                i=ids.index(cid);intervals.append(dict(block=test['block'],mean=test['mean'][i],lower=test['lower'][i],upper=test['upper'][i],adjusted_p=test['adjusted_p'][i]))
        if intervals:
            f=pd.DataFrame(intervals);f['plus']=f.upper-f['mean'];f['minus']=f['mean']-f.lower
            st.plotly_chart(px.scatter(f,x='block',y='mean',error_y='plus',error_y_minus='minus',title='Одновременные bootstrap-интервалы среднего дневного результата'),width='stretch');st.dataframe(f)
        else:st.warning('Недостаточно полных дней для блочных доверительных интервалов.')
    st.caption('Прошлые результаты и оценки издержек не доказывают торговое преимущество. Критерии не ослабляются для заполнения списка.')
    st.download_button('Экспорт результатов JSON',json.dumps(r,ensure_ascii=False),file_name='coliseum-result.json',mime='application/json')
