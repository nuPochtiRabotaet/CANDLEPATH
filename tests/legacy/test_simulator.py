import unittest
import numpy as np
import pandas as pd
from time_machine_core.simulator import simulate
from time_machine_core.moex_data import demo_daily

class TestSimulator(unittest.TestCase):
    def setUp(self):
        self.series = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(2).normal(0,.01,250))))

    def test_probabilities_sum_to_one(self):
        r = simulate(self.series, runs=2000, horizon=20)
        s = r.stats
        self.assertAlmostEqual(s['p_target'] + s['p_stop'] + s['p_open'], 1.0)
        self.assertEqual(r.paths.shape, (2000, 21))
        self.assertEqual(len(r.exits), 2000)

    def test_reproducibility(self):
        a = simulate(self.series, runs=200, seed=33)
        b = simulate(self.series, runs=200, seed=33)
        np.testing.assert_array_equal(a.net_returns, b.net_returns)

    def test_costs_reduce_returns(self):
        free = simulate(self.series, runs=200, commission_pct=0, slippage_pct=0, seed=3)
        costly = simulate(self.series, runs=200, commission_pct=.5, slippage_pct=.5, seed=3)
        self.assertTrue(np.all(costly.net_returns < free.net_returns))

    def test_demo_is_labeled_and_usable(self):
        df, meta = demo_daily()
        self.assertIn('Искусственные', meta['name'])
        self.assertEqual(len(df), 420)
        self.assertTrue(df['CLOSE'].gt(0).all())

    def test_validation(self):
        with self.assertRaises(ValueError):
            simulate(self.series.iloc[:40])
        with self.assertRaises(ValueError):
            simulate(self.series, stop_pct=101)

if __name__ == '__main__':
    unittest.main()
