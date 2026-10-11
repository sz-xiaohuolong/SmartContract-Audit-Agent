"""离线保存候选入口不可篡改源码身份，缺工具不生成安全裁决。"""
import unittest
from unittest.mock import patch
from pathlib import Path

import test_compiler_facts as fixtures
from audit_runner import analyze_saved


class SavedAuditRunnerTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompilerFactsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.target = {'fullSource': self.fixture.source, 'compilerManifest': self.fixture.manifest}
        self.hypotheses = [{'contract': 'C', 'function': 'f', 'riskLine': 1,
                            'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL'}]

    def test_CLI最小目标仍核验候选但缺双收据未知(self):
        with patch('bound_slither.analyze_bound', return_value={'engine': 'SLITHER',
                'status': 'PROCESS_ERROR', 'issues': []}), \
                patch('audit_run.model_runner', side_effect=AssertionError('保存候选不得调用模型')):
            result = analyze_saved(self.fixture.root, self.target, self.hypotheses)
        self.assertEqual('FAILED', result['status'])
        assessment = result['d2']['assessments'][0]
        self.assertEqual('solc-standard-json', assessment['provider'])
        self.assertEqual('UNKNOWN', assessment['verdict'])
        self.assertEqual('PROVED', assessment['candidateProof']['status'])
        self.assertEqual(0, result['newModelRequests'])

    def test_调用方错误源码身份不能被覆盖(self):
        with self.assertRaisesRegex(ValueError, '源码摘要'):
            analyze_saved(self.fixture.root, {**self.target, 'sourceHash': '0' * 64}, self.hypotheses)

    def test_编译失败逐候选保留六义务与失败状态(self):
        with patch('audit_runner.prepare_compilation', side_effect=ValueError('证据缺失')):
            result = analyze_saved(self.fixture.root, self.target, self.hypotheses)
        self.assertEqual('FAILED', result['status'])
        self.assertEqual('FAILED', result['d2']['status'])
        self.assertEqual(6, len(result['d2']['assessments'][0]['obligations']))
        self.assertEqual('UNKNOWN', result['d2']['verdict'])


if __name__ == '__main__':
    unittest.main()
