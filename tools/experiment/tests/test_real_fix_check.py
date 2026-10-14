"""维护者修复正反验收消费各自源码和最终 D2，不能用局部保护义务冒充反驳。"""
import unittest
from unittest.mock import patch
import test_compiler_facts as fixtures


class RealFixCheckTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompilerFactsTest(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.candidate = {'contract': 'C', 'function': 'f()', 'riskLine': 1,
                          'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL'}

    def test_错机制的跨版本候选不得比较(self):
        from real_fix_check import validate_fix_pair
        after = {**self.candidate, 'vulnerabilityType': 'REENTRANCY', 'riskOperation': 'CALL'}
        with self.assertRaises(ValueError):
            validate_fix_pair(self.fixture.root, self.fixture.manifest, self.candidate,
                              self.fixture.manifest, after)

    def test_同源码或缺工具即使局部保护已证也不算真实修复验收(self):
        from real_fix_check import validate_fix_pair
        with patch('bound_slither.analyze_bound', return_value={'engine': 'SLITHER',
                'status': 'PROCESS_ERROR', 'issues': []}):
            result = validate_fix_pair(self.fixture.root, self.fixture.manifest, self.candidate,
                                      self.fixture.manifest, self.candidate)
        self.assertFalse(result['acceptancePassed'])
        self.assertEqual('UNKNOWN', result['after']['verdict'])
        self.assertEqual('PROVED', result['after']['localProofStatus'])
        self.assertTrue(result['candidatesUnchanged'])
        self.assertEqual(0, result['newModelRequests'])
