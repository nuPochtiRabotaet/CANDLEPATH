"""Synthetic validation of dependence analysis and fail-closed evidence gates."""
from datetime import date, timedelta
from decimal import Decimal
import pytest

from moex_intelligence.crypto.coliseum_statistics import evaluate_statistics
from moex_intelligence.crypto.paper_path_research import simulate_paper_paths
from .test_paper_path_research_v09 import history, plug


def fixture(days_per_fold=7, source='USER_SUPPLIED_CSV_UNVERIFIED'):
    candidates = ['alpha', 'alpha_variant', 'cash', 'opposite']
    paper = {}
    for candidate in candidates:
        folds = []
        for f in range(1, 4):
            marks = []
            for i in range(days_per_fold):
                day = (date(2026, 1, 1) + timedelta(days=(f-1)*days_per_fold+i)).isoformat()
                x = Decimal(str((i % 5 - 2) * 2))
                if candidate == 'cash': x = Decimal(0)
                if candidate == 'opposite': x = -x
                marks.append(dict(day=day, bars=288, pnl_usdt=str(x)))
            folds.append(dict(fold=f,
                net_return_pct=str(sum(Decimal(m['pnl_usdt']) for m in marks) / 100),
                daily=marks))
        paper[candidate] = dict(folds=folds)
    return dict(source=source, results=dict(PAPER=paper))


def test_short_unverified_stays_blocked():
    r = evaluate_statistics(fixture())
    assert r['inference'] == 'NOT_COMPUTED'
    assert r['adjusted_p_values'] is None
    assert set(r['blockers']) == {'INSUFFICIENT_COMPLETE_DAYS', 'UNVERIFIED_SOURCE_LABEL'}
    assert ['alpha', 'alpha_variant', 'opposite'] in r['correlation']['groups']
    assert r['correlation']['flat_candidates'] == ['cash']
    assert not r['statistical_acceptance']


def test_trusted_label_long_history_deterministic_only_exploratory():
    study = fixture(days_per_fold=50, source='VERIFIED_LOCAL_ARCHIVE')
    x = evaluate_statistics(study, replicates=199)
    y = evaluate_statistics(study, replicates=199)
    assert x == y and x['inference'] == 'COMPUTED_EXPLORATORY_ONLY'
    assert set(x['adjusted_p_values']) == set(study['results']['PAPER'])
    assert x['adjusted_p_values']['cash'] is None
    assert x['statistical_acceptance'] is False
    for name, p in x['adjusted_p_values'].items():
        if p is not None:
            assert p >= x['unadjusted_p_values'][name]


def test_failed_daily_reconciliation_rejected():
    study = fixture()
    study['results']['PAPER']['alpha']['folds'][0]['daily'][0]['pnl_usdt'] = '999'
    with pytest.raises(ValueError, match='reconcile'):
        evaluate_statistics(study)


def test_misaligned_dates_rejected():
    study = fixture()
    study['results']['PAPER']['alpha']['folds'][0]['daily'][1]['day'] = '2020-01-01'
    with pytest.raises(ValueError, match='out-of-order'):
        evaluate_statistics(study)


def test_missing_daily_marks_rejected():
    study = fixture()
    del study['results']['PAPER']['alpha']['folds'][0]['daily']
    with pytest.raises(ValueError, match='missing daily'):
        evaluate_statistics(study)


def test_reduce_minimum_history_refused():
    with pytest.raises(ValueError, match='cannot be weakened'):
        evaluate_statistics(fixture(), min_full_days=30)


def test_partial_days_excluded_and_aligned():
    study = fixture()
    for r in study['results']['PAPER'].values():
        r['folds'][0]['daily'][0]['bars'] = 80
    assert evaluate_statistics(study)['full_utc_days'] == 20


def test_real_research_replay_daily_marks_opt_in_and_accounting(monkeypatch):
    plug(monkeypatch, [(140, {})])
    bars = history()
    ordinary = simulate_paper_paths(bars, 'BTCUSDT', '1')
    marked = simulate_paper_paths(bars, 'BTCUSDT', '1', collect_daily_equity=True)
    for a, b in zip(ordinary['folds'], marked['folds']):
        assert 'daily_equity' not in a
        series = b['daily_equity']
        assert series and sum(m['bars'] for m in series) == b['end_exclusive'] - b['start_index'] - 1
        assert sum(Decimal(m['pnl_usdt']) for m in series) == (
            Decimal(b['ending_cash']) - Decimal(b['starting_cash']))
        assert [m['day'] for m in series] == sorted(set(m['day'] for m in series))
        assert a['trades'] == b['trades']
    assert ordinary['final_holdout_sha256'] == marked['final_holdout_sha256']
    assert marked['final_holdout_evaluated'] is False


def test_daily_mark_opt_in_validated():
    with pytest.raises(ValueError, match='bool'):
        simulate_paper_paths(history(200), 'BTCUSDT', '1', collect_daily_equity=1)
