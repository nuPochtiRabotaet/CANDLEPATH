"""EXIT readiness must agree with the existing manual Paper sale preview.

Synthetic quotes and isolated SQLite only; ACTIONABLE never posts an order.
"""
import copy
import time
import uuid

import pytest

from moex_intelligence.crypto.lifecycle import SignalLifecycle
from moex_intelligence.crypto.orders import OrderPreview, sell_preview
from moex_intelligence.crypto.risk import RiskError
from .test_order_preview_v082 import fixture
from .test_signal_lifecycle_v081 import signal


def opened(tmp_path):
    store, paper, gateway, quotes, rules, request = fixture(tmp_path)
    intent = gateway.prepare(request, quotes, rules, 'owner')
    assert gateway.confirm(intent['id'], 'owner', quotes, rules, True)['status'] == 'Filled'
    return store, paper, gateway, quotes, rules, request


def evaluate(store, paper, quotes, rule, quantity='1', sig=None, **kwargs):
    sig = signal(time.time(), 'EXIT') if sig is None else sig
    return SignalLifecycle(store).update(
        [sig], [], 'BTCUSDT', '15', quotes['BTCUSDT'], 'Bearish',
        paper.state(), rule, quantity, **kwargs)['active']


@pytest.mark.parametrize('case', [
    'stale_rules', 'future_rules', 'missing_rules', 'off_step', 'oversell',
    'maximum', 'minimum', 'dust', 'zero', 'nan',
])
def test_exit_rejects_the_same_invalid_sale_as_paper(tmp_path, case):
    store, paper, gateway, quotes, rules, request = opened(tmp_path)
    rule = rules['BTCUSDT']
    quantity = '1'
    if case == 'stale_rules': rule['retrieved'] = 0
    if case == 'future_rules': rule['retrieved'] = time.time() + 60
    if case == 'missing_rules': rule = None
    if case == 'off_step': quantity = '.9999'
    if case == 'oversell': quantity = '2'
    if case == 'maximum': rule['maximum'] = '.5'
    if case == 'minimum': rule['minimum'] = '101'
    if case == 'dust': quantity = '.96'
    if case == 'zero': quantity = '0'
    if case == 'nan': quantity = 'NaN'
    before, orders = paper.state(), store.orders()
    with pytest.raises((RiskError, ValueError, ArithmeticError)):
        sell_preview(before, quotes, 'BTCUSDT', quantity, rule)
    active = evaluate(store, paper, quotes, rule, quantity)
    assert active['state'] == 'REJECTED_BY_RISK', active
    assert active['reason']
    assert paper.state() == before and store.orders() == orders


def test_exit_recovers_after_rule_refresh_and_requires_manual_confirmation(tmp_path):
    store, paper, gateway, quotes, rules, request = opened(tmp_path)
    sig = signal(time.time(), 'EXIT')
    rule = rules['BTCUSDT']
    rule['retrieved'] = 0
    blocked = evaluate(store, paper, quotes, rule, sig=sig)
    assert blocked['state'] == 'REJECTED_BY_RISK'
    rule['retrieved'] = time.time()
    ready = evaluate(store, paper, quotes, rule, sig=sig)
    assert ready['state'] == 'ACTIONABLE'
    assert ready['id'] == blocked['id']
    assert ready['confirmed_at'] == blocked['confirmed_at']
    assert len(store.orders()) == 1 and paper.state()['positions']
    sell = {**request, 'id': str(uuid.uuid4()), 'side': 'SELL'}
    intent = gateway.prepare(sell, quotes, rules, 'owner')
    assert len(store.orders()) == 1
    filled = gateway.confirm(intent['id'], 'owner', quotes, rules, True)
    assert filled['status'] == 'Filled' and not paper.state()['positions']
    assert OrderPreview(store).confirm(intent['id'], 'owner', quotes, rules, True) == filled
    assert len(store.orders()) == 2


@pytest.mark.parametrize('gate', ['quote', 'candle', 'no_position'])
def test_exit_stays_confirmed_without_fresh_market_or_position(tmp_path, gate):
    store, paper, gateway, quotes, rules, request = fixture(tmp_path) if gate == 'no_position' else opened(tmp_path)
    if gate == 'quote': quotes['BTCUSDT']['fresh'] = False
    before = copy.deepcopy(paper.state())
    active = evaluate(store, paper, quotes, rules['BTCUSDT'], candle_fresh=gate != 'candle')
    assert active['state'] == 'CONFIRMED'
    assert paper.state() == before


def test_valid_partial_exit_is_actionable_without_selling(tmp_path):
    store, paper, gateway, quotes, rules, request = opened(tmp_path)
    assert evaluate(store, paper, quotes, rules['BTCUSDT'], '.5')['state'] == 'ACTIONABLE'
    assert paper.state()['positions']['BTCUSDT']['qty'] == '1'
    assert len(store.orders()) == 1


def test_exit_uses_evaluation_clock_for_rule_expiry(tmp_path):
    store, paper, gateway, quotes, rules, request = opened(tmp_path)
    now = time.time() + 86401
    quotes['BTCUSDT']['ts'] = now
    active = evaluate(store, paper, quotes, rules['BTCUSDT'],
                      sig=signal(now, 'EXIT'), now=now)
    assert active['state'] == 'REJECTED_BY_RISK'
    rules['BTCUSDT']['retrieved'] = now
    active = evaluate(store, paper, quotes, rules['BTCUSDT'],
                      sig=signal(now, 'EXIT'), now=now)
    assert active['state'] == 'ACTIONABLE'
    assert len(store.orders()) == 1
