"""Child of the BASE-01 test. All commands after startup require runtime ownership."""
from contextlib import closing, contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch


NOW = 1_700_000_000
BUY = '00000000-0000-4000-8000-000000000001'
SELL = '00000000-0000-4000-8000-000000000002'
SYMBOL = 'BTCUSDT'
SESSION = 'base-01-test'
QUOTE = {'price': 100, 'bid': 99.99, 'ask': 100.01, 'ts': NOW, 'fresh': True,
         'source': 'synthetic BASE-01 fixture'}
RULES = {'step': '.001', 'tick': '.01', 'minimum': '5', 'maximum': '100', 'retrieved': NOW}


class FixtureHub:
    def retain(self, owner, pairs, store):
        pass

    def get(self, symbol, interval, store):
        assert symbol == SYMBOL
        return self

    def snapshot(self):
        return {'quote': QUOTE, 'fresh': True, 'rules': RULES}


def report(message):
    print(json.dumps(message), flush=True)


def interrupt_confirm(gateway):
    """Stop at the context-manager boundary immediately before SQLite COMMIT."""
    connect = gateway.store.connect

    @contextmanager
    def pause_writer():
        with closing(connect()) as db, db:
            yield db
            if db.in_transaction:
                order = db.execute('SELECT body FROM orders WHERE id=?', (SELL,)).fetchone()
                intent = db.execute('SELECT body FROM intents WHERE id=?', (SELL,)).fetchone()
                state = json.loads(db.execute('SELECT body FROM paper WHERE id=1').fetchone()[0])
                assert json.loads(order[0])['status'] == json.loads(intent[0])['status'] == 'Filled'
                assert Decimal(state['positions'][SYMBOL]['qty']) == Decimal('0.5')
                assert Decimal(state['realized']) < 0
                report('sell staged before commit')
                # Only SIGKILL should end this wait. EOF or a command rolls back.
                sys.stdin.readline()
                raise AssertionError('interrupted sale must never commit')

    with patch.object(gateway.store, 'connect', pause_writer):
        gateway.confirm(SELL, SESSION, {SYMBOL: QUOTE}, {SYMBOL: RULES}, ack=True)
    raise AssertionError('sale returned without reaching its transaction boundary')


def main():
    db_path = Path(os.environ['MOEX_DATA_DIR']) / 'crypto-v08.sqlite3'

    def isolate(event, args):
        if event.startswith('socket.') or (event == 'sqlite3.connect' and Path(args[0]) != db_path):
            # Fail the process even if the background monitor catches an exception.
            os.write(2, b'BASE-01 isolation violation\n')
            os._exit(90)

    sys.addaudithook(isolate)
    from moex_intelligence.crypto import runtime
    from moex_intelligence.crypto.orders import OrderPreview
    from moex_intelligence.crypto.storage import Store

    with patch.object(runtime, 'hub', return_value=FixtureHub()), patch.object(time, 'time', lambda: NOW):
        try:
            worker = runtime.start()
        except RuntimeError as exc:
            if 'Другой экземпляр CandlePath' not in str(exc):
                raise
            report('ownership denied')
            return

        try:
            assert worker.thread.is_alive() and worker.store.path == db_path
            # Independent gateway connection; the fault barrier never wraps the monitor's connections.
            gateway = OrderPreview(Store(db_path))
            quotes, rules = {SYMBOL: QUOTE}, {SYMBOL: RULES}
            if sys.argv[1] == 'initial':
                gateway.prepare({'id': BUY, 'symbol': SYMBOL, 'side': 'BUY', 'quantity': '1',
                                 'stop': '97', 'target': '106'}, quotes, rules, SESSION)
            fill = gateway.confirm(BUY, SESSION, quotes, rules, ack=True)
            if sys.argv[1] == 'initial':
                gateway.prepare({'id': SELL, 'symbol': SYMBOL, 'side': 'SELL', 'quantity': '0.5'},
                                quotes, rules, SESSION)
            worker.tick()
            assert worker.status()['active']
            report(fill)
            command = sys.stdin.readline().strip()
            if command == 'stage sale':
                interrupt_confirm(gateway)
            else:
                assert command == 'shutdown', command
        finally:
            runtime.shutdown()


if __name__ == '__main__':
    main()
