"""Offline selection tests; no exchange, portfolio, CSV or Paper orders."""
import hashlib
import json
from dataclasses import replace

import pytest

from moex_intelligence.crypto.strategy_coliseum_research import (
    SelectionPolicy, select_coliseum_candidates, run_cli)


def fixture(n=1, *, rows=70000, source="VERIFIED_PUBLIC_ARCHIVE", all_positive=True):
    names = [f"candidate-{i:04d}" for i in range(n)]
    roster = [{"id": name,
               "family": f"family-{i % 10}",
               "spec_sha256": hashlib.sha256(name.encode()).hexdigest()}
              for i, name in enumerate(names)]
    def result(fold_pct):
        folds = [{"fold": i + 1, "trade_count": 25,
                  "net_return_pct": str(pct)}
                 for i, pct in enumerate(fold_pct)]
        net = sum(fold_pct) * 100  # 10,000 USDT per fold
        return {"trades": 75, "net_pnl": str(net),
                "expectancy": str(net / 75),
                "profit_factor": "1.8" if net > 0 else "0.1",
                "win_rate": 0.55 if net > 0 else 0.10,
                "max_drawdown": "2.1", "folds": folds}
    results = {s: {} for s in ("LOW", "PAPER", "STRESS")}
    for name in names:
        for s, ret in (("LOW", [0.3, 0.3, 0.3]),
                       ("PAPER", [0.2, 0.2, 0.2] if all_positive else [-0.2, -0.2, -0.2]),
                       ("STRESS", [0.1, 0.1, 0.1])):
            results[s][name] = result(ret)
    return ({"source_sha256": "a" * 64, "source": source,
             "rows": rows, "development_end_exclusive": rows * 80 // 100,
             "sealed_final_evaluated": False, "results": results}, roster)


def test_candidates_can_be_shortlisted_but_never_integrated():
    study, roster = fixture(3)
    out = select_coliseum_candidates(study, roster)
    assert out["candidate_count"] == 3
    assert len(out["selection_run_sha256"]) == 64
    assert out["selection_run_sha256"] == select_coliseum_candidates(study, roster)["selection_run_sha256"]
    assert out["qualified_count"] == 3
    assert out["shortlisted_for_independent_validation"] == [r["id"] for r in roster]
    assert out["sealed_final_evaluated"] is False
    assert out["trading_edge_verified"] is False
    assert out["auto_execution_enabled"] is False
    assert out["production_integrations"] == 0
    json.dumps(out, allow_nan=False)


def test_short_month_history_blocks_all_promotions():
    study, roster = fixture(3, rows=8640)
    out = select_coliseum_candidates(study, roster)
    assert out["qualified_count"] == 0
    assert all("INSUFFICIENT_HISTORY_5M" in r["rejection_reasons"] for r in out["standings"])


def test_arbitrary_provenance_label_is_not_trusted():
    study, roster = fixture(source="SOME_RANDOM_LABEL")
    out = select_coliseum_candidates(study, roster)
    assert out["qualified_count"] == 0
    assert "UNVERIFIED_SOURCE" in out["standings"][0]["rejection_reasons"]


def test_roster_hash_does_not_depend_on_input_order():
    study, roster = fixture(3)
    a = select_coliseum_candidates(study, roster)
    b = select_coliseum_candidates(study, list(reversed(roster)))
    assert a["roster_sha256"] == b["roster_sha256"]
    assert a["selection_run_sha256"] == b["selection_run_sha256"]


def test_unverified_provenance_blocks_shortlist():
    study, roster = fixture(source="USER_SUPPLIED_CSV_UNVERIFIED")
    out = select_coliseum_candidates(study, roster)
    assert out["qualified_count"] == 0
    assert "UNVERIFIED_SOURCE" in out["standings"][0]["rejection_reasons"]


def test_negative_paper_expectancy_rejected_even_if_stress_positive():
    study, roster = fixture(all_positive=False)
    out = select_coliseum_candidates(study, roster)
    assert out["qualified_count"] == 0
    assert "NONPOSITIVE_PAPER_EXPECTANCY" in out["standings"][0]["rejection_reasons"]
    assert "PAPER_FOLD_LOSS" in out["standings"][0]["rejection_reasons"]


def test_weak_stress_loss_rejected_without_backtest_tuning():
    study, roster = fixture()
    bad = study["results"]["STRESS"][roster[0]["id"]]
    for fold in bad["folds"]:
        fold["net_return_pct"] = "-0.1"
    bad["net_pnl"] = "-30"
    bad["expectancy"] = "-0.4"
    bad["profit_factor"] = "0.1"
    out = select_coliseum_candidates(study, roster)
    assert out["qualified_count"] == 0
    assert "STRESS_COST_FAILURE" in out["standings"][0]["rejection_reasons"]


