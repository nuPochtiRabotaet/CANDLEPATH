import copy,time
from .test_crypto_v08 import candles
from .MOEX_v08_regression_tests import setup,quote
from moex_intelligence.crypto.lifecycle import SignalLifecycle,provisional
from moex_intelligence.crypto.analysis import analyze

def signal(t,kind='BUY'):
    return {'id':'signal-1','symbol':'BTCUSDT','timeframe':'15','strategy':'Trend Following','type':kind,'status':'confirmed','candle_time':t-900,'timestamp':t,'reference_price':100,'risk_estimates':{'stop':98,'target':105},'explanation':['test causal fixture']}

def test_lifecycle_potential_invalidate_reappear_confirm_expire(tmp_path):
    s,p,q,r=setup(tmp_path);engine=SignalLifecycle(s);now=time.time();sig=signal(now+30);potential={**sig,'status':'POTENTIAL'}
    def run(candidates,confirmed=(),t=now):return engine.update(list(confirmed),candidates,'BTCUSDT','15',q['BTCUSDT'],'Bullish',p.state(),r['BTCUSDT'],'1',now=t)
    a=run([potential]);assert a['active']['state']=='POTENTIAL';first=a['active']['first_seen'];assert not a['active']['confirmed_at']
    assert run([])['active']['state']=='INVALIDATED';a=run([potential]);assert a['active']['first_seen']==first
    assert len([n for n in a['notifications'] if n['state']=='POTENTIAL'])==1
    # It is impossible to confirm before the candle boundary.
    assert run([], [sig])['active']['confirmed_at'] is None
    q['BTCUSDT']['ts']=now+31
    a=run([], [sig],now+31);assert a['active']['state']=='ACTIONABLE';assert a['active']['confirmed_at']==now+31
    assert run([], [sig],now+1000)['active']['state']=='EXPIRED'
    assert SignalLifecycle(s).update([sig],[],'BTCUSDT','15',q['BTCUSDT'],'Bullish',p.state(),r['BTCUSDT'],'1',now=now+1001)['active']['confirmed_at']==now+31

def test_historical_stale_drift_and_risk(tmp_path):
    s,p,q,r=setup(tmp_path);e=SignalLifecycle(s);now=time.time();sig=signal(now)
    def run(t=now):return e.update([sig],[],'BTCUSDT','15',q['BTCUSDT'],'Bullish',p.state(),r['BTCUSDT'],'100',now=t)
    assert run()['active']['state']=='REJECTED_BY_RISK'
    q['BTCUSDT']['fresh']=False;assert run()['active']['state']=='CONFIRMED'
    q['BTCUSDT']=quote(102,101.9,102);a=run();assert a['active']['state']=='EXPIRED' and 'Opportunity Missed' in a['active']['reason']
    sig={**signal(now-300),'id':'historical'};a=run();assert not any(n['id'].startswith('historical') for n in a['notifications'])

def test_real_formula_potential_causal_and_no_history_rewrite():
    rows=candles();confirmed=analyze(rows,'BTCUSDT','15')['signals'];last=confirmed[-1]
    index=next(i for i,c in enumerate(rows) if c['time']==last['candle_time']);rows=rows[:index+1];rows[-1]['closed']=False
    before=copy.deepcopy(rows);candidates=provisional(rows,'BTCUSDT','15');assert candidates and candidates[-1]['status']=='POTENTIAL';assert rows==before
    assert last['id'] not in [s['id'] for s in analyze(rows,'BTCUSDT','15')['signals']]
