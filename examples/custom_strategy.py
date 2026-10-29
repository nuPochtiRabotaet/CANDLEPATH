"""Trusted local Python only. Called with a COPY of the historical prefix."""
from moex_intelligence.backtest import backtest
from time_machine_core.moex_data import demo_daily


def signal(history):
    if len(history) < 30:
        return 0
    return int(history['CLOSE'].iloc[-1] > history['CLOSE'].tail(30).mean())


if __name__ == '__main__':
    data, _ = demo_daily()
    result = backtest(data, custom=signal)
    print(result.stats)
