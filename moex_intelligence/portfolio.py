"""RUB-only virtual cash ledger. No brokerage connectivity or order execution."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import sqlite3
import uuid
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from moex import identifier
from .validation import finite, integer

KINDS = {'deposit', 'withdrawal', 'buy', 'sell', 'dividend', 'coupon', 'opening'}


def validate_event(event):
    e = dict(event)
    e['date'] = date.fromisoformat(e['date']).isoformat()
    if e.get('kind') not in KINDS: raise ValueError('Unknown ledger event kind.')
    if e.get('currency', 'RUB') != 'RUB': raise ValueError('MVP portfolio supports RUB only; no implicit FX conversion.')
    e['currency'] = 'RUB'
    e['fee'] = finite(e.get('fee', 0.), 'fee', 0, 1e12)
    if e['kind'] == 'opening':
        e['amount'] = finite(e.get('amount', 0), 'opening cash', 0, 1e12)
        if e['fee']: raise ValueError('Начальный остаток не является сделкой и не имеет комиссии.')
        holdings = e.get('holdings', [])
        if not isinstance(holdings, list) or len(holdings) > 100: raise ValueError('Не более 100 начальных позиций.')
        clean = []
        for p in holdings:
            clean.append({'symbol': identifier(p['symbol']),
                          'quantity': integer(p['quantity'], 'quantity', 1, 100000000),
                          'price': finite(p['price'], 'average cost in RUB per unit', 1e-8, 1e12)})
        if len({p['symbol'] for p in clean}) != len(clean): raise ValueError('Повторяющиеся бумаги в начальном остатке.')
        e['holdings'] = clean
    elif e['kind'] in {'buy','sell'}:
        e['symbol'] = identifier(e['symbol'])
        e['quantity'] = integer(e['quantity'], 'quantity', 1, 100000000)
        e['price'] = finite(e['price'], 'price (RUB per unit)', 1e-8, 1e12)
    else:
        e['amount'] = finite(e['amount'], 'amount', 1e-8, 1e12)
        if e['kind'] in {'dividend','coupon'}:
            e['symbol'] = identifier(e['symbol'])
            if not isinstance(e.get('source'), str) or not e['source'].strip():
                raise ValueError('Dividend/coupon requires a source reference, e.g. broker statement date.')
    if len(json.dumps(e)) > (32768 if e['kind'] == 'opening' else 4096): raise ValueError('Event too large.')
    return e


def ledger_state(events):
    if len(events) > 5000: raise ValueError('Portfolio limited to 5000 events.')
    ordered = sorted([validate_event(e) for e in events], key=lambda e: e['date'])
    opening = [e for e in ordered if e['kind'] == 'opening']
    if len(opening) > 1 or opening and ordered[0]['kind'] != 'opening':
        raise ValueError('Начальный остаток должен быть единственным и предшествовать всем операциям.')
    cash, contributed, realized, income = 0., 0., 0., 0.
    positions = defaultdict(lambda: {'quantity': 0, 'cost_basis': 0.})
    for e in ordered:
        kind = e['kind']; fee = e['fee']
        if kind == 'opening':
            cash = e['amount']
            for p in e['holdings']:
                positions[p['symbol']] = {'quantity': p['quantity'], 'cost_basis': p['quantity']*p['price']}
            contributed = cash + sum(p['cost_basis'] for p in positions.values())
        elif kind == 'deposit': cash += e['amount']-fee; contributed += e['amount']
        elif kind == 'withdrawal': cash -= e['amount']+fee; contributed -= e['amount']
        elif kind in {'dividend','coupon'}: cash += e['amount']-fee; income += e['amount']-fee
        else:
            pos = positions[e['symbol']]; qty = e['quantity']; gross = qty*e['price']
            if kind == 'buy':
                cash -= gross+fee; pos['quantity'] += qty; pos['cost_basis'] += gross+fee
            else:
                if qty > pos['quantity']: raise ValueError(f"{e['symbol']}: cannot sell more units than held")
                removed = pos['cost_basis'] * qty / pos['quantity']
                pos['quantity'] -= qty; pos['cost_basis'] -= removed
                cash += gross-fee; realized += gross-fee-removed
        if cash < -1e-7: raise ValueError(f"Insufficient cash on {e['date']}; deposits must precede purchases.")
    return {'cash': max(cash, 0.), 'net_contributions': contributed, 'realized_pnl': realized, 'income': income,
            'positions': {k:v for k,v in positions.items() if v['quantity']}, 'events': ordered,
            'history_complete': not bool(opening), 'tracking_start': ordered[0]['date'] if ordered else None}


def analyze_portfolio(events, marks):
    """Marks: {ticker: {price: RUB per unit incl. bond accrued interest, as_of, source}}."""
    state = ledger_state(events)
    positions = []
    last_event = max((e['date'] for e in state['events']), default=None)
    for symbol, p in state['positions'].items():
        mark = marks.get(symbol)
        if not isinstance(mark, dict): raise ValueError(f'Missing dated valuation for {symbol}.')
        price = finite(mark.get('price'), f'{symbol} valuation', 1e-8, 1e12)
        as_of = date.fromisoformat(mark['as_of']).isoformat()
        if last_event and as_of < last_event: raise ValueError('Valuation must not predate ledger events.')
        if not isinstance(mark.get('source'), str) or not mark['source'].strip(): raise ValueError('Valuation source required.')
        value = price * p['quantity']
        positions.append({'symbol': symbol, **p, 'price': price, 'market_value': value,
                          'unrealized_pnl': value-p['cost_basis'], 'as_of': as_of, 'source': mark['source']})
    dates = {p['as_of'] for p in positions}
    if len(dates) > 1: raise ValueError('All portfolio valuations must use the same as_of date.')
    nav = state['cash'] + sum(p['market_value'] for p in positions)
    for p in positions: p['weight_pct'] = p['market_value']/nav*100 if nav else 0.
    return {k:state[k] for k in ['cash','net_contributions','realized_pnl','income']} | {
        'equity': nav, 'total_pnl': nav-state['net_contributions'] if state['history_complete'] else None, 'positions': positions,
        'history_complete': state['history_complete'], 'tracking_start': state['tracking_start'],
        'unrealized_pnl': sum(p['unrealized_pnl'] for p in positions),
        'as_of': next(iter(dates), last_event), 'currency': 'RUB',
        'limitations': ['Manual ledger and sourced valuations; dividend/coupon source is not automatically verified.',
                        'Bond entries and marks must be dirty RUB price per bond, not quoted percent of face value.',
                        'Snapshot P&L is not time-weighted return. Use dated valuation history for return/drawdown.']}


def portfolio_curve(events, prices):
    """Strict complete valuations at each date; external flows assumed at start of day."""
    state = ledger_state(events)
    if prices.empty or not isinstance(prices.index, pd.DatetimeIndex) or prices.index.hasnans or prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError('Unique increasing daily valuation index required.')
    dates = set(prices.index.strftime('%Y-%m-%d'))
    if any(e['date'] not in dates for e in state['events']):
        raise ValueError('Each event date must have a valuation row; no implicit holiday shifting.')
    previous, unit_nav, curve = 0., 1., []
    history = []
    for day, marks in prices.iterrows():
        daystr = str(day.date()); todays = [e for e in state['events'] if e['date'] == daystr]
        history.extend(todays)
        snapshot = analyze_portfolio(history, {sym:{'price':val,'as_of':daystr,'source':'supplied valuation history'} for sym,val in marks.items()})
        external = sum(e['amount']*(1 if e['kind']=='deposit' else -1) for e in todays if e['kind'] in {'deposit','withdrawal'})
        # The transfer day's observed market NAV is the baseline, never the supplied old cost.
        for e in todays:
            if e['kind'] == 'opening':
                opening_marks = {sym:{'price':val,'as_of':daystr,'source':'supplied valuation history'} for sym,val in marks.items()}
                external += analyze_portfolio([e], opening_marks)['equity']
        denominator = previous + external
        if denominator < 0 or denominator == 0 and snapshot['equity'] != 0:
            raise ValueError('Daily-flow convention cannot measure this return; add intraday valuations.')
        daily_return = snapshot['equity']/denominator-1 if denominator else 0.
        unit_nav *= 1+daily_return
        curve.append({'date':day, 'equity':snapshot['equity'], 'external_flow':external,'daily_return':daily_return, 'unit_nav':unit_nav})
        previous = snapshot['equity']
    frame = pd.DataFrame(curve).set_index('date')
    values = np.r_[1., frame['unit_nav']]
    frame['drawdown'] = (values / np.maximum.accumulate(values)-1)[1:]
    return frame, {'time_weighted_return_pct': (unit_nav-1)*100, 'max_drawdown_pct': float(frame['drawdown'].min()*100),
                   'flow_timing': 'External deposits/withdrawals at beginning of each valuation day; no mark forward-fill.'}


def stress_test(snapshot, shocks):
    """One-step price shocks in percent. Cash unchanged. No guessed correlations."""
    if set(shocks) - {p['symbol'] for p in snapshot['positions']}:
        raise ValueError('Shock symbol not in portfolio.')
    loss = sum(p['market_value'] * finite(shocks.get(p['symbol'], 0), 'shock', -100, 500) / 100 for p in snapshot['positions'])
    return {'equity_before': snapshot['equity'], 'equity_after': snapshot['equity']+loss, 'change_rub': loss,
            'change_pct': loss/snapshot['equity']*100 if snapshot['equity'] else 0., 'shocks_pct': shocks,
            'assumption': 'Instantaneous specified price changes, unchanged cash; no forecast probabilities.'}


class ConflictError(ValueError):
    pass


class PortfolioStore:
    """Account-scoped ledger; atomic replay, optimistic locking and correction audit.

    load/append_many remain compatible with v0.4. Corrections replace a record,
    never fabricate a compensating trade. The UI uses bundle() revision guards.
    """
    def __init__(self, path, account_id='alfa-main'):
        self.path = Path(path)
        self.account_id = identifier(account_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            exists = db.execute("SELECT name FROM sqlite_master WHERE name='events'").fetchone()
            columns = [r[1] for r in db.execute('PRAGMA table_info(events)')] if exists else []
            if exists and 'account_id' not in columns:
                backup = self.path.with_name(self.path.name+'.v04-backup')
                if not backup.exists():
                    with sqlite3.connect(backup) as target: db.backup(target)
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, id TEXT UNIQUE, body TEXT NOT NULL)')
            if 'account_id' not in [r[1] for r in db.execute('PRAGMA table_info(events)')]:
                db.execute("ALTER TABLE events ADD COLUMN account_id TEXT NOT NULL DEFAULT 'ALFA-MAIN'")
            db.execute('CREATE TABLE IF NOT EXISTS portfolio_revisions (account_id TEXT PRIMARY KEY, revision INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO portfolio_revisions VALUES (?,0)', (self.account_id,))
            db.execute('CREATE TABLE IF NOT EXISTS portfolio_audit (seq INTEGER PRIMARY KEY, account_id TEXT, changed_at TEXT, action TEXT, event_id TEXT, old_body TEXT, new_body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS import_keys (account_id TEXT, key TEXT, event_id TEXT, PRIMARY KEY(account_id,key))')

    def connect(self): return sqlite3.connect(self.path, timeout=10)

    def _records(self, db):
        return [{'id': r[0], 'event': json.loads(r[1])} for r in db.execute(
            'SELECT id,body FROM events WHERE account_id=? ORDER BY seq', (self.account_id,))]

    def bundle(self):
        with self.connect() as db:
            db.execute('BEGIN')
            revision = db.execute('SELECT revision FROM portfolio_revisions WHERE account_id=?', (self.account_id,)).fetchone()[0]
            return {'revision': revision, 'records': self._records(db), 'account_id': self.account_id}

    def load(self): return [r['event'] for r in self.bundle()['records']]

    def _guard(self, db, revision):
        current = db.execute('SELECT revision FROM portfolio_revisions WHERE account_id=?', (self.account_id,)).fetchone()[0]
        if revision is not None and revision != current:
            raise ConflictError('Портфель изменён в другом окне. Обновите страницу и проверьте действие заново.')

    def _audit(self, db, action, event_id, old, new):
        db.execute('INSERT INTO portfolio_audit(account_id,changed_at,action,event_id,old_body,new_body) VALUES (?,?,?,?,?,?)',
                   (self.account_id, datetime.now(timezone.utc).isoformat(), action, event_id,
                    json.dumps(old, ensure_ascii=False) if old is not None else None,
                    json.dumps(new, ensure_ascii=False) if new is not None else None))

    def _bump(self, db):
        db.execute('UPDATE portfolio_revisions SET revision=revision+1 WHERE account_id=?', (self.account_id,))

    def imported_keys(self):
        with self.connect() as db:
            return {r[0] for r in db.execute('SELECT key FROM import_keys WHERE account_id=?', (self.account_id,))}

    def append_many(self, events, *, expected_revision=None):
        if not isinstance(events, list) or not events: raise ValueError('Nonempty event list required.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._guard(db, expected_revision)
            clean = [validate_event(e) for e in events]
            ledger_state([r['event'] for r in self._records(db)]+clean)
            ids = []
            for e in clean:
                event_id = str(uuid.uuid4())
                if e.get('import_key'):
                    if not isinstance(e['import_key'], str) or len(e['import_key']) > 256: raise ValueError('Invalid import key.')
                    try: db.execute('INSERT INTO import_keys VALUES (?,?,?)', (self.account_id,e['import_key'],event_id))
                    except sqlite3.IntegrityError as exc: raise ValueError('Эта строка отчёта уже импортирована, включая исправленные или удалённые записи.') from exc
                db.execute('INSERT INTO events(id,body,account_id) VALUES (?,?,?)', (event_id,json.dumps(e,ensure_ascii=False),self.account_id))
                self._audit(db,'add',event_id,None,e);ids.append(event_id)
            self._bump(db)
            return ids

    def correct(self, event_id, event, *, expected_revision):
        return self._change(event_id, validate_event(event), expected_revision)

    def delete(self, event_id, *, expected_revision):
        return self._change(event_id, None, expected_revision)

    def _change(self, event_id, new, revision):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._guard(db,revision)
            records = self._records(db)
            record = next((r for r in records if r['id']==event_id), None)
            if record is None: raise ValueError('Запись не найдена в этом счёте.')
            old = record['event']
            if new is not None:
                # Keep statement identity through corrections to block a later accidental reimport.
                new = {**new, **{k:old[k] for k in ('import_key','import_file','external_id') if k in old}}
            replay = [new if r['id']==event_id else r['event'] for r in records if r['id']!=event_id or new is not None]
            ledger_state(replay)
            if new is None: db.execute('DELETE FROM events WHERE id=? AND account_id=?', (event_id,self.account_id))
            else: db.execute('UPDATE events SET body=? WHERE id=? AND account_id=?', (json.dumps(new,ensure_ascii=False),event_id,self.account_id))
            self._audit(db,'delete' if new is None else 'correct',event_id,old,new)
            self._bump(db)

    def audit(self):
        with self.connect() as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute('SELECT changed_at,action,event_id,old_body,new_body FROM portfolio_audit WHERE account_id=? ORDER BY seq DESC', (self.account_id,))]


