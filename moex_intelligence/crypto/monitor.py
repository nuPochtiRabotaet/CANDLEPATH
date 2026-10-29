"""Local process-scoped paper protection worker; independent of browser fragment ticks."""
import atexit,threading,time
from .paper import Paper
from .costs import CostModel,D
from .inventory import liquidation_at
class PaperMonitor:
    def __init__(self,store,hub):
        self.store=store;self.hub=hub;self.stop=threading.Event();self.heartbeat=0;self.ready=False;self.error='';self.last_success=0;self.health='Recovering';self.owner='protection:'+str(store.path)
        self.thread=threading.Thread(target=self.run,daemon=True,name='paper-protection');self.thread.start();atexit.register(self.stop.set)
    def tick(self):
        paper=Paper(self.store);symbols=list(paper.state()['positions']);self.hub.retain(self.owner,[(s,'15') for s in symbols],self.store)
        snapshots={s:self.hub.get(s,'15',self.store).snapshot() for s in symbols}
        quotes={s:{**v['quote'],'fresh':v['fresh']} for s,v in snapshots.items()};rules={s:v['rules'] for s,v in snapshots.items()}
        attempts=paper.protect(quotes,rules);paper.mark(quotes);now=time.time()
        fresh=all(v['fresh'] for v in snapshots.values())
        valid_rules=all(v['rules'] and 0<=now-v['rules'].get('retrieved',0)<=86400 for v in snapshots.values())
        from .paper import position_key
        obligations={position_key(s,p) for s,p in paper.state()['positions'].items()}
        failed=any(a['id'] in obligations and a['status'] not in ('Filled','new') for a in attempts)
        self.partial=False;unprotected=False
        if fresh and valid_rules:
            state=paper.state();model=CostModel.from_state(state)
            for sym,position in state['positions'].items():
                allocation,_=liquidation_at(position,position['stop'],rules[sym],model)
                self.partial=self.partial or not allocation['fully_sellable']
                unprotected=unprotected or D(allocation['sellable_quantity'])==0 or D(allocation['remaining_after_sale'])>D(position.get('protection_residue_limit','0'))
        self.ready=fresh and valid_rules and not failed and not unprotected
        self.health='Stale Market Data' if not fresh else 'Degraded' if not self.ready else 'Partial Coverage' if self.partial else 'Running'
        if self.ready:self.last_success=now
        self.heartbeat=now;self.error=''
    def run(self):
        while not self.stop.is_set():
            try:self.tick()
            except Exception as exc:self.error=type(exc).__name__;self.ready=False;self.health='Degraded'
            self.stop.wait(2)
        self.hub.retain(self.owner,[],self.store)
    def status(self):
        active=self.thread.is_alive() and time.time()-self.heartbeat<8 and self.ready
        return {'active':active,'state':self.health if self.thread.is_alive() and (not self.heartbeat or time.time()-self.heartbeat<8) else 'Not Monitoring','last_success':self.last_success,'heartbeat':self.heartbeat,'message':('Local protective monitor active · продаваемая часть; остаток НЕ защищён' if getattr(self,'partial',False) else 'Local protective monitor active · только пока работает процесс приложения') if active else 'Protective Orders Not Actively Monitored','error':self.error}
