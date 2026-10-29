"""Explicit live MOEX integration check. Run from root: python -m scripts.verify_live."""
import asyncio
from datetime import date, datetime, timezone, timedelta
import json
from pathlib import Path
from moex_intelligence.config import configure_logging
from moex_intelligence.data import get_engine, market_today
from time_machine_core.simulator import simulate
from time_machine_mcp import run_analysis
from moex_intelligence.backtest import compare_backtest


async def main():
    configure_logging()
    engine=get_engine()
    end=market_today()-timedelta(days=1); start=end-timedelta(days=390)
    evidence={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'start':str(start),'end':str(end),'instruments':[]}
    for symbol in ['SBER','SBMX','SU26238RMFS4']:
        frame,meta=await engine.frame(symbol,start,end)
        quote=await engine.research_quote(symbol)
        item={'symbol':symbol,'rows':len(frame),'metadata':meta,'last_close':float(frame.CLOSE.iloc[-1]),
              'quote':{'last':quote['last_price'],'currency':quote['currency'],'lot':quote['security'].get('LOTSIZE'),
                       'retrieved_at_utc':quote['retrieved_at_utc'],'source':quote['source']}}
        assert len(frame)>65
        if symbol=='SBER':
            item['simulation']=simulate(frame.CLOSE,runs=10000,seed=42).stats
            item['holdout_backtest']=compare_backtest(frame,lot_size=quote['security']['LOTSIZE'])['test'].stats
            # Same bridge loader used by the registered MCP tools; exact same data provenance.
            bridge=await asyncio.to_thread(run_analysis,symbol,scenarios=1000,history_loader=engine.frame_sync,as_of=str(end))
            assert not bridge['instrument']['demo_data']
            item['bridge_analysis']=bridge
            assert (await engine.history(symbol,str(start),str(end)))['count']==len(frame)
        evidence['instruments'].append(item)
        print(f'PASS {symbol}: {len(frame)} observations, {meta["asset_type"]}, {meta["board"]}',flush=True)
    path=Path('docs/live-verification.json'); path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2,allow_nan=False))
    print(f'PASS evidence: {path}')


if __name__=='__main__': asyncio.run(main())
