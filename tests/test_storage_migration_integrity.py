"""BASE-02: reopen a populated rc2 ledger, including its uncheckpointed history."""
import errno
import json
import os
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from moex_intelligence.crypto import runtime
from moex_intelligence.crypto.orders import OrderPreview
from moex_intelligence.crypto.paper import Paper
from moex_intelligence.crypto.risk import metrics
from moex_intelligence.crypto.storage import Store

BUY = "00000000-0000-4000-8000-000000000001"
SELL = "00000000-0000-4000-8000-000000000002"
CLOSE = "00000000-0000-4000-8000-000000000003"
SYMBOL = "BTCUSDT"
NOW = 1_700_000_000

# rc2 tables only. In particular, these data predate equity_samples and forecasts.
V4_SCHEMA = """
CREATE TABLE candles(symbol TEXT,interval TEXT,time INTEGER,body TEXT NOT NULL,PRIMARY KEY(symbol,interval,time));
CREATE TABLE signals(id TEXT PRIMARY KEY,body TEXT NOT NULL,detected_at REAL NOT NULL);
CREATE TABLE paper(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE TABLE orders(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL,body TEXT);
CREATE TABLE protective(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE lifecycle(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE notifications(id TEXT PRIMARY KEY,time REAL,body TEXT NOT NULL);
CREATE TABLE intents(id TEXT PRIMARY KEY,body TEXT NOT NULL);
PRAGMA user_version=4;
"""


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / "crypto-v08.sqlite3"
    # Buy one BTC at 100 with a .001 BTC fee. Sell half the net quantity at
    # 120 with a .1% quote fee. At a later lot step of .001, .0005 is dust.
    position = dict(qty="0.4995", cost_basis="50", entry="100", entry_fee="0",
                    stop="97", target="130", position_id=BUY, opened=NOW)
    state = dict(initial="1000", cash="959.88006", realized="9.88006",
                 positions={SYMBOL: position}, peak="1020", day="2023-11-14",
                 week="2023-46", last_equity="1019.82006",
                 day_equity="1000", week_equity="1000")
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(V4_SCHEMA)
        db.execute("INSERT INTO paper VALUES(1,?)", (json.dumps(state),))
        for ident, side, qty, price, currency, fee, delta in [
            (BUY, "BUY", "1", "100", "base", "0.001", "-100"),
            (SELL, "SELL", "0.4995", "120", "quote", "0.05994", "59.88006"),
        ]:
            values = dict(fee_currency=currency, fee_quantity=fee, cash_delta=delta)
            order = dict(id=ident, status="Filled", side=side, symbol=SYMBOL, fill=price,
                         filled_quantity=qty, cash_delta=delta, execution={"values": values})
            if side == "SELL":
                order.update(allocated_basis="50", realized="9.88006")
            intent = dict(owner="fixture", id=ident, status="Filled",
                          request=dict(id=ident, side=side, symbol=SYMBOL))
            for table, body in [("orders", order), ("intents", intent)]:
                db.execute(f"INSERT INTO {table} VALUES(?,?)", (ident, json.dumps(body)))
            db.execute("INSERT INTO events(time,body) VALUES(?,?)", (NOW, json.dumps({"order": ident})))
        candle = dict(time=NOW, open=100, high=125, low=95, close=120, volume=5, closed=True)
        db.execute("INSERT INTO candles VALUES(?,?,?,?)", (SYMBOL, "15", NOW, json.dumps(candle)))
    return path


def snapshot(path):
    """Read all rows and their IDs in one snapshot, preserving historical JSON bytes."""
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        version = db.execute("PRAGMA user_version").fetchone()[0]
        tables = db.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()
        return version, {name: db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                         for name, in tables}


def backup_path(path):
    return path.with_name(path.name + ".before-rc3")


