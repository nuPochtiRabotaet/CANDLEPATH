"""Entirely synthetic bookkeeping example, not market prices."""
import json
from pathlib import Path
import pandas as pd
from moex_intelligence.portfolio import portfolio_curve

if __name__=='__main__':
    folder=Path(__file__).parent
    events=json.loads((folder/'portfolio_events.json').read_text())
    prices=pd.read_csv(folder/'portfolio_valuations.csv',index_col=0,parse_dates=True)
    _,stats=portfolio_curve(events,prices)
    print(stats)
