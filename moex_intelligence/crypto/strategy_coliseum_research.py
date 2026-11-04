"""CandlePath Strategy Coliseum v0.1: fail-closed *selection*, not execution.

Consumes an already computed development-fold study (e.g. PR #40's
deep_paper_validation_v09.py JSON) and an independently frozen roster.
Never evaluates historical candles, strategy code or the final holdout.
No strategy is certified for real or autonomous trading by this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

SCENARIOS = ("LOW", "PAPER", "STRESS")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COLISEUM_VERSION = "coliseum-research-0.1"
TRUSTED_SOURCE_LABELS = frozenset({"VERIFIED_PUBLIC_ARCHIVE", "VERIFIED_LOCAL_ARCHIVE"})


@dataclass(frozen=True)
class SelectionPolicy:
    min_days_5m: int = 180
    min_trades: int = 60
    min_trades_per_fold: int = 10
    min_paper_profit_factor: Decimal = Decimal("1.20")
    maximum_paper_drawdown_pct: Decimal = Decimal("10")
    maximum_shortlist: int = 20
    maximum_per_family: int = 4
    fold_capital_usdt: Decimal = Decimal("10000")


def _number(value, name: str) -> Decimal:
    if isinstance(value, bool) or value is None or isinstance(value, (list, dict)):
        raise ValueError(f"{name}: missing or invalid finite number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name}: missing or invalid finite number") from exc
    if not result.is_finite():
        raise ValueError(f"{name}: nonfinite number")
    return result


def _whole(value, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}: expected integer >= {minimum}")
    return value


def _metric(record: dict, candidate: str, scenario: str, policy: SelectionPolicy) -> dict:
    if not isinstance(record, dict):
        raise ValueError(f"{candidate}/{scenario}: invalid metric record")
    trades = _whole(record.get("trades"), f"{candidate}/{scenario} trades")
    folds = record.get("folds")
    if not isinstance(folds, list) or len(folds) != 3:
        raise ValueError(f"{candidate}/{scenario}: exactly 3 chronological folds required")
    fold_counts, fold_returns = [], []
    for number, fold in enumerate(folds, start=1):
        if not isinstance(fold, dict) or fold.get("fold") != number:
            raise ValueError(f"{candidate}/{scenario}: folds out of sequence")
        fold_counts.append(_whole(fold.get("trade_count"), f"{candidate}/{scenario} fold trades"))
        fold_returns.append(_number(fold.get("net_return_pct"), f"{candidate}/{scenario} fold return"))
    if sum(fold_counts) != trades:
        raise ValueError(f"{candidate}/{scenario}: fold trade counts differ from total")
    net = _number(record.get("net_pnl"), f"{candidate}/{scenario} net_pnl")
    expectancy = _number(record.get("expectancy"), f"{candidate}/{scenario} expectancy") if trades else None
    profit_factor = _number(record.get("profit_factor"), f"{candidate}/{scenario} profit_factor") if record.get("profit_factor") is not None else None
    dd = _number(record.get("max_drawdown"), f"{candidate}/{scenario} drawdown")
    win = _number(record.get("win_rate"), f"{candidate}/{scenario} win rate") if trades else None
    if dd < 0 or dd > 100 or (profit_factor is not None and profit_factor < 0):
        raise ValueError(f"{candidate}/{scenario}: invalid drawdown/profit factor")
    if win is not None and not 0 <= win <= 1:
        raise ValueError(f"{candidate}/{scenario}: invalid win rate")
    if trades and (net - expectancy * trades).copy_abs() > Decimal("0.01"):
        raise ValueError(f"{candidate}/{scenario}: net P&L and expectancy inconsistent")
    if (net - sum(fold_returns) * policy.fold_capital_usdt / 100).copy_abs() > Decimal("0.01"):
        raise ValueError(f"{candidate}/{scenario}: net P&L and fold returns inconsistent")
    if not trades and net != 0:
        raise ValueError(f"{candidate}/{scenario}: profit without trades")
    return {"trades": trades, "fold_counts": fold_counts,
            "fold_returns": fold_returns, "net": net,
            "profit_factor": profit_factor, "drawdown": dd,
            "expectancy": expectancy}


def select_coliseum_candidates(study: dict, roster: list[dict], *,
                               policy: SelectionPolicy = SelectionPolicy()) -> dict:
    """Rank *research-only* candidates and account for every declared variant.

    Passing a gate only permits further independent testing, never promotion to
    production/Paper execution. Every source and threshold must be frozen before
    inspecting scoring folds; this API cannot independently prove preregistration.
    """
    if not isinstance(study, dict) or not isinstance(roster, list) or not roster:
        raise ValueError("Study and nonempty frozen roster are required")
    if not 1 <= policy.maximum_shortlist <= 20 or not 1 <= policy.maximum_per_family <= 20:
        raise ValueError("Maximum shortlist must be 1..20; family cap 1..20")
    if policy.min_days_5m < 1 or policy.min_trades < 1 or policy.min_trades_per_fold < 1:
        raise ValueError("Sample thresholds must be positive")
    if policy.fold_capital_usdt <= 0 or policy.maximum_paper_drawdown_pct <= 0:
        raise ValueError("Invalid financial policy")
    if not SHA256.fullmatch(str(study.get("source_sha256", ""))):
        raise ValueError("Invalid source SHA256")
    rows = _whole(study.get("rows"), "rows", 1)
    dev_end = _whole(study.get("development_end_exclusive"), "development end", 1)
    if dev_end > (rows * 80 // 100) or dev_end >= rows:
        raise ValueError("Final >=20% holdout is not sealed")
    if study.get("sealed_final_evaluated") is not False:
        raise ValueError("Final holdout must not be evaluated")
    results = study.get("results")
    if not isinstance(results, dict) or set(results) != set(SCENARIOS):
        raise ValueError("LOW/PAPER/STRESS scenarios required, no omitted experiments")
    manifest: dict[str, dict] = {}
    hashes: set[str] = set()
    for entry in roster:
        if not isinstance(entry, dict):
            raise ValueError("Invalid roster entry")
        cid, family, spec = entry.get("id"), entry.get("family"), entry.get("spec_sha256")
        if not isinstance(cid, str) or not (1 <= len(cid) <= 128) or not cid.strip():
            raise ValueError("Invalid candidate ID")
        if not isinstance(family, str) or not (1 <= len(family) <= 64) or not family.strip():
            raise ValueError(f"Invalid family for {cid}")
        if not isinstance(spec, str) or not SHA256.fullmatch(spec):
            raise ValueError(f"Missing canonical spec fingerprint for {cid}")
        if cid in manifest or spec in hashes:
            raise ValueError(f"Duplicate candidate or identical configuration fingerprint: {cid}")
        manifest[cid] = {"family": family, "spec_sha256": spec}
        hashes.add(spec)
    for scenario in SCENARIOS:
        data = results[scenario]
        if not isinstance(data, dict) or set(data) != set(manifest):
            raise ValueError(f"{scenario}: scoring roster does not match frozen manifest")

    globally_blocked = []
    # Even whitelisted provenance labels need external verification; a label itself is not proof.
    if study.get("source") not in TRUSTED_SOURCE_LABELS:
        globally_blocked.append("UNVERIFIED_SOURCE")
    if rows < policy.min_days_5m * 24 * 12:
        globally_blocked.append("INSUFFICIENT_HISTORY_5M")
    if not study.get("source"):
        globally_blocked.append("MISSING_SOURCE_LABEL")

    canonical_roster = [{"id": cid, **meta} for cid, meta in sorted(manifest.items())]
    roster_digest = hashlib.sha256(json.dumps(canonical_roster, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    frozen_policy = {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(policy).items()}
    run_identity = {"dataset": study["source_sha256"], "roster": roster_digest,
                    "policy": frozen_policy, "version": COLISEUM_VERSION}
    run_digest = hashlib.sha256(json.dumps(run_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    standings = []
    for cid, meta in manifest.items():
        metrics = {scenario: _metric(results[scenario][cid], cid, scenario, policy)
                   for scenario in SCENARIOS}
        paper, stress = metrics["PAPER"], metrics["STRESS"]
        reasons = list(globally_blocked)
        if paper["trades"] < policy.min_trades or any(
                count < policy.min_trades_per_fold for count in paper["fold_counts"]):
            reasons.append("INSUFFICIENT_TRADES")
        if paper["net"] <= 0 or paper["expectancy"] is None or paper["expectancy"] <= 0:
            reasons.append("NONPOSITIVE_PAPER_EXPECTANCY")
        if paper["profit_factor"] is None or paper["profit_factor"] < policy.min_paper_profit_factor:
            reasons.append("INSUFFICIENT_PROFIT_FACTOR")
        if any(value <= 0 for value in paper["fold_returns"]):
            reasons.append("PAPER_FOLD_LOSS")
        if stress["net"] <= 0 or any(value <= 0 for value in stress["fold_returns"]):
            reasons.append("STRESS_COST_FAILURE")
        if paper["drawdown"] > policy.maximum_paper_drawdown_pct:
            reasons.append("EXCESSIVE_OBSERVED_DRAWDOWN")
        standings.append({"candidate_id": cid, "family": meta["family"],
            "spec_sha256": meta["spec_sha256"],
            "paper_net_usdt": str(paper["net"]),
            "stress_net_usdt": str(stress["net"]),
            "paper_profit_factor": str(paper["profit_factor"]) if paper["profit_factor"] is not None else None,
            "paper_max_observed_drawdown_pct": str(paper["drawdown"]),
            "paper_worst_fold_return_pct": str(min(paper["fold_returns"])),
            "paper_trade_count": paper["trades"],
            "rejection_reasons": reasons, "shortlisted": False,
            "_ranking": (min(paper["fold_returns"]), stress["net"], paper["net"])})
    standings.sort(key=lambda x: (-x["_ranking"][0], -x["_ranking"][1],
                                 -x["_ranking"][2], x["candidate_id"]))
    family_counts: dict[str, int] = {}
    shortlisted = []
    for row in standings:
        if not row["rejection_reasons"]:
            if len(shortlisted) >= policy.maximum_shortlist:
                row["rejection_reasons"].append("SHORTLIST_CAP_REACHED")
            elif family_counts.get(row["family"], 0) >= policy.maximum_per_family:
                row["rejection_reasons"].append("FAMILY_CAP_REACHED")
            else:
                row["shortlisted"] = True
                shortlisted.append(row["candidate_id"])
                family_counts[row["family"]] = family_counts.get(row["family"], 0) + 1
        del row["_ranking"]
    return {
        "mode": "ISOLATED_RESEARCH_SELECTION_NOT_EXECUTION",
        "version": COLISEUM_VERSION,
        "policy": frozen_policy,
        "roster_sha256": roster_digest,
        "selection_run_sha256": run_digest,
        "source_sha256": study["source_sha256"],
        "source_label": study.get("source"),
        "sealed_final_evaluated": False,
        "candidate_count": len(manifest),
        "tested_variant_count": len(manifest),
        "standings": standings,
        "shortlisted_for_independent_validation": shortlisted,
        "qualified_count": len(shortlisted),
        "production_integrations": 0,
        "auto_execution_enabled": False,
        "trading_edge_verified": False,
        "limitations": [
            "Frozen manifest and archive origin are asserted, not independently attested by this process",
            "180 full 5m days are a minimum proxy, not coverage or regime-diversity proof",
            "Fold returns are dependent; selection among many variants inflates false discoveries",
            "Per-family caps do not prove strategy independence or return correlation",
            "Observed open/close drawdown may understate intrabar drawdown",
            "Research shortlist needs new untouched data and prospective forward Paper Trading",
        ],
    }


def run_cli(argv=None) -> int:
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Read-only Strategy Coliseum v0.1 judge")
    parser.add_argument("study", type=Path)
    parser.add_argument("roster", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    if args.output.resolve() in (args.study.resolve(), args.roster.resolve()):
        parser.error("Output must differ from source and roster")
    study = json.loads(args.study.read_text(encoding="utf-8"))
    roster = json.loads(args.roster.read_text(encoding="utf-8"))
    judged = select_coliseum_candidates(study, roster)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(judged, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Coliseum: {judged['candidate_count']} candidates, "
          f"{judged['qualified_count']} research shortlists; no trading enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
