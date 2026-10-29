"""Ledger analytics are opt-in and outside the one-second chart fragment."""
from datetime import datetime,timezone,timedelta
import streamlit as st
import plotly.graph_objects as go
from .performance import report
from .storage import Store

@st.cache_data(ttl=5,max_entries=8,show_spinner=False)
def snapshot(path,start,end):return report(Store(path),start=start,end=end)

def render(store):
    with st.expander('Trading Performance · полный журнал'):
        if not st.toggle('Показать аналитику журнала',key='performance_enabled'):return
        period=st.segmented_control('Период закрытия · UTC',['Всё','7 дней','30 дней','Период'],default='Всё',key='performance_period')
        now=datetime.now(timezone.utc);start=None;end=None
        if period in ('7 дней','30 дней'):start=(now-timedelta(days=7 if period=='7 дней' else 30)).timestamp()
        elif period=='Период':
            dates=st.date_input('Диапазон UTC',(now.date()-timedelta(days=7),now.date()),key='performance_dates')
            if len(dates)!=2:return
            start=datetime.combine(dates[0],datetime.min.time(),timezone.utc).timestamp();end=datetime.combine(dates[1]+timedelta(days=1),datetime.min.time(),timezone.utc).timestamp()
        if st.button('Обновить статистику',key='performance_refresh'):snapshot.clear()
        r=snapshot(str(store.path),start,end);s=r['summary'];fmt=lambda x:'—' if x is None else f'{float(x):,.2f}'
        for c,label,value in zip(st.columns(4),['Закрытые позиции','Net P&L · USDT','Win rate','Profit factor'],[s['closed_positions'],fmt(s['net_pnl']),fmt(float(s['win_rate'])*100)+'%' if s['win_rate'] is not None else '—',fmt(s['profit_factor'])]):c.metric(label,value)
        st.caption(f"Весь журнал: {r['total_order_count']} заявок. Исполнения/списания за период: {r['filled_orders_in_period']}. Частично закрытые позиции: {r['partial_positions']}. PF: {s['profit_factor_status']}. Локальная практика, не проверка статистического преимущества стратегии.")
        details={'Средняя прибыль':fmt(s['average_win']),'Средний убыток':fmt(s['average_loss']),'Expectancy':fmt(s['expectancy']),
          'Комиссии периода':fmt(r['fees_in_period']),'Slippage периода':fmt(r['slippage_in_period']),'½ spread по исполнениям':fmt(r['half_spread_cost_in_period']),
          'Средний фактический R':fmt(s['average_realized_r']),'Среднее удержание · сек':fmt(s['average_holding_seconds']),
          'Наблюдаемая MTM просадка':fmt(float(r['sampled_max_drawdown'])*100)+'%' if r['sampled_max_drawdown'] is not None else '—'}
        columns=st.columns(3)
        for index,(label,value) in enumerate(details.items()):columns[index%3].metric(label,value)
        if r['orphan_exit_orders'] or not r['realized_reconciles'] or r['cash_reconciles'] is not True:st.warning('История неполна или не сверяется с балансом. Неизвестные данные не заполняются предположениями.')
        if r['unknown_cost_orders']:st.caption('Для части старых исполнений нет детализации spread/slippage; показана только известная сумма.')
        fig=go.Figure()
        for name,points in [('Realized equity',r['realized_curve']),('Observed MTM equity',r['observed_equity'])]:
            x=[];y=[];previous=None
            for p in points:
                at=datetime.fromtimestamp(p['time'],timezone.utc)
                if name.startswith('Observed') and previous and p['time']-previous>120:x.append(at);y.append(None)
                x.append(at);y.append(float(p.get('equity',p.get('value'))) if p.get('complete',True) else None);previous=p['time']
            fig.add_trace(go.Scatter(x=x,y=y,name=name,mode='lines+markers',connectgaps=False,line_shape='hv' if name.startswith('Realized') else 'linear'))
        fig.update_layout(height=260,template='plotly_dark',margin=dict(l=15,r=15,t=15,b=15),yaxis_title='USDT',legend_orientation='h')
        st.plotly_chart(fig,width='stretch',key='performance_curve')
        st.caption('MTM записывается раз в минуту и при исполнении начиная с rc3. Пробелы не заполняются. Gross до комиссий, после spread/slippage; Net уже учитывает издержки — повторно их не вычитаем.')
        st.dataframe(r['trades'],hide_index=True,width='stretch');st.dataframe([{'Стратегия / TF':k,**v} for k,v in r['by_strategy_timeframe'].items()],hide_index=True,width='stretch')
