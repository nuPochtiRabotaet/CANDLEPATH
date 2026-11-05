"""Performance-only synthetic trials through the existing Paper-path engine."""
import copy
import csv
import json
import resource
import sys
import time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_coliseum_v02 import run
from moex_intelligence.crypto.coliseum_catalog import roster, digest


def candidates(count):
    if count not in (100, 500, 2000):
        raise ValueError('Expected 100, 500 or 2000')
    base = roster()
    if count == 100:
        return base
    result = []
    for candidate in base:
        for hold in (8, 16, 24, 32, 64):
            for stop in ((2, 2.5, 3, 4) if count == 2000 else (2,)):
                c = copy.deepcopy(candidate)
                c['id'] += f'__hold{hold}_stop{stop}'
                c['spec'].update(max_hold_bars=hold, stop_atr=stop, target_atr=2*stop)
                c['spec_sha256'] = digest(c['spec'])
                result.append(c)
    return result


def fixture(path):
    rng = np.random.default_rng(135)
    close = 100*np.exp(np.cumsum(rng.normal(0, .002, 450)))
    volume = rng.uniform(100, 200, 450)
    with path.open('w') as f:
        w = csv.writer(f)
        w.writerow(['timestamp_ms','open','high','low','close','volume'])
        for i, c in enumerate(close):
            o = close[i-1] if i else 100.
            w.writerow([(1500000000//300*300+i*300)*1000, o, max(o,c)*1.002,
                        min(o,c)*.998, c, volume[i]])


if __name__ == '__main__':
    count = int(sys.argv[1]); root = Path(sys.argv[2]); root.mkdir(parents=True,exist_ok=True)
    destination = root/f'run-{count}'
    if destination.exists():
        raise SystemExit('Cold benchmark needs a new destination; existing evidence preserved')
    source = root/'synthetic.csv'; fixture(source)
    frozen = candidates(count)
    start = time.perf_counter()
    first = run(source, destination, candidates=frozen, source_kind='SYNTHETIC_FIXTURE')
    cold = time.perf_counter()-start; start = time.perf_counter()
    second = run(source, destination, candidates=frozen, source_kind='SYNTHETIC_FIXTURE')
    result = dict(candidates=count,bars=450,scenarios=3,cold_seconds=cold,
        warm_seconds=time.perf_counter()-start,peak_rss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        platform=sys.platform,failures=len(first['failures']),qualified=first['judge']['qualified_count'],
        same_result=first==second,source='SYNTHETIC_FIXTURE',not_economic_validation=True)
    assert result['same_result'] and not result['failures']
    (root/f'measurement-{count}.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
