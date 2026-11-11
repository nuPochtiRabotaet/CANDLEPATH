"""Bybit V5 spot public connector; no order submission methods."""
import asyncio,json,time,threading,atexit,copy,math
from dataclasses import dataclass,asdict
import httpx
from websockets.asyncio.client import connect

SYMBOLS=('BTCUSDT','ETHUSDT','SOLUSDT')
INTERVALS={'1m':'1','5m':'5','15m':'15','30m':'30','1h':'60','4h':'240','1D':'D'}
def seconds(interval):return 86400 if interval=='D' else int(interval)*60
class MarketError(ValueError):pass
@dataclass(frozen=True)
class Candle:
    time:int;open:float;high:float;low:float;close:float;volume:float;closed:bool
    def __post_init__(self):
        # A non-boolean closed flag (e.g. the string "false") must NEVER be
        # interpreted as a confirmed price observation.
        if type(self.time) is not int or self.time<0 or type(self.closed) is not bool:
            raise MarketError('Некорректное время или признак закрытия свечи')
        values=(self.open,self.high,self.low,self.close,self.volume)
        if any(type(v) not in (int,float) for v in values):
            raise MarketError('Некорректный тип цены/объёма свечи')
        try:
            finite=all(math.isfinite(float(v)) for v in values)
        except (OverflowError,TypeError,ValueError) as exc:
            raise MarketError('Некорректная свеча: переполнение числового поля') from exc
        if (not finite or self.low<=0 or self.volume<0
                or self.high<max(self.open,self.close,self.low)
                or self.low>min(self.open,self.close)):
            raise MarketError('Некорректная свеча')

def merge_candles(existing,incoming,interval):
    rows={c.time:c for c in existing}
    for c in incoming:
        if c.time%seconds(interval):raise MarketError('Свеча не выровнена по UTC-интервалу')
        if c.time in rows and rows[c.time].closed:
            if c.closed and c!=rows[c.time]:raise MarketError('Изменилась закрытая свеча; требуется проверка источника')
            continue
        rows[c.time]=c
    out=sorted(rows.values(),key=lambda c:c.time)
    gaps=[(a.time+seconds(interval),b.time) for a,b in zip(out,out[1:]) if b.time-a.time!=seconds(interval)]
    return out,gaps

def validate_live_candle_times(rows,interval):
    """Reject source clock/confirmation errors before live analysis or persistence.

    Historical research uses explicit cutoffs separately; never add wall-clock
    filtering to the pure analyzer. Persisted data is retained on rejection.
    """
    now=time.time();step=seconds(interval)
    if any(c.time>now or (c.closed and c.time+step>now) for c in rows):
        raise MarketError('Свеча из будущего или закрыта до конца интервала; проверьте часы и источник')

def validate_quote(q):
    try:
        if not isinstance(q,dict) or not all(math.isfinite(float(v)) for v in q.values()):
            raise ValueError('Nonfinite or non-dict quote')
        price=float(q.get('price',0))
        bid=float(q.get('bid',0))
        ask=float(q.get('ask',0))
        if price<=0 or min(bid,ask)<0 or bid>ask:
            raise ValueError('Invalid quote values')
    except (TypeError,ValueError,OverflowError) as exc:
        raise MarketError('Некорректная котировка Bybit') from exc
    return q

