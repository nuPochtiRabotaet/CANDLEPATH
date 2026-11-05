"""Exploratory, dependence-aware statistical diagnostics for Coliseum.

Requires aligned UTC daily *after-cost liquidation-equity changes* from the
research replay. Never infers p-values from three fold aggregates, never
scores the sealed holdout, and never permits automated promotion.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import math

import numpy as np

VERSION = "coliseum-statistics-0.2.1"
CAPITAL = Decimal("10000")


def _decimal(value, label):
    try:
        if type(value) not in (str, int, float, Decimal):
            raise ValueError(label)
        result = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if not result.is_finite():
        raise ValueError(f"Nonfinite {label}")
    return result


def _daily_panel(study):
    """Validate a candidate-by-day panel; return full UTC-day P&L only."""
    if not isinstance(study, dict) or not isinstance(study.get("results"), dict):
        raise ValueError("Missing frozen study results")
    paper = study["results"].get("PAPER")
    if not isinstance(paper, dict) or not paper:
        raise ValueError("PAPER result roster required")
    names = sorted(paper)
    master_keys = None
    fold_slices = None
    panel = []
    discarded = 0
    for name in names:
        record = paper[name]
        folds = record.get("folds") if isinstance(record, dict) else None
        if not isinstance(folds, list) or len(folds) != 3:
            raise ValueError(f"{name}: three folds required")
        keys, daily_pnl, lengths = [], [], []
        last_date_by_fold = {}
        discarded_here = 0
        for index, fold in enumerate(folds, 1):
            if fold.get("fold") != index:
                raise ValueError(f"{name}: invalid fold ordering")
            marks = fold.get("daily")
            if not isinstance(marks, list) or not marks:
                raise ValueError(f"{name}: missing daily marked-equity telemetry")
            total = Decimal(0)
            full_in_fold = 0
            for mark in marks:
                if not isinstance(mark, dict):
                    raise ValueError(f"{name}: malformed daily mark")
                day = mark.get("day")
                if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                    raise ValueError(f"{name}: malformed UTC day")
                bars = mark.get("bars")
                if type(bars) is not int or not 1 <= bars <= 288:
                    raise ValueError(f"{name}: invalid bars in UTC day")
                if index in last_date_by_fold and day <= last_date_by_fold[index]:
                    raise ValueError(f"{name}: duplicate/out-of-order UTC day")
                last_date_by_fold[index] = day
                pnl = _decimal(mark.get("pnl_usdt"), f"{name} daily P&L")
                total += pnl
                if bars == 288:
                    keys.append((index, day))
                    daily_pnl.append(float(pnl))
                    full_in_fold += 1
                else:
                    discarded_here += 1
            expected = _decimal(fold.get("net_return_pct"), f"{name} fold return") * CAPITAL / 100
            if abs(total - expected) > Decimal("0.01"):
                raise ValueError(f"{name}: daily marks do not reconcile with fold P&L")
            lengths.append(full_in_fold)
        if master_keys is None:
            master_keys, fold_slices = keys, lengths
            discarded = discarded_here
        elif master_keys != keys or fold_slices != lengths or discarded != discarded_here:
            raise ValueError(f"{name}: misaligned daily marked-equity series")
        panel.append(daily_pnl)
    return names, np.asarray(panel, dtype=float), fold_slices, discarded


def _correlation_clusters(names, values, threshold):
    """Absolute Pearson return-correlation components; flat series omitted."""
    n = len(names)
    parent = list(range(n))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    std = values.std(axis=1) if values.shape[1] else np.zeros(n)
    valid = np.flatnonzero(std > 1e-12)
    linked = 0
    if values.shape[1] >= 3 and len(valid) >= 2:
        corr = np.corrcoef(values[valid])
        for a, ia in enumerate(valid):
            for b in range(a + 1, len(valid)):
                if abs(float(corr[a, b])) >= threshold:
                    parent[root(int(ia))] = root(int(valid[b]))
                    linked += 1
    groups = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(names[i])
    return dict(threshold=threshold,
                connected_pairs=linked,
                groups=sorted((sorted(g) for g in groups.values() if len(g) > 1),
                              key=lambda g: (-len(g), g[0])),
                flat_candidates=[names[i] for i in range(n) if std[i] <= 1e-12])


def evaluate_statistics(study, *, seed=20261105, replicates=999,
                        block_days=3, min_full_days=120, correlation_threshold=.85):
    """Report joint-block max-T *exploratory* p-values when panel is sufficient.

    The same circular day-block indices are drawn for all candidates, within
    each independent-capital development fold; thus cross-candidate dependence
    is preserved. Null-centered statistics are studentized by original daily
    standard deviation. Block length/thresholds must be preregistered before
    looking at further data. No inference on an unverified one-month archive.
    """
    if type(seed) is not int or type(replicates) is not int or replicates < 199:
        raise ValueError("Seed integer and >=199 resamples required")
    if type(block_days) is not int or not 2 <= block_days <= 30:
        raise ValueError("Block size must be 2..30 UTC days")
    if type(min_full_days) is not int or min_full_days < 120:
        raise ValueError("Minimum full UTC days cannot be weakened below 120")
    if not isinstance(correlation_threshold, (float, int)) or not .5 <= correlation_threshold <= .99:
        raise ValueError("Invalid correlation threshold")
    names, values, fold_lengths, partials = _daily_panel(study)
    n_days = values.shape[1]
    clusters = _correlation_clusters(names, values, float(correlation_threshold))
    result = dict(version=VERSION, mode="EXPLORATORY_DEV_ONLY_NO_PROMOTION",
        candidate_count=len(names), full_utc_days=n_days,
        partial_days_per_candidate_discarded=partials,
        fold_full_utc_days=fold_lengths,
        correlation=clusters,
        block_days=block_days, seed=seed, bootstrap_replicates=replicates,
        min_full_days=min_full_days,
        final_holdout_evaluated=False, multiple_testing_family=len(names),
        independent_validation=False, production_integrations=0,
        statistical_acceptance=False,
        note="Correlated strategies and short/uncertain history prevent alpha claims; p-values, if provided, are exploratory, not proof of edge.")
    if (n_days < min_full_days or min(fold_lengths) < block_days or
            study.get("source") not in ("VERIFIED_PUBLIC_ARCHIVE", "VERIFIED_LOCAL_ARCHIVE")):
        reasons = []
        if n_days < min_full_days: reasons.append("INSUFFICIENT_COMPLETE_DAYS")
        if min(fold_lengths) < block_days: reasons.append("FOLD_TOO_SHORT_FOR_BLOCKS")
        if study.get("source") not in ("VERIFIED_PUBLIC_ARCHIVE", "VERIFIED_LOCAL_ARCHIVE"):
            reasons.append("UNVERIFIED_SOURCE_LABEL")
        result.update(inference="NOT_COMPUTED", blockers=reasons, adjusted_p_values=None)
        return result
    # A trusted source *label* still needs external provenance attestation.
    rng = np.random.default_rng(seed)
    n = len(names)
    offsets = np.cumsum([0, *fold_lengths])
    centered = values.copy()
    for fi, m in enumerate(fold_lengths):
        a, b = offsets[fi:fi + 2]
        centered[:, a:b] -= values[:, a:b].mean(axis=1, keepdims=True)
    std = values.std(axis=1, ddof=1)
    denom = std / math.sqrt(n_days)
    valid = denom > 1e-12
    observed = np.full(n, -np.inf, dtype=float)
    observed[valid] = values[valid].mean(axis=1) / denom[valid]
    above = np.zeros(n, dtype=int)
    max_above = np.zeros(n, dtype=int)
    sampled_raw_means = np.empty((replicates, n), dtype=float)
    for iteration in range(replicates):
        picks = []
        for fi, length in enumerate(fold_lengths):
            a = int(offsets[fi]); b = int(offsets[fi + 1])
            selected = []
            while len(selected) < length:
                start = int(rng.integers(a, b))
                selected.extend(a + (start - a + j) % length for j in range(block_days))
            picks.extend(selected[:length])
        sampled_raw_means[iteration] = values[:, picks].mean(axis=1)
        null = centered[:, picks].mean(axis=1)
        sampled = np.full(n, -np.inf)
        sampled[valid] = null[valid] / denom[valid]
        max_stat = max(sampled)
        above += sampled >= observed
        max_above += max_stat >= observed
    p_individual = {}
    p_adjusted = {}
    for idx, name in enumerate(names):
        p_individual[name] = round((above[idx] + 1) / (replicates + 1), 6) if valid[idx] and observed[idx] > 0 else None
        p_adjusted[name] = round((max_above[idx] + 1) / (replicates + 1), 6) if valid[idx] and observed[idx] > 0 else None
    lower, upper = np.quantile(sampled_raw_means, [.05, .95], axis=0)
    descriptive_intervals = {name: [round(float(lower[i]), 6), round(float(upper[i]), 6)]
                             for i, name in enumerate(names)}
    result.update(inference="COMPUTED_EXPLORATORY_ONLY", blockers=["SOURCE_PROVENANCE_REQUIRES_EXTERNAL_ATTESTATION", "INDEPENDENT_OUT_OF_SAMPLE_NOT_EVALUATED", "REGIME_STRATIFICATION_NOT_EVALUATED"],
                  unadjusted_p_values=p_individual, adjusted_p_values=p_adjusted,
                  exploratory_90pct_daily_pnl_interval_usdt=descriptive_intervals,
                  interval_caveat="Percentile blocks are descriptive and not simultaneous post-selection confidence intervals",
                  method="Within-fold synchronized circular-day-block centered max-T bootstrap; one-sided positive mean daily net P&L; shared draws preserve candidate dependence")
    return result
