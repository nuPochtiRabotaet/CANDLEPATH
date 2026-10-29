"""Unified local MCP endpoint: Reader + simulation + backtesting + virtual portfolio."""
from __future__ import annotations
import argparse
import asyncio
from datetime import timedelta
from typing import Any

from time_machine_mcp import register_time_machine_tools, run_analysis
from time_machine_core.moex_data import demo_daily
from time_machine_core.simulator import compare_scenarios, validate_options
from .backtest import compare_backtest
from .config import configure_logging
from .data import get_engine, market_today, require_equity
from .mcp_factory import build_reader, ANNOTATIONS
from .portfolio import analyze_portfolio, stress_test
from .research import render_report
from .validation import integer

client = get_engine()
mcp = build_reader(client, 'MOEX Intelligence')
register_time_machine_tools(mcp, client.frame_sync, background=True)


async def research_frame(symbol, lookback_days, demo):
    integer(lookback_days, 'lookback_days', 120, 3650)
    if demo:
        return demo_daily()
    last = market_today()-timedelta(days=1)
    frame, meta = await client.frame(symbol, last-timedelta(days=lookback_days), last)
    require_equity(meta)
    return frame, meta


@mcp.tool(annotations=ANNOTATIONS)
async def get_instrument(symbol: str) -> dict[str, Any]:
    """Resolve primary board and quote equity/fund/bond. Bond prices remain % of face value."""
    return await client.research_quote(symbol)


@mcp.tool(annotations=ANNOTATIONS)
async def strategy_backtest(symbol: str = 'SBER', strategy: str = 'ma_cross', lookback_days: int = 730,
    demo: bool = False, initial_cash: float = 100000., commission_pct: float = .05, slippage_pct: float = .05,
    train_fraction: float = .7, fast: int = 20, slow: int = 50) -> dict[str, Any]:
    """Fixed-parameter held-out historical test with next-open fills, costs and buy/hold benchmark. No optimization."""
    if strategy not in {'buy_hold','ma_cross','ema_cross','rsi'}: raise ValueError('Invalid built-in strategy.')
    frame, meta = await research_frame(symbol, lookback_days, demo)
    lot = 1
    if not demo:
        q = await client.research_quote(symbol)
        lot = q['security'].get('LOTSIZE')
        integer(lot, 'MOEX lot size', 1, 1000000)
    result = await asyncio.to_thread(compare_backtest, frame, strategy, train_fraction,
        initial_cash=initial_cash, commission_pct=commission_pct, slippage_pct=slippage_pct, lot_size=lot, fast=fast, slow=slow)
    return {'instrument':meta, 'train':result['train'].stats, 'test':result['test'].stats,
            'benchmark':result['benchmark'].stats, 'split_date':result['split_date'], 'policy':result['policy']}


@mcp.tool(annotations=ANNOTATIONS)
async def portfolio_analyze(events: list[dict[str, Any]], marks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Analyze supplied virtual RUB ledger and sourced dated valuations. Does not persist or execute trades."""
    return await asyncio.to_thread(analyze_portfolio, events, marks)


@mcp.tool(annotations=ANNOTATIONS)
async def portfolio_stress(events: list[dict[str, Any]], marks: dict[str, dict[str, Any]], shocks_pct: dict[str, float]) -> dict[str, Any]:
    """Specified one-step portfolio price shocks, unchanged cash. No probability estimate."""
    snapshot = await asyncio.to_thread(analyze_portfolio, events, marks)
    return stress_test(snapshot, shocks_pct)


@mcp.tool(annotations=ANNOTATIONS)
async def compare_market_scenarios(symbol: str = 'SBER', demo: bool = False, horizon: int = 20,
                                   scenarios: int = 10000, seed: int = 42) -> dict[str, Any]:
    """Three explicit drift/volatility sensitivity assumptions; same historical data and random seed."""
    validate_options(horizon, scenarios, 8, 5, .05, .05, 5, seed)
    frame, meta = await research_frame(symbol, 730, demo)
    result = await asyncio.to_thread(compare_scenarios, frame['CLOSE'], horizon=horizon, runs=scenarios, seed=seed)
    return {'instrument':meta, 'scenarios':result, 'notice':'Assumed regimes, not predicted future probabilities.'}


@mcp.tool(annotations=ANNOTATIONS)
async def research_report(symbol: str = 'SBER', demo: bool = False, scenarios: int = 1000) -> dict[str, Any]:
    """Generate a sourced deterministic numerical report for interpretation by your connected AI assistant."""
    result = await asyncio.to_thread(run_analysis, symbol, demo=demo, scenarios=scenarios, history_loader=client.frame_sync)
    return {'report_markdown': render_report(result), 'analysis': result}


@mcp.tool(annotations=ANNOTATIONS)
async def evaluate_investment(symbol: str = 'SBER', profile: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None, demo: bool = False, scenarios: int = 2000, seed: int = 42) -> dict[str, Any]:
    """Deterministic risk/fit verdict. Profile: amount, horizon_months, max_drawdown_pct, risk_preference low/medium/high, needs_money_early boolean. Missing profile means no personal fit conclusion. Never a guarantee or order."""
    from .advisor import investigate, render_investment_report
    result,_ = await investigate(symbol,profile,portfolio,demo=demo,runs=scenarios,seed=seed)
    return {'analysis':result,'report_markdown':render_investment_report(result)}


@mcp.tool(annotations=ANNOTATIONS)
async def compare_investments(symbol: str, benchmark: str = 'SBMX', lookback_days: int = 730) -> dict[str, Any]:
    """Price-only historical comparison on identical overlapping dates. Index is not investible; no ranking of future attractiveness."""
    from .comparison import compare_instruments
    return await compare_instruments(symbol,benchmark,lookback_days)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=['stdio','streamable-http'], default='stdio')
    args = parser.parse_args()
    configure_logging()
    mcp.run(transport=args.transport)


if __name__ == '__main__': main()
