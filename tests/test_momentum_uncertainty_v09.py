"""Uncertainty annotations for fixed, research-only directional candidate."""
import json
import math
import pytest

from moex_intelligence.crypto.momentum_evaluation import _wilson_95, compare_momentum_to_rw
from tests.test_momentum_candidate_v09 import series


@pytest.mark.parametrize("successes,trials",[(0,0),(0,1),(1,1),(50,100),(100,100),(10,30)])
def test_wilson_is_finite_bounded_and_contains_observed_proportion(successes,trials):
    low,high=_wilson_95(successes,trials)
    if not trials:
        assert low is None and high is None
    else:
        assert 0<=low<=successes/trials<=high<=1
        assert all(math.isfinite(x) for x in (low,high))


@pytest.mark.parametrize("successes,trials",[(-1,10),(3,2),(1,-1),(True,2),(1,True)])
def test_wilson_rejects_invalid_counts(successes,trials):
    with pytest.raises(ValueError):
        _wilson_95(successes,trials)


def test_perfect_synthetic_trend_is_not_presented_as_certain():
    report=compare_momentum_to_rw(series(mode="trend"),"BTCUSDT","15")
    assert report.status=="EVALUATED_DEVELOPMENT_ONLY"
    for fold in report.folds:
        for point in fold.horizons:
            assert point.direction_hits==point.nonflat_actuals
            assert point.direction_calls==point.nonflat_actuals
            assert point.candidate_direction_hit_rate==1
            assert 0<point.direction_wilson_95_lower<1
            assert point.direction_wilson_95_upper==1
            assert point.direction_sample_sufficient is True
    json.dumps(report.as_dict(),allow_nan=False)


def test_flat_market_returns_null_confidence_not_fake_zero():
    report=compare_momentum_to_rw(series(mode="flat"),"ETHUSDT","15")
    for fold in report.folds:
        for point in fold.horizons:
            assert point.direction_hits==point.direction_calls==0
            assert point.direction_wilson_95_lower is None
            assert point.direction_wilson_95_upper is None
            assert point.direction_sample_sufficient is False
            assert point.candidate_direction_hit_rate is None


def test_sealed_holdout_remains_unscored():
    report=compare_momentum_to_rw(series(),"SOLUSDT","15")
    assert report.final_holdout_evaluated is False
    assert "descriptive" in report.note
    assert "not imply independent" in report.note
