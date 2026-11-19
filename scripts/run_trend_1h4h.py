"""Run only the preregistered BTC/ETH development study. Emits aggregate JSON."""
import argparse
import asyncio
import hashlib
import json
import platform
import sys
import zipfile
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_coliseum_v02 import summary
from moex_intelligence.crypto.coliseum_catalog import digest
from moex_intelligence.crypto.coliseum_diagnostics import trade_diagnostics
from moex_intelligence.crypto.coliseum_statistics import assess
from moex_intelligence.crypto.trend_history import (
    DEV_END, ROOT, SEALED_END, SYMBOLS, SourceUnavailable, binance_history,
    bybit_history, check_calendar, four_hour)
from moex_intelligence.crypto.trend_research import (
    CAPITAL, HYPOTHESES, daily_regimes, fold_dates, passive_daily, portfolio_paths, rules_for)

D = Decimal
COMPARATORS = ("USDT", "HOLD_25")
PROTOCOL = ROOT / "docs/research/trend_1h4h/PROTOCOL.md"


def sum_field(rows, field):
    return sum((D(r[field]) for r in rows), D(0))


def evaluate_path(rows, symbol, timeframe, hypothesis, multiplier):
    report, model, spread = portfolio_paths(rows, symbol, timeframe, hypothesis, multiplier)
    diagnostic = trade_diagnostics(report, rows, model, spread)
    keys = [(d["fold"], d["day"]) for d in diagnostic["daily"] if d["complete"]]
    if len(keys) != 3 * 177 or len(set(keys)) != len(diagnostic["daily"]):
        raise ValueError("Incomplete scored UTC day panel")
    daily = {k: D(d["net_pnl"]) for k, d in zip(keys, diagnostic["daily"], strict=True)}
    rules = rules_for(symbol)
    comparators = {"USDT": dict.fromkeys(keys, D(0))}
    for label, cap in (("HOLD_25", D(".25")), ("HOLD_100", D(1))):
        comparators[label] = passive_daily(rows, report, cap, model, spread, rules)
        if comparators[label].keys() != daily.keys():
            raise ValueError("Passive dates do not align")
    result = summary(report)
    result["net_return_pct"] = str(100 * D(result["net_pnl"]) / (3 * CAPITAL))
    result["benchmarks_pct"] = {
        label: str(100 * sum(panel.values()) / (3 * CAPITAL)) for label, panel in comparators.items()}
    result["entry_regimes"] = diagnostic["regimes"]
    labels = daily_regimes(rows, timeframe)
    regime_results = {}
    for key, pnl in daily.items():
        day_regime = labels[key[1]]
        group = regime_results.setdefault(day_regime, dict(days=0, net_usdt=D(0), passive_25_usdt=D(0)))
        group["days"] += 1
        group["net_usdt"] += pnl
        group["passive_25_usdt"] += comparators["HOLD_25"][key]
    result["regime_at_day_open"] = {
        label: dict(days=g["days"], net_usdt=str(g["net_usdt"]), passive_25_usdt=str(g["passive_25_usdt"]))
        for label, g in regime_results.items()}

    result["cost_model"] = model.snapshot()
    result["full_spread_bps"] = spread
    result["assumed_rules"] = rules.snapshot()
    result["modeled_costs_usdt"] = {
        field: str(sum_field(diagnostic["trades"], field))
        for field in ("gross_pnl", "fee_cost", "spread_cost", "slippage_cost")}
    for f, replay in zip(result["folds"], report["folds"], strict=True):
        trades = replay["trades"]
        changes = [D(t["net_pnl_quote"]) for t in trades]
        gains = sum(x for x in changes if x > 0)
        losses = -sum(x for x in changes if x < 0)
        f.update(net_usdt=str(sum(changes, D(0))), expectancy_usdt=str(sum(changes) / len(trades)) if trades else None,
                 win_rate=sum(x > 0 for x in changes) / len(trades) if trades else None,
                 profit_factor=str(gains / losses) if losses else None,
                 marked_drawdown_pct=replay["marked_equity_guards"]["max_marked_drawdown_pct"],
                 events=replay["events"], benchmarks_pct={
                     label: str(100 * sum(v for (n, _), v in panel.items() if n == f["fold"]) / CAPITAL)
                     for label, panel in comparators.items()})
    contrasts = {label: {k: float((v - comparators[label][k]) / CAPITAL) for k, v in daily.items()}
                 for label in COMPARATORS}
    return result, contrasts


