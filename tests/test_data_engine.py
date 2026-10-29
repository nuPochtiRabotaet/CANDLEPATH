from datetime import date
import httpx
import pytest
from moex import ISS, rows
from moex_intelligence.data import DataEngine, normalize_history, describe_response


def table(cols, values): return {'columns':cols,'data':values}


def test_real_description_shape_and_bond_detection():
    payload={'description':table(['name','value'],[['SHORTNAME','ОФЗ'],['TYPE','ofz_bond']]),
             'boards':table(['boardid','engine','market','is_primary','is_traded'],[['TQOB','stock','bonds',1,1]])}
    meta=describe_response(payload,'SU26238RMFS4')
    assert meta['asset_type']=='bond' and meta['board']=='TQOB' and meta['name']=='ОФЗ'


@pytest.mark.parametrize('records',[
    [{'TRADEDATE':'2026-01-01','CLOSE':100},{'TRADEDATE':'2026-01-02','CLOSE':None}],
    [{'TRADEDATE':'2026-01-01','CLOSE':100},{'TRADEDATE':'2026-01-01','CLOSE':101}],
    [{'TRADEDATE':'bad','CLOSE':100}],
    [{'TRADEDATE':'2026-01-01','CLOSE':float('inf')}],
    [{'TRADEDATE':'2026-01-02','CLOSE':100},{'TRADEDATE':'2026-01-01','CLOSE':99}],
])
def test_invalid_history_not_silently_changed(records):
    with pytest.raises(ValueError): normalize_history(records)


async def test_cache_timestamp_and_mutation_isolation():
    calls=[]
    async def handler(req):
        calls.append(req)
        return httpx.Response(200,json={'securities':table(['SECID'],[['SBER']]),'marketdata':table(['LAST'],[[300]])})
    engine=DataEngine(ISS(httpx.MockTransport(handler)),ttl=300)
    first=await engine.quote('SBER'); stamp=first['retrieved_at_utc']; first['security']['SECID']='BAD'
    second=await engine.quote('SBER')
    assert len(calls)==1 and second['cache']['hit'] and second['retrieved_at_utc']==stamp
    assert second['security']['SECID']=='SBER'
    engine.ttl=0
    await engine.quote('SBER')
    assert len(calls)==2


async def test_invalid_quote_and_errors_not_cached():
    calls=[]
    async def handler(req):
        calls.append(req)
        return httpx.Response(200,json={'securities':table(['SECID'],[['SBER']]),'marketdata':table(['LAST'],[[-1]])})
    engine=DataEngine(ISS(httpx.MockTransport(handler)),ttl=300)
    for _ in range(2):
        with pytest.raises(ValueError): await engine.quote('SBER')
    assert len(calls)==2


async def test_bond_market_url_and_no_ruble_conversion():
    paths=[]
    async def handler(req):
        paths.append(req.url.path)
        return httpx.Response(200,json={'securities':table(['SECID','FACEVALUE','ACCRUEDINT'],[['BOND',1000,20]]),'marketdata':table(['LAST'],[[85]])})
    result=await ISS(httpx.MockTransport(handler)).quote('BOND','TQOB','bonds')
    assert '/markets/bonds/' in paths[0] and result['last_price']==85


async def test_proxy_error_wrapped_and_no_substitute():
    async def handler(req): raise httpx.ProxyError('offline')
    with pytest.raises(ValueError,match='no substitute'):
        await ISS(httpx.MockTransport(handler)).search('SBER')


def test_bad_table_row_shape():
    with pytest.raises(ValueError): rows({'x':table(['a'],[None])},'x')
