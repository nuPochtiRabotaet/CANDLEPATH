"""Deterministic synthetic local replay; engineering latency, never market alpha.

The baseline measures the original two full analysis passes (no UI/poll wait).
The new path measures Feed.receive including journal/lifecycle persistence.
Run from repo root. No network, portfolio, real history, or sealed data access.
"""
import copy
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_crypto_v08 import candles
from tests.test_intrabar_signals_v09 import message, records
from tests.test_market_feed_atomic_v09 import new_feed
from moex_intelligence.crypto.analysis import analyze
from moex_intelligence.crypto.market import Candle


def summarize(values):
    ordered=sorted(values)
    return {'samples':len(values),'median_ms':round(statistics.median(values),3),
            'p95_ms':round(ordered[int(.95*(len(ordered)-1))],3),'max_ms':round(max(values),3)}


def main():
    rows=candles(500);rows[-1]['closed']=False
    clock=[rows[-1]['time']+30];baseline=[];processing=[];indicators=[];lifecycle=[]
    with tempfile.TemporaryDirectory(prefix='candlepath-intrabar-') as directory,patch('time.time',lambda:clock[0]):
        feed=new_feed(Path(directory));feed.rows=[Candle(**r) for r in rows[:-1]]
        feed.store.save_candles(feed.symbol,feed.interval,feed.rows)
        feed._observe_signals(initial=True,received_at=clock[0])
        for i in range(100):
            clock[0]+=.1;rows[-1]['volume']+=1
            before=time.perf_counter()
            analyze(rows,'BTCUSDT','15')
            provisional=copy.deepcopy(rows);provisional[-1]['closed']=True
            analyze(provisional,'BTCUSDT','15')
            baseline.append((time.perf_counter()-before)*1000)
            feed.receive(message([rows[-1]],clock[0]))
            timing=feed.signal_timing
            processing.append(timing['processing_ms']);indicators.append(timing['indicators_ms'])
            lifecycle.append(timing['lifecycle_publish_ms'])
        assert feed.version==100
        assert not any(r['confirmed_at'] for r in records(feed.store).values() if r['candle_time']==rows[-1]['time'])
    return {'data':'SYNTHETIC FUNCTIONAL REPLAY; 500 bars, 100 ordered partial updates',
        'baseline_two_analysis_passes':summarize(baseline),
        'event_receive_to_publication':summarize(processing),
        'indicator_stage':summarize(indicators),'lifecycle_and_publication':summarize(lifecycle),
        'ui_refresh':'Existing 1s Streamlit fragment; scheduling/transfer/paint not measured locally',
        'network_latency':'NOT MEASURED; source-clock delta is not a pure network latency',
        'profitability':'NOT EVALUABLE WITH AVAILABLE DATA; synthetic updates cannot establish returns'}


if __name__=='__main__':print(json.dumps(main(),indent=2))
