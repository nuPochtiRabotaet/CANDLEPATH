"""Decimal accounting for simulated spot Market (taker only).
BUY uses ask, SELL uses bid: spread is observed, never added again.
"""
from dataclasses import dataclass,asdict
from decimal import Decimal,ROUND_FLOOR
from typing import Literal
D=lambda x:Decimal(str(x))
FeeCurrency=Literal['base','quote']
BudgetMode=Literal['notional','total']
@dataclass(frozen=True)
class FeeSchedule:
    version:str='paper-default-v1'
    maker:str='0.001'
    taker:str='0.001'
    buy_currency:FeeCurrency='quote'
    sell_currency:FeeCurrency='quote'
    source:str='LOCAL PAPER assumption; not account-verified'
    def __post_init__(self):
        if not self.version or self.buy_currency not in ('base','quote') or self.sell_currency!='quote':raise ValueError('SELL/base is unsupported')
        for x in (self.maker,self.taker):
            if not D(x).is_finite() or not 0<=D(x)<=D('.02'):raise ValueError('Fee must be 0–2%')
@dataclass(frozen=True)
class ExecutionAssumptions:
    slippage_bps:str='5'
    version:str='paper-slippage-v1'
    def __post_init__(self):
        if not D(self.slippage_bps).is_finite() or not 0<=D(self.slippage_bps)<=100:raise ValueError('Slippage must be 0–100 bps')
    @property
    def slip(self):return D(self.slippage_bps)/10000
@dataclass(frozen=True)
class CostModel:
    fees:FeeSchedule=FeeSchedule()
    execution:ExecutionAssumptions=ExecutionAssumptions()
    def snapshot(self):return asdict(self)
    @classmethod
    def from_state(cls,state):
        raw=state.get('cost_model') or {}
        return cls(FeeSchedule(**raw.get('fees',{})),ExecutionAssumptions(**raw.get('execution',{})))
@dataclass(frozen=True)
class EstimatedFill:
    side:str
    quantity:Decimal
    price:Decimal
    notional:Decimal
    fee_currency:FeeCurrency
    fee_quantity:Decimal
    fee_quote_value:Decimal
    net_base:Decimal
    cash_delta:Decimal
    spread:Decimal
    slippage_cost:Decimal
    def strings(self):return {k:str(v) if isinstance(v,Decimal) else v for k,v in asdict(self).items()}
@dataclass(frozen=True)
class SimulatedFill:
    estimate:EstimatedFill
    model:CostModel
    source:str='LOCAL PAPER'
    def snapshot(self):return {'values':self.estimate.strings(),'model':self.model.snapshot(),'source':self.source,'engine_version':'costs-v1','liquidity':'taker'}
def estimate(side,quantity,quote,model):
    qty=D(quantity)
    if side not in ('BUY','SELL') or not qty.is_finite() or qty<=0:raise ValueError('Invalid fill quantity/side')
    ref=D(quote['ask' if side=='BUY' else 'bid']);slip=model.execution.slip
    if not ref.is_finite() or ref<=0:raise ValueError('Invalid execution reference')
    price=ref*(1+slip if side=='BUY' else 1-slip);amount=price*qty;rate=D(model.fees.taker)
    currency=model.fees.buy_currency if side=='BUY' else model.fees.sell_currency
    fee=qty*rate if currency=='base' else amount*rate
    base=qty-fee if side=='BUY' and currency=='base' else qty
    delta=-(amount+(fee if currency=='quote' else 0)) if side=='BUY' else amount-fee
    return EstimatedFill(side,qty,price,amount,currency,fee,fee*price if currency=='base' else fee,base,delta,D(quote.get('ask',ref))-D(quote.get('bid',ref)),qty*ref*slip)
def budget_quantity(budget,quote,step,model,mode:BudgetMode='notional'):
    value=D(budget);step=D(step)
    if mode not in ('notional','total') or not value.is_finite() or value<=0 or not step.is_finite() or step<=0:raise ValueError('Invalid budget/step')
    unit=estimate('BUY',1,quote,model);divisor=unit.notional if mode=='notional' else -unit.cash_delta
    return (value/divisor/step).to_integral_value(rounding=ROUND_FLOOR)*step
def basis(p):return D(p['cost_basis']) if 'cost_basis' in p else D(p['entry'])*D(p['qty'])+D(p['entry_fee'])
def scenario(quantity,quote,stop,target,model):
    buy=estimate('BUY',quantity,quote,model);exit_now=estimate('SELL',buy.net_base,quote,model)
    debit=-buy.cash_delta;loss=debit-estimate('SELL',buy.net_base,{'bid':stop},model).cash_delta
    gain=estimate('SELL',buy.net_base,{'bid':target},model).cash_delta-debit
    mid=(D(quote['bid'])+D(quote['ask']))/2;gross_loss=(mid-D(stop))*D(quantity)
    return buy,{'total':debit,'received':buy.net_base,'loss':loss,'gain':gain,'rr':gain/loss if loss>0 else D(0),
      'gross_rr':(D(target)-mid)*D(quantity)/gross_loss if gross_loss>0 else D(0),
      'round_trip_fee':buy.fee_quote_value+exit_now.fee_quote_value,'round_trip_cost':debit-exit_now.cash_delta,
      'exit_fee':exit_now.fee_quote_value,'spread_bps':buy.spread/mid*10000,'slippage_cost':buy.slippage_cost+exit_now.slippage_cost,
      'stop_distance':mid-D(stop),'target_distance':D(target)-mid}
