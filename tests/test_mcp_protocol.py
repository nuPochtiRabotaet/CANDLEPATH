import os
from pathlib import Path
import sys
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from moex_intelligence.config import Settings


def test_local_only_configuration(monkeypatch):
    monkeypatch.setenv('HOST','0.0.0.0')
    with pytest.raises(ValueError,match='loopback'): Settings.from_env()
    monkeypatch.setenv('HOST','127.0.0.1'); monkeypatch.setenv('PUBLIC_HOST','public.example')
    with pytest.raises(ValueError,match='loopback'): Settings.from_env()


async def test_real_stdio_handshake_and_tool_invocations():
    root=Path(__file__).resolve().parents[1]
    params=StdioServerParameters(command=sys.executable,args=['-m','moex_intelligence.mcp_server'],cwd=str(root),env={**os.environ,'HOST':'127.0.0.1','PUBLIC_HOST':''})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            tools=(await session.list_tools()).tools
            assert len(tools)==15 and all(t.outputSchema for t in tools)
            assert {'search_security','get_quote','get_daily_history','analyze_history','get_market_snapshot','time_machine_simulate','time_machine_demo','get_instrument','strategy_backtest','portfolio_analyze','portfolio_stress','compare_market_scenarios','research_report'} <= {t.name for t in tools}
            assert all(t.annotations.readOnlyHint and not t.annotations.destructiveHint for t in tools)
            demo=await session.call_tool('time_machine_demo',{'scenarios':100})
            assert not demo.isError and demo.structuredContent['instrument']['demo_data']
            backtest=await session.call_tool('strategy_backtest',{'demo':True})
            assert not backtest.isError and backtest.structuredContent['test']['bars']>10
            advice=await session.call_tool('evaluate_investment',{'demo':True,'scenarios':100})
            assert not advice.isError and advice.structuredContent['analysis']['verdict']['category']=='insufficient'
            bad=await session.call_tool('time_machine_simulate',{'scenarios':0})
            assert bad.isError
            report=await session.call_tool('research_report',{'demo':True,'scenarios':100})
            assert not report.isError and 'ИСКУССТВЕННЫЕ' in report.structuredContent['report_markdown']
