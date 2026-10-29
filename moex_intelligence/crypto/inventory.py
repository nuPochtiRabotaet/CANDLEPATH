"""Decimal holdings decomposition; residues remain owned and retain their basis."""
import hashlib
import json
from decimal import ROUND_FLOOR
from .costs import D, basis, estimate


def position_revision(position):
    payload = json.dumps(position, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def inventory(quantity, quote, rules, model, cost_basis='0'):
    held, step = D(quantity), D(rules['step'])
    minimum, maximum = D(rules['minimum']), D(rules.get('maximum') or max(held, D(1)))
    if not all(x.is_finite() for x in (held, step, minimum, maximum)) or held < 0 or step <= 0 or minimum < 0 or maximum <= 0:
        raise ValueError('Invalid inventory/rules')
    aligned = (held / step).to_integral_value(rounding=ROUND_FLOOR) * step
    price = estimate('SELL', 1, quote, model).price
    available = min(aligned, (maximum / step).to_integral_value(rounding=ROUND_FLOOR) * step)
    if available * price < minimum:
        available = D(0)
    # Maximum order size does not turn an otherwise tradeable balance into dust.
    residue = held - aligned if aligned * price >= minimum else held
    b = D(cost_basis)
    allocated = b * available / held if held else D(0)
    residue_basis = b * residue / held if held else D(0)
    values = {
        'net_holdings': held, 'aligned_quantity': aligned,
        'sellable_quantity': available, 'non_sellable_residue': residue,
        'remaining_after_sale': held - available, 'residue_value': residue * D(quote['bid']),
        'residue_basis': residue_basis, 'residue_unrealized': residue * D(quote['bid']) - residue_basis,
        'sellable_basis': allocated, 'remaining_basis': b - allocated,
        'coverage_fraction': available / held if held else D(0),
    }
    return {**{k: str(v) for k, v in values.items()},
            'fully_sellable': available == held and held > 0,
            'protection': 'Full quantity' if available == held and held > 0 else 'Partial quantity' if available else 'Not executable'}


def validate_sale(position, quantity, quote, rules, model, dispose_sellable=False):
    qty, held, step = D(quantity), D(position['qty']), D(rules['step'])
    if not qty.is_finite() or not 0 < qty <= held:
        raise ValueError('Количество превышает позицию / некорректно')
    before = inventory(held, quote, rules, model, basis(position))
    if qty > D(before['sellable_quantity']):
        raise ValueError('Количество превышает доступное по текущим правилам')
    if qty / step != (qty / step).to_integral_value():
        raise ValueError('Количество не кратно шагу')
    if estimate('SELL', qty, quote, model).notional < D(rules['minimum']):
        raise ValueError('Сумма ниже минимума')
    if dispose_sellable and qty != D(before['sellable_quantity']):
        raise ValueError('Продаваемое количество изменилось: новый preview')
    remaining = held - qty
    if remaining:
        after = inventory(remaining, quote, rules, model)
        if D(after['non_sellable_residue']) > D(before['non_sellable_residue']) and not dispose_sellable:
            raise ValueError('DUST: частичная продажа создаёт новый неторгуемый остаток. Подтвердите продажу всего доступного отдельно.')
    return before


def liquidation_at(position, level, rules, model):
    """Conservative scenario: only legal quantity can yield proceeds; residue recovery = 0."""
    allocation = inventory(position['qty'], {'bid': str(level)}, rules, model, basis(position))
    qty = D(allocation['sellable_quantity'])
    proceeds = estimate('SELL', qty, {'bid': str(level)}, model).cash_delta if qty else D(0)
    return allocation, proceeds
