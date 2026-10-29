"""Original five Reader tool names and call signatures preserved."""
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse
from moex import metrics
from .config import Settings
from . import __version__

ANNOTATIONS = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def build_reader(client, name='MOEX Reader'):
    settings = Settings.from_env()
    mcp = FastMCP(name, host=settings.host, port=settings.port, stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=['127.0.0.1:*','localhost:*','[::1]:*'],
            allowed_origins=['http://localhost:*','http://127.0.0.1:*','http://[::1]:*']),
        instructions='Read-only MOEX research, no trading. State source, board, currency, observation date, retrieval time and synthetic status. Numerical results come from Python. Distinguish model frequencies from real-world probabilities. No guaranteed profit. Unadjusted prices omit dividends and splits. Never invent missing quotes.')

    @mcp.tool(annotations=ANNOTATIONS)
    async def search_security(query: str, limit: int = 10) -> dict[str, Any]:
        """Search MOEX instruments; inspect type and primary board before quoting."""
        return await client.search(query, limit)

    @mcp.tool(annotations=ANNOTATIONS)
    async def get_quote(ticker: str, board: str = 'TQBR') -> dict[str, Any]:
        """Original Reader stock/fund quote. LAST only, possibly missing; timestamps included."""
        return await client.quote(ticker, board)

    @mcp.tool(annotations=ANNOTATIONS)
    async def get_daily_history(ticker: str, start: str, end: str, board: str = 'TQBR') -> dict[str, Any]:
        """Original Reader paginated stock/fund history. ISO dates, at most 3660 calendar days."""
        return await client.history(ticker, start, end, board)

    @mcp.tool(annotations=ANNOTATIONS)
    async def analyze_history(ticker: str, start: str, end: str, board: str = 'TQBR') -> dict[str, Any]:
        """Original Reader price return, historical volatility, drawdown, SMA20/50; no forecast."""
        history = await client.history(ticker, start, end, board)
        return {k: history[k] for k in ('source','retrieved_at_utc','notice','ticker','board')} | {'metrics': metrics(history), 'cache': history.get('cache')}

    @mcp.tool(annotations=ANNOTATIONS)
    async def get_market_snapshot(tickers: list[str], board: str = 'TQBR') -> dict[str, Any]:
        """Original Reader sequential 1–10 stock/fund snapshots; partial failures explicit."""
        return await client.snapshot(tickers, board)

    @mcp.custom_route('/health', methods=['GET'])
    async def health(request):
        return JSONResponse({'status':'ok','service':name,'version':__version__,'upstream_checked':False})
    return mcp