class Bybit:
    base='https://api.bybit.com'
    ws='wss://stream.bybit.com/v5/public/spot'
    def __init__(self,transport=None):self.transport=transport
    async def get(self,path,params=None):
        try:
            async with httpx.AsyncClient(timeout=12,transport=self.transport) as client:
                r=await client.get(self.base+path,params=params)
                if r.status_code in (403,451):raise MarketError('Доступ Bybit ограничен платформой или регионом; обход не выполняется')
                r.raise_for_status()
                try:body=r.json()
                except ValueError:raise MarketError('Bybit вернул страницу вместо JSON (Site Unavailable / ограничение сети)')
                if body.get('retCode')!=0:raise MarketError('Bybit API: код '+str(body.get('retCode')))
                return body
        except httpx.HTTPError as e:raise MarketError('Bybit: '+type(e).__name__) from None
    async def history(self,symbol,interval,start=None,end=None):
        self.validate(symbol,interval)
        p={'category':'spot','symbol':symbol,'interval':interval,'limit':1000}
        if start is not None:p['start']=int(start*1000)
        if end is not None:p['end']=int(end*1000)
        b=await self.get('/v5/market/kline',p);now=int(b['time'])//1000
        rows=[Candle(int(x[0])//1000,*map(float,x[1:6]),int(x[0])//1000+seconds(interval)<=now) for x in b['result']['list']]
        return merge_candles([],rows,interval)[0]
    async def rules(self,symbol):
        b=await self.get('/v5/market/instruments-info',{'category':'spot','symbol':symbol});x=b['result']['list'][0];lot=x['lotSizeFilter']
        if x['status']!='Trading':raise MarketError('Инструмент не торгуется')
        return {'step':lot['basePrecision'],'tick':x['priceFilter']['tickSize'],'minimum':lot['minOrderAmt'],'maximum':lot.get('maxMarketOrderQty',lot.get('maxOrderQty')),'retrieved':time.time()}
    async def ticker(self,symbol):
        b=await self.get('/v5/market/tickers',{'category':'spot','symbol':symbol});x=b['result']['list'][0]
        return validate_quote({'price':float(x['lastPrice']),'bid':float(x.get('bid1Price') or 0),'ask':float(x.get('ask1Price') or 0),'change':float(x.get('price24hPcnt') or 0)*100,'ts':int(b['time'])/1000})
    @staticmethod
    def validate(symbol,interval):
        if symbol not in SYMBOLS or interval not in INTERVALS.values():raise MarketError('Неподдерживаемый рынок')
    async def stream(self,symbol,interval,handler,stop,include_book=False):
        self.validate(symbol,interval)
        async with connect(self.ws,open_timeout=12,ping_interval=20,ping_timeout=20,close_timeout=3,max_size=2**20) as ws:
            await ws.send(json.dumps({'op':'subscribe','args':[f'kline.{interval}.{symbol}',f'tickers.{symbol}']+([f'orderbook.1.{symbol}'] if include_book else [])}))
            last_ping=time.monotonic()
            while not stop.is_set():
                if time.monotonic()-last_ping>20:await ws.send('{"op":"ping"}');last_ping=time.monotonic()
                try:raw=await asyncio.wait_for(ws.recv(),timeout=5)
                except asyncio.TimeoutError:continue
                body=json.loads(raw)
                if body.get('success') is False:raise MarketError('Подписка Bybit отклонена')
                handler(body)

class Feed:
    def __init__(self,symbol,interval,store,connector=None):
        self.symbol=symbol;self.interval=interval;self.store=store;self.api=connector or Bybit();self.lock=threading.RLock();self.stop=threading.Event();self.touched=time.monotonic();self.rows=store.candles(symbol,interval);self.rules=None;self.quote={};self.status='Connecting';self.error='';self.events=[];self.last_ws=0;self.version=0;self.backfills=0
        validate_live_candle_times(self.rows,self.interval)
        self.thread=threading.Thread(target=lambda:asyncio.run(self.run()),daemon=True);self.thread.start()
    def event(self,message):
        self.events=(self.events+[{'time':int(time.time()),'message':message}])[-50:]
    def receive(self,b):
        with self.lock:
            topic=b.get('topic','');ts=b.get('ts',0)/1000
            if topic==f'kline.{self.interval}.{self.symbol}':
                if ts<getattr(self,'last_candle_ts',0):return
                incoming=[]
                for x in b['data']:
                    if not isinstance(x,dict) or type(x.get('confirm')) is not bool:
                        raise MarketError('Некорректный тип kline confirm: требуется Boolean')
                    try:
                        candle=Candle(int(x['start'])//1000,
                                      *[float(x[k]) for k in ('open','high','low','close','volume')],
                                      x['confirm'])
                    except (KeyError,TypeError,ValueError,OverflowError) as exc:
                        raise MarketError('Некорректная свеча в kline WebSocket') from exc
                    incoming.append(candle)
                validate_live_candle_times(incoming,self.interval)
                merged,gaps=merge_candles(self.rows,incoming,self.interval)
                if gaps:raise MarketError('Обнаружен пропуск свечей; backfill')
                if any(not c.closed for c in merged[:-1]):raise MarketError('Пропущено подтверждение закрытия свечи; backfill')
                # Do not publish a rejected gap/unconfirmed candle, or advance the
                # event watermark before a durable journal write succeeds.
                self.store.save_candles(self.symbol,self.interval,incoming)
                self.rows=merged
                self.last_candle_ts=ts
                self.version+=1;self.last_candle_event=time.time()
            elif topic==f'tickers.{self.symbol}':
                x=b['data'];x=x[0] if isinstance(x,list) else x
                if ts<self.quote.get('ts',0):return
                candidate=dict(self.quote) if b.get('type')=='delta' else {}
                for key in ('price','bid','ask'):
                    if key in candidate:candidate.setdefault(key+'_ts',candidate.get('ts',0))
                for source,key in [('lastPrice','price'),('bid1Price','bid'),('ask1Price','ask')]:
                    if source in x:candidate[key]=float(x[source] or 0);candidate[key+'_ts']=ts
                if 'price24hPcnt' in x:candidate['change']=float(x['price24hPcnt'])*100
                # The book and ticker are independent feeds. A stale book
                # quote must not override a *newer* executable ticker side.
                for side in ('bid','ask'):
                    book=getattr(self,'book',{})
                    stamp=side+'_ts'
                    if side in book and book.get(stamp,0)>=candidate.get(stamp,0):
                        candidate[side]=book[side]
                        candidate[stamp]=book.get(stamp,0)
                candidate['ts']=ts
                # Keep chart/transport active on invalid executable prices; readiness fails closed.
                self.quote=candidate
            elif topic==f'orderbook.1.{self.symbol}':
                x=b['data']
                if not isinstance(x,dict):raise MarketError('Некорректное обновление стакана')
                snapshot=b.get('type')=='snapshot'
                previous=getattr(self,'book',{})
                book={} if snapshot else dict(previous)
                for side,key in [('b','bid'),('a','ask')]:
                    entries=x.get(side)
                    if entries is None:
                        if not snapshot:continue
                        entries=[]
                    if not isinstance(entries,list):raise MarketError('Некорректная сторона стакана')
                    # An empty DELTA means "unchanged", never "book side absent".
                    if not snapshot and not entries:continue
                    stamp=key+'_ts'
                    if ts<previous.get(stamp,0):continue
                    if entries:
                        try:
                            price=float(entries[0][0])
                            qty=float(entries[0][1])
                        except (IndexError,TypeError,ValueError,OverflowError) as exc:
                            raise MarketError('Некорректный уровень стакана') from exc
                        if not math.isfinite(price) or not math.isfinite(qty) or qty<0 or (qty>0 and price<=0):
                            raise MarketError('Некорректная цена или объём стакана')
                        book[key]=price if qty>0 else 0
                    else:
                        book[key]=0
                    book[stamp]=ts
                self.book=book
                # Only a newer book side may supersede an existing quote;
                # omitted/unchanged sides retain their own causal timestamp.
                for key in ('bid','ask'):
                    stamp=key+'_ts'
                    if key in book and book.get(stamp,0)>=self.quote.get(stamp,0):
                        self.quote[key]=book[key]
                        self.quote[stamp]=book[stamp]
            elif b.get('op')=='subscribe' and b.get('success'):
                self.transport_connected=True;return
            else:return
            self.transport_connected=True
            self.last_ws=time.time();self.status='Live' if self.quote.get('price') else 'Synchronizing'
    async def sync(self):
        rules=await self.api.rules(self.symbol);recent=await self.api.history(self.symbol,self.interval)
        if not recent:raise MarketError('Bybit вернул пустую историю')
        # Paginate backwards to the persisted anchor; never silently skip outage candles.
        anchor=self.rows[-1].time if self.rows else recent[0].time
        pages=0
        while recent[0].time>anchor+seconds(self.interval):
            older=await self.api.history(self.symbol,self.interval,end=recent[0].time-1)
            if not older or older[0].time>=recent[0].time:raise MarketError('Backfill не достиг сохранённой истории')
            recent=older+recent;pages+=1
            if pages>=50:raise MarketError('Слишком большой разрыв; нужна проверка истории')
            await asyncio.sleep(.15)
        quote=await self.api.ticker(self.symbol)
        with self.lock:
            rows,gaps=merge_candles(self.rows,recent,self.interval)
            validate_live_candle_times(rows,self.interval)
            if gaps:raise MarketError('История содержит пропуски')
            # Persist before exposing the synchronized candles/quotes. If a
            # disk error occurs the previous in-memory view remains intact.
            self.store.save_candles(self.symbol,self.interval,recent)
            self.rows=rows;self.rules=rules;self.quote=quote;self.book={}
            self.last_candle_ts=0
            self.version+=1;self.backfills+=1;self.event('REST синхронизация завершена');self.status='Connecting';self.error=''
    async def run(self):
        delay=1
        while not self.stop.is_set() and time.monotonic()-self.touched<90:
            try:
                await self.sync();connected_at=time.time()
                task=asyncio.create_task(self.api.stream(self.symbol,self.interval,self.receive,self.stop,include_book=True))
                try:
                    while not task.done() and not self.stop.is_set() and time.monotonic()-self.touched<90:
                        await asyncio.sleep(1)
                        if time.time()-max(self.last_ws,connected_at)>60:raise MarketError('Нет событий WebSocket 60 секунд; переподключение')
                        if self.last_ws-connected_at>30:delay=1
                        if time.time()-self.rules.get('retrieved',0)>3600 and time.time()-getattr(self,'rules_attempt',0)>60:
                            self.rules_attempt=time.time()
                            try:
                                refreshed=await self.api.rules(self.symbol)
                                with self.lock:self.rules=refreshed
                            except MarketError as e:self.event('Правила: '+str(e))
                    if task.done():await task
                finally:
                    task.cancel()
                    try:await task
                    except asyncio.CancelledError:pass
            except Exception as e:
                with self.lock:self.transport_connected=False;self.status='Connection Lost';self.error=str(e) if isinstance(e,MarketError) else type(e).__name__;self.event(self.error)
                for _ in range(delay):
                    if self.stop.is_set():break
                    await asyncio.sleep(1)
                delay=min(delay*2,60)
        self.stop.set()
    def snapshot(self):
        self.touched=time.monotonic()
        with self.lock:
            now=time.time();age=now-self.quote.get('ts',0)
            from .risk import quote_ok
            active=now-self.last_ws<=20 and self.status=='Live'
            def finite_number(value):
                if type(value) not in (int,float):
                    return False
                try:
                    return math.isfinite(value)
                except (OverflowError,TypeError,ValueError):
                    return False
            def valid_price(k):
                value=self.quote.get(k,0)
                return finite_number(value) and value>0
            last_fresh=valid_price('price') and -2<=now-self.quote.get('price_ts',self.quote.get('ts',0))<=15
            bid_ask=valid_price('bid') and valid_price('ask') and self.quote['bid']<=self.quote['ask']
            candle_fresh=bool(self.rows) and self.rows[-1].time<=now<self.rows[-1].time+seconds(self.interval)+5 and 0<=now-getattr(self,'last_candle_event',0)<=65
            # Forecast freshness follows actual kline updates, never order execution readiness.
            # Ticker/quote may be unavailable even while the candle stream is healthy.
            stop_event=getattr(self,'stop',None)
            candle_stream_active=bool(getattr(self,'transport_connected',False)) and not (stop_event and stop_event.is_set()) and 0<=now-getattr(self,'last_candle_event',0)<=65
            fresh=active and quote_ok({**self.quote,'fresh':True},now)
            readiness={'transport_connected':getattr(self,'transport_connected',False),'market_stream_active':active,
                       'last_price_fresh':last_fresh,'bid_ask_valid':bid_ask,'candle_data_fresh':candle_fresh,
                       'forecast_feed_ready':candle_stream_active and candle_fresh,'trade_execution_ready':fresh}
            status=self.status if fresh or self.status!='Live' else 'Stale Data'
            clean_quote={k:v for k,v in self.quote.items() if finite_number(v)}
            readiness['rules_fresh']=bool(self.rules) and 0<=now-self.rules.get('retrieved',0)<=86400
            readiness['trade_execution_ready']=fresh and readiness['rules_fresh']
            return {'symbol':self.symbol,'interval':self.interval,'candles':[asdict(x) for x in self.rows],'rules':copy.deepcopy(self.rules),'quote':clean_quote,'status':status,'fresh':fresh,'readiness':readiness,'age':age,'error':self.error,'events':list(self.events),'version':self.version}


class Hub:
    def __init__(self):self.feeds={};self.leases={};self.lock=threading.Lock();atexit.register(self.close)
    def retain(self,owner,pairs,store):
        with self.lock:
            now=time.monotonic();self.leases[owner]=(now,{(str(store.path),s,i) for s,i in pairs})
            self.leases={o:v for o,v in self.leases.items() if now-v[0]<90}
            wanted=set().union(*(v[1] for v in self.leases.values()))
            for key in list(self.feeds):
                if key not in wanted:self.feeds.pop(key).stop.set()
    def get(self,symbol,interval,store):
        key=(str(store.path),symbol,interval)
        with self.lock:
            for k,f in list(self.feeds.items()):
                if f.stop.is_set() or time.monotonic()-f.touched>90:f.stop.set();del self.feeds[k]
            if key not in self.feeds:
                if len(self.feeds)>=4:raise MarketError('Достигнут лимит 4 потоков. Закройте лишние вкладки и подождите 90 секунд.')
                self.feeds[key]=Feed(symbol,interval,store)
            return self.feeds[key]
    def close(self):
        for f in self.feeds.values():f.stop.set()
