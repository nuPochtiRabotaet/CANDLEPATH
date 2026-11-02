"""Paper risk gate must not trust string 'false' or lexical quote ordering."""
import time
import uuid

import pytest

from moex_intelligence.crypto.paper import Paper
from moex_intelligence.crypto.risk import quote_ok, plan, RiskError
from moex_intelligence.crypto.storage import Store


def quote(now, *,bid="99",ask="101",fresh=True):
    return {"price":100.0,"bid":bid,"ask":ask,"ts":now,"fresh":fresh}


@pytest.mark.parametrize("untrusted",[False,None,"false","False","true",0,1,[],{}])
def test_market_quote_must_have_literal_boolean_true_fresh(untrusted):
    now=time.time()
    assert quote_ok(quote(now,fresh=untrusted),now) is False


def test_numeric_crossed_quote_rejected_even_with_lexically_sorted_strings():
    now=time.time()
    # '100' < '99' lexically, but 100 > 99 economically: crossed bid/ask.
    q=quote(now,bid="100",ask="99")
    assert "100"<"99"
    assert quote_ok(q,now) is False


@pytest.mark.parametrize("bad",["false","true",1])
def test_untrusted_freshness_cannot_execute_paper_order(tmp_path,bad):
    store=Store(tmp_path/f"false-{str(bad)}.sqlite3")
    paper=Paper(store)
    now=time.time()
    q={"BTCUSDT":quote(now,bid=99.99,ask=100.01,fresh=bad)}
    rules={"BTCUSDT":{"step":".01","tick":".01","minimum":"5","maximum":"100","retrieved":now}}
    req={"id":str(uuid.uuid4()),"symbol":"BTCUSDT","side":"BUY",
         "quantity":"1","stop":"98","target":"105"}
    result=paper.execute(req,q,rules)
    assert result["status"]=="Rejected"
    assert paper.state()["positions"]=={}
    assert paper.state()["cash"]=="10000"


def test_crossed_string_quote_cannot_pass_risk_plan(tmp_path):
    paper=Paper(Store(tmp_path/"crossed.sqlite3"))
    now=time.time()
    q={"BTCUSDT":quote(now,bid="100",ask="99")}
    rule={"step":".01","tick":".01","minimum":"5","maximum":"100","retrieved":now}
    with pytest.raises(RiskError,match="Stale Data"):
        plan(paper.state(),q,"BTCUSDT","1","98","105",rule)
