"""Synthetic sizing microbenchmark against the pinned integration base. No trading."""
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time
from moex_intelligence.crypto.paper import new_state
from moex_intelligence.crypto import risk
BASE='a0ca13d26cee204bf152ee20ef5bc8b1e7969e42'


def main():
    source=subprocess.check_output(['git','show',BASE+':moex_intelligence/crypto/risk.py'],text=True)
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)/'risk.py';p.write_text(source)
        spec=importlib.util.spec_from_file_location('moex_intelligence.crypto._risk_benchmark_base',p)
        baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
        state=new_state('10000');clock=time.time()
        quotes={'BTCUSDT':{'price':100,'bid':99.99,'ask':100.01,'ts':clock,'fresh':True}}
        rules={'step':'.001','tick':'.01','minimum':'5','maximum':'100','retrieved':clock}
        results={}
        for label,module in [('base',baseline),('explainable',risk)]:
            times=[]
            for _ in range(7):
                started=time.perf_counter()
                for _ in range(1000):module.plan(state,quotes,'BTCUSDT','1','97','106',rules,now=clock)
                times.append((time.perf_counter()-started)/1000)
            results[label]={'median_microseconds_per_plan':statistics.median(times)*1e6,'samples':7,'calls_per_sample':1000}
        print(json.dumps({'mode':'SYNTHETIC_MICROBENCHMARK','base_sha':BASE,'python':platform.python_version(),
            'platform':platform.platform(),'results':results,
            'note':'Same fixture and clock, sequential in one process; no market history or holdout read. Added diagnostics incur overhead; not an application throughput or financial result.'},indent=2))

if __name__=='__main__':main()
