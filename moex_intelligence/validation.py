import math
from numbers import Real, Integral


def finite(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f'{name}: finite number required')
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f'{name}: outside allowed range [{minimum}, {maximum}]')
    return float(value)


def integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, Integral) or not minimum <= value <= maximum:
        raise ValueError(f'{name}: integer in [{minimum}, {maximum}] required')
    return int(value)
