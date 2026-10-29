import unittest
from unittest.mock import patch

from time_machine_mcp import register_time_machine_tools, run_analysis
from time_machine_core.moex_data import demo_daily


class DummyMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def save(func):
            self.tools[func.__name__] = func
            return func
        return save


class TimeMachineToolTests(unittest.TestCase):
    def test_registers_expected_tools(self):
        server = DummyMCP()
        register_time_machine_tools(server)
        self.assertEqual(set(server.tools), {'time_machine_simulate', 'time_machine_demo'})

    def test_demo_never_networks(self):
        server = DummyMCP()
        register_time_machine_tools(server)
        with patch('time_machine_mcp.load_moex_daily', side_effect=AssertionError('network called')):
            r = server.tools['time_machine_demo'](scenarios=500)
        self.assertTrue(r['instrument']['demo_data'])
        self.assertIn('SYNTHETIC', r['method'].upper() + ' SYNTHETIC')
        self.assertEqual(r['parameters']['simulated_paths'], 500)
        self.assertAlmostEqual(sum(r['scenario_frequencies'][k] for k in ('target_first','stop_first','neither_reached')),1,places=5)

    def test_can_use_reader_history_loader(self):
        server = DummyMCP()
        frame, meta = demo_daily(seed=37)
        meta = dict(meta, symbol='SBER', source='mock Reader')
        received = []
        def existing_reader_loader(symbol, first, last):
            received.append((symbol, first, last))
            return frame, meta
        register_time_machine_tools(server, history_loader=existing_reader_loader)
        r = server.tools['time_machine_simulate'](symbol='sber',scenarios=250)
        self.assertEqual(received[0][0], 'SBER')
        self.assertEqual(r['instrument']['data_source'], 'mock Reader')
        self.assertEqual(r['instrument']['symbol'], 'SBER')

    def test_validation_before_loading(self):
        calls = []
        def reader_loader(*args):
            calls.append(args)
            raise AssertionError('No calls should be made')
        with self.assertRaises(ValueError):
            run_analysis(scenarios=0, history_loader=reader_loader)
        self.assertEqual(calls, [])

    def test_tool_json_serializable(self):
        import json
        val = run_analysis(demo=True, scenarios=200)
        self.assertTrue(json.dumps(val, ensure_ascii=False))
        self.assertNotIn('paths', val)
        self.assertIn('scenario_frequencies', val)

    def test_demo_determinism(self):
        a = run_analysis(demo=True, seed=11, scenarios=200)
        b = run_analysis(demo=True, seed=11, scenarios=200)
        self.assertEqual(a,b)


if __name__ == '__main__':
    unittest.main()
