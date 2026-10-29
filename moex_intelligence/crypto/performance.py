"""Read-only statistics from the complete ledger, with Decimal reconciliation.
Closed position != exit order. Gross is before fees, after spread/slippage.
MTM is sampled Bid equity, never a reconstructed or interpolated history.
"""
import json,time
from decimal import Decimal as D
from .risk import metrics


def record_equity(db,state,quotes,*,force=False,now=None):
    now=time.time() if now is None else now
    last=db.execute('SELECT time FROM equity_samples ORDER BY id DESC LIMIT 1').fetchone()
    if not force and last and now-last[0]<60:return
    m=metrics(state,quotes,now)
    value={'equity':m['equity_decimal'],'realized_equity':str(D(state['initial'])+D(state['realized'])),
           'cash':state['cash'],'unrealized':m['unrealized_decimal'],'complete':not m['missing_quotes'],
           'missing_quotes':m['missing_quotes'],'source':'observed Bid; future exit costs excluded'}
    db.execute('INSERT INTO equity_samples(time,body) VALUES(?,?)',(now,json.dumps(value)))


def statistics(trades):
    values=[D(t['net_pnl']) for t in trades];wins=[v for v in values if v>0];losses=[v for v in values if v<0]
    n=len(values);profit=sum(wins,D(0));loss=-sum(losses,D(0))
    rr=[D(t['realized_r']) for t in trades if t.get('realized_r') is not None]
    return {'closed_positions':n,'wins':len(wins),'losses':len(losses),'breakeven':n-len(wins)-len(losses),
        'win_rate':str(D(len(wins))/n) if n else None,'average_win':str(profit/len(wins)) if wins else None,
        'average_loss':str(-loss/len(losses)) if losses else None,'expectancy':str(sum(values,D(0))/n) if n else None,
        'profit_factor':str(profit/loss) if loss else None,'profit_factor_status':'defined' if loss else 'no losing positions' if n else 'no closed positions',
        'net_pnl':str(sum(values,D(0))),'average_holding_seconds':sum(t['duration_seconds'] for t in trades)/n if n else None,
        'average_realized_r':str(sum(rr,D(0))/len(rr)) if rr else None,'r_sample_count':len(rr)}


