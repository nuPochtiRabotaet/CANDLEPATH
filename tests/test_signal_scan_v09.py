import copy
import pytest
from moex_intelligence.crypto.signal_scan import scan_candidates
from tests.test_crypto_v08 import candles


def snapshot():
    rows=candles()
    return {'BTCUSDT':{'candles':rows}},rows[-1]['time']+900


def test_missing_candidate_is_not_a_complete_empty_scan():
    data,now=snapshot();r=scan_candidates(data,['BTCUSDT','ETHUSDT'],'15',now=now)
    assert (r['status'],r['requested'],r['scanned'],r['excluded'])==('PARTIAL',2,1,1)
    assert r['exclusion_counts']=={'MISSING_HISTORY':1}
    assert r['execution_authorized'] is False


def test_causal_prefix_and_no_forming_signal():
    data,now=snapshot();before=copy.deepcopy(data)
    r=scan_candidates(data,['BTCUSDT'],'15',now=now)
    future=copy.deepcopy(data['BTCUSDT']['candles'][-1]);future.update(time=now,closed=False,close=999999)
    data['BTCUSDT']['candles'].append(future)
    after=scan_candidates(data,['BTCUSDT'],'15',now=now)
    assert after['candidates']==r['candidates'] and after['forming_or_unavailable_bars']==1
    assert all(s['timestamp']<=now for s in after['candidates'][0]['signals'])
    assert before['BTCUSDT']['candles']==data['BTCUSDT']['candles'][:-1]


@pytest.mark.parametrize('defect',['gap','duplicate','nan','bad_ohlc','negative_volume','closed_flag','unclosed_history','identity'])
def test_invalid_history_is_explicitly_excluded(defect):
    data,now=snapshot();rows=data['BTCUSDT']['candles']
    if defect=='gap':rows.pop(100)
    elif defect=='duplicate':rows.insert(100,copy.deepcopy(rows[100]))
    elif defect=='nan':rows[100]['close']=float('nan')
    elif defect=='bad_ohlc':rows[100]['low']=1000000
    elif defect=='negative_volume':rows[100]['volume']=-1
    elif defect=='closed_flag':rows[100]['closed']='true'
    elif defect=='identity':data['BTCUSDT']['symbol']='ETHUSDT'
    else:rows[100]['closed']=False
    r=scan_candidates(data,['BTCUSDT'],'15',now=now)
    assert r['status']=='INCOMPLETE' and r['scanned']==0
    assert r['exclusion_counts']=={'INVALID_HISTORY':1}


def test_delayed_last_bar_is_not_known_at_close():
    data,now=snapshot();rows=data['BTCUSDT']['candles']
    rows[-1]['observed_at']=now+20;rows[-1]['available_at']=now+20
    r=scan_candidates(data,['BTCUSDT'],'15',now=now)
    assert r['candidates'][0]['closed_bars']==len(rows)-1
    assert all(s['timestamp']<now for s in r['candidates'][0]['signals'])


def test_short_stale_and_duplicate_universe():
    data,now=snapshot();short={'BTCUSDT':{'candles':data['BTCUSDT']['candles'][-20:]}}
    assert scan_candidates(short,['BTCUSDT'],'15',now=now)['exclusion_counts']=={'INSUFFICIENT_SAMPLE':1}
    assert scan_candidates(data,['BTCUSDT'],'15',now=now+2701)['exclusion_counts']=={'STALE_HISTORY':1}
    with pytest.raises(ValueError):scan_candidates(data,['BTCUSDT','BTCUSDT'],'15',now=now)
