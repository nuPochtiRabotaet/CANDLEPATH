"""Long-only research backtests: past-close signal, next-open execution, whole lots."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import numpy as np
import pandas as pd
from .validation import finite, integer


@dataclass
class BacktestResult:
    curve: pd.DataFrame
    trades: pd.DataFrame
    stats: dict


def validate_bars(frame):
    if not 3 <= len(frame) <= 10000 or not {'OPEN', 'CLOSE'} <= set(frame.columns):
        raise ValueError('3–10000 bars with OPEN and CLOSE are required.')
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.has_duplicates or not frame.index.is_monotonic_increasing or frame.index.hasnans:
        raise ValueError('Unique, ordered, valid DatetimeIndex required.')
    values = frame[['OPEN','CLOSE']].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('Missing/invalid OPEN or CLOSE; no bars silently dropped.')


def rsi(close, period=14):
    """Wilder smoothing initialized with the first period's simple averages."""
    integer(period, 'period', 2, 100)
    delta = close.diff().to_numpy()
    result = np.full(len(close), np.nan)
    if len(close) <= period:
        return pd.Series(result, index=close.index)
    gain = np.maximum(delta[1:period+1], 0).mean()
    loss = np.maximum(-delta[1:period+1], 0).mean()
    for t in range(period, len(close)):
        if t > period:
            gain = (gain*(period-1)+max(delta[t], 0))/period
            loss = (loss*(period-1)+max(-delta[t], 0))/period
        result[t] = 50 if gain == loss == 0 else 100 if loss == 0 else 100-100/(1+gain/loss)
    return pd.Series(result, index=close.index)


def signals(frame, strategy='buy_hold', fast=20, slow=50, rsi_period=14, rsi_low=30., rsi_high=70.,
            custom: Callable | None = None):
    validate_bars(frame)
    close = frame['CLOSE']
    if custom is not None:
        # Only historical prefixes are given to trusted local Python code. No eval/import from MCP/UI.
        if len(frame) > 2600:
            raise ValueError('Custom strategy prefix evaluation is limited to 2600 bars.')
        values = [custom(frame.iloc[:i+1].copy()) for i in range(len(frame))]
        if any(isinstance(x, bool) or not isinstance(x, (int, float, np.integer, np.floating)) or x not in (0, 1) for x in values):
            raise ValueError('Custom strategy must return scalar 0 or 1 for every historical prefix.')
        return pd.Series(values, index=frame.index, dtype=float)
    if strategy == 'buy_hold':
        return pd.Series(1., index=frame.index)
    if strategy in {'ma_cross','ema_cross'}:
        integer(fast, 'fast', 2, 250); integer(slow, 'slow', 3, 500)
        if fast >= slow:
            raise ValueError('fast must be less than slow')
        if strategy == 'ema_cross':
            return (close.ewm(span=fast,adjust=False,min_periods=fast).mean() > close.ewm(span=slow,adjust=False,min_periods=slow).mean()).astype(float)
        return (close.rolling(fast).mean() > close.rolling(slow).mean()).astype(float)
    if strategy == 'rsi':
        finite(rsi_low, 'rsi_low', 0, 100); finite(rsi_high, 'rsi_high', 0, 100)
        if rsi_low >= rsi_high:
            raise ValueError('rsi_low must be less than rsi_high')
        indicator = rsi(close, rsi_period)
        state, values = 0, []
        for value in indicator:
            if value <= rsi_low: state = 1
            elif value >= rsi_high: state = 0
            values.append(state)
        return pd.Series(values, index=frame.index, dtype=float)
    raise ValueError('Supported strategies: buy_hold, ma_cross, rsi; Python API also accepts custom callable.')


