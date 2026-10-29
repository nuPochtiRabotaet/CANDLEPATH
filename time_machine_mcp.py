"""Drop-in MCP extension for an existing FastMCP-based MOEX Reader server.

Keeps the original server.py unchanged until the user explicitly registers
these tools. Read-only, educational; does not connect to a brokerage account.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Any

from time_machine_core.moex_data import demo_daily, load_moex_daily
from time_machine_core.simulator import simulate
from time_machine_core.simulator import validate_options
from moex_intelligence.data import market_today, require_equity
from moex_intelligence.validation import integer

# Loader convention: (symbol, start_date, end_date) -> (DataFrame, metadata dict).
HistoryLoader = Callable[[str, date, date], tuple]


def _check_options(
    lookback_days: int, horizon: int, scenarios: int,
    target_pct: float, stop_pct: float,
    commission_pct: float, slippage_pct: float, block: int,
) -> None:
    """Validate before any potentially expensive MOEX network calls."""
    integer(lookback_days, 'lookback_days', 120, 3650)
    validate_options(horizon, scenarios, target_pct, stop_pct, commission_pct, slippage_pct, block)
    if not 120 <= lookback_days <= 3650:
        raise ValueError('lookback_days должен быть от 120 до 3650 календарных дней.')
    if not 1 <= horizon <= 120:
        raise ValueError('horizon должен быть от 1 до 120 торговых дней.')
    if not 100 <= scenarios <= 50_000:
        raise ValueError('scenarios должен быть от 100 до 50000.')
    if not 0 < target_pct <= 500:
        raise ValueError('target_pct должен быть больше 0 и не больше 500%.')
    if not 0 < stop_pct < 100:
        raise ValueError('stop_pct должен быть больше 0 и меньше 100%.')
    if not (0 <= commission_pct < 10 and 0 <= slippage_pct < 10):
        raise ValueError('Издержки задаются неотрицательными процентами меньше 10.')
    if not 1 <= block <= 20:
        raise ValueError('block должен быть от 1 до 20 торговых дней.')


def run_analysis(
    symbol: str = 'SBER',
    *,
    lookback_days: int = 730,
    horizon: int = 20,
    scenarios: int = 10_000,
    target_pct: float = 8.0,
    stop_pct: float = 5.0,
    commission_pct: float = 0.05,
    slippage_pct: float = 0.05,
    block: int = 5,
    seed: int = 42,
    demo: bool = False,
    history_loader: HistoryLoader | None = None,
    as_of: str | None = None,
) -> dict:
    """Structured tool result; no raw scenario arrays sent to an LLM."""
    _check_options(lookback_days, horizon, scenarios, target_pct, stop_pct,
                   commission_pct, slippage_pct, block)
    integer(seed, 'seed', 0, 1_000_000)
    if demo:
        df, meta = demo_daily(seed=1007)
    else:
        symbol = symbol.strip().upper()
        loader = history_loader or load_moex_daily
        today = date.fromisoformat(as_of) if as_of else market_today() - timedelta(days=1)
        df, meta = loader(symbol, today - timedelta(days=lookback_days), today)
    require_equity(meta)
    if 'CLOSE' not in df.columns:
        raise ValueError('Источник не предоставил колонку CLOSE с ценами закрытия.')
    r = simulate(df['CLOSE'], horizon=horizon, runs=scenarios,
                 target_pct=target_pct, stop_pct=stop_pct,
                 commission_pct=commission_pct, slippage_pct=slippage_pct,
                 block=block, seed=seed)
    s = r.stats
    return {
        'tool': 'MOEX Reader + Time Machine',
        'instrument': {
            'symbol': meta.get('symbol', symbol),
            'name': meta.get('name', ''),
            'board': meta.get('board', ''),
            'data_source': meta.get('source', 'MOEX Reader'),
            'last_observation_date': str(df.index[-1].date()),
            'history_observations': s['history_points'],
            'demo_data': bool(demo or meta.get('demo_data')),
            'history_sha256': meta.get('history_sha256'),
            'retrieved_at_utc': meta.get('retrieved_at_utc'),
            'cache': meta.get('cache'),
            'coverage': meta.get('coverage'),
            'data_warnings': [meta[k] for k in ('coverage_warning', 'freshness_warning') if k in meta],
        },
        'parameters': {
            'horizon_trading_days': horizon,
            'simulated_paths': scenarios,
            'lookback_calendar_days': lookback_days,
            'bootstrap_block_days': block,
            'target_pct': target_pct,
            'stop_pct': stop_pct,
            'commission_pct_per_side': commission_pct,
            'slippage_pct_per_side': slippage_pct,
            'seed': seed,
        },
        'scenario_frequencies': {
            'target_first': round(s['p_target'], 6),
            'stop_first': round(s['p_stop'], 6),
            'neither_reached': round(s['p_open'], 6),
            'net_loss': round(s['p_loss'], 6),
        },
        'net_return_distribution': {
            'mean_pct': round(s['mean_return'] * 100, 4),
            'median_pct': round(s['median_return'] * 100, 4),
            'p05_pct': round(s['p05_return'] * 100, 4),
            'p95_pct': round(s['p95_return'] * 100, 4),
            'average_worst_5pct_pct': round(s['cvar05_return'] * 100, 4),
        },
        'levels': {
            'last_close': round(s['start_price'], 6),
            'target': round(s['target_price'], 6),
            'stop': round(s['stop_price'], 6),
        },
        'risk': {k: round(s[k] * 100, 4) for k in ['var95_loss', 'es95_loss', 'historical_volatility',
                   'historical_max_drawdown', 'median_strategy_max_drawdown', 'p05_strategy_max_drawdown']},
        'risk_units': 'percent; VaR and ES use signed loss convention',
        'method': 'Block bootstrap historical daily log returns; first DAILY CLOSE crossing only.',
        'limitations': [
            'Частоты исходов — внутри модели, НЕ вероятность будущей прибыли.',
            'Не моделирует внутридневные касания стопа или цели и исполнение заявок.',
            'Исторические данные могут быть не скорректированы на дивиденды и корпоративные действия.',
            'Без налогов, стакана заявок и оценённой ошибки вне выборки.',
            'Информационный исследовательский инструмент, не инвестиционная рекомендация.',
            'VaR/ES are signed losses in percent; negative means a gain in this model. ES averages ceil(5% × runs) worst outcomes.',
        ],
    }


def register_time_machine_tools(mcp, history_loader: HistoryLoader | None = None, *, background: bool = False) -> None:
    """Register two read-only tools with an existing FastMCP instance.

    Pass an existing Reader history loader for a truly shared data layer.
    Without a loader, the extension fetches MOEX ISS history itself.
    """

    def tool(fn):
        if not background:
            return mcp.tool()(fn)
        import asyncio
        from functools import wraps
        from mcp.types import ToolAnnotations
        @wraps(fn)
        async def threaded(*args, **kwargs):
            return await asyncio.to_thread(fn, *args, **kwargs)
        return mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))(threaded)

    @tool
    def time_machine_simulate(
        symbol: str = 'SBER',
        lookback_days: int = 730,
        horizon: int = 20,
        scenarios: int = 10_000,
        target_pct: float = 8.0,
        stop_pct: float = 5.0,
        commission_pct: float = 0.05,
        slippage_pct: float = 0.05,
        block: int = 5,
        seed: int = 42,
    ) -> dict[str, Any]:
        """MOEX educational risk scenarios. NEVER a forecast or trade signal.

        Reads DAILY historical prices, simulates close-only exits with a
        block bootstrap, returns compact frequencies and risk statistics.
        No orders are placed, no brokerage accounts are accessed.
        """
        return run_analysis(
            symbol=symbol, lookback_days=lookback_days, horizon=horizon,
            scenarios=scenarios, target_pct=target_pct, stop_pct=stop_pct,
            commission_pct=commission_pct, slippage_pct=slippage_pct,
            block=block, seed=seed, history_loader=history_loader,
        )

    @tool
    def time_machine_demo(
        horizon: int = 20,
        scenarios: int = 1_000,
        target_pct: float = 8.0,
        stop_pct: float = 5.0,
        seed: int = 42,
    ) -> dict[str, Any]:
        """Offline educational simulation using SYNTHETIC DATA ONLY."""
        return run_analysis(
            demo=True, horizon=horizon, scenarios=scenarios,
            target_pct=target_pct, stop_pct=stop_pct, seed=seed,
        )
