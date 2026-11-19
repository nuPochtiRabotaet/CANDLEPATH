"""Breakout verification on explicitly synthetic bars only; no economic evidence."""
from copy import deepcopy
from decimal import Decimal as D

import pytest

from scripts import run_volatility_breakout as study
from moex_intelligence.crypto.coliseum_catalog import digest
from moex_intelligence.crypto.costs import CostModel, FeeSchedule, ExecutionAssumptions, budget_quantity, estimate
from moex_intelligence.crypto.paper_path_research import _quote_at
from moex_intelligence.crypto.trend_history import START, DEV_END, SEALED_END, SYMBOLS, four_hour
from moex_intelligence.crypto.trend_research import CAPITAL, rules_for


def flat(i, price=100., step=3600):
    return dict(time=START + i * step, open=price, high=price + 1, low=price - 1,
                close=price, volume=1., closed=True)


@pytest.mark.parametrize("tf", ["60", "240"])
def test_boundaries_use_closed_prior_channel_and_wilder_atr(tf):
    step = int(tf) * 60
    rows = [flat(i, step=step) for i in range(20)]
    # Previous ATR=2. Current TR=2.50 exactly; including current TR in ATR
    # would reject, including current high in Donchian would also reject.
    signal_bar = dict(flat(20, step=step), high=102., low=99.5, close=101.5)
    def found(last):
        return study.breakout_signals(rows + [last], tf, study.HYPOTHESIS, rules_for("BTCUSDT"))
    signal, = found(signal_bar)
    levels = signal["risk_estimates"]
    assert (D(levels["stop"]), D(levels["target"])) == (D("97.50"), D("109.50"))
    assert rules_for("BTCUSDT").levels_on_tick(levels["stop"], levels["target"])
    assert signal["timestamp"] == signal_bar["time"] + step
    assert not found(dict(signal_bar, close=101.))  # equal prior high
    assert not found(dict(signal_bar, low=99.51))  # TR just below threshold
    gap = dict(signal_bar, open=103., high=103.5, low=103., close=103.5)
    assert found(gap)  # high-low < threshold, gap makes TR sufficient
    with pytest.raises(ValueError, match="closed"):
        found(dict(signal_bar, closed=False))
    rows.pop(0)
    assert not found(signal_bar)  # 19 preceding highs


def test_expiring_channel_and_future_shock_cannot_rewrite_signal():
    rows = [flat(i) for i in range(21)]
    rows[0]["high"] = 200.
    rows.append(dict(flat(21), high=140., close=120.))
    def run(bars):
        return study.breakout_signals(bars, "60", study.HYPOTHESIS, rules_for("BTCUSDT"))
    original = run(rows)
    assert [s["candle_time"] for s in original] == [rows[-1]["time"]]
    expected_atr = (101 + 13 * 2) / 14  # first range 101, followed by 13 ranges of 2
    for _ in range(7):
        expected_atr = (13 * expected_atr + 2) / 14
    assert float(original[0]["risk_estimates"]["stop"]) == pytest.approx(120 - 2 * expected_atr, abs=.01)
    extended = run(rows + [dict(flat(22), high=9000., close=8900.)])
    assert [s for s in extended if s["timestamp"] <= rows[-1]["time"] + 3600] == original


def hourly_market(price):
    rows = []
    for i in range(576 * 24):
        phase = i % 96
        bar = flat(i, price=price + 10 if 4 <= phase < 12 else price)
        if phase == 3:
            bar.update(close=price + 10, high=price + 12)
        rows.append(bar)
    return rows


