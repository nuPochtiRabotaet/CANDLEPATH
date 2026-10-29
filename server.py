"""Compatibility server: the original five MOEX Reader tools, loopback HTTP."""
from moex_intelligence.config import configure_logging
from moex_intelligence.data import get_engine
from moex_intelligence.mcp_factory import build_reader

client = get_engine()
mcp = build_reader(client)

if __name__ == '__main__':
    configure_logging()
    mcp.run(transport='streamable-http')
