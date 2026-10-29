"""Independent actual REST and WS checks, with no alternate hosts or fixtures."""
import asyncio,json,time
from pathlib import Path
import httpx,websockets
async def main():
 out={'checked_at':time.time(),'type':'REAL NETWORK; no mocks'}
 try:
  async with httpx.AsyncClient(timeout=12) as c:
   r=await c.get('https://api.bybit.com/v5/market/kline',params={'category':'spot','symbol':'BTCUSDT','interval':'15','limit':3})
   try:b=r.json();out['rest']={'http_status':r.status_code,'retCode':b.get('retCode'),'rows':len(b.get('result',{}).get('list',[]))}
   except ValueError:out['rest']={'http_status':r.status_code,'json':False,'site_unavailable':'Site Unavailable' in r.text}
 except Exception as e:out['rest']={'error':type(e).__name__}
 try:
  async with websockets.connect('wss://stream.bybit.com/v5/public/spot',open_timeout=12) as ws:
   await ws.send(json.dumps({'op':'subscribe','args':['kline.15.BTCUSDT','orderbook.1.BTCUSDT']}))
   topics=[]
   async with asyncio.timeout(15):
    while not topics:
     b=json.loads(await ws.recv())
     if b.get('topic'):topics.append(b['topic'])
   out['websocket']={'connected':True,'topics':topics}
 except Exception as e:out['websocket']={'connected':False,'error':type(e).__name__,'message':str(e)[:160]}
 p=Path(__file__).resolve().parents[1]/'docs/rc2/network.json';p.write_text(json.dumps(out,indent=2));print(p.read_text())
asyncio.run(main())
