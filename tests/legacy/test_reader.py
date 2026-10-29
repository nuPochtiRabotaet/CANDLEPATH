import httpx
import pytest
from moex import ISS, identifier, rows, metrics

def table(columns, data):
    return {'columns': columns, 'data': data}

@pytest.mark.parametrize('value', ['../SBER', 'https://evil.test', '', 'SBER?x=1'])
def test_reject_paths(value):
    with pytest.raises(ValueError): identifier(value)

def test_malformed_table():
    with pytest.raises(ValueError): rows({'x': table(['a'], [[1,2]])}, 'x')

@pytest.mark.asyncio
async def test_missing_last_not_previous_price():
    async def handler(req):
        return httpx.Response(200, json={'securities': table(['SECID','PREVPRICE'], [['SBER',300]]), 'marketdata': table(['LAST'], [[None]])})
    r = await ISS(httpx.MockTransport(handler)).quote('sber')
    assert r['last_price'] is None and r['last_price_missing']

@pytest.mark.asyncio
async def test_pagination():
    offsets=[]
    async def handler(req):
        offset=int(req.url.params['start']); offsets.append(offset)
        return httpx.Response(200,json={'history': table(['TRADEDATE','CLOSE'], [['2026-01-01',100]] if offset==0 else ([['2026-01-02',110]] if offset==1 else []))})
    r=await ISS(httpx.MockTransport(handler)).history('SBER','2026-01-01','2026-01-05')
    assert offsets == [0,1,2] and r['count']==2 and r['complete']

@pytest.mark.asyncio
async def test_retries():
    calls=[]
    async def handler(req):
        calls.append(req)
        return httpx.Response(503) if len(calls)<3 else httpx.Response(200,json={'securities':table(['secid'],[['SBER']])})
    r=await ISS(httpx.MockTransport(handler)).search('SBER')
    assert len(calls)==3 and r['results'][0]['secid']=='SBER'

@pytest.mark.asyncio
async def test_bad_json():
    async def handler(req): return httpx.Response(200,text='<html>error</html>')
    with pytest.raises(ValueError): await ISS(httpx.MockTransport(handler)).search('SBER')

@pytest.mark.asyncio
async def test_range():
    with pytest.raises(ValueError): await ISS().history('SBER','2026-02-01','2026-01-01')

def test_metrics():
    r=metrics({'rows':[{'TRADEDATE':str(i),'CLOSE':p} for i,p in enumerate([100,120,90,110])]})
    assert r['price_return_pct']==pytest.approx(10)
    assert r['max_close_drawdown_pct']==pytest.approx(-25)
    assert r['sma20'] is None

def test_missing_close_rejected():
    with pytest.raises(ValueError): metrics({'rows':[{'CLOSE':100},{'CLOSE':None}]})

@pytest.mark.asyncio
async def test_unknown_security():
    async def handler(req):
        return httpx.Response(200,json={'securities':table(['SECID'],[]),'marketdata':table(['LAST'],[])})
    with pytest.raises(ValueError,match='not found'): await ISS(httpx.MockTransport(handler)).quote('NOSUCH')

@pytest.mark.asyncio
async def test_stuck_pagination():
    async def handler(req): return httpx.Response(200,json={'history':table(['TRADEDATE'],[['2026-01-01']])})
    with pytest.raises(ValueError,match='pagination'): await ISS(httpx.MockTransport(handler)).history('SBER','2026-01-01','2026-01-02')

@pytest.mark.asyncio
async def test_mcp_schema_and_structured_output(monkeypatch):
    from server import mcp, client
    async def fake_quote(*args, **kwargs): return {'ticker':'SBER','last_price':100}
    monkeypatch.setattr(client,'quote',fake_quote)
    tools=await mcp.list_tools()
    assert len(tools)==5 and all(t.outputSchema for t in tools)
    result=await mcp.call_tool('get_quote',{'ticker':'SBER'})
    assert isinstance(result,tuple) and result[1]['ticker']=='SBER'
