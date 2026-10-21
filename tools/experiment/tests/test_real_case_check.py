"""真实案例诊断不把编译或局部路径通过提升为研究裁决。"""
import copy
import unittest
from unittest.mock import patch

import test_compiler_facts as fixtures


class RealCaseCheckTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompilerFactsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.candidate = {'contract': 'C', 'function': 'f()', 'riskLine': 2,
                          'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL'}

    def test_重新编译只给局部诊断且不改候选(self):
        from verirag.evaluation.real_case_check import check_case
        original = copy.deepcopy(self.candidate)
        report = check_case(self.fixture.root, self.fixture.manifest, self.candidate)
        self.assertEqual('RECOMPILED_MATCH', report['compilation']['status'])
        self.assertEqual('PARTIAL', report['status'])
        self.assertEqual('UNKNOWN', report['verdict'])
        self.assertFalse(report['researchEligible'])
        self.assertEqual(0, report['newModelRequests'])
        self.assertEqual(original, self.candidate)
        self.assertEqual(1, len(report['sourceClosure']))
        self.assertTrue(report['candidateUnchanged'])

    def test_损坏原件保留编译失败和未知(self):
        from verirag.evaluation.real_case_check import check_case
        (self.fixture.root / 'contracts/C.sol').write_text('损坏')
        report = check_case(self.fixture.root, self.fixture.manifest, self.candidate)
        self.assertEqual('FAILED', report['status'])
        self.assertEqual('UNKNOWN', report['verdict'])
        self.assertEqual('COMPILATION_BINDING_FAILED', report['errorCategory'])
        self.assertIn('摘要', report['error'])
        self.assertNotIn('candidateProof', report)

    def test_不支持机制不能当作成功空证明(self):
        from verirag.evaluation.real_case_check import check_case
        candidate = {**self.candidate, 'vulnerabilityType': 'OTHER'}
        report = check_case(self.fixture.root, self.fixture.manifest, candidate)
        self.assertEqual('FAILED', report['status'])
        self.assertEqual('UNKNOWN', report['verdict'])
        self.assertEqual('UNSUPPORTED_MECHANISM', report['errorCategory'])

    def test_证明器异常保留编译证据但不产生裁决(self):
        from verirag.evaluation.real_case_check import check_case
        with patch('verirag.evaluation.real_case_check.prove_candidate', side_effect=ValueError('不支持的控制流')):
            report = check_case(self.fixture.root, self.fixture.manifest, self.candidate)
        self.assertEqual('RECOMPILED_MATCH', report['compilation']['status'])
        self.assertEqual('CANDIDATE_PROOF_FAILED', report['errorCategory'])
        self.assertEqual('UNKNOWN', report['verdict'])
        self.assertEqual('FAILED', report['status'])


if __name__ == '__main__':
    unittest.main()