@pytest.fixture(scope="module")
def synthetic_inputs():
    hourly, reference, quadruple, baselines = {}, {}, {}, {}
    for symbol, price in zip(SYMBOLS, [10000., 2000.], strict=True):
        hourly[symbol] = hourly_market(price)
        reference[symbol] = dict(files={str(i): f"SYNTHETIC-{i}" for i in range(19)},
                                 hourly_sha256=digest(hourly[symbol]), bars=576 * 24)
        quadruple[symbol] = digest(four_hour(hourly[symbol]))
        rules = rules_for(symbol)
        # All three folds start and end on the same flat synthetic price.
        for tf in study.INTERVALS:
            path = {}
            for tag, m in (("base", 1), ("double", 2)):
                quote = _quote_at(price, 4 * m)
                model = CostModel(FeeSchedule(taker=str(D(".001") * m)), ExecutionAssumptions(str(5 * m)))
                passive = {"USDT": "0"}
                for label, cap in (("HOLD_25", D(".25")), ("HOLD_100", D(1))):
                    qty = budget_quantity(CAPITAL * cap, quote, rules.step, model, "total")
                    debit = estimate("BUY", qty, quote, model).cash_delta
                    credit = estimate("SELL", qty, quote, model).cash_delta
                    passive[label] = str(100 * (debit + credit) / CAPITAL)
                path[tag] = dict(benchmarks_pct=passive)
            baselines[f"{symbol}/{tf}/EMA_REGIME"] = path
    previous = dict(data=dict(instruments=reference, source="BINANCE_PUBLIC_DATA_HTTPS"),
                    four_hour_sha256=quadruple, paths=baselines)
    return hourly, previous


def test_registration_and_fail_closed_on_source_failure(tmp_path, monkeypatch):
    reference = study.registered_inputs()
    assert reference["data"]["source"] == "BINANCE_PUBLIC_DATA_HTTPS"
    assert len(reference["paths"]) == 8 and len(reference["statistics"]["columns"]) == 16
    called = []
    def unavailable(folder):
        called.append(folder)
        raise OSError("synthetic transport outage")
    monkeypatch.setattr(study, "binance_history", unavailable)
    monkeypatch.setattr(study, "evaluate", lambda *args: pytest.fail("must stop before outcomes"))
    result = study.run(tmp_path)
    assert called == [tmp_path] and result["status"] == "NOT EVALUABLE"
    assert len(result["paths"]) == 4 and all(s["base"] is None for s in result["paths"].values())
    assert result["statistics"] is None and result["reserved_interval"] == [DEV_END, SEALED_END]


@pytest.mark.parametrize("fault", ["venue", "archive", "hourly", "4h", "duplicate", "missing", "sealed"])
def test_integrity_before_any_replay(synthetic_inputs, fault):
    hourly, previous = synthetic_inputs
    rows = dict(hourly)
    meta = deepcopy(previous["data"])
    symbol = SYMBOLS[1]
    if fault == "venue":
        meta["source"] = "BYBIT_V5_PUBLIC_HTTPS"
    elif fault == "archive":
        meta["instruments"][symbol]["files"]["5"] = "ALTERED"
    elif fault == "hourly":
        rows[symbol] = [dict(hourly[symbol][0], volume=0.)] + hourly[symbol][1:]
    elif fault == "4h":
        previous = dict(previous, four_hour_sha256={**previous["four_hour_sha256"], symbol: "wrong"})
    elif fault == "duplicate":
        rows[symbol] = hourly[symbol][:1] + hourly[symbol][:-1]
    elif fault == "missing":
        rows[symbol] = hourly[symbol][1:]
    else:
        rows[symbol] = hourly[symbol] + [dict(hourly[symbol][-1], time=DEV_END)]
    with pytest.raises(ValueError):
        study.verified_panels(rows, meta, previous)


