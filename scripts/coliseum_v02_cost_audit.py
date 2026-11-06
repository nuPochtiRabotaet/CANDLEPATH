"""Deterministic quote-fee cost attribution for Coliseum v0.2 summaries.

This is RESEARCH ONLY. It algebraically reverses aggregate entry debit and
exit credit; it does not reconstruct individual fills, test alpha, or touch
the Paper/Live engines. Applicable only to the frozen quote-denominated,
symmetric taker-fee, fixed spread/slippage configuration in PR #42.
"""
from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

D = Decimal
ZERO = D("0")
CENT = D("0.000001")


def number(value, label):
    if isinstance(value, bool) or value is None or isinstance(value, (list, dict)):
        raise ValueError(f"{label}: invalid number")
    try:
        result = D(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label}: invalid number") from exc
    if not result.is_finite():
        raise ValueError(f"{label}: nonfinite number")
    return result


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def fmt(value):
    return str(value.quantize(CENT))


def attribute_metrics(metrics, costs):
    """Infer historical mid-price exposure from exactly two stored aggregates.

    T = sum(entry_total_debit + exit_net_credit)
    N = sum(exit_net_credit - entry_total_debit)
    D_entry = (T-N)/2, C_exit = (T+N)/2.
    Both sides pay the same quoted taker fee, and entry/exit use symmetric
    half-spreads plus deterministic side-specific slippage.
    """
    if not isinstance(metrics, dict) or not isinstance(costs, (list, tuple)) or len(costs) != 3:
        raise ValueError("Invalid aggregate metrics or cost scenario")
    trades = metrics.get("trades")
    if type(trades) is not int or trades < 0:
        raise ValueError("Invalid trade count")
    net = number(metrics.get("net_pnl"), "net_pnl")
    turnover = number(metrics.get("turnover_quote"), "turnover_quote")
    fee, slip_bps, spread_bps = (number(c, "cost") for c in costs)
    if not ZERO <= fee <= D(".02") or not ZERO <= slip_bps <= 100 or not ZERO <= spread_bps <= 100:
        raise ValueError("Cost assumptions out of bounds")
    h = spread_bps / D(20000)  # half the full quoted spread
    slip = slip_bps / D(10000)
    buy_factor = (1 + h) * (1 + slip) * (1 + fee)
    sell_factor = (1 - h) * (1 - slip) * (1 - fee)
    if sell_factor <= 0:
        raise ValueError("Nonpositive exit factor")
    if trades == 0:
        if net != 0 or turnover != 0:
            raise ValueError("Nonzero P&L or turnover without trades")
        entry_mid = exit_mid = ZERO
    else:
        debit, credit = (turnover - net) / 2, (turnover + net) / 2
        if debit <= 0 or credit <= 0:
            raise ValueError("Impossible positive aggregate debit/credit")
        entry_mid, exit_mid = debit / buy_factor, credit / sell_factor

    gross = exit_mid - entry_mid
    spread_cost = h * (entry_mid + exit_mid)
    slippage_cost = slip * (entry_mid * (1 + h) + exit_mid * (1 - h))
    fee_cost = fee * (entry_mid * (1 + h) * (1 + slip) +
                      exit_mid * (1 - h) * (1 - slip))
    reconstructed = gross - spread_cost - slippage_cost - fee_cost
    if abs(reconstructed - net) > D("0.00000001"):
        raise ValueError("Cost components do not reconcile to net P&L")
    return {
        "trades": trades, "turnover_quote": turnover,
        "entry_mid_notional": entry_mid, "exit_mid_notional": exit_mid,
        "gross_pnl": gross, "fee_cost": fee_cost,
        "spread_cost": spread_cost, "slippage_cost": slippage_cost,
        "total_cost": fee_cost + spread_cost + slippage_cost,
        "net_pnl": net,
    }


