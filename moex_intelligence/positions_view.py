"""Read-only responsive portfolio list. No ledger mutation entry points."""
from functools import lru_cache
from pathlib import Path
import hashlib,json
import streamlit as st
from .design import css_vars
from .formatting import money,price,percent,quantity

ASSETS=Path(__file__).with_name('components')


@lru_cache(maxsize=1)
def component():
    return st.components.v2.component('moex_positions_v071',html=(ASSETS/'positions.html').read_text(),css=css_vars(':host')+(ASSETS/'positions.css').read_text(),js=(ASSETS/'positions.js').read_text())


def positions_list(state,snapshot,marks,revision):
    values={p['symbol']:p for p in snapshot['positions']} if snapshot else {}
    rows=[]
    for symbol,held in state['positions'].items():
        p=values.get(symbol,{});mark=marks.get(symbol,{});raw={'name':mark.get('name') or symbol,'quantity':held['quantity'],'price':mark.get('price'),'value':p.get('market_value'),'weight':p.get('weight_pct'),'pnl':p.get('unrealized_pnl')}
        rows.append({'symbol':symbol,'name':raw['name'],'sort':raw,'display':{'quantity':quantity(raw['quantity']),'price':price(raw['price']),'value':money(raw['value']),'weight':percent(raw['weight']),'pnl':money(raw['pnl'],signed=True)}})
    symbols=[r['symbol'] for r in rows];selected=st.session_state.get('portfolio_selected_symbol')
    if selected not in symbols:selected=symbols[0]
    st.session_state.portfolio_selected_symbol=selected
    context=hashlib.sha256(json.dumps([revision,rows],sort_keys=True).encode()).hexdigest()[:20]
    previous=st.session_state.get('portfolio_selection_state',{});seq=previous.get('seq',0) if previous.get('context')==context else 0
    key='positions_'+context
    def receive():
        value=st.session_state[key];event=value.get('selection') if isinstance(value,dict) else value.selection
        if event and event.get('context')==context and event.get('symbol') in symbols and isinstance(event.get('seq'),int) and event['seq']>=seq:
            st.session_state.portfolio_selected_symbol=event['symbol'];st.session_state.portfolio_selection_state=event
    def action():
        value=st.session_state[key];event=value.get('action') if isinstance(value,dict) else value.action
        if event and event.get('context')==context and event.get('symbol') in symbols and event.get('kind') in {'evaluate','existing','buy'}:
            from .portfolio_ui import open_research
            open_research(event['symbol'],event['kind'])
    component()(key=key,data={'rows':rows,'selected':selected,'context':context,'seq':seq},on_selection_change=receive,on_action_change=action)
    return st.session_state.get('portfolio_selected_symbol',selected),values
