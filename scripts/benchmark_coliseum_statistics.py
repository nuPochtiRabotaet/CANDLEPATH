"""Separate daily-inference throughput; not an OHLCV or alpha experiment."""
import json,sys,time,resource
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moex_intelligence.crypto.coliseum_statistics import assess

results=[]
for n in (100,500,2000):
    rng=np.random.default_rng(135);x=rng.normal(0,.001,(270,n))
    for i in range(1,len(x)):x[i]+=.4*x[i-1]
    start=time.perf_counter();r=assess(x,np.repeat([1,2,3],90))
    row=dict(candidates=n,days=270,replicates_per_block=1999,blocks=[3,7,14],
        seconds=time.perf_counter()-start,peak_rss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        source='SYNTHETIC_AR1_NULL',stable=len(r['stable_candidates']),statistically_validated=False)
    results.append(row);print(json.dumps(row),flush=True)
Path(sys.argv[1]).write_text(json.dumps(results,indent=2))
