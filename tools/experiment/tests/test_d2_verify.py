"""D2 初版只核查已有证据，不能根据空告警推断安全。"""
import unittest
from d2_verify import evaluate


class D2VerifyTest(unittest.TestCase):
    def test_missing_or_failed_tool_is_unknown(self):
        result = evaluate({'riskLine': 10, 'function': 'withdraw', 'evidenceIds': []},
                          {'facts': []}, [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}])
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual(6, len(result['obligations']))
        failed = evaluate({'riskLine': 10, 'function': 'withdraw', 'evidenceIds': []},
                          {'facts': []}, [{'engine': 'SLITHER', 'status': 'TIMEOUT', 'issues': []}])
        self.assertEqual('UNKNOWN', failed['verdict'])

    def test_explicit_counterexample_can_refute(self):
        result = evaluate({'riskLine': 10, 'function': 'withdraw', 'evidenceIds': []},
                          {'facts': []}, [{'engine': 'SLITHER', 'status': 'OK',
                                           'issues': [{'check': 'reentrancy-eth', 'elements': [{'source_mapping': {'lines': [10]}}]}]}])
        self.assertEqual('REFUTED', result['verdict'])
        self.assertTrue(result['references'])


if __name__ == '__main__':
    unittest.main()