def assess_family(results, contrasts, source):
    ids = list(contrasts)
    if len(ids) != 16:
        raise ValueError("Incomplete family of strategy and baseline contrasts")
    keys = sorted(contrasts[ids[0]])
    if any(contrasts[c].keys() != set(keys) for c in ids):
        raise ValueError("Unaligned daily paths")
    inference = assess([[contrasts[c][k] for c in ids] for k in keys], [f for f, _ in keys])
    inference["columns"] = ids
    eligible = {ids[i] for i in inference["stable_candidates"]}
    for name, scenarios in results.items():
        base, stress = scenarios["base"], scenarios["double"]
        folds = base["folds"]
        fold_pnl = [D(f["net_usdt"]) for f in folds]
        gates = dict(
            provenance=source in ("BINANCE_PUBLIC_DATA_HTTPS", "BYBIT_V5_PUBLIC_HTTPS"),
            sample=all(f["trade_count"] >= 30 for f in folds),
            all_positive=all(x > 0 for x in fold_pnl),
            stress=D(stress["net_pnl"]) > 0,
            without_best=sum(fold_pnl) - max(fold_pnl) > 0,
            drawdown=all(D(f["marked_drawdown_pct"]) <= 12 for f in folds),
            simultaneous=all(f"{name}/{c}" in eligible for c in COMPARATORS))
        scenarios["gates"] = gates
        scenarios["decision"] = ("INDEPENDENT_REVIEW_ONLY" if all(gates.values())
                                 else "NO TRADE / INSUFFICIENT EVIDENCE")
    return inference


def study(histories, provenance):
    paths, contrasts, fingerprints = {}, {}, {}
    for symbol in SYMBOLS:
        hourly = histories[symbol]
        if digest(hourly) != provenance["instruments"][symbol]["hourly_sha256"]:
            raise ValueError("Development data fingerprint changed")
        aggregated = four_hour(hourly)
        fingerprints[symbol] = digest(aggregated)
        for timeframe, rows in (("60", hourly), ("240", aggregated)):
            for hypothesis in HYPOTHESES:
                name = f"{symbol}/{timeframe}/{hypothesis}"
                paths[name] = {}
                for scenario, multiplier in (("base", 1), ("double", 2)):
                    metrics, panel = evaluate_path(rows, symbol, timeframe, hypothesis, multiplier)
                    paths[name][scenario] = metrics
                    if scenario == "base":
                        for label, series in panel.items():
                            contrasts[f"{name}/{label}"] = series
    inference = assess_family(paths, contrasts, provenance["source"])
    return dict(status="EXPLORATORY", data=provenance, four_hour_sha256=fingerprints,
                paths=paths, statistics=inference)


def run(archive_dir=None):
    dependencies = sorted((ROOT / "moex_intelligence/crypto").glob("*.py"))
    dependencies += [Path(__file__).resolve(), ROOT / "scripts/run_coliseum_v02.py",
                     ROOT / "docs/research/original_holdout_guard.json"]
    source_hash = digest({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in dependencies})
    meta = dict(research_source_sha256=source_hash, python=platform.python_version(),
                packages={name: version(name) for name in ("pandas", "numpy", "httpx")},
                protocol_sha256=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
                sealed_utc=[DEV_END, SEALED_END], sealed_evaluated=False, folds=fold_dates(),
                validated=False)
    try:
        check_calendar()
        try:
            histories, source = binance_history(archive_dir)
        except SourceUnavailable as exc:
            meta["archive_error"] = str(exc)
            if archive_dir is not None:
                raise
            histories, source = asyncio.run(bybit_history())
        return dict(**meta, **study(histories, source))
    except (ValueError, OSError, ArithmeticError, zipfile.BadZipFile) as exc:
        return dict(**meta, status="NOT EVALUABLE", decision="NO TRADE / INSUFFICIENT EVIDENCE",
                    error=str(exc), paths={})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, help="Offline directory of original ZIPs and .CHECKSUM files")
    parser.add_argument("--output", type=Path, help="New aggregate JSON file (default stdout)")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("--output must be a new file")
    report = run(args.archive_dir)
    encoded = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x") as output:
            output.write(encoded)
    else:
        print(encoded, end="")
    sys.exit(0 if report["status"] == "EXPLORATORY" else 2)