def analyze(manifest, result):
    if not isinstance(manifest, dict) or not isinstance(result, dict):
        raise ValueError("Invalid experiment input")
    if result.get("failures") != []:
        raise ValueError("Incomplete or failed candidate experiments")
    if result.get("manifest_sha256") != digest(manifest):
        raise ValueError("Result does not match frozen manifest")
    study = result.get("study")
    if not isinstance(study, dict) or study.get("source_sha256") != manifest.get("source_sha256"):
        raise ValueError("Source fingerprint mismatch")
    if study.get("rows") != manifest.get("rows") or study.get("development_end_exclusive") != manifest.get("development_end_exclusive"):
        raise ValueError("History split mismatch")
    if study.get("sealed_final_evaluated") is not False:
        raise ValueError("Sealed final holdout is not protected")
    roster = manifest.get("roster")
    costs = manifest.get("costs")
    results = study.get("results")
    if not isinstance(roster, list) or not isinstance(costs, dict) or not isinstance(results, dict):
        raise ValueError("Missing roster or results")
    ids = [x["id"] for x in roster]
    if len(ids) != len(set(ids)) or set(results) != set(costs):
        raise ValueError("Inconsistent scenarios or duplicate candidates")

    summary = {}
    details = {}
    fields = ("gross_pnl", "fee_cost", "spread_cost", "slippage_cost", "total_cost", "net_pnl", "turnover_quote")
    for scenario, settings in costs.items():
        bucket = results[scenario]
        if not isinstance(bucket, dict) or set(bucket) != set(ids):
            raise ValueError(f"{scenario}: missing, duplicate or extra participants")
        totals = {name: ZERO for name in fields}
        active = gross_positive = net_positive = trades = 0
        details[scenario] = {}
        for candidate in ids:
            record = attribute_metrics(bucket[candidate], settings)
            for name in fields:
                totals[name] += record[name]
            trades += record["trades"]
            active += record["trades"] > 0
            gross_positive += record["gross_pnl"] > 0
            net_positive += record["net_pnl"] > 0
            details[scenario][candidate] = {
                k: (v if k == "trades" else fmt(v)) for k, v in record.items()
            }
        if abs(totals["gross_pnl"] - totals["total_cost"] - totals["net_pnl"]) > D("0.00000001"):
            raise ValueError(f"{scenario}: aggregate reconciliation failure")
        summary[scenario] = {
            "candidates": len(ids), "active_candidates": active,
            "zero_trade_candidates": len(ids) - active, "total_trades": trades,
            "gross_positive_candidates": gross_positive,
            "net_positive_candidates": net_positive,
            **{name: fmt(totals[name]) for name in fields},
            "average_gross_per_trade": fmt(totals["gross_pnl"] / trades) if trades else None,
            "average_net_per_trade": fmt(totals["net_pnl"] / trades) if trades else None,
            "cost_share_of_abs_net_loss_pct": (
                fmt(100 * totals["total_cost"] / -totals["net_pnl"])
                if totals["net_pnl"] < 0 else None
            ),
        }
    return {
        "status": "DERIVED_AGGREGATE_ATTRIBUTION_NOT_TRADE_LEVEL_AUDIT",
        "manifest_sha256": digest(manifest), "source_sha256": manifest["source_sha256"],
        "source": study["source"], "sealed_final_evaluated": False,
        "model": "SYMMETRIC_TAKER_FEE_IN_QUOTE_FIXED_BPS_SPREAD_SLIPPAGE",
        "notes": [
            "100 independent candidate studies; sums are NOT a deployable portfolio P&L.",
            "Aggregated result inversion; individual fills, price paths and exit reasons NOT verified.",
            "No historical bid/ask, exchange rules, fill latency or independent alpha validation.",
            "Only valid while quote-side fees and frozen cost arithmetic match the experiment.",
        ],
        "summary": summary, "candidates": details,
    }


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        raise SystemExit("Usage: python scripts/coliseum_v02_cost_audit.py MANIFEST_JSON RESULT_JSON OUTPUT_JSON")
    manifest = json.loads(Path(args[0]).read_text())
    result = json.loads(Path(args[1]).read_text())
    output = Path(args[2])
    report = analyze(manifest, result)
    encoded = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if output.exists() and output.read_text() != encoded:
        raise ValueError("Existing attribution report differs; refuse silent overwrite")
    output.write_text(encoded)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
