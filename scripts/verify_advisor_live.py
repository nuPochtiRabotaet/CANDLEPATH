"""Explicit live SBER advisor and IMOEX/fund comparison, no trade execution."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
from moex_intelligence.advisor import investigate,render_investment_report
from moex_intelligence.comparison import compare_instruments
from moex_intelligence.data import get_engine

async def main():
    profile={'amount':5000.,'horizon_months':12,'max_drawdown_pct':5.,'risk_preference':'low','needs_money_early':False}
    result,_=await investigate('SBER',profile,runs=1000)
    assert result['quality']['synthetic'] is False
    assert result['verdict']['category']=='unsuitable'
    assert result['risk']['hard_conflicts']
    index=await get_engine().research_quote('IMOEX')
    comparison=await compare_instruments('SBER','SBMX',730)
    assert comparison['observations']>=65
    out={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'advisor':result,'index':index,'comparison':comparison}
    Path('docs/advisor-live.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False))
    Path('docs/SBER_example_report.md').write_text(render_investment_report(result))
    print('PASS live SBER advisor, 5% risk limit, IMOEX snapshot and SBMX common-date comparison')

if __name__=='__main__':asyncio.run(main())
