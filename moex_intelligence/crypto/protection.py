"""Persisted Edit -> Preview -> Confirm -> Commit for LOCAL PAPER protection."""
import json
import time
import uuid
from .orders import OrderPreview, revision, rule_revision, digest, spread
from .inventory import position_revision
from .paper import Paper, position_key
from .risk import protection_plan, quote_ok, PROFILE, RiskError, D


class ProtectionPreview(OrderPreview):
    def prepare(self, request, quotes, rules, owner):
        if not owner:
            raise RiskError('Нет сессии')
        rid = str(request['id'])
        uuid.UUID(rid)
        symbol = request['symbol']
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT body FROM intents WHERE id=?', (rid,)).fetchone()
            if old:
                intent = json.loads(old[0])
                if intent['owner'] != owner or intent.get('kind') != 'protection':
                    raise RiskError('ID принадлежит другому действию')
                return intent
            state = json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0])
            Paper.refresh(state, quotes)
            rule = rules.get(symbol)
            plan = protection_plan(state, quotes, symbol, request['stop'], request['target'], rule, rules)
            if not plan['allowed']:
                raise RiskError('; '.join(plan['errors']))
            pos, now, quote = state['positions'][symbol], time.time(), quotes[symbol]
            intent = {'id': rid, 'kind': 'protection', 'owner': owner, 'status': 'Prepared',
                      'created': now, 'expires': now+30,
                      'request': {'id': rid, 'symbol': symbol, 'stop': plan['stop'], 'target': plan['target']},
                      'estimate': plan, 'position_id': position_key(symbol, pos),
                      'position_revision': position_revision(pos), 'account_revision': revision(state),
                      'rule_revision': rule_revision(rule), 'profile': digest(PROFILE), 'quote': quote,
                      'spread_bps': str(spread(quote)), 'source': 'LOCAL PAPER · '+quote.get('source', 'public Bybit quote'),
                      'history': [{'status': 'Prepared', 'time': now}]}
            db.execute('INSERT INTO intents VALUES(?,?)', (rid, json.dumps(intent)))
            db.execute('INSERT INTO events(time,body) VALUES(?,?)', (now, json.dumps({'message': 'Protection preview prepared', 'intent': rid, 'position_id': intent['position_id']})))
            return intent

    def confirm(self, ident, owner, quotes, rules, ack=False):
        if ack is not True:
            raise RiskError('Подтвердите изменение локальной защиты')
        failure, result = None, None
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM intents WHERE id=?', (ident,)).fetchone()
            if not row:
                raise RiskError('Предпросмотр отсутствует')
            intent = json.loads(row[0])
            if intent['owner'] != owner or intent.get('kind') != 'protection':
                raise RiskError('Другая сессия / тип действия')
            if intent['status'] == 'Applied':
                return intent
            try:
                if intent['status'] != 'Prepared' or time.time() > intent['expires']:
                    raise RiskError('Предпросмотр недоступен или истёк')
                state = json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0])
                Paper.refresh(state, quotes)
                symbol = intent['request']['symbol']
                pos, quote, rule = state['positions'].get(symbol), quotes.get(symbol, {}), rules.get(symbol)
                if not pos or position_key(symbol, pos) != intent['position_id'] or position_revision(pos) != intent['position_revision']:
                    raise RiskError('Позиция изменилась: нужен новый preview')
                if revision(state) != intent['account_revision'] or digest(PROFILE) != intent['profile']:
                    raise RiskError('Счёт / тариф / риск изменились')
                if not quote_ok(quote):
                    raise RiskError('Stale Data')
                if not rule or not 0 <= time.time()-rule.get('retrieved', 0) <= 86400 or rule_revision(rule) != intent['rule_revision']:
                    raise RiskError('Правила изменились / устарели')
                if abs(D(quote['bid'])/D(intent['quote']['bid'])-1)*10000 > 10 or spread(quote) > D(intent['spread_bps'])+2:
                    raise RiskError('Цена / спред изменились')
                plan = protection_plan(state, quotes, symbol, intent['request']['stop'], intent['request']['target'], rule, rules)
                if not plan['allowed']:
                    raise RiskError('; '.join(plan['errors']))
                pos.update(stop=plan['stop'], target=plan['target'], protection_residue_limit=plan['inventory']['remaining_after_sale'], protection_revision=pos.get('protection_revision', 0)+1)
                intent.update(status='Applied', result=plan, applied_at=time.time())
                intent['history'].append({'status': 'Applied', 'time': intent['applied_at']})
                db.execute('UPDATE paper SET body=? WHERE id=1', (json.dumps(state),))
                db.execute('INSERT INTO events(time,body) VALUES(?,?)', (intent['applied_at'], json.dumps({
                    'message': 'LOCAL PAPER protection updated', 'intent': ident, 'position_id': intent['position_id'],
                    'before': {'stop': plan['old_stop'], 'target': plan['old_target']},
                    'after': {'stop': plan['stop'], 'target': plan['target']}, 'risk_delta': plan['risk_delta']})))
                result = intent
            except (ValueError, KeyError, ArithmeticError) as error:
                failure = RiskError(str(error))
                if intent['status'] == 'Prepared':
                    intent.update(status='Expired', error=str(error))
                    intent['history'].append({'status': 'Expired', 'time': time.time()})
                db.execute('INSERT INTO events(time,body) VALUES(?,?)', (time.time(), json.dumps({'message': 'Protection change blocked: '+str(error), 'intent': ident})))
            db.execute('UPDATE intents SET body=? WHERE id=?', (json.dumps(intent), ident))
        if failure:
            raise failure
        return result