def test_breakout_replay_twice_accounting_and_adjustment(synthetic_inputs, tmp_path, monkeypatch):
    hourly, previous = synthetic_inputs
    monkeypatch.setenv("MOEX_DATA_DIR", str(tmp_path / "unused"))
    # Registered production manifest remains immutable; only this unit-level
    # fixture uses a private synthetic digest manifest.
    meta = dict(previous["data"], source="LOCAL_BINANCE_ARCHIVES_PROVENANCE_UNVERIFIED")
    panels = study.verified_panels(hourly, meta, previous)
    first = study.evaluate(panels, previous)
    assert first == study.evaluate(panels, previous)
    assert not (tmp_path / "unused").exists()
    assert len(first["paths"]) == 4 and len(first["statistics"]["columns"]) == 8
    assert first["statistics"]["observations"] == 531
    for t, b in zip(first["statistics"]["tests"], (3, 7, 14), strict=True):
        assert t["block"] == b and t["replicates"] == 1999
        assert len(t["lower"]) == len(t["upper"]) == len(t["adjusted_p"]) == 8
        assert t["two_study_bonferroni_sensitivity_p"] == [min(1, 2*p) for p in t["adjusted_p"]]
    for path in first["paths"].values():
        for m in ("base", "double"):
            r = path[m]
            assert r["trades"] == sum(f["trade_count"] for f in r["folds"]) > 0
            net = D(r["net_pnl"])
            costs = {k: D(v) for k, v in r["modeled_costs_usdt"].items()}
            gross = costs.pop("gross_pnl")
            assert abs(gross - sum(costs.values()) - net) < D("1e-8")
            folds = [D(f["net_usdt"]) for f in r["folds"]]
            assert abs(net - sum(folds)) < D("1e-8")
            assert D(r["without_best_fold_net_usdt"]) == sum(folds) - max(folds)


def test_no_local_timestamp_relabeling():
    dates = study.fold_dates()
    entry = dates[0]["first_open"]
    trade = dict(signal_time=entry - 3600, entry_open_time=entry, exit_bar_open_time=entry,
                 exit_event_time=entry + 3600, exit_time_precision="BAR_CLOSE_AVAILABILITY",
                 reason="STOP_FIRST_AMBIGUOUS")
    report = dict(timeframe="60", folds=[dict(trades=[trade]), dict(trades=[]), dict(trades=[])])
    origins = {entry - 3600: entry}
    study.audit_timestamps(report, origins)
    trade["exit_event_time"] = entry
    with pytest.raises(ValueError, match="Noncausal"):
        study.audit_timestamps(report, origins)
    trade.update(reason="STOP_GAP", exit_time_precision="NEXT_OPEN", entry_open_time=entry-3600)
    with pytest.raises(ValueError, match="Noncausal"):
        study.audit_timestamps(report, origins)


@pytest.mark.parametrize("reason", ["STOP_FIRST_AMBIGUOUS", "STOP_GAP", "OPEN_BELOW_STOP"])
def test_registered_signal_through_next_open_and_protection(reason):
    rows = [flat(i) for i in range(576 * 24)]
    _, origin, _ = next(study.fold_windows("60"))
    rows[origin].update(high=104., low=99., close=102.)
    if reason == "STOP_FIRST_AMBIGUOUS":
        rows[origin + 1].update(open=102., high=112., low=97., close=102.)
    elif reason == "STOP_GAP":
        rows[origin + 1].update(open=102., high=103., low=101., close=102.)
        rows[origin + 2].update(open=97., high=99., low=96., close=97.)
    else:
        rows[origin + 1].update(open=97., high=100., low=96., close=97.)
    report, _, _ = study.portfolio_paths(rows, "BTCUSDT", "60", study.HYPOTHESIS, 1,
                                         signal_provider=study.breakout_signals)
    fold = report["folds"][0]
    if reason == "OPEN_BELOW_STOP":
        assert fold["events"]["rejected_entry"] >= 1 and not fold["trades"]
        return
    trade = fold["trades"][0]
    assert trade["entry_open_time"] == rows[origin + 1]["time"]
    assert trade["reason"] == reason
    assert D(trade["exit_reference_price"]) == (98 if reason == "STOP_FIRST_AMBIGUOUS" else 97)
    assert trade["exit_event_time"] == rows[origin + 2]["time"]
    assert D(trade["entry_total_debit"]) <= D(2500)
    assert D(trade["base_quantity"]) % rules_for("BTCUSDT").step == 0


def test_entry_below_minimum_notional():
    from moex_intelligence.crypto.paper_path_research import _buy_for_cash
    # Even the maximum 100 base units cost less than the assumed minimum 10 USDT.
    order = _buy_for_cash(CAPITAL, D("0.05"), D("0.03"), 4, CostModel(), rules_for("BTCUSDT"))
    assert order is None
