"""Preregistered, offline-capable Binance Spot study. No broker or ledger interface."""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import zipfile
from decimal import ROUND_CEILING, ROUND_FLOOR
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moex_intelligence.crypto.analysis import indicators
from moex_intelligence.crypto.coliseum_catalog import digest
from moex_intelligence.crypto.costs import D
from moex_intelligence.crypto.market import seconds
from moex_intelligence.crypto.trend_history import (
    DEV_END, ROOT, SEALED_END, SYMBOLS, binance_history, check_calendar, check_development, four_hour)
from moex_intelligence.crypto.trend_research import CAPITAL, fold_dates, fold_windows, portfolio_paths, rules_for
from scripts.run_trend_1h4h import COMPARATORS, assess_paths, summarize_path

REGISTRATION = "edf3aa8352f6ca00fcf72dd15dc8c899b9fcdf7d"
SUMS_SHA256 = "0799890707ecbaa4f59a15d46e30a6bcf818ade2d4b5dca284bd24df7e96586c"
DIRECTORY = ROOT / "docs/research/volatility_breakout"
PREVIOUS = ROOT / "docs/research/trend_1h4h/market_run_20261119.json"
HYPOTHESIS = "VOLATILITY_BREAKOUT"
INTERVALS = ("60", "240")
NO_TRADE = "NO TRADE / INSUFFICIENT EVIDENCE"


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registered_inputs():
    sums = DIRECTORY / "SHA256SUMS"
    if fingerprint(sums) != SUMS_SHA256:
        raise ValueError("Registration checksum file changed")
    for line in sums.read_text().splitlines():
        checksum, path = line.split(maxsplit=1)
        if fingerprint(ROOT / path) != checksum:
            raise ValueError(f"Preregistered input changed: {path}")
    check_calendar()
    return json.loads(PREVIOUS.read_text())


def verified_panels(hourly, metadata, previous):
    """Validate both markets and both resolutions before evaluating any strategy."""
    reference = previous["data"]
    if (reference["source"] != "BINANCE_PUBLIC_DATA_HTTPS" or
            metadata["source"] not in ("BINANCE_PUBLIC_DATA_HTTPS", "LOCAL_BINANCE_ARCHIVES_PROVENANCE_UNVERIFIED")):
        raise ValueError("Expected registered Binance Spot source")
    panels = {}
    for symbol in SYMBOLS:
        rows = hourly[symbol]
        check_development(rows, "60")
        instrument = reference["instruments"][symbol]
        if (metadata["instruments"][symbol] != instrument or len(instrument["files"]) != 19
                or digest(rows) != instrument["hourly_sha256"]):
            raise ValueError(f"{symbol} archive or hourly digest differs from registration")
        grouped = four_hour(rows)
        if digest(grouped) != previous["four_hour_sha256"][symbol]:
            raise ValueError(f"{symbol} four-hour digest differs from registration")
        panels[symbol, "60"] = rows
        panels[symbol, "240"] = grouped
    return panels


def breakout_signals(prefix, timeframe, hypothesis, rules):
    if timeframe not in INTERVALS or hypothesis != HYPOTHESIS:
        raise ValueError("Unregistered breakout path")
    if any(row["closed"] is not True for row in prefix):
        raise ValueError("Signal inputs must be closed")
    if len(prefix) <= 20:
        return []
    frame = indicators(prefix)
    candidates = frame.index[frame.close > frame.resistance]
    signals = []
    for i in candidates:
        bar = prefix[i]
        prior_atr = D(frame.atr.iloc[i - 1])
        high, low, close = (D(bar[k]) for k in ("high", "low", "close"))
        prior_close = D(prefix[i - 1]["close"])
        tr = max(high - low, abs(high - prior_close), abs(low - prior_close))
        if not prior_atr.is_finite() or prior_atr <= 0 or tr < D("1.25") * prior_atr:
            continue
        stop = ((close - 2 * prior_atr) / rules.tick).to_integral_value(rounding=ROUND_FLOOR) * rules.tick
        target = ((close + 4 * prior_atr) / rules.tick).to_integral_value(rounding=ROUND_CEILING) * rules.tick
        if 0 < stop < close < target:
            signals.append(dict(strategy=hypothesis, type="BUY", status="confirmed",
                                candle_time=bar["time"], timestamp=bar["time"] + seconds(timeframe),
                                reference_price=bar["close"], risk_estimates=dict(stop=str(stop), target=str(target))))
    return signals


