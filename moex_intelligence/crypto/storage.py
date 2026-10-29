"""Isolated SQLite v1 schema; never opens or migrates the MOEX portfolio ledger."""
import json,sqlite3,time
from pathlib import Path
from .market import Candle,MarketError

class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version>5:raise ValueError('Crypto database is newer than this application')
            if version in (1,2,3,4):
                backup=self.path.with_name(self.path.name+('.before-v081' if version==1 else '.before-v082' if version==2 else '.before-rc2' if version==3 else '.before-rc3'))
                if not backup.exists():
                    import os,tempfile
                    fd,name=tempfile.mkstemp(dir=self.path.parent);os.close(fd)
                    try:
                        with sqlite3.connect(name) as dest:db.backup(dest)
                        try:os.link(name,backup)
                        except FileExistsError:pass
                    finally:os.unlink(name)
            db.executescript('''BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS candles(symbol TEXT,interval TEXT,time INTEGER,body TEXT NOT NULL,PRIMARY KEY(symbol,interval,time));
CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY,body TEXT NOT NULL,detected_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS paper(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL,body TEXT);
CREATE TABLE IF NOT EXISTS protective(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lifecycle(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,time REAL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS intents(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS equity_samples(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ui_preferences(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY,published_at REAL NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS forecast_outcomes(forecast_id TEXT,target_time INTEGER,body TEXT NOT NULL,PRIMARY KEY(forecast_id,target_time));
CREATE TRIGGER IF NOT EXISTS forecasts_no_update BEFORE UPDATE ON forecasts BEGIN SELECT RAISE(ABORT,'immutable forecast'); END;
CREATE TRIGGER IF NOT EXISTS forecasts_no_delete BEFORE DELETE ON forecasts BEGIN SELECT RAISE(ABORT,'immutable forecast'); END;
CREATE TRIGGER IF NOT EXISTS outcomes_no_update BEFORE UPDATE ON forecast_outcomes BEGIN SELECT RAISE(ABORT,'immutable outcome'); END;
CREATE TRIGGER IF NOT EXISTS outcomes_no_delete BEFORE DELETE ON forecast_outcomes BEGIN SELECT RAISE(ABORT,'immutable outcome'); END;
PRAGMA user_version=5;
COMMIT;''')
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.execute('PRAGMA journal_mode=WAL');return db
    def candles(self,symbol,interval):
        with self.connect() as db:return [Candle(**json.loads(r[0])) for r in db.execute('SELECT body FROM candles WHERE symbol=? AND interval=? ORDER BY time',(symbol,interval))]
    def save_candles(self,symbol,interval,rows):
        from dataclasses import asdict
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for c in rows:
                old=db.execute('SELECT body FROM candles WHERE symbol=? AND interval=? AND time=?',(symbol,interval,c.time)).fetchone()
                if old and json.loads(old[0])['closed']:
                    if c.closed and Candle(**json.loads(old[0]))!=c:raise MarketError('Закрытая свеча в журнале неизменяема')
                    continue
                db.execute('INSERT OR REPLACE INTO candles VALUES(?,?,?,?)',(symbol,interval,c.time,json.dumps(asdict(c))))
    def publish(self,signals):
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO signals VALUES(?,?,?)',[(s['id'],json.dumps(s,ensure_ascii=False,allow_nan=False),time.time()) for s in signals])
    def signals(self,symbol,interval):
        with self.connect() as db:
            rows=db.execute('SELECT body,detected_at FROM signals ORDER BY detected_at').fetchall()
        return [dict(json.loads(b),detected_at=t) for b,t in rows if json.loads(b)['symbol']==symbol and json.loads(b)['timeframe']==interval]
    def orders(self):
        with self.connect() as db:return [json.loads(r[0]) for r in db.execute('SELECT body FROM orders ORDER BY rowid DESC LIMIT 200')]
    def events(self):
        with self.connect() as db:return [{'time':r[0],**json.loads(r[1])} for r in db.execute('SELECT time,body FROM events ORDER BY id DESC LIMIT 200')]
