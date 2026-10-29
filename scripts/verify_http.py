"""Real subprocess/HTTP/JSON-RPC smoke; no remote network needed."""
import asyncio
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def exercise(port):
    url=f'http://127.0.0.1:{port}'
    async with httpx.AsyncClient(trust_env=False) as client:
        health=(await client.get(url+'/health')).json()
        assert health['status']=='ok' and not health['upstream_checked']
        rejected=await client.post(url+'/mcp',headers={'Host':'untrusted.example'},json={})
        assert rejected.status_code==421
        async with streamable_http_client(url+'/mcp',http_client=client) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                names=[t.name for t in (await session.list_tools()).tools]
                assert len(names)==15
                result=await session.call_tool('time_machine_demo',{'scenarios':100})
                assert not result.isError and result.structuredContent['instrument']['demo_data']
                bad=await session.call_tool('get_quote',{'ticker':'../invalid'})
                assert bad.isError
    return {'checked_at_utc':datetime.now(timezone.utc).isoformat(),'health':health,'tools':names,
            'demo_call':'PASS','invalid_ticker':'PASS','dns_rebinding_host_rejection':rejected.status_code}


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(root/'docs'));args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env={**os.environ,'HOST':'127.0.0.1','PORT':str(port),'PUBLIC_HOST':''}
    with open(output/'http-server.log','w') as log:
        process=subprocess.Popen([sys.executable,'-m','moex_intelligence.mcp_server','--transport','streamable-http'],cwd=root,env=env,stdout=log,stderr=log)
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1): break
                except OSError:
                    if process.poll() is not None: raise RuntimeError('MCP server exited; inspect docs/http-server.log')
                    time.sleep(.1)
            else: raise TimeoutError('MCP server did not start in ten seconds')
            evidence=asyncio.run(exercise(port))
            (output/'http-verification.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
            print('PASS HTTP health, MCP initialize/list/call, invalid ticker and hostile Host')
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()


if __name__=='__main__':main()
