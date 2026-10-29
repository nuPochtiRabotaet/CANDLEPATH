import numpy as np
import pandas as pd
import pytest
from moex_intelligence.comparison import compare_frames


def test_common_dates_define_both_returns_and_beta():
    dates=pd.bdate_range('2025-01-01',periods=100)
    a=pd.DataFrame({'CLOSE':np.exp(np.arange(100)*.003+np.sin(np.arange(100))*.01)},index=dates)
    b=pd.DataFrame({'CLOSE':a.CLOSE*2},index=dates).iloc[15:]
    meta={'symbol':'A','asset_type':'equity','currency':'RUB'}
    r=compare_frames(a,b,meta,{**meta,'symbol':'B'})
    assert r['observations']==85 and r['first_date']==str(dates[15].date())
    assert r['stats'][0]['return_pct']==pytest.approx(r['stats'][1]['return_pct'])
    assert r['beta']==pytest.approx(1)
    assert r['normalized_prices']['asset'][0]==100


@pytest.mark.parametrize('changes',[{'asset_type':'bond'},{'currency':'USD'}])
def test_incompatible_price_units_not_compared(changes):
    frame=pd.DataFrame({'CLOSE':np.ones(100)},index=pd.bdate_range('2025-01-01',periods=100))
    meta={'symbol':'A','asset_type':'equity','currency':'RUB'}
    with pytest.raises(ValueError):compare_frames(frame,frame,meta,{**meta,**changes})