def test_wal_crash_migrate_restore_and_close_position(ledger, tmp_path, monkeypatch):
    # Exit without closing SQLite. A committed event lives in WAL, the cash
    # overwrite belongs to a different, uncommitted transaction.
    child = subprocess.run([sys.executable, "-c", """
import os, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
db.execute("PRAGMA wal_autocheckpoint=0")
db.execute("INSERT INTO events(time, body) VALUES(?,?)", (1700000001, '{"checkpoint":1}'))
db.commit()
db.execute("UPDATE paper SET body='uncommitted'")
os._exit(72)
""", str(ledger)], timeout=10)
    assert child.returncode == 72
    assert Path(str(ledger) + "-wal").stat().st_size > 32
    with closing(sqlite3.connect(ledger.as_uri() + "?immutable=1", uri=True)) as main_only:
        assert main_only.execute("SELECT COUNT(*) FROM events").fetchone() == (2,)
    # Pin a reader so merely checking the fixture cannot checkpoint the WAL away.
    with closing(sqlite3.connect(ledger)) as reader:
        reader.execute("BEGIN")
        assert reader.execute("SELECT COUNT(*) FROM events").fetchone() == (3,)
        version, before = snapshot(ledger)
        assert version == 4
        Store(ledger)
    backup = backup_path(ledger)
    assert snapshot(backup) == (4, before)
    restored = tmp_path / "restored.sqlite3"
    shutil.copyfile(backup, restored)
    assert snapshot(restored) == (4, before)
    Store(restored)
    assert snapshot(restored) == snapshot(ledger)
    version, after = snapshot(ledger)
    assert version == 5
    assert {k: after[k] for k in before} == before
    assert after.keys() - before.keys() == {"equity_samples", "forecasts", "forecast_outcomes", "ui_preferences"}

    original_backup = backup.read_bytes()
    orders = {key: json.loads(body) for key, body in before["orders"]}
    assert Decimal(orders[BUY]["cash_delta"]) == -Decimal(orders[BUY]["fill"])
    assert orders[BUY]["execution"]["values"]["fee_currency"] == "base"
    assert Decimal(orders[BUY]["execution"]["values"]["fee_quantity"]) == Decimal(".001")
    assert orders[SELL]["execution"]["values"]["fee_currency"] == "quote"
    assert Decimal(orders[SELL]["cash_delta"]) + Decimal(orders[SELL]["execution"]["values"]["fee_quantity"]) == Decimal(".4995") * 120
    gateway = OrderPreview(Store(ledger))
    for ident, raw in before["orders"]:
        assert gateway.confirm(ident, "fixture", {}, {}, ack=True) == json.loads(raw)
    assert snapshot(ledger) == (5, after)
    assert backup.read_bytes() == original_backup

    # Independent Decimal oracle across the migration and a new real Paper confirm.
    monkeypatch.setattr("time.time", lambda: NOW)
    quotes = {SYMBOL: dict(price=120, bid=120, ask=120, ts=NOW, fresh=True)}
    rules = {SYMBOL: dict(step=".0001", tick=".01", minimum="5", maximum="100", retrieved=NOW)}
    state = gateway.paper.state()
    position = state["positions"][SYMBOL]
    fee_base = Decimal("1") * Decimal(".001")
    sold = (1 - fee_base) / 2
    credit = sold * 120 * Decimal(".999")
    remaining = Decimal(position["qty"])
    assert remaining == 1 - fee_base - sold
    assert remaining % Decimal(".001") == Decimal(".0005")
    allocated = Decimal(100) * sold / (1 - fee_base)
    assert Decimal(position["cost_basis"]) == 100 - allocated
    cash, realized = Decimal(state["cash"]), Decimal(state["realized"])
    assert cash == 1000 - 100 + credit
    assert realized == credit - allocated
    assert cash + Decimal(position["cost_basis"]) == 1000 + realized
    mark = metrics(state, quotes)
    assert Decimal(mark["unrealized_decimal"]) == remaining * 120 - Decimal(position["cost_basis"])
    assert Decimal(mark["equity_decimal"]) == cash + remaining * 120

    gateway.prepare(dict(id=CLOSE, symbol=SYMBOL, side="SELL", quantity=str(remaining)),
                    quotes, rules, "fixture")
    fill = gateway.confirm(CLOSE, "fixture", quotes, rules, ack=True)
    assert fill["status"] == "Filled"
    assert Decimal(fill["allocated_basis"]) == Decimal(position["cost_basis"])
    gross = remaining * Decimal(fill["fill"])
    fee = gross * Decimal(".001")
    assert Decimal(fill["fee"]) == fee
    assert Decimal(fill["cash_delta"]) == gross - fee
    final = Paper(Store(ledger)).state()
    assert final["positions"] == {}
    assert Decimal(final["cash"]) == cash + gross - fee == 1000 + Decimal(final["realized"])
    assert snapshot(backup) == (4, before)


def test_abort_before_version_commit_retries_once(ledger, monkeypatch):
    before = snapshot(ledger)
    connect = sqlite3.connect
    denied = []

    def inject(*args, **kwargs):
        db = connect(*args, **kwargs)
        def authorize(action, key, value, *_):
            if action == sqlite3.SQLITE_PRAGMA and key == "user_version" and value == "5":
                denied.append(True)
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        db.set_authorizer(authorize)
        return db

    with monkeypatch.context() as fault:
        fault.setattr(sqlite3, "connect", inject)
        with pytest.raises(sqlite3.DatabaseError, match="authorized"):
            Store(ledger)
    assert denied and snapshot(ledger) == snapshot(backup_path(ledger)) == before
    Store(ledger)
    migrated = snapshot(ledger)
    assert migrated[0] == 5 and {k: migrated[1][k] for k in before[1]} == before[1]
    Store(ledger)
    assert snapshot(ledger) == migrated


def test_failed_backup_publication_preserves_ledger(ledger, monkeypatch):
    before = snapshot(ledger)
    files = set(ledger.parent.iterdir())
    def no_space(*args):
        raise OSError(errno.ENOSPC, "fixture filesystem full")
    with monkeypatch.context() as fault:
        fault.setattr(os, "link", no_space)
        with pytest.raises(OSError) as error:
            Store(ledger)
    assert error.value.errno == errno.ENOSPC
    assert snapshot(ledger) == before
    assert set(ledger.parent.iterdir()) == files
    Store(ledger)
    assert snapshot(backup_path(ledger)) == before


