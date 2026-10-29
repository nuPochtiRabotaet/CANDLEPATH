"""Synthetic QA ONLY. Never selected or imported by production code."""
import sys,os,time,math,runpy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from moex_intelligence.crypto import ui
from moex_intelligence.crypto.market import seconds
assert os.environ.get('MOEX_DATA_DIR'), 'QA needs an isolated data directory'
class TestFeed:
    def __init__(self,symbol,interval):self.symbol=symbol;self.interval=interval
    def snapshot(self):
        dt=seconds(self.interval);end=int(time.time())//dt*dt;base={'BTCUSDT':68000,'ETHUSDT':3400,'SOLUSDT':145}[self.symbol];rows=[]
        for i in range(280):
            c=base*(1+.06*math.sin(i/17)+i*.0001);o=base*(1+.06*math.sin((i-1)/17)+(i-1)*.0001)
            rows.append({'time':end-(279-i)*dt,'open':o,'high':max(o,c)+base*.002,'low':min(o,c)-base*.002,'close':c,'volume':100+50*(i%7),'closed':i<279})
        if st.session_state.get('qa_potential',False):
            from moex_intelligence.crypto.analysis import analyze
            closed=[dict(x,closed=True) for x in rows]
            buy=[x for x in analyze(closed,self.symbol,self.interval)['signals'] if x['type']=='BUY'][-1]
            rows=[x for x in rows if x['time']<=buy['candle_time']]
            shift=end-rows[-1]['time']
            rows=[dict(x,time=x['time']+shift,closed=True) for x in rows];rows[-1]['closed']=False
        price=rows[-1]['close'];fresh=not st.session_state.get('qa_stale',False)
        return {'symbol':self.symbol,'interval':self.interval,'candles':rows,'rules':{'step':'.00001' if self.symbol=='BTCUSDT' else '.001','tick':'.01','minimum':'5','maximum':'10000','retrieved':time.time()},'quote':{'source':'QA SYNTHETIC · not Bybit live','price':price,'bid':price*.9999,'ask':price*1.0001,'change':1.75,'ts':time.time()-(60 if not fresh else 0)},'status':'Live' if fresh else 'Stale Data','fresh':fresh,'age':0 if fresh else 60,'error':'','events':[{'time':time.time(),'message':'QA synthetic adapter · not a Bybit connection'}],'version':2 if st.session_state.get('qa_potential',False) else 1}
class TestHub:
    def retain(self,*args):pass
    def get(self,symbol,interval,store):return TestFeed(symbol,interval)
ui.hub=lambda:TestHub()
from moex_intelligence.crypto.storage import Store as ActualStore
ui.Store=lambda path:ActualStore(Path(path).with_name('qa-potential.sqlite3') if st.session_state.get('qa_potential',False) else path)
class TestMonitor:
    def status(self):return {'active':False,'message':'QA fixture · Protective Orders Not Actively Monitored'}
ui.monitor=lambda path:TestMonitor()
st.warning('QA FIXTURE · искусственные свечи для проверки интерфейса. Не рыночные данные и не соединение Bybit.')
st.checkbox('QA: устаревшая цена',key='qa_stale')
st.checkbox('QA: предварительный BUY',key='qa_potential')
runpy.run_path(str(Path(__file__).with_name('ui_fixture.py')),run_name='__main__')
