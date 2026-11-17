"""Bounded append-only research evidence. No portfolio or execution capability."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


class EvidenceRecorder:
    def __init__(self,path,*,synthetic=False,max_events=100000,max_bytes=64*1024*1024):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.synthetic=synthetic;self.max_events=max_events;self.max_bytes=max_bytes
        self.error='';self.session=hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:16]
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS evidence(seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, body TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS evidence_kind ON evidence(json_extract(body,'$.kind'));
CREATE TRIGGER IF NOT EXISTS evidence_update BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS evidence_delete BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;''')
        self.verify()

    def connect(self):
        db=sqlite3.connect(self.path,timeout=.25)
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA wal_autocheckpoint=100')
        db.execute('PRAGMA max_page_count='+str(max(16,self.max_bytes//4096)))
        return db

    def verify(self):
        with self.connect() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Evidence integrity failure')
            previous=''
            for body,prior,digest in db.execute('SELECT body,previous,hash FROM evidence ORDER BY seq'):
                if prior!=previous or hashlib.sha256((prior+body).encode()).hexdigest()!=digest:
                    raise ValueError('Evidence chain failure')
                previous=digest

    def append(self,kind,payload,*,identity,received_at,event_at=None):
        processed_at=time.time()
        if not math.isfinite(received_at) or received_at<0:raise ValueError('Invalid receive clock')
        body=encoded({'kind':kind,'payload':payload,'received_at':received_at,'processed_at':processed_at,
            'event_at':event_at,'source_clock_delta_seconds':received_at-event_at if event_at is not None else None,
            'clock_uncertainty':'UNKNOWN: difference includes transport delay and clock skew',
            'session':self.session,'monotonic_at':time.monotonic(),'synthetic':self.synthetic,'verification':'UNVERIFIED'})
        if len(body.encode())>65536:raise ValueError('Evidence payload too large')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM evidence WHERE id=?',(identity,)).fetchone():return False
            if db.execute('SELECT count(*) FROM evidence').fetchone()[0]>=self.max_events:raise ValueError('Evidence capacity reached; recording stopped, archive explicitly')
            last=db.execute('SELECT body FROM evidence ORDER BY seq DESC LIMIT 1').fetchone()
            record=json.loads(body)
            record['clock_regressed']=bool(last and received_at<json.loads(last[0])['received_at'])
            body=encoded(record)
            old=db.execute('SELECT hash FROM evidence ORDER BY seq DESC LIMIT 1').fetchone()
            prior=old[0] if old else '';digest=hashlib.sha256((prior+body).encode()).hexdigest()
            db.execute('INSERT INTO evidence(id,body,previous,hash) VALUES(?,?,?,?)',(identity,body,prior,digest))
        return True

    def replay(self,*,as_of,limit=1000,after=0):
        if not 1<=limit<=10000:raise ValueError('Invalid page size')
        # Pagination is by append sequence, never by exchange timestamp. Late
        # packets remain late. Include neither unreceived nor unprocessed facts.
        with self.connect() as db:
            rows=db.execute('SELECT seq,body FROM evidence WHERE seq>? ORDER BY seq LIMIT ?',(after,limit)).fetchall()
        if any(json.loads(body).get('clock_regressed') for _,body in rows):
            raise ValueError('Wall clock regressed; timestamp replay is not causally evaluable')
        return [{'seq':seq,**json.loads(body)} for seq,body in rows
                if max(json.loads(body)['received_at'],json.loads(body)['processed_at'])<=as_of]

    def status(self):
        with self.connect() as db:
            count=db.execute('SELECT count(*) FROM evidence').fetchone()[0]
            row=db.execute("SELECT body FROM evidence WHERE json_extract(body,'$.kind')='market_message' ORDER BY seq DESC LIMIT 1").fetchone()
            rejected=db.execute("SELECT count(*) FROM evidence WHERE json_extract(body,'$.kind')='rejected'").fetchone()[0]
            gaps=db.execute("SELECT count(*) FROM evidence WHERE json_extract(body,'$.kind')='source_status' AND (body LIKE '%пропуск%' OR body LIKE '%gap%')").fetchone()[0]
            quote=db.execute("SELECT body FROM evidence WHERE json_extract(body,'$.kind')='processing_result' ORDER BY seq DESC LIMIT 1").fetchone()
        last=json.loads(row[0]) if row else None
        return {'status':'BLOCKED' if self.error or count>=self.max_events else 'UNVERIFIED',
            'error':self.error,'events':count,'rejected_events':rejected,'reported_gaps':gaps,
            'bid_ask':json.loads(quote[0])['payload'].get('quote',{}) if quote else None,'last_received_at':last['received_at'] if last else None,
            'age_seconds':time.time()-last['received_at'] if last else None,
            'abc':'NOT EVALUABLE WITH AVAILABLE DATA',
            'note':'Observed messages, not tick tape; source timing/coverage not independently verified.'}