def test_stale_backup_fails_closed(ledger):
    backup = backup_path(ledger)
    shutil.copyfile(ledger, backup)
    with closing(sqlite3.connect(backup)) as db, db:
        db.execute("DELETE FROM events WHERE id=2")
    before, stale = snapshot(ledger), snapshot(backup)
    with pytest.raises((ValueError, OSError)):
        Store(ledger)
    assert snapshot(ledger) == before and snapshot(backup) == stale


def test_writer_cannot_commit_between_backup_and_upgrade(ledger, monkeypatch):
    publish = os.link
    def competing_writer(src, dst):
        publish(src, dst)
        with closing(sqlite3.connect(ledger, timeout=0)) as other, other:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("INSERT INTO events(time,body) VALUES(0,'{}')")
    monkeypatch.setattr(os, "link", competing_writer)
    Store(ledger)
    _, saved = snapshot(backup_path(ledger))
    _, current = snapshot(ledger)
    assert {k: current[k] for k in saved} == saved


def test_future_version_preserves_bytes_and_journal_mode(ledger):
    with closing(sqlite3.connect(ledger)) as db:
        db.execute("PRAGMA user_version=6")
    original = ledger.read_bytes()
    with pytest.raises(ValueError, match="newer"):
        Store(ledger)
    assert ledger.read_bytes() == original
    assert set(ledger.parent.iterdir()) == {ledger}


def test_corruption_does_not_create_empty_account(ledger):
    ledger.write_bytes(b"synthetic damaged header" * 128)
    original = ledger.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        Paper(Store(ledger))
    assert ledger.read_bytes() == original
    assert set(ledger.parent.iterdir()) == {ledger}


@pytest.fixture
def invest(tmp_path):
    # v0.4 Invest schema, before account_id. Crypto must not upgrade this file.
    path = tmp_path / "portfolio.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY, id TEXT UNIQUE, body TEXT NOT NULL)")
        db.execute("INSERT INTO events VALUES(1,'invest-deposit',?)",
                   (json.dumps(dict(kind="deposit", amount=500, date="2023-11-14")),))
    return path


def test_foreign_ledger_refused_even_if_passed_as_crypto(invest):
    original = invest.read_bytes()
    with pytest.raises(ValueError):
        Store(invest)
    assert invest.read_bytes() == original
    assert set(invest.parent.iterdir()) == {invest}


@pytest.mark.parametrize("fail", [False, True])
def test_normal_runtime_path_isolates_invest(ledger, invest, fail, monkeypatch):
    original = invest.read_bytes()
    monkeypatch.setenv("MOEX_DATA_DIR", str(ledger.parent))
    # The real worker monitors a synthetic quote strictly inside the position's
    # stop/target. No market subscriptions are opened.
    class FixtureHub:
        def retain(self, owner, pairs, store):
            pass

        def get(self, symbol, interval, store):
            assert symbol == SYMBOL
            return self

        def snapshot(self):
            return {"quote": {"price": 120, "bid": 120, "ask": 120, "ts": NOW},
                    "fresh": True, "rules": {"step": ".001", "tick": ".01",
                                             "minimum": "5", "retrieved": NOW}}

    monkeypatch.setattr("time.time", lambda: NOW)
    monkeypatch.setattr(runtime, "hub", FixtureHub)
    connect = sqlite3.connect
    opened = []
    def checked_connect(path, *args, **kwargs):
        opened.append(str(path))
        assert invest.name not in str(path)
        return connect(path, *args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", checked_connect)
    if fail:
        ledger.write_bytes(b"invalid Crypto" * 100)
    try:
        if fail:
            with pytest.raises(sqlite3.DatabaseError):
                runtime.start()
        else:
            worker = runtime.start()
            assert worker.store.path == ledger
            worker.tick()
            assert worker.heartbeat == NOW
            assert Paper(worker.store).state()["cash"] == "959.88006"
    finally:
        runtime.shutdown()
    assert opened and invest.read_bytes() == original
    assert not list(invest.parent.glob("portfolio.sqlite3.*"))


def test_damaged_data_page_blocks_migration(ledger):
    with closing(sqlite3.connect(ledger)) as db:
        page = db.execute("SELECT rootpage FROM sqlite_schema WHERE name='orders'").fetchone()[0]
        size = db.execute("PRAGMA page_size").fetchone()[0]
    with ledger.open("r+b") as f:
        f.seek((page - 1) * size)
        f.write(b"\0")  # A readable SQLite header with an invalid b-tree page type.
    original = ledger.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        Store(ledger)
    assert ledger.read_bytes() == original
    assert not backup_path(ledger).exists()


def test_truncated_existing_ledger_is_not_a_new_account(ledger):
    ledger.write_bytes(b"")
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        Paper(Store(ledger))
    assert ledger.read_bytes() == b""


def test_old_store_instance_refuses_upgraded_ledger(ledger):
    store = Store(ledger)
    with closing(sqlite3.connect(ledger)) as db:
        db.execute("PRAGMA user_version=6")
    original = ledger.read_bytes()
    with pytest.raises(ValueError, match="newer"):
        Paper(store)
    assert ledger.read_bytes() == original
