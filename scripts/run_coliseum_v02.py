"""Resumable fixed-roster experiment; no live accounts or automatic promotion."""
import csv, json, sys, time, platform, hashlib, os, resource
import numpy, pandas
from pathlib import Path
from decimal import Decimal as D
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moex_intelligence.crypto.coliseum_catalog import roster, digest, CandidateProvider, features, hypotheses
from moex_intelligence.crypto.paper_path_research import simulate_paper_paths
from moex_intelligence.crypto.costs import CostModel, FeeSchedule, ExecutionAssumptions
from moex_intelligence.crypto.forecast_evaluation import _closed_rows
from moex_intelligence.crypto.strategy_coliseum_research import select_coliseum_candidates
from moex_intelligence.crypto.coliseum_diagnostics import trade_diagnostics
from moex_intelligence.crypto.coliseum_data import load_history
from moex_intelligence.crypto.coliseum_statistics import assess

def summary(report):
    trades=[t for f in report['folds'] for t in f['trades']]; pnl=[D(t['net_pnl_quote']) for t in trades]
    gain=sum((x for x in pnl if x>0),D(0));loss=-sum((x for x in pnl if x<0),D(0));net=sum(pnl,D(0))
    return dict(trades=len(pnl),net_pnl=str(net),expectancy=str(net/len(pnl)) if pnl else None,
        profit_factor=str(gain/loss) if loss else None,win_rate=sum(x>0 for x in pnl)/len(pnl) if pnl else None,
        max_drawdown=max(float(f['marked_equity_guards']['max_marked_drawdown_pct']) for f in report['folds']),
        turnover_quote=str(sum((D(t['entry_total_debit'])+D(t['exit_net_credit']) for t in trades),D(0))),
        folds=[{k:f[k] for k in ('fold','trade_count','net_return_pct')} for f in report['folds']])

