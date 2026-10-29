"""Public connectivity check only; no keys, orders, alternate hosts or access bypass."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moex_intelligence.crypto.market import Bybit,MarketError
async def main():
    api=Bybit()
    try:
        rules=await api.rules('BTCUSDT');rows=await api.history('BTCUSDT','15');ticker=await api.ticker('BTCUSDT')
        print(json.dumps({'status':'REST OK','candles':len(rows),'first_utc_seconds':rows[0].time,'last_utc_seconds':rows[-1].time,'rules':rules,'ticker':ticker},ensure_ascii=False,indent=2))
        import threading
        stop=threading.Event()
        def receive(msg):
            if msg.get('topic'):print('WebSocket OK:',msg['topic']);stop.set()
        await asyncio.wait_for(api.stream('BTCUSDT','15',receive,stop),timeout=30)
    except Exception as e:
        print('Bybit недоступен:',str(e) if isinstance(e,MarketError) else type(e).__name__);return 1
    return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
