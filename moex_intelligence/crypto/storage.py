"""SQLite storage for the isolated Local Paper ledger."""
from contextlib import closing
from hashlib import file_digest
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from .market import Candle, MarketError


SCHEMA_VERSION = 5
_BACKUP_SUFFIX = {1: ".before-v081", 2: ".before-v082", 3: ".before-rc2", 4: ".before-rc3"}
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS candles(symbol TEXT,interval TEXT,time INTEGER,body TEXT NOT NULL,PRIMARY KEY(symbol,interval,time))",
    "CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY,body TEXT NOT NULL,detected_at REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS paper(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL,body TEXT)",
    "CREATE TABLE IF NOT EXISTS protective(id TEXT PRIMARY KEY,body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS lifecycle(id TEXT PRIMARY KEY,body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,time REAL,body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS intents(id TEXT PRIMARY KEY,body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS equity_samples(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL NOT NULL,body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS ui_preferences(id TEXT PRIMARY KEY,body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY,published_at REAL NOT NULL,body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS forecast_outcomes(forecast_id TEXT,target_time INTEGER,body TEXT NOT NULL,PRIMARY KEY(forecast_id,target_time))",
    "CREATE TRIGGER IF NOT EXISTS forecasts_no_update BEFORE UPDATE ON forecasts BEGIN SELECT RAISE(ABORT,'immutable forecast'); END",
    "CREATE TRIGGER IF NOT EXISTS forecasts_no_delete BEFORE DELETE ON forecasts BEGIN SELECT RAISE(ABORT,'immutable forecast'); END",
    "CREATE TRIGGER IF NOT EXISTS outcomes_no_update BEFORE UPDATE ON forecast_outcomes BEGIN SELECT RAISE(ABORT,'immutable outcome'); END",
    "CREATE TRIGGER IF NOT EXISTS outcomes_no_delete BEFORE DELETE ON forecast_outcomes BEGIN SELECT RAISE(ABORT,'immutable outcome'); END",
)
_CORE_TABLES = {"paper", "orders", "events", "candles"}


def _verify_existing_backup(backup, snapshot):
    # Preserve the first backup. A retry can reuse the same standalone image,
    # but cannot silently accept a stale, damaged, or still-active database.
    if (backup.is_symlink() or not backup.is_file()
            or any(Path(str(backup) + ext).exists() for ext in ("-journal", "-wal"))):
        raise ValueError(f"Expected a standalone Crypto backup at {backup}")
    with backup.open("rb") as existing, open(snapshot, "rb") as fresh:
        if file_digest(existing, "sha256").digest() != file_digest(fresh, "sha256").digest():
            raise ValueError(f"Existing Crypto backup differs from the current ledger: {backup}")


def _backup_locked(path, version):
    backup = path.with_name(path.name + _BACKUP_SUFFIX[version])
    fd, name = tempfile.mkstemp(dir=path.parent)
    os.close(fd)
    try:
        # Use a separate reader: SQLite backup cannot copy from the connection
        # holding BEGIN IMMEDIATE. Its lock keeps this snapshot valid until DDL commits.
        uri = path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as source, closing(sqlite3.connect(name)) as dest:
            source.backup(dest)
            dest.execute("PRAGMA journal_mode=DELETE")
            if dest.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise sqlite3.DatabaseError("Crypto backup failed its SQLite integrity check")
        try:
            os.link(name, backup)
        except FileExistsError:
            _verify_existing_backup(backup, name)
        # Persist the published name before committing the new schema.
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        os.unlink(name)


def _version(db):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError("Crypto database is newer than this application")
    return version


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        # A normal connect enables WAL, which is itself a persistent mutation.
        # Identify the ledger and make the backup before changing journal mode.
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            version = _version(db)
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if version == 0:
                if existed or tables:
                    raise ValueError("Refusing to initialize an existing unversioned Crypto database")
            elif version not in (*_BACKUP_SUFFIX, SCHEMA_VERSION) or not _CORE_TABLES <= tables:
                raise ValueError("Unrecognized Crypto ledger schema")
            if version in _BACKUP_SUFFIX:
                _backup_locked(self.path, version)
            if version < SCHEMA_VERSION:
                for statement in _SCHEMA:
                    db.execute(statement)
                db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            if _version(db) != SCHEMA_VERSION:
                raise ValueError("Crypto ledger version changed; reopen the store")
            db.execute("PRAGMA journal_mode=WAL")
        except (ValueError, sqlite3.Error):
            db.close()
            raise
        return db

    def candles(self,symbol,interval):
        with self.connect() as db:return [Candle(**json.loads(r[0])) for r in db.execute('SELECT body FROM candles WHERE symbol=? AND interval=? ORDER BY time',(symbol,interval))]
    def save_candles(self,symbol,interval,rows):
        """Persist a batch without one SQLite read per candle.

        The immutable-closed-candle rule is checked against the database and
        against earlier rows *within the same batch*. A conflicting update
        aborts the transaction; pre-existing user data is never overwritten.
        Bounded IN queries avoid SQLite parameter-count limits.
        """
        from dataclasses import asdict
        items=list(rows)
        if not items:
            return
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing={}
            times=list(dict.fromkeys(c.time for c in items))
            for offset in range(0,len(times),400):
                batch=times[offset:offset+400]
                placeholders=','.join('?' for _ in batch)
                for stamp,body in db.execute(
                    f'SELECT time,body FROM candles WHERE symbol=? AND interval=? AND time IN ({placeholders})',
                    (symbol,interval,*batch)):
                    existing[stamp]=json.loads(body)
            changes=[]
            for c in items:
                previous=existing.get(c.time)
                if previous and previous['closed']:
                    if c.closed and Candle(**previous)!=c:
                        raise MarketError('Закрытая свеча в журнале неизменяема')
                    continue
                record=asdict(c)
                existing[c.time]=record
                changes.append((symbol,interval,c.time,json.dumps(record)))
            if changes:
                db.executemany('INSERT OR REPLACE INTO candles VALUES(?,?,?,?)',changes)
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