def build_report(state,orders,samples,*,start=None,end=None):
    """Aggregate full position lifetime before filtering by final exit UTC."""
    inside=lambda t:(start is None or t>=start) and (end is None or t<end)
    groups={};orphans=[];cash=D(state['initial']);realized=D(0);curve=[]
    filled=sorted((o for o in orders if o.get('status') in ('Filled','Written Off')),key=lambda o:(o['time'],o.get('id','')))
    fees=slippage=spread=D(0);unknown_costs=0
    for o in filled:
        vals=o.get('execution',{}).get('values',{})
        if inside(o['time']):
            fees+=D(o.get('fee','0'))
            if vals:
                slippage+=D(vals.get('slippage_cost','0'));spread+=D(vals.get('spread','0'))*D(o.get('quantity','0'))/2
            elif o['side']!='WRITE_OFF':unknown_costs+=1
        if 'cash_delta' in o:cash+=D(o['cash_delta'])
        if 'realized' in o:
            realized+=D(o['realized']);curve.append({'time':o['time'],'value':str(D(state['initial'])+realized),'order_id':o['id']})
        pid=o.get('position_id') or (o['symbol']+':'+o['id'] if o['side']=='BUY' else None)
        if o['side']=='BUY':
            if pid==o['id']:pid=o['symbol']+':'+pid
            groups[pid]={'buy':o,'exits':[]}
        elif pid in groups:groups[pid]['exits'].append(o)
        else:orphans.append(o['id'])
    closed=[];partial=[]
    open_ids={s+':'+str(p.get('position_id',p['opened'])) for s,p in state['positions'].items()}
    for pid,g in groups.items():
        b=g['buy'];exits=g['exits'];meta=b.get('trade_metadata',{})
        net_qty=D(b.get('execution',{}).get('values',{}).get('net_base',b['quantity']))
        disposed=sum((D(o['quantity']) for o in exits),D(0))
        if not exits or pid in open_ids or disposed!=net_qty:
            if exits:partial.append(pid)
            continue
        net=sum((D(o['realized']) for o in exits),D(0));fee=D(b.get('fee','0'))+sum((D(o.get('fee','0')) for o in exits),D(0));initial_risk=meta.get('initial_risk')
        closed.append({'position_id':pid,'symbol':b['symbol'],'opened_at':b['time'],'closed_at':exits[-1]['time'],
          'entry_price':b.get('fill'),'exit_price':str(sum((D(o.get('fill','0'))*D(o['quantity']) for o in exits),D(0))/net_qty),
          'net_quantity':str(net_qty),'exit_orders':len(exits),'net_pnl':str(net),'gross_pnl':str(net+fee),'fees':str(fee),
          'duration_seconds':max(0,exits[-1]['time']-b['time']),'strategy':meta.get('strategy') or 'Unknown / legacy','timeframe':meta.get('timeframe') or 'Unknown / legacy',
          'signal_id':meta.get('signal_id'),'signal_state_at_entry':meta.get('signal_state'),'signal_state_at_preview':meta.get('signal_state_at_preview'),
          'entry_reason':meta.get('entry_reason'),'notes':meta.get('notes'),'exit_reasons':[o.get('reason') for o in exits],
          'initial_risk':initial_risk,'planned_net_rr':meta.get('planned_net_rr'),
          'realized_r':str(net/D(initial_risk)) if initial_risk and D(initial_risk)>0 else None,
          'contains_writeoff':any(o['side']=='WRITE_OFF' for o in exits)})
    selected=[t for t in closed if inside(t['closed_at'])];grouped={}
    for t in selected:grouped.setdefault(t['strategy']+' · '+t['timeframe'],[]).append(t)
    observations=[p for p in samples if inside(p['time'])];peak=None;max_dd=D(0);previous=None;gaps=0
    for p in observations:
        if not p['complete']:previous=None;continue
        if previous and p['time']-previous>120:gaps+=1
        previous=p['time'];v=D(p['equity']);peak=v if peak is None else max(peak,v)
        if peak>0:max_dd=max(max_dd,(peak-v)/peak)
    return {'summary':statistics(selected),'trades':selected,'by_strategy_timeframe':{k:statistics(v) for k,v in grouped.items()},
        'total_order_count':len(orders),'filled_orders_in_period':sum(inside(o['time']) for o in filled),'partial_positions':len(partial),
        'fees_in_period':str(fees),'slippage_in_period':str(slippage),'half_spread_cost_in_period':str(spread),'unknown_cost_orders':unknown_costs,
        'realized_curve':[p for p in curve if inside(p['time'])],'observed_equity':observations,'sampled_max_drawdown':str(max_dd) if peak is not None else None,
        'mtm_gaps':gaps,'mtm_history_start':samples[0]['time'] if samples else None,'orphan_exit_orders':orphans,
        'realized_reconciles':realized==D(state['realized']),'cash_reconciles':cash==D(state['cash']) if all('cash_delta' in o for o in filled) else None,
        'history_note':'MTM starts with rc3 monitoring. Gaps not interpolated. Drawdown sampled, not continuous. Legacy metadata unknown.'}


def report(store,*,start=None,end=None):
    with store.connect() as db:
        db.execute('BEGIN')
        state=json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0])
        orders=[json.loads(r[0]) for r in db.execute('SELECT body FROM orders ORDER BY rowid')]
        samples=[{'time':r[0],**json.loads(r[1])} for r in db.execute('SELECT time,body FROM equity_samples ORDER BY id')]
    return build_report(state,orders,samples,start=start,end=end)
