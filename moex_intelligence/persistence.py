"""Local settings and immutable, versioned research snapshots; no API keys."""
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid


class ResearchStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS preferences (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS studies (id TEXT PRIMARY KEY, created TEXT NOT NULL, symbol TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL)')
    def connect(self):return sqlite3.connect(self.path,timeout=10)
    def preferences(self):
        with self.connect() as db: row=db.execute('SELECT body FROM preferences WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {}
    def save_preferences(self,value):
        allowed={'experience','goal','profile','onboarding_done','ui_mode','commission'}
        clean={k:v for k,v in value.items() if k in allowed}
        if 'commission' in clean:
            from .validation import finite
            c=clean['commission']
            if not isinstance(c,dict):raise ValueError('Invalid commission settings.')
            clean['commission']={'pct':finite(c.get('pct'),'commission pct',0,10),'minimum':finite(c.get('minimum',0),'minimum fee',0,1e9)}
        body=json.dumps(clean,ensure_ascii=False,allow_nan=False)
        if len(body)>10000:raise ValueError('Settings too large.')
        with self.connect() as db:db.execute('INSERT INTO preferences(id,body) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(body,))
    def save(self,result,frame):
        payload={'result':result,'history_csv':frame.to_csv()}
        body=json.dumps(payload,ensure_ascii=False,allow_nan=False,sort_keys=True)
        if len(body)>2_000_000:raise ValueError('Study snapshot exceeds 2 MB.')
        key=str(uuid.uuid4());digest=hashlib.sha256(body.encode()).hexdigest()
        with self.connect() as db:db.execute('INSERT INTO studies VALUES(?,?,?,?,?)',(key,result['computed_at_utc'],result['instrument']['symbol'],body,digest))
        return key
    def list(self,limit=50):
        with self.connect() as db:rows=db.execute('SELECT id,created,symbol FROM studies ORDER BY created DESC LIMIT ?', (max(1,min(int(limit),200)),)).fetchall()
        return [{'id':r[0],'created':r[1],'symbol':r[2]} for r in rows]
    def load(self,key):
        with self.connect() as db:row=db.execute('SELECT body,digest FROM studies WHERE id=?',(key,)).fetchone()
        if row is None:raise ValueError('Research not found.')
        if hashlib.sha256(row[0].encode()).hexdigest()!=row[1]:raise ValueError('Research snapshot integrity check failed.')
        return json.loads(row[0])
