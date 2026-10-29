"""Reproducible, close-to-close block-bootstrap scenario simulator.

This does NOT predict future returns or model intraday execution.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
import threading
from functools import wraps
from moex_intelligence.validation import finite, integer

MAX_CELLS = 2_000_000
_slot = threading.BoundedSemaphore(1)


def bounded(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        if not _slot.acquire(blocking=False):
            raise ValueError('Another simulation is running in this process. Retry after it finishes.')
        try:
            return fn(*args, **kwargs)
        finally:
            _slot.release()
    return run


def validate_options(horizon, runs, target_pct, stop_pct, commission_pct, slippage_pct, block, seed=42,
                     drift_shift_pct=0.0, volatility_scale=1.0):
    integer(horizon, 'horizon', 1, 252)
    integer(runs, 'runs', 100, 50_000)
    integer(block, 'block', 1, 20)
    integer(seed, 'seed', 0, 1_000_000)
    if runs * (horizon + 1) > MAX_CELLS:
        raise ValueError(f'Resource limit: runs × (horizon + 1) must be <= {MAX_CELLS:,}.')
    finite(target_pct, 'target_pct', .000001, 500)
    finite(stop_pct, 'stop_pct', .000001, 99.999999)
    finite(commission_pct, 'commission_pct', 0, 9.999999)
    finite(slippage_pct, 'slippage_pct', 0, 9.999999)
    finite(drift_shift_pct, 'drift_shift_pct', -100, 100)
    finite(volatility_scale, 'volatility_scale', .1, 3)


def clean_prices(prices):
    try:
        series = pd.Series(prices, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError('Prices must all be finite positive numbers.') from exc
    if len(series) < 65 or len(series) > 10_000 or not np.isfinite(series).all() or (series <= 0).any():
        raise ValueError('65–10000 finite positive closes required; invalid rows are not dropped.')
    if isinstance(series.index, pd.DatetimeIndex) and (series.index.has_duplicates or not series.index.is_monotonic_increasing):
        raise ValueError('Prices must have unique increasing dates.')
    return series


@dataclass
class SimulationResult:
    paths: np.ndarray
    exits: np.ndarray
    net_returns: np.ndarray
    hit_target: np.ndarray
    hit_stop: np.ndarray
    still_open: np.ndarray
    exit_steps: np.ndarray
    stats: dict
    wealth_paths: np.ndarray


@bounded
def simulate(
    prices: pd.Series,
    horizon: int = 20,
    runs: int = 10_000,
    target_pct: float = 8.0,
    stop_pct: float = 5.0,
    commission_pct: float = 0.05,
    slippage_pct: float = 0.05,
    block: int = 5,
    seed: int = 42,
    drift_shift_pct: float = 0.0,
    volatility_scale: float = 1.0,
    model: str = 'block_bootstrap',
    exit_policy: str = 'barriers',
) -> SimulationResult:
    """Draw contiguous blocks of historical log returns, then classify first close crossing.

    target_pct, stop_pct, commission_pct, slippage_pct are percentage points.
    Both target/stop hits are determined by simulated *daily closing prices* only.
    Exits occur at the closing price on the first crossing, not at stop/target level.
    """
    validate_options(horizon, runs, target_pct, stop_pct, commission_pct, slippage_pct, block, seed,
                     drift_shift_pct, volatility_scale)
    series = clean_prices(prices)
    if model not in {'block_bootstrap','historical_bootstrap','gbm'}:
        raise ValueError('Unknown simulation model.')
    if exit_policy not in {'barriers','horizon'}:
        raise ValueError('exit_policy must be barriers or horizon.')

    log_returns = np.diff(np.log(series.to_numpy(dtype=float)))
    history_returns = log_returns.copy()
    log_returns = (log_returns - log_returns.mean()) * volatility_scale + log_returns.mean() + drift_shift_pct / 100 / 252
    block = min(1 if model == 'historical_bootstrap' else block, len(log_returns), horizon)
    n_blocks = int(np.ceil(horizon / block))
    rng = np.random.default_rng(seed)
    # Each batch preserves short runs of returns (not an IID shuffle of single days).
    choices = rng.integers(0, len(log_returns) - block + 1, size=(runs, n_blocks))
    idx = choices[:, :, None] + np.arange(block)[None, None, :]
    sampled = log_returns[idx].reshape(runs, -1)[:, :horizon]
    if model == 'gbm':
        # Calibrate daily LOG drift directly; no second subtraction of sigma²/2.
        rng = np.random.default_rng(seed)
        sampled = rng.normal(log_returns.mean(), log_returns.std(ddof=1), size=(runs, horizon))
    initial = float(series.iloc[-1])
    with np.errstate(over='raise', invalid='raise'):
        try:
            future = initial * np.exp(np.cumsum(sampled, axis=1))
        except FloatingPointError as exc:
            raise ValueError('Numerical overflow: inspect corporate actions or reduce scenario horizon.') from exc
    if not np.isfinite(future).all() or (future <= 0).any():
        raise ValueError('Scenario prices outside numerical range.')
    paths = np.column_stack([np.full(runs, initial), future])

    crossed_stop = future <= initial * (1 - stop_pct / 100)
    crossed_target = future >= initial * (1 + target_pct / 100)
    touched = crossed_stop | crossed_target
    if exit_policy == 'horizon':
        touched[:] = False
    any_touched = np.any(touched, axis=1)
    first = np.argmax(touched, axis=1)
    rows = np.arange(runs)
    hit_stop = any_touched & crossed_stop[rows, first]
    hit_target = any_touched & crossed_target[rows, first]
    still_open = ~any_touched
    exit_steps = np.where(any_touched, first + 1, horizon)
    exits = future[rows, exit_steps - 1]

    one_way = (commission_pct + slippage_pct) / 100
    net_returns = (exits * (1 - one_way)) / (initial * (1 + one_way)) - 1
    if not np.isfinite(net_returns).all():
        raise ValueError('Numerical overflow in returns; inspect input prices.')
    n_5 = max(1, int(np.ceil(runs * 0.05)))
    worst = np.partition(net_returns, n_5 - 1)[:n_5]
    wealth = paths / initial * (1 - one_way) / (1 + one_way)
    # Liquidation NAV until exit; proceeds remain in zero-interest cash thereafter.
    wealth[np.arange(horizon + 1)[None, :] >= exit_steps[:, None]] = np.broadcast_to((1 + net_returns)[:, None], wealth.shape)[np.arange(horizon + 1)[None, :] >= exit_steps[:, None]]
    wealth[:, 0] = 1.0  # pre-entry capital: drawdown includes transaction costs.
    drawdowns = (wealth / np.maximum.accumulate(wealth, axis=1) - 1).min(axis=1)
    historical_dd = series / series.cummax() - 1
    stats = {
        'start_price': initial,
        'history_points': len(series),
        'p_target': float(hit_target.mean()),
        'p_stop': float(hit_stop.mean()),
        'p_open': float(still_open.mean()),
        'p_loss': float((net_returns < 0).mean()),
        'mean_return': float(net_returns.mean()),
        'median_return': float(np.median(net_returns)),
        'p05_return': float(np.quantile(net_returns, .05)),
        'p95_return': float(np.quantile(net_returns, .95)),
        'cvar05_return': float(worst.mean()),
        'target_price': initial * (1 + target_pct / 100),
        'stop_price': initial * (1 - stop_pct / 100),
        'fee_per_side_pct': commission_pct + slippage_pct,
        'var95_loss': float(-np.quantile(net_returns, .05)),
        'es95_loss': float(-worst.mean()),
        'historical_volatility': float(np.std(history_returns, ddof=1) * np.sqrt(252)),
        'historical_max_drawdown': float(historical_dd.min()),
        'median_strategy_max_drawdown': float(np.median(drawdowns)),
        'p05_strategy_max_drawdown': float(np.quantile(drawdowns, .05)),
        'drift_shift_pct': drift_shift_pct,
        'volatility_scale': volatility_scale,
        'model': model,
        'exit_policy': exit_policy,
        'barriers_evaluated': exit_policy == 'barriers',
    }
    return SimulationResult(paths, exits, net_returns, hit_target, hit_stop, still_open, exit_steps, stats, wealth)


def compare_scenarios(prices, **options):
    """Sensitivity assumptions, not calibrated future regimes. Same seed in each case."""
    result = []
    for name, shift, scale in [('Historical', 0.0, 1.0), ('Downside assumption', -20.0, 1.5), ('Upside assumption', 20.0, 1.0)]:
        r = simulate(prices, **options, drift_shift_pct=shift, volatility_scale=scale)
        result.append({'scenario': name, **r.stats})
    return result
