"""Read-only fixed-parameter study; user CSV is never uploaded or modified."""
import csv, hashlib, json, sys
from pathlib import Path
from decimal import Decimal as D
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.paper_path_research import simulate_paper_paths, _quote_at
from moex_intelligence.crypto.costs import CostModel, FeeSchedule, ExecutionAssumptions, estimate
from moex_intelligence.crypto.signal_outcome_research import STRATEGIES

def summarize(report):
    trades=[t for f in report['folds'] for t in f['trades']]
    pnls=[D(t['net_pnl_quote']) for t in trades]
    wins=sum((p for p in pnls if p>0),D(0));loss=-sum((p for p in pnls if p<0),D(0))
    return dict(trades=len(trades),net_pnl=str(sum(pnls)),win_rate=sum(p>0 for p in pnls)/len(pnls) if pnls else None,
        expectancy=str(sum(pnls)/len(pnls)) if pnls else None,profit_factor=str(wins/loss) if loss else None,
        max_drawdown=max(float(f['marked_equity_guards']['max_marked_drawdown_pct']) for f in report['folds']),
        exits=dict(Counter(t['reason'] for t in trades)),folds=[{k:f[k] for k in ('fold','trade_count','net_return_pct')} for f in report['folds']])

def main(source,output):
    path=Path(source);rows=[]
    with path.open() as stream:
        for r in csv.DictReader(stream):
            stamp=r.get('open_time_ms',r.get('timestamp_ms'))
            if int(stamp)%300000:raise ValueError('Unaligned 5m candle')
            rows.append(Candle(int(stamp)//1000,*[float(r[k]) for k in ('open','high','low','close','volume')],True))
    results={};baselines={}
    for name,fee,slip in [('LOW','0.0005','2'),('PAPER','0.001','5'),('STRESS','0.002','10')]:
        model=CostModel(FeeSchedule(taker=fee),ExecutionAssumptions(slip))
        results[name]={}
        for strategy in STRATEGIES:
            report=simulate_paper_paths(rows,'BTCUSDT','5',strategy=strategy,cost_model=model,assumed_spread_bps=4)
            assert not report['final_holdout_evaluated']
            results[name][strategy]=summarize(report)
        # Passive reference only: same folds, 25% allocation, same costs, no stop.
        # Not risk-matched to active strategies; cash baseline is exactly zero.
        baseline=[]
        for f in report['folds']:
            start,end=f['start_index']+1,f['end_exclusive']
            unit=estimate('BUY',1,_quote_at(rows[start].open,4),model)
            qty=(D(2500)/-unit.cash_delta).quantize(D('.000001'),rounding='ROUND_FLOOR')
            buy=estimate('BUY',qty,_quote_at(rows[start].open,4),model)
            cash=D(10000)+buy.cash_delta;peak=D(10000);dd=D(0)
            for bar in rows[start:end]:
                for price in (bar.open,bar.close):
                    equity=cash+estimate('SELL',buy.net_base,_quote_at(price,4),model).cash_delta
                    peak=max(peak,equity);dd=max(dd,(peak-equity)/peak)
            baseline.append(dict(net_pnl=str(equity-10000),max_drawdown_pct=str(dd*100)))
        baselines[name]=baseline
    out=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source='USER_SUPPLIED_CSV_UNVERIFIED',
        rows=len(rows),development_end_exclusive=int(len(rows)*.8),sealed_final_evaluated=False,
        assumptions='Spread 4bps; per-side fee/slippage LOW 5/2, PAPER 10/5, STRESS 20/10 bps. Fixed, no tuning.',
        aggregation='Three separately capitalized 10000-USDT folds; net P&L summed, not compounded; DD is worst fold sampled liquidation DD.',
        results=results,passive_25pct_buy_hold=baselines,cash_baseline_net_pnl=0,
        limitations=['No observed bid/ask or historical symbol rules','Intrabar threshold fills optimistic; availability at close','One month / one instrument; no proven edge','Passive reference has no stop; not risk-matched'])
    with Path(output).open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False)
    print(json.dumps(out,indent=2))

if __name__=='__main__':main(*sys.argv[1:])
