"""Run against an already running local/public MCP server; real MOEX calls."""
import asyncio
import json
import sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    url = sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000/mcp'
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names=[t.name for t in (await session.list_tools()).tools]
            assert len(names)==5, names
            print('PASS initialize and tools/list:', ', '.join(names))
            cases=[('search_security',{'query':'SBER'}),('get_quote',{'ticker':'SBER'}),('get_daily_history',{'ticker':'SBER','start':'2025-01-01','end':'2025-08-01'}),('analyze_history',{'ticker':'SBER','start':'2025-01-01','end':'2025-08-01'}),('get_market_snapshot',{'tickers':['SBER','VTBR','SBMX']})]
            for name,args in cases:
                result=await session.call_tool(name,args)
                assert not result.isError, (name,result)
                data=result.structuredContent
                if data is None:
                    data=json.loads(next(c.text for c in result.content if c.type=='text'))
                if 'result' in data and isinstance(data['result'], dict):
                    data=data['result']
                if name=='get_daily_history': assert data['count']>100 and data['complete']
                if name=='get_quote': assert data['security']['SECID']=='SBER'
                if name=='get_market_snapshot': assert all('error' not in r for r in data['results']), data
                print('PASS',name)
                if name=='get_quote': print(json.dumps({k:data.get(k) for k in ['ticker','last_price','retrieved_at_utc']},ensure_ascii=False))
            bad=await session.call_tool('get_quote',{'ticker':'../bad'})
            assert bad.isError
            print('PASS invalid ticker produces MCP error')

if __name__=='__main__': asyncio.run(main())
