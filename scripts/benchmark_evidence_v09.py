"""Synthetic recorder overhead, not exchange latency. No external source."""
import json
import statistics
import tempfile
import time
from pathlib import Path
from moex_intelligence.crypto.evidence import EvidenceRecorder


def main():
    results=[]
    with tempfile.TemporaryDirectory() as folder:
        r=EvidenceRecorder(Path(folder)/'synthetic.db',synthetic=True)
        seq=0
        for target in (300,3000):
            times=[]
            while seq<target:
                start=time.perf_counter()
                r.append('market_message',{'source':'SYNTHETIC_QA','message':{'ts':seq,'bid':'100','ask':'101'}},identity=str(seq),received_at=time.time(),event_at=time.time())
                times.append(time.perf_counter()-start);seq+=1
            status_start=time.perf_counter();r.status();status_ms=(time.perf_counter()-status_start)*1000
            results.append({'journal_events':target,'throughput_per_second':len(times)/sum(times),'median_append_ms':statistics.median(times)*1000,'p95_append_ms':sorted(times)[int(len(times)*.95)]*1000,'status_ms':status_ms,'database_bytes':r.path.stat().st_size})
        start=time.perf_counter();r.verify();integrity_ms=(time.perf_counter()-start)*1000
    print(json.dumps({'data':'SYNTHETIC_QA','measure':'synchronous FULL SQLite append overhead, not network latency','results':results,'integrity_scan_ms':integrity_ms},indent=2))
if __name__=='__main__':main()
