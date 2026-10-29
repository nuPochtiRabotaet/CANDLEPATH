"""Russian display formatting only. Does not round financial calculation inputs."""
from decimal import Decimal,ROUND_HALF_UP,InvalidOperation
import math

NBSP='\u00a0'


def number(value,digits=2,*,signed=False,trim=False):
    if value is None:return '—'
    try:
        decimal=Decimal(str(value))
        if not decimal.is_finite():return '—'
        quantum=Decimal(1).scaleb(-digits);rounded=decimal.quantize(quantum,rounding=ROUND_HALF_UP)
        result=f'{abs(rounded):,.{digits}f}'.replace(',',NBSP).replace('.',',')
        if trim and ',' in result:result=result.rstrip('0').rstrip(',')
        if rounded<0:result='−'+result
        elif signed and rounded>0:result='+'+result
        return result
    except (ValueError,TypeError,InvalidOperation):return '—'


def money(value,digits=2,*,signed=False):
    text=number(value,digits,signed=signed)
    return text if text=='—' else text+' ₽'


def price(value):
    if value is None:return '—'
    try:
        raw=Decimal(str(value))
        if not raw.is_finite():return '—'
        # Suppress binary floating tails after bond clean+accrued conversion.
        rounded=raw.quantize(Decimal('0.00000001'),rounding=ROUND_HALF_UP)
        digits=max(2,min(8,-rounded.normalize().as_tuple().exponent))
        return money(value,digits)
    except (InvalidOperation,ValueError,TypeError):return '—'


def percent(value,digits=1,*,signed=False,points=False):
    text=number(value,digits,signed=signed)
    return text if text=='—' else text+(' п.п.' if points else '%')


def quantity(value):return number(value,0)
