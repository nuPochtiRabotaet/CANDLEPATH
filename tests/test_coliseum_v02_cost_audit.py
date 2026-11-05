"""Fail-closed checks for the read-only Coliseum v0.2 cost breakdown."""
import copy
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from scripts.coliseum_v02_cost_audit import analyze, attribute_metrics, digest, main
from moex_intelligence.crypto.costs import CostModel, FeeSchedule, ExecutionAssumptions, estimate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs" / "research" / "coliseum_v02"


def close(a, b):
    assert abs(a - b) < D("0.00000001")


@pytest.mark.parametrize("fees,slip,spread", [
    ("0.0005", "2", "4"), ("0.001", "5", "4"), ("0.002", "10", "8"),
    ("0", "0", "0")
])
@pytest.mark.parametrize("exit_mid", ["97", "100", "104"])
def test_exact_cost_components_against_existing_fill_model(fees, slip, spread, exit_mid):
    model = CostModel(FeeSchedule(taker=fees), ExecutionAssumptions(slip))
    entry = D("100")
    exit_price = D(exit_mid)
    qty = D("2.75")
    half = D(spread) / D("20000")

    def quote(mid):
        return {"ask": str(mid * (1 + half)), "bid": str(mid * (1 - half))}

    buy = estimate("BUY", qty, quote(entry), model)
    sell = estimate("SELL", qty, quote(exit_price), model)
    metrics = {
        "trades": 1,
        "net_pnl": str(buy.cash_delta + sell.cash_delta),
        "turnover_quote": str(-buy.cash_delta + sell.cash_delta)
    }
    audit = attribute_metrics(metrics, [fees, slip, spread])
    close(audit["entry_mid_notional"], qty * entry)
    close(audit["exit_mid_notional"], qty * exit_price)
    close(audit["gross_pnl"], qty * (exit_price - entry))
    close(audit["fee_cost"], buy.fee_quote_value + sell.fee_quote_value)
    close(audit["slippage_cost"], buy.slippage_cost + sell.slippage_cost)
    close(audit["spread_cost"], qty * half * (entry + exit_price))
    close(audit["gross_pnl"] - audit["total_cost"], audit["net_pnl"])


def test_no_trades_must_have_no_cashflow():
    zero = attribute_metrics({"trades": 0, "net_pnl": "0", "turnover_quote": "0"}, [".001", 5, 4])
    assert zero["total_cost"] == 0 and zero["gross_pnl"] == 0
    with pytest.raises(ValueError, match="without trades"):
        attribute_metrics({"trades": 0, "net_pnl": "1", "turnover_quote": "0"}, [".001", 5, 4])


@pytest.mark.parametrize("metrics", [
    {"trades": 1, "net_pnl": "NaN", "turnover_quote": "100"},
    {"trades": 1, "net_pnl": "200", "turnover_quote": "100"},
    {"trades": 1, "net_pnl": "-200", "turnover_quote": "100"},
    {"trades": True, "net_pnl": "0", "turnover_quote": "100"},
    {"trades": 1, "net_pnl": "0", "turnover_quote": "-100"},
])
def test_invalid_or_impossible_cashflows_fail_closed(metrics):
    with pytest.raises(ValueError):
        attribute_metrics(metrics, [".001", 5, 4])


def inputs():
    return (json.loads((FIXTURE / "manifest.json").read_text()),
            json.loads((FIXTURE / "result.json").read_text()))


def test_actual_frozen_experiment_is_reconciled_and_deterministic():
    manifest, original = inputs()
    a = analyze(manifest, original)
    b = analyze(manifest, original)
    assert a == b
    assert a["manifest_sha256"] == digest(manifest)
    assert a["sealed_final_evaluated"] is False
    for scenario in ("LOW", "PAPER", "STRESS"):
        s = a["summary"][scenario]
        assert s["candidates"] == 100
        assert s["active_candidates"] == 95
        assert s["zero_trade_candidates"] == 5
        assert s["net_positive_candidates"] == 0
        assert len(a["candidates"][scenario]) == 100
        close(D(s["gross_pnl"]) - D(s["total_cost"]), D(s["net_pnl"]))
    paper = a["summary"]["PAPER"]
    assert paper["gross_positive_candidates"] == 33
    assert paper["total_trades"] == 15842
    assert D("97") < D(paper["cost_share_of_abs_net_loss_pct"]) < D("98")


def test_missing_participant_and_stale_manifest_are_rejected():
    manifest, original = inputs()
    altered = copy.deepcopy(original)
    altered["study"]["results"]["LOW"].pop(next(iter(altered["study"]["results"]["LOW"])))
    with pytest.raises(ValueError, match="participants"):
        analyze(manifest, altered)
    altered = copy.deepcopy(original)
    altered["manifest_sha256"] = "x" * 64
    with pytest.raises(ValueError, match="manifest"):
        analyze(manifest, altered)


def test_cli_create_or_equal_only(tmp_path):
    manifest, result = inputs()
    m = tmp_path / "manifest.json"
    r = tmp_path / "result.json"
    out = tmp_path / "audit.json"
    m.write_text(json.dumps(manifest))
    r.write_text(json.dumps(result))
    main([str(m), str(r), str(out)])
    first = out.read_bytes()
    main([str(m), str(r), str(out)])
    assert out.read_bytes() == first
    out.write_text('{"fabricated":true}')
    with pytest.raises(ValueError, match="refuse silent overwrite"):
        main([str(m), str(r), str(out)])