def test_final_holdout_poison_or_leakage_fails_closed():
    study, roster = fixture()
    study["sealed_final_evaluated"] = True
    with pytest.raises(ValueError, match="Final holdout"):
        select_coliseum_candidates(study, roster)
    study["sealed_final_evaluated"] = False
    study["development_end_exclusive"] = 69000
    with pytest.raises(ValueError, match="holdout"):
        select_coliseum_candidates(study, roster)


def test_missing_and_extra_candidates_are_fatal():
    study, roster = fixture(2)
    del study["results"]["PAPER"][roster[1]["id"]]
    with pytest.raises(ValueError, match="roster"):
        select_coliseum_candidates(study, roster)
    study, roster = fixture(2)
    study["results"]["LOW"]["invisible-loser"] = study["results"]["LOW"][roster[0]["id"]]
    with pytest.raises(ValueError, match="roster"):
        select_coliseum_candidates(study, roster)


def test_duplicate_configurations_and_ids_are_fatal():
    study, roster = fixture(2)
    roster[1]["spec_sha256"] = roster[0]["spec_sha256"]
    with pytest.raises(ValueError, match="Duplicate"):
        select_coliseum_candidates(study, roster)
    study, roster = fixture(2)
    roster[1]["id"] = roster[0]["id"]
    with pytest.raises(ValueError, match="Duplicate"):
        select_coliseum_candidates(study, roster)


def test_financial_results_must_be_finite_and_reconcile():
    for field, value in (("net_pnl", "NaN"), ("net_pnl", "999"),
                         ("max_drawdown", "Infinity"), ("win_rate", 1.01)):
        study, roster = fixture()
        study["results"]["PAPER"][roster[0]["id"]][field] = value
        with pytest.raises(ValueError):
            select_coliseum_candidates(study, roster)


def test_shortlist_never_exceeds_20_and_family_cap():
    study, roster = fixture(2000)
    result = select_coliseum_candidates(study, roster)
    assert result["candidate_count"] == len(result["standings"]) == 2000
    assert result["qualified_count"] == 20
    assert len(set(result["shortlisted_for_independent_validation"])) == 20
    assert result["standings"] == select_coliseum_candidates(study, roster)["standings"]
    cap_two = replace(SelectionPolicy(), maximum_per_family=2)
    result = select_coliseum_candidates(study, roster, policy=cap_two)
    assert result["qualified_count"] == 20
    counts = {}
    for row in result["standings"]:
        if row["shortlisted"]:
            counts[row["family"]] = counts.get(row["family"], 0) + 1
    assert all(value <= 2 for value in counts.values())


def test_max_shortlist_over_20_is_not_allowed():
    study, roster = fixture()
    with pytest.raises(ValueError, match="Maximum shortlist"):
        select_coliseum_candidates(study, roster,
                                   policy=replace(SelectionPolicy(), maximum_shortlist=21))


def test_readonly_cli_refuses_to_overwrite_sources_and_output(tmp_path):
    study, roster = fixture(1)
    src, man, out = (tmp_path / f for f in ("study.json", "roster.json", "ranking.json"))
    src.write_text(json.dumps(study))
    man.write_text(json.dumps(roster))
    assert run_cli([str(src), str(man), str(out)]) == 0
    actual = json.loads(out.read_text())
    assert actual["qualified_count"] == 1
    with pytest.raises(FileExistsError):
        run_cli([str(src), str(man), str(out)])
    with pytest.raises(SystemExit):
        run_cli([str(src), str(man), str(src)])
    assert json.loads(src.read_text()) == study
    assert json.loads(man.read_text()) == roster

def test_selection_gates_cannot_be_silently_weakened():
    from decimal import Decimal
    study, roster = fixture()
    defaults = SelectionPolicy()
    for replacement in (
        {"min_days_5m": 30}, {"min_trades": 2},
        {"min_trades_per_fold": 1},
        {"min_paper_profit_factor": Decimal("1.00")},
        {"maximum_paper_drawdown_pct": Decimal("40")},
        {"maximum_per_family": 20},
        {"fold_capital_usdt": Decimal("100")},
    ):
        with pytest.raises(ValueError):
            select_coliseum_candidates(study, roster, policy=replace(defaults, **replacement))
