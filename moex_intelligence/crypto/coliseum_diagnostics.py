"""Trade-level modeled accounting, bounded OHLC excursions and causal regimes."""
from decimal import Decimal as D
from collections import defaultdict
from .costs import estimate
from .paper_path_research import _quote_at
from .analysis import indicators

def trade_diagnostics(report, rows, model, spread):
    if model.fees.buy_currency!='quote' or model.fees.sell_currency!='quote':
        raise ValueError('Diagnostic attribution requires quote fees')
    frame=indicators(rows);lookup={r['time']:i for i,r in enumerate(rows)}
    ratio=frame.atr/frame.close;median=ratio.shift().rolling(100).median()
    details=[]
    for fold in report['folds']:
        for t in fold['trades']:
            i=lookup[t['entry_open_time']];j=lookup[t['exit_bar_open_time']]
            qty=D(t['base_quantity']);entry=D(str(rows[i]['open']));exit=D(t['exit_reference_price'])
            buy=estimate('BUY',qty,_quote_at(entry,spread),model);sell=estimate('SELL',qty,_quote_at(exit,spread),model)
            if abs(-buy.cash_delta-D(t['entry_total_debit']))>D('1e-8') or abs(sell.cash_delta-D(t['exit_net_credit']))>D('1e-8'):
                raise ValueError('Journal/cost model mismatch')
            gross=qty*(exit-entry);fees=buy.fee_quote_value+sell.fee_quote_value
            spread_cost=qty*(entry+exit)*D(str(spread))/20000
            slip=buy.slippage_cost+sell.slippage_cost;net=sell.cash_delta+buy.cash_delta
            if abs(gross-fees-spread_cost-slip-net)>D('1e-8') or abs(net-D(t['net_pnl_quote']))>D('1e-8'):
                raise ValueError('Trade accounting does not reconcile')
            # Exit bar extrema may happen AFTER a threshold fill: bounds, never exact MFE/MAE.
            known=rows[i:j];possible=rows[i:j+1] if t['exit_time_precision']=='BAR_CLOSE_AVAILABILITY' else known
            def excursion(bars):
                hi=max([float(entry),float(exit)]+[r['high'] for r in bars]);lo=min([float(entry),float(exit)]+[r['low'] for r in bars])
                return [(hi/float(entry)-1)*100,(lo/float(entry)-1)*100]
            r=frame.iloc[i-1];trend='Sideways' if r.adx<20 else ('Rising' if r.ema_fast>r.ema_slow else 'Falling')
            vol='High' if ratio.iloc[i-1]>median.iloc[i-1] else 'Low'
            details.append(dict(**t,fold=fold['fold'],entry_reference_price=str(entry),
                holding_seconds_upper=t['exit_event_time']-t['entry_open_time'],
                duration_precision=t['exit_time_precision'],gross_pnl=str(gross),fee_cost=str(fees),
                spread_cost=str(spread_cost),slippage_cost=str(slip),net_pnl=str(net),
                mfe_mae_completed_bars_pct=excursion(known),mfe_mae_possible_bounds_pct=excursion(possible),
                regime_at_entry=trend,volatility_at_entry=vol,
                provenance='MODELED_EXECUTION; OHLC_EXCURSION_BOUNDS; NOT_OBSERVED_FILLS'))
    regime={}
    for label in ('Rising','Falling','Sideways','High','Low'):
        selected=[t for t in details if label in (t['regime_at_entry'],t['volatility_at_entry'])]
        regime[label]=dict(trades=len(selected),net_pnl=str(sum((D(t['net_pnl']) for t in selected),D(0))))
    daily=[]
    for fold in report['folds']:
        previous=D(fold['starting_cash']);buckets=defaultdict(lambda:[D(0),0])
        for stamp,equity in fold['equity_marks']:
            day=(stamp-1)//86400;value=D(equity);buckets[day][0]+=value-previous;buckets[day][1]+=1;previous=value
        for day,(pnl,count) in sorted(buckets.items()):
            daily.append(dict(fold=fold['fold'],day=day,net_pnl=str(pnl),bars=count,complete=count==288))
        if abs(sum((v[0] for v in buckets.values()),D(0))-(D(fold['ending_cash'])-D(fold['starting_cash'])))>D('1e-8'):
            raise ValueError('Daily equity does not reconcile')
    return dict(trades=details,daily=daily,regimes=regime,
        observed='Input OHLCV only; source authenticity separate',modeled='Fees, spread, slippage, fills, stop/target',
        limitations='Exit-bar extrema and event time are bounds. High/Low relative to trailing 100-bar ATR median; not absolute risk.')
