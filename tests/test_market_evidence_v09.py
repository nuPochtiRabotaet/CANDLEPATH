"""Synthetic tape only. Tests never connect to market or open a user ledger."""
import json
import sqlite3
import subprocess
import sys
import time
import pytest
from moex_intelligence.crypto.evidence import EvidenceRecorder
from .test_intrabar_signals_v09 import fixture, message
from .test_market_feed_atomic_v09 import new_feed
from moex_intelligence.crypto.market import Candle, MarketError


def test_append_duplicate_restart_cutoff_and_integrity(tmp_path,monkeypatch):
    monkeypatch.setattr(time,'time',lambda:100.)
    r=EvidenceRecorder(tmp_path/'tape.db',synthetic=True)
    assert r.append('test',{'price':1},identity='x',received_at=99,event_at=98)
    assert not r.append('test',{'price':1},identity='x',received_at=100,event_at=98)
    assert r.replay(as_of=99)==[]
    assert r.replay(as_of=100)[0]['verification']=='UNVERIFIED'
    r=EvidenceRecorder(r.path,synthetic=True)
    assert not r.append('test',{},identity='x',received_at=100)
    with r.connect() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE evidence SET body='{}'")
    assert r.status()['abc']=='NOT EVALUABLE WITH AVAILABLE DATA'


def test_capacity_and_crash_rollback(tmp_path):
    path=tmp_path/'tape.db';r=EvidenceRecorder(path,synthetic=True,max_events=1)
    r.append('test',{},identity='1',received_at=time.time())
    with pytest.raises(ValueError,match='capacity'):r.append('test',{},identity='2',received_at=time.time())
    subprocess.run([sys.executable,'-c',"import sqlite3,os,sys;d=sqlite3.connect(sys.argv[1]);d.execute('BEGIN IMMEDIATE');d.execute(\"INSERT INTO evidence(id,body,previous,hash) VALUES('crash','{}','','bad')\");os._exit(7)",str(path)])
    recovered=EvidenceRecorder(path,synthetic=True);recovered.verify()
    assert len(recovered.replay(as_of=time.time()))==1


def test_hash_corruption_detected(tmp_path):
    r=EvidenceRecorder(tmp_path/'tape.db',synthetic=True)
    r.append('test',{},identity='1',received_at=time.time())
    with r.connect() as db:
        db.execute('DROP TRIGGER evidence_update');db.execute("UPDATE evidence SET body='{}'")
    with pytest.raises(ValueError,match='chain'):EvidenceRecorder(r.path,synthetic=True)


@pytest.mark.parametrize('kind',['BUY','EXIT'])
def test_feed_potential_received_invalidation_confirmation_and_no_paper(tmp_path,monkeypatch,kind):
    rows,sig=fixture(kind);clock=[rows[-1]['time']+30.25]
    monkeypatch.setattr(time,'time',lambda:clock[0])
    f=new_feed(tmp_path);f.evidence=EvidenceRecorder(tmp_path/'research'/'tape.db',synthetic=True)
    f.rows=[Candle(**r) for r in rows[:-1]]
    f.store.save_candles(f.symbol,f.interval,f.rows)
    first=message([rows[-1]],clock[0]);f.receive(first)
    tape=f.evidence.replay(as_of=clock[0]);assert tape[0]['kind']=='market_message'
    observations=[e for e in tape if e['kind']=='signal_observation']
    assert any(r['state']=='POTENTIAL' for r in observations[-1]['payload']['records'])
    count=len(tape);f.receive(first);assert len(f.evidence.replay(as_of=clock[0]))==count
    assert not f.evidence.replay(as_of=clock[0]-.01)
    clock[0]+=3;reverse=80 if kind=='BUY' else 120
    neutral={**rows[-1],'close':reverse,'high':max(rows[-1]['high'],reverse),'low':min(rows[-1]['low'],reverse),'volume':rows[-1]['volume']+1}
    f.receive(message([neutral],clock[0]))
    assert any(r['state']=='INVALIDATED' for e in f.evidence.replay(as_of=clock[0]) if e['kind']=='signal_observation' for r in e['payload']['records'])
    clock[0]=rows[-1]['time']+900+.25
    f.receive(message([{**rows[-1],'closed':True}],clock[0]))
    tape=f.evidence.replay(as_of=clock[0]);records=[r for e in tape if e['kind']=='signal_observation' for r in e['payload']['records']]
    assert any(r['state']=='CONFIRMED' and r['confirmed_at']>=rows[-1]['time']+900 for r in records)
    assert all(e['synthetic'] for e in tape)
    assert all(e['payload'].get('displayed_at') is None for e in tape)
    with f.store.connect() as db:
        assert db.execute('SELECT count(*) FROM paper').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM orders').fetchone()[0]==0
    # Late delivery stays in arrival order and cannot rewrite prior facts.
    before=tape[:];clock[0]+=1;late=message([rows[-1]],rows[-1]['time']+1);f.receive(late)
    after=f.evidence.replay(as_of=clock[0]);assert after[:len(before)]==before
    f.event('Connection Lost / gaps; reconnect required')
    assert f.evidence.replay(as_of=clock[0])[-1]['kind']=='source_status'


def test_rejected_gap_and_invalid_close_recorded(tmp_path,monkeypatch):
    rows,_=fixture();clock=rows[-1]['time']+30
    monkeypatch.setattr(time,'time',lambda:clock)
    f=new_feed(tmp_path);f.evidence=EvidenceRecorder(tmp_path/'tape.db',synthetic=True)
    with pytest.raises(MarketError):f.receive(message([{**rows[-1],'closed':True}],clock))
    tape=f.evidence.replay(as_of=clock)
    assert [e['kind'] for e in tape]==['market_message','rejected']
    assert not any(e['kind']=='signal_observation' for e in tape)


def test_clock_rollback_refuses_timestamp_replay(tmp_path,monkeypatch):
    clock=[100.];monkeypatch.setattr(time,'time',lambda:clock[0])
    r=EvidenceRecorder(tmp_path/'tape.db',synthetic=True)
    r.append('test',{},identity='a',received_at=100,event_at=105)
    clock[0]=90
    r.append('test',{},identity='b',received_at=90,event_at=106)
    r.verify()
    with pytest.raises(ValueError,match='clock regressed'):r.replay(as_of=100)
