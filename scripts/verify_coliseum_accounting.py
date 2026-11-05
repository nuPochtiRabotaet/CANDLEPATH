"""Reconcile full trial journals with PR44 aggregates; no new backtest or tuning."""
import json,sys
from decimal import Decimal as D
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.coliseum_v02_cost_audit import analyze,digest


def verify(folder):
    folder=Path(folder)
    manifest=json.loads((folder/'manifest.json').read_text())
    result=json.loads((folder/'result.json').read_text())
    attribution=analyze(manifest,result)
    checked=0;largest=D(0)
    for scenario in manifest['costs']:
        for c in manifest['roster']:
            key=digest([digest(manifest),c['spec_sha256'],scenario])
            envelope=json.loads((folder/(key+'.json')).read_text())
            if envelope['key']!=key or envelope['sha256']!=digest(envelope['result']):
                raise ValueError('Corrupt trial journal')
            trades=envelope['result']['diagnostics']['trades']
            for field in ('gross_pnl','fee_cost','spread_cost','slippage_cost','net_pnl'):
                total=sum((D(t[field]) for t in trades),D(0))
                difference=abs(total-D(attribution['candidates'][scenario][c['id']][field]))
                largest=max(largest,difference)
                if difference>D('.000001'):raise ValueError('Trial/aggregate disagreement')
            for trade in trades:
                balance=D(trade['gross_pnl'])-sum(D(trade[f]) for f in ('fee_cost','spread_cost','slippage_cost'))
                if abs(balance-D(trade['net_pnl']))>D('1e-8'):raise ValueError('Trade cash conservation')
                checked+=1
    # Paired descriptive development results, not additional discoveries.
    pairs=[]
    for c in manifest['roster']:
        if c['spec']['variant']!='unfiltered':continue
        other=c['idea']+'__low_volatility'
        for scenario,bucket in result['study']['results'].items():
            a,b=bucket[c['id']],bucket[other]
            pairs.append(dict(idea=c['idea'],scenario=scenario,
                net_change=str(D(b['net_pnl'])-D(a['net_pnl'])),
                turnover_change=str(D(b['turnover_quote'])-D(a['turnover_quote'])),
                trade_change=b['trades']-a['trades']))
    statistics=result.get('statistics',{})
    return dict(status='TRADE_JOURNALS_RECONCILED_MODELED_EXECUTION',
        source_sha256=manifest['source_sha256'],manifest_sha256=digest(manifest),
        trades_checked_all_scenarios=checked,max_aggregate_rounding_difference=str(largest),
        summary=attribution['summary'],hypothesis_B_descriptive_pairs=pairs,
        baselines={s:{k:v for k,v in b.items() if k.startswith('control_')} for s,b in result['study']['results'].items()},
        statistical_status=statistics.get('status'),complete_daily_observations=statistics.get('observations'),
        dependence_groups=len(set(statistics.get('dependence',{}).get('groups',[]))),
        duplicate_pairs=len(statistics.get('dependence',{}).get('near_duplicates',[])),
        sealed_final_evaluated=False,independent_validation=False,
        limitations=['Costs and fills modeled, not observed exchange executions.',
            'Sums across independent candidate bankroll experiments are not a portfolio.',
            'Cost share is an accounting ratio, not causal proof of alpha without costs.',
            'Short already-examined unverified history: paired comparisons are diagnostic only.',
            'A longer holding and C timeframe comparison: NOT EXECUTED on historical data.'])

if __name__=='__main__':
    report=verify(sys.argv[1]);Path(sys.argv[2]).write_text(json.dumps(report,indent=2,sort_keys=True))
    print(json.dumps({k:v for k,v in report.items() if k not in ('hypothesis_B_descriptive_pairs','baselines')},indent=2))