def run(source, destination):
    started=time.perf_counter(); out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    guard=json.loads((Path(__file__).resolve().parents[1]/'docs/research/original_holdout_guard.json').read_text())
    # The original full dataset keeps its established boundary; new/cropped inputs
    # must not turn its old holdout into development rows.
    rows,quality=load_history(source)
    if quality['sha256']!=guard['source_sha256']:
        rows,quality=load_history(source,protected_interval=guard['sealed_interval'])
    dev=len(rows)*80//100; candidates=roster()
    # Freeze before computing signals/outcomes. Changed source/code/config cannot resume into this directory.
    code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),*((Path(__file__).resolve().parents[1]/'moex_intelligence/crypto'/name) for name in ('coliseum_catalog.py','coliseum_statistics.py','coliseum_diagnostics.py','coliseum_data.py','strategy_coliseum_research.py','paper_path_research.py','paper_risk_research.py','paper_rules_research.py','costs.py','analysis.py','risk.py','forecast_walkforward.py','forecast_evaluation.py','forecast_baseline.py','signal_outcome_research.py','market.py')))}
    manifest=dict(source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),roster=candidates,
        code=code,python=platform.python_version(),numpy=numpy.__version__,pandas=pandas.__version__,rows=len(rows),development_end_exclusive=dev,
        quality=quality,protocol_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/'docs/COLISEUM_STATISTICAL_PROTOCOL.md').read_bytes()).hexdigest(),costs={'LOW':[.0005,2,4],'PAPER':[.001,5,4],'STRESS':[.002,10,8]},seed=0)
    mpath=out/'manifest.json'
    if mpath.exists():
        if json.loads(mpath.read_text())!=manifest:raise ValueError('Frozen experiment mismatch; no silent resume')
    else:mpath.write_text(json.dumps(manifest,sort_keys=True,indent=2))
    f=features(rows[:dev]);shared=(f,hypotheses(f));results={k:{} for k in manifest['costs']};failures=[]; diagnostics={}
    for candidate in candidates:
        if (out/'cancel.requested').exists():raise InterruptedError('Research paused; completed trials retained')
        provider=CandidateProvider(rows[:dev],candidate,shared)
        for scenario,(fee,slip,spread) in manifest['costs'].items():
            key=digest([digest(manifest),candidate['spec_sha256'],scenario]); path=out/(key+'.json')
            if path.exists():
                envelope=json.loads(path.read_text());result=envelope['result']
                if envelope.get('key')!=key or envelope['sha256']!=digest(result):raise ValueError('Corrupt cached result')
            else:
                try:
                    report=simulate_paper_paths(rows,'BTCUSDT','5',strategy=candidate['id'],research_signal_provider=provider,
                        cost_model=CostModel(FeeSchedule(taker=str(fee)),ExecutionAssumptions(str(slip))),assumed_spread_bps=spread,record_equity=True)
                    result=dict(status='COMPLETED',metrics=summary(report),diagnostics=trade_diagnostics(report,rows[:dev],CostModel(FeeSchedule(taker=str(fee)),ExecutionAssumptions(str(slip))),spread))
                except (ValueError,ArithmeticError) as exc:result=dict(status='FAILED',error=str(exc))
                tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(dict(key=key,result=result,sha256=digest(result)),sort_keys=True));os.replace(tmp,path)
            if result['status']=='COMPLETED':
                results[scenario][candidate['id']]=result['metrics']
                if scenario=='PAPER':diagnostics[candidate['id']]=result['diagnostics']
            else:failures.append(dict(candidate=candidate['id'],scenario=scenario,**result))
        print(candidate['id'],flush=True)
    study=dict(source_sha256=manifest['source_sha256'],source='USER_SUPPLIED_CSV_UNVERIFIED',rows=len(rows),
        development_end_exclusive=dev,sealed_final_evaluated=False,results=results)
    # Errors invalidate the entire tournament, not just losing participants.
    judged=select_coliseum_candidates(study,candidates) if not failures else dict(status='INVALID_INCOMPLETE_TOURNAMENT',qualified_count=0)
    statistics={'status':'INVALID_INCOMPLETE_TOURNAMENT'}
    if not failures:
        ids=[c['id'] for c in candidates]
        keys=[(d['fold'],d['day']) for d in diagnostics[ids[0]]['daily'] if d['complete']]
        aligned=[]
        for cid in ids:
            days={(d['fold'],d['day']):float(d['net_pnl'])/10000 for d in diagnostics[cid]['daily'] if d['complete']}
            if set(days)!=set(keys):raise ValueError('Unaligned daily paths')
            aligned.append([days[k] for k in keys])
        statistics=assess(numpy.array(aligned).T,[k[0] for k in keys]) if len(keys)>=2 else {'status':'INSUFFICIENT_SAMPLE'}
        statistics['candidate_ids']=ids
        # Refinement of existing judge, never a replacement or automatic promotion.
        allowed={ids[i] for i in statistics.get('stable_candidates',[])};groups=statistics.get('dependence',{}).get('groups',list(range(len(ids))))
        seen=set();selected=[]
        for row in judged['standings']:
            group=groups[ids.index(row['candidate_id'])]
            if row['shortlisted'] and row['candidate_id'] not in allowed:
                row['shortlisted']=False;row['rejection_reasons'].append('STATISTICAL_GATE')
            if row['shortlisted'] and group in seen:
                row['shortlisted']=False;row['rejection_reasons'].append('DEPENDENCE_GROUP_CAP')
            if row['shortlisted']:seen.add(group);selected.append(row['candidate_id'])
        judged['shortlisted_for_independent_validation']=selected;judged['qualified_count']=len(selected)
    result=dict(study=study,judge=judged,statistics=statistics,diagnostics=diagnostics,failures=failures,manifest_sha256=digest(manifest),
        independent_validation=False,multiple_testing_correction='SYNCHRONIZED_BLOCK_MAX_STATISTIC_EXPERIMENTAL',production_integrations=0)
    target=out/'result.json'
    if target.exists() and json.loads(target.read_text())!=result:raise ValueError('Nondeterministic replay')
    target.write_text(json.dumps(result,indent=2,sort_keys=True))
    print(json.dumps(dict(seconds=time.perf_counter()-started,qualified=judged['qualified_count'],failures=len(failures),peak_rss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,platform=sys.platform)))
    return result
if __name__=='__main__':
    import fcntl
    destination=Path(sys.argv[2]);destination.mkdir(parents=True,exist_ok=True)
    with (destination/'.writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run(*sys.argv[1:])

