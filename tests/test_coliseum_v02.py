import json
import pytest
from moex_intelligence.crypto.coliseum_catalog import roster,features,hypotheses,CandidateProvider,digest
from moex_intelligence.crypto.paper_path_research import simulate_paper_paths
from .test_paper_path_research_v09 import history

def rows():
    from dataclasses import asdict
    return [asdict(x) for x in history(420)]

def test_roster_frozen_and_distinct():
    a=roster();assert a==roster() and len(a)==100
    assert len({x['idea'] for x in a})==50
    assert len({x['spec_sha256'] for x in a})==100
    assert all(digest(x['spec'])==x['spec_sha256'] for x in a)

@pytest.mark.parametrize('candidate',roster(),ids=lambda c:c['id'])
def test_causal_prefix_and_ids(candidate):
    data=rows();full=CandidateProvider(data,candidate);prefix=CandidateProvider(data[:200],candidate)
    a=full(data[:200],'BTCUSDT','5');b=prefix(data[:200],'BTCUSDT','5')
    assert a==b
    assert len({s['id'] for s in a})==len(a)
    assert all(s['timestamp']==s['candle_time']+300 for s in a)

def test_research_provider_rejects_foreign_prefix():
    data=rows();p=CandidateProvider(data,roster()[0]);bad=[dict(x) for x in data];bad[0]['close']+=1
    with pytest.raises(ValueError):p(bad,'BTCUSDT','5')

def test_batch_resume_and_corrupt_cache(tmp_path,monkeypatch):
    import csv
    from scripts import run_coliseum_v02 as runner
    source=tmp_path/'bars.csv';data=rows()
    with source.open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['timestamp_ms','open','high','low','close','volume']);writer.writeheader()
        for i,r in enumerate(data):writer.writerow(dict(timestamp_ms=1500000000000//300000*300000+i*300000,**{k:r[k] for k in ('open','high','low','close','volume')}))
    monkeypatch.setattr(runner,'roster',lambda:[x for x in roster() if x['idea']=='control_cash'])
    out=tmp_path/'run';a=runner.run(source,out);b=runner.run(source,out)
    assert a==b and a['judge']['qualified_count']==0 and not a['failures']
    assert all(m['trades']==0 for m in a['study']['results']['PAPER'].values())
    cache=next(p for p in out.glob('*.json') if len(p.stem)==64)
    envelope=json.loads(cache.read_text());envelope['key']='corrupt';cache.write_text(json.dumps(envelope))
    with pytest.raises(ValueError,match='Corrupt'):runner.run(source,out)