def audit_prefixes(rows, symbol, timeframe):
    rules = rules_for(symbol)
    signals = breakout_signals(rows, timeframe, HYPOTHESIS, rules)
    for _, start, end in fold_windows(timeframe):
        for cutoff in (start + 1, (start + end) // 2, end):
            actual = breakout_signals(rows[:cutoff], timeframe, HYPOTHESIS, rules)
            expected = [s for s in signals if s["candle_time"] <= rows[cutoff - 1]["time"]]
            if actual != expected:
                raise ValueError("Signal, timestamp or protection changed under prefix replay")
    return {s["candle_time"]: s["timestamp"] for s in signals}


def audit_timestamps(report, origins):
    step = seconds(report["timeframe"])
    for fold, window in zip(report["folds"], fold_dates(), strict=True):
        last_exit_open = -1
        for trade in fold["trades"]:
            entry, exit_open = trade["entry_open_time"], trade["exit_bar_open_time"]
            reason = trade["reason"]
            if reason in ("STOP_GAP", "TARGET_GAP", "MAX_HOLD"):
                available, precision = exit_open, "NEXT_OPEN"
            elif reason in ("STOP", "TARGET", "STOP_FIRST_AMBIGUOUS", "FOLD_CLOSE_OPTIMISTIC"):
                available, precision = exit_open + step, "BAR_CLOSE_AVAILABILITY"
            else:
                raise ValueError("Unregistered breakout exit")
            if (origins.get(trade["signal_time"]) != entry or trade["signal_time"] + step != entry
                    or not window["first_open"] <= entry <= exit_open < window["end_exclusive"]
                    or entry <= last_exit_open or exit_open - entry > 16 * step
                    or (precision == "NEXT_OPEN" and exit_open <= entry)
                    or (reason == "MAX_HOLD" and exit_open != entry + 16 * step)
                    or (reason == "FOLD_CLOSE_OPTIMISTIC" and available != window["end_exclusive"])
                    or available > window["end_exclusive"] or trade["exit_event_time"] != available
                    or trade["exit_time_precision"] != precision):
                raise ValueError("Noncausal breakout fill or overlapping positions")
            last_exit_open = exit_open


def evaluate(panels, previous):
    paths, contrasts = {}, {}
    for (symbol, timeframe), rows in panels.items():
        name = f"{symbol}/{timeframe}"
        origins = audit_prefixes(rows, symbol, timeframe)
        scenarios = {}
        for label, multiplier in (("base", 1), ("double", 2)):
            report, model, spread = portfolio_paths(rows, symbol, timeframe, HYPOTHESIS, multiplier,
                                                   signal_provider=breakout_signals)
            audit_timestamps(report, origins)
            metrics, panel = summarize_path(rows, symbol, timeframe, report, model, spread)
            passive = previous["paths"][name + "/EMA_REGIME"][label]["benchmarks_pct"]
            if any(D(metrics["benchmarks_pct"][c]) != D(v) for c, v in passive.items()):
                raise ValueError("Passive benchmark differs from previous study on identical data")
            pnl = [D(f["net_usdt"]) for f in metrics["folds"]]
            remaining = sum(pnl) - max(pnl)
            metrics["without_best_fold_net_usdt"] = str(remaining)
            metrics["without_best_fold_return_pct"] = str(100 * remaining / (2 * CAPITAL))
            scenarios[label] = metrics
            if label == "base":
                contrasts.update({name + "/" + c: panel[c] for c in COMPARATORS})
        scenarios["causality_audit"] = dict(prefix_comparisons=9, development_signal_origins=len(origins),
                                            both_scenarios_fill_timestamps_checked=True)
        paths[name] = scenarios

    inference = assess_paths(paths, contrasts, expected_count=8, provenance_verified=True)
    for path in paths.values():
        path["gates"]["causality"] = True  # A failed audit raises before inference.
    for test in inference["tests"]:
        test["two_study_bonferroni_sensitivity_p"] = [min(1, 2 * p) for p in test["adjusted_p"]]
    candidates = [k for k, v in paths.items() if v["decision"] == "INDEPENDENT_REVIEW_ONLY"]
    return dict(status="EXPLORATORY", decision="INDEPENDENT_REVIEW_ONLY" if candidates else NO_TRADE,
                independent_review_candidates=candidates, paths=paths, statistics=inference)


def run(folder=None):
    sources = [*sorted((ROOT / "moex_intelligence/crypto").glob("*.py")), Path(__file__).resolve(),
               ROOT / "scripts/run_trend_1h4h.py", ROOT / "scripts/run_coliseum_v02.py"]
    result = dict(code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  implementation_sha256=digest({str(p.relative_to(ROOT)): fingerprint(p) for p in sources}),
                  preregistration_commit=REGISTRATION, protocol_sha256=fingerprint(DIRECTORY / "PROTOCOL.md"),
                  python=platform.python_version(), packages={n: version(n) for n in ("numpy", "pandas", "httpx")},
                  seed=20261105, development_folds=fold_dates(), reserved_interval=[DEV_END, SEALED_END],
                  sealed_evaluated=False, validated=False, previous_paths=8, new_paths=4,
                  primary_contrasts=8, previous_primary_contrasts=16)
    try:
        previous = registered_inputs()
        result["previous_study_reference_only"] = {
            f"{s}/{t}": previous["paths"][f"{s}/{t}/EMA_REGIME"]["base"]["benchmarks_pct"]
            for s in SYMBOLS for t in INTERVALS}
        hourly, metadata = binance_history(folder)
        panels = verified_panels(hourly, metadata, previous)
        computed = evaluate(panels, previous)
        result.update(computed, archive_transport="HTTPS" if folder is None else "LOCAL_FILES",
                      provenance_basis="Publisher checksums and preregistered archive, 1h and 4h fingerprints",
                      source=metadata["instruments"],
                      four_hour_sha256=previous["four_hour_sha256"], matched_registered_archives=38)
    except (ValueError, OSError, ArithmeticError, zipfile.BadZipFile) as exc:
        result.update(status="NOT EVALUABLE", decision=NO_TRADE, error=str(exc), statistics=None,
                      paths={f"{s}/{t}": dict(status="NOT EVALUABLE", base=None, double=None)
                             for s in SYMBOLS for t in INTERVALS})
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archive-dir", type=Path, help="Original registered ZIP and CHECKSUM pairs")
    cli.add_argument("--output", type=Path, required=True, help="New aggregate JSON file")
    args = cli.parse_args()
    if args.output.exists():
        cli.error("--output must be a new file")
    result = run(args.archive_dir)
    with args.output.open("x", encoding="utf-8") as destination:
        json.dump(result, destination, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        destination.write("\n")
    print(result["status"], result["decision"])
    if "error" in result:
        print(result["error"], file=sys.stderr)
    sys.exit(0 if result["status"] == "EXPLORATORY" else 2)
