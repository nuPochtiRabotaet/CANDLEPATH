"""Independent regression tests exposing v0.8 shortcomings.
Run from v0.8 repository root:
  PYTHONPATH=. python -m pytest -q /mnt/data/moex_review/test_new_regressions_v08.py
These are expected-to-Fail until the issues are fixed.
"""
import time
import uuid
import threading
from pathlib import Path
from moex_intelligence.crypto.paper import Paper
from moex_intelligence.crypto.storage import Store
from moex_intelligence.crypto.market import Feed


def quote(price=100, bid=99.9, ask=100):
    return {"price":price,"bid":bid,"ask":ask,"ts":time.time(),"fresh":True}


def order(side, quantity, stop="98", target="105"):
    return {"id":str(uuid.uuid4()),"symbol":"BTCUSDT","side":side,"quantity":quantity,"stop":stop,"target":target}


def setup(tmp_path):
    store=Store(tmp_path/"crypto.sqlite3")
    paper=Paper(store,capital=1000)
    quotes={"BTCUSDT":quote()}
    rules={"BTCUSDT":{"step":".001","tick":".01","minimum":"5","maximum":"1000","retrieved":time.time()}}
    return store,paper,quotes,rules


def test_rejected_protective_order_must_retry_after_cause_removed(tmp_path):
    store,paper,quotes,rules=setup(tmp_path)
    assert paper.execute(order("BUY",".055",stop="90",target="130"),quotes,rules)["status"]=="Filled"
    quotes["BTCUSDT"]=quote(89,89,89.1)
    paper.protect(quotes,rules)
    assert store.orders()[0]["status"]=="Rejected"  # min order notional
    rules["BTCUSDT"]["minimum"]="1"  # retry is now valid
    paper.protect(quotes,rules)
    assert not paper.state()["positions"], "BUG: rejected stop blocks all subsequent attempts"


def test_partial_exit_must_not_leave_uncloseable_dust(tmp_path):
    store,paper,quotes,rules=setup(tmp_path)
    assert paper.execute(order("BUY",".10"),quotes,rules)["status"]=="Filled"
    paper.execute(order("SELL",".06"),quotes,rules)
    remains=paper.state()["positions"].get("BTCUSDT")
    if remains:
        final=paper.execute(order("SELL",remains["qty"]),quotes,rules)
        assert final["status"]=="Filled", "BUG: partial exit created stranded dust"


def test_protective_exit_recovers_after_rules_refresh(tmp_path):
    store,paper,quotes,rules=setup(tmp_path)
    assert paper.execute(order("BUY","1"),quotes,rules)["status"]=="Filled"
    quotes["BTCUSDT"]=quote(97,96.9,97)
    rules["BTCUSDT"]["retrieved"]=time.time()-90000
    paper.protect(quotes,rules)
    assert store.orders()[0]["status"]=="Rejected"
    rules["BTCUSDT"]["retrieved"]=time.time()
    paper.protect(quotes,rules)
    assert not paper.state()["positions"], "BUG: refreshing stale rules does not re-arm stop"


def test_quote_with_missing_bid_ask_must_not_be_reported_fresh(tmp_path):
    f=object.__new__(Feed)
    f.symbol="BTCUSDT";f.interval="15";f.lock=threading.RLock()
    f.quote={"price":100,"bid":0,"ask":0,"ts":time.time()}
    f.status="Live";f.last_ws=time.time();f.rows=[];f.rules={};f.events=[];f.version=0;f.error="";f.touched=time.monotonic()
    s=f.snapshot()
    assert not s["fresh"], "BUG: UI may report Live/Fresh although bid/ask are invalid"
