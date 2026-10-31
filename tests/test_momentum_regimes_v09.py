"""Volatility-regime diagnostics must be causal and conserve paired scores."""
from dataclasses import replace
import math
import time

import pytest

from moex_intelligence.crypto.market import Candle
from moex_intelligence.crypto.momentum_evaluation import compare_momentum_to_rw
from moex_intelligence.crypto.regime_research import (
    REGIMES, REGIME_VERSION, classify_past_volatility)

STEP = 60


def prices(older, recent):
    result = [100.0]
    for ret in [*older, *recent]:
        result.append(result[-1] * math.exp(ret))
    assert len(result) == 120
    return result


def candles(n=1600):
    start = int(time.time()//STEP)*STEP-(n+10)*STEP
    result = []
    for i in range(n):
        scale = (.02 if i < 400 else .35 if i < 800 else
                 .04 if i < 1100 else .8)
        price = 100 + .003*i + scale*math.sin(i*.45)
        result.append(Candle(start+i*STEP,price,price+.9,price-.9,
                             price,5.,True))
    return result


def test_three_regimes_are_defined_only_by_prior_returns():
    stable=prices([0.] * 99,[0.] * 20)
    expanding=prices([.0001,-.0001] * 49+[.0001], [.003,-.003] * 10)
    contracting=prices([.003,-.003] * 49+[.003], [.0001,-.0001] * 10)
    assert classify_past_volatility(stable) == "STABLE"
    assert classify_past_volatility(expanding) == "EXPANDING"
    assert classify_past_volatility(contracting) == "CONTRACTING"
    assert REGIMES == ("EXPANDING","STABLE","CONTRACTING")
    assert REGIME_VERSION.startswith("trailing-rms-ratio")


@pytest.mark.parametrize("bad", [
    [], [100.]*119, [100.]*121,
    [100.]*119+[0.], [100.]*119+[float("nan")],
    [100.]*119+[float("inf")],
    [100.]*119+[10**400],
    [100.]*119+["100"],
    [100.]*119+[1000.],
])
def test_classifier_rejects_invalid_or_future_looking_windows(bad):
    with pytest.raises(ValueError):
        classify_past_volatility(bad)


def test_every_fold_regime_partition_reconciles_to_original_paired_scores():
    result=compare_momentum_to_rw(candles(),"BTCUSDT","1")
    assert result.status=="EVALUATED_DEVELOPMENT_ONLY"
    assert result.regime_version==REGIME_VERSION
    assert result.final_holdout_evaluated is False
    for fold in result.folds:
        assert fold.origins >= 30
        for score in fold.horizons:
            strata=[s for s in fold.volatility_regimes
                    if s.horizon_candles==score.horizon_candles]
            assert sum(s.observations for s in strata)==score.observations
            assert sum(s.nonflat_actuals for s in strata)==score.nonflat_actuals
            assert sum(s.direction_hits for s in strata)==score.direction_hits
            assert set(s.regime for s in strata).issubset(set(REGIMES))
            n=score.observations
            assert sum(s.observations*s.rw_mae for s in strata)/n == pytest.approx(
                score.rw_mae,rel=1e-9,abs=1e-10)
            assert sum(s.observations*s.candidate_mae for s in strata)/n == pytest.approx(
                score.candidate_mae,rel=1e-9,abs=1e-10)
            assert sum(s.observations*s.rw_coverage for s in strata)/n == pytest.approx(
                score.rw_coverage)
            assert sum(s.observations*s.candidate_coverage for s in strata)/n == pytest.approx(
                score.candidate_coverage)
            assert all(s.sample_sufficient == (
                s.observations>=30 and s.nonflat_actuals>=30) for s in strata)


def test_changing_sealed_final_cannot_change_any_regime_score():
    data=candles()
    original=compare_momentum_to_rw(data,"BTCUSDT","1")
    start=math.floor(len(data)*.8)
    changed=data[:start]+[replace(
        bar,open=bar.open*1.1,high=bar.high*1.1,
        low=bar.low*1.1,close=bar.close*1.1)
        for bar in data[start:]]
    rerun=compare_momentum_to_rw(changed,"BTCUSDT","1")
    assert original.folds==rerun.folds
    assert original.final_holdout_sha256!=rerun.final_holdout_sha256
    assert original.final_holdout_evaluated is False
    assert rerun.final_holdout_evaluated is False


def test_classifier_receives_only_same_120_causal_prices_as_candidate(monkeypatch):
    import moex_intelligence.crypto.momentum_evaluation as module
    seen=[]
    original=module.classify_past_volatility
    def capture(window):
        if not seen:
            seen.append(tuple(window))
        return original(window)
    monkeypatch.setattr(module,"classify_past_volatility",capture)
    data=candles()
    result=module.compare_momentum_to_rw(data,"BTCUSDT","1")
    start=result.folds[0].validation_start_index
    assert len(seen)==1
    assert seen[0]==tuple(c.close for c in data[start-120:start])
    assert data[start].close not in seen[0]