def backtest(frame, strategy='buy_hold', *, initial_cash=100000., commission_pct=.05, slippage_pct=.05,
             lot_size=1, evaluation_start=None, custom=None, **params):
    validate_bars(frame)
    finite(initial_cash, 'initial_cash', 1, 1e12)
    finite(commission_pct, 'commission_pct', 0, 5); finite(slippage_pct, 'slippage_pct', 0, 5)
    integer(lot_size, 'lot_size', 1, 1000000)
    unknown = set(params) - {'fast','slow','rsi_period','rsi_low','rsi_high'}
    if unknown:
        raise ValueError(f'Unknown strategy parameters: {sorted(unknown)}')
    target = signals(frame, strategy, custom=custom, **params)
    start = 0 if evaluation_start is None else int(frame.index.searchsorted(pd.Timestamp(evaluation_start)))
    if start >= len(frame)-2:
        raise ValueError('At least three evaluation bars required.')
    cash, units, trades, equity, holdings = float(initial_cash), 0, [], [], []
    commission, slip = commission_pct/100, slippage_pct/100
    def execute(side, quantity, price, day, signal_date, reason):
        nonlocal cash, units
        fill = price*(1+slip if side == 'BUY' else 1-slip)
        gross = fill*quantity; fee = gross*commission
        if side == 'BUY': cash -= gross+fee; units += quantity
        else: cash += gross-fee; units -= quantity
        trades.append({'date': str(day.date()), 'signal_date': str(signal_date.date()) if signal_date is not None else None,
                       'side': side, 'quantity': quantity, 'fill': fill, 'fee': fee, 'reason': reason})
    for i in range(start, len(frame)):
        day = frame.index[i]
        desired = target.iloc[i-1] if i > 0 else 0
        opening = float(frame['OPEN'].iloc[i]); close = float(frame['CLOSE'].iloc[i])
        if desired == 0 and units:
            execute('SELL', units, opening, day, frame.index[i-1], 'previous_close_signal')
        elif desired == 1 and units == 0:
            quantity = int(cash / (opening*(1+slip)*(1+commission)*lot_size)) * lot_size
            if quantity:
                execute('BUY', quantity, opening, day, frame.index[i-1], 'previous_close_signal')
        if i == len(frame)-1 and units:
            execute('SELL', units, close, day, None, 'planned_end_liquidation')
        equity.append(cash+units*close); holdings.append(units)
    values = np.r_[initial_cash, equity]
    returns = values[1:]/values[:-1]-1
    dd = values / np.maximum.accumulate(values)-1
    curve = pd.DataFrame({'equity': equity, 'units': holdings, 'drawdown': dd[1:]}, index=frame.index[start:])
    stats = {'initial_cash': initial_cash, 'final_equity': equity[-1], 'return_pct': (equity[-1]/initial_cash-1)*100,
             'max_drawdown_pct': float(dd.min()*100), 'annualized_volatility_pct': float(np.std(returns, ddof=1)*np.sqrt(252)*100),
             'trades': len(trades), 'fees': sum(x['fee'] for x in trades), 'lot_size': lot_size,
             'lot_policy': 'Fixed lot size throughout test; historical lot-size changes are not modeled.',
             'first_date': str(curve.index[0].date()), 'last_date': str(curve.index[-1].date()),
             'bars': len(curve), 'execution': 'Previous close signal -> next OPEN; cash/no leverage; whole lots; final CLOSE liquidation.',
             'limitations': 'Unadjusted price-only return; no dividends, taxes, liquidity, funding, borrow or intraday fills.'}
    return BacktestResult(curve, pd.DataFrame(trades), stats)


def compare_backtest(frame, strategy='ma_cross', train_fraction=.7, **options):
    finite(train_fraction, 'train_fraction', .2, .9)
    validate_bars(frame)
    split = int(len(frame)*train_fraction)
    if split < 10 or len(frame)-split < 10:
        raise ValueError('Need at least ten training and ten held-out bars.')
    strategy_options = {k: v for k,v in options.items() if k not in {'fast','slow','rsi_period','rsi_low','rsi_high','custom'}}
    test_start = frame.index[split]
    train = backtest(frame.iloc[:split], strategy, **options)
    test = backtest(frame, strategy, evaluation_start=test_start, **options)
    benchmark = backtest(frame, 'buy_hold', evaluation_start=test_start, **strategy_options)
    return {'train': train, 'test': test, 'benchmark': benchmark,
            'split_date': str(test_start.date()),
            'policy': 'Parameters supplied by user, no automatic optimization. Prior bars only warm up indicators. Test starts with fresh cash. Repeated manual tuning on test invalidates holdout.'}
