"""Optional server-only Bybit GET adapter. Requires an explicitly read-only API key."""
import hashlib,hmac,os,time
from urllib.parse import urlencode
import httpx
from .market import MarketError

class ReadOnly:
    def __init__(self):
        self.key=os.getenv('BYBIT_READONLY_KEY','');self.secret=os.getenv('BYBIT_READONLY_SECRET','')
        self.base='https://api.bybit.com'
        if not self.key or not self.secret:raise MarketError('Задайте BYBIT_READONLY_KEY и BYBIT_READONLY_SECRET на сервере. Для публичного графика они не нужны.')
    async def get(self,path,params=None):
        allowed={'/v5/user/query-api','/v5/account/wallet-balance','/v5/order/realtime','/v5/execution/list'}
        if path not in allowed:raise MarketError('Только разрешённые read-only endpoints')
        query=urlencode(params or {});ts=str(int(time.time()*1000));window='5000'
        signature=hmac.new(self.secret.encode(),(ts+self.key+window+query).encode(),hashlib.sha256).hexdigest()
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                r=await client.get(self.base+path+('?' +query if query else ''),headers={'X-BAPI-API-KEY':self.key,'X-BAPI-TIMESTAMP':ts,'X-BAPI-RECV-WINDOW':window,'X-BAPI-SIGN':signature})
                r.raise_for_status();body=r.json()
                if body.get('retCode')!=0:raise MarketError('Private API: код '+str(body.get('retCode')))
                return body['result']
        except (httpx.HTTPError,ValueError):raise MarketError('Private API недоступен. Проверьте платформу аккаунта, регион, часы и права ключа.') from None
    async def snapshot(self):
        info=await self.get('/v5/user/query-api')
        if info.get('readOnly')!=1 or 'Withdraw' in info.get('permissions',{}).get('Wallet',[]):raise MarketError('Нужен ключ Read Only без права вывода. Доступ отклонён.')
        balances=await self.get('/v5/account/wallet-balance',{'accountType':'UNIFIED'})
        orders=await self.get('/v5/order/realtime',{'category':'spot','limit':50})
        fills=await self.get('/v5/execution/list',{'category':'spot','limit':50})
        # Explicit allowlists: API key metadata and all secrets remain on the server.
        return {'balances':[{'equity':x.get('totalEquity'),'available':x.get('totalAvailableBalance'),'coins':[{k:c.get(k) for k in ('coin','walletBalance','usdValue','locked')} for c in x.get('coin',[])]} for x in balances.get('list',[])],
                'orders':[{k:x.get(k) for k in ('symbol','side','qty','price','orderStatus','createdTime')} for x in orders.get('list',[])],
                'executions':[{k:x.get(k) for k in ('symbol','side','execQty','execPrice','execFee','execTime')} for x in fills.get('list',[])],
                'notice':'UNIFIED · последние 50 ордеров/исполнений. Доступные средства зависят от режима аккаунта; отсутствующее поле не равно нулю.'}
