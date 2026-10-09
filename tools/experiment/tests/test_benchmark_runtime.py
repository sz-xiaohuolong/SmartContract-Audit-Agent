"""真实批量审计的报告级预测与无风险事实软对比。"""
import unittest

from benchmark_runtime import BenchmarkRuntime, interpret_model, soft_without_risk
from pathlib import Path
from tempfile import TemporaryDirectory
from formal_recall import select_strategy


class BenchmarkRuntimeTest(unittest.TestCase):
    def test_失败和离线空假设不变成阴性预测(self):
        self.assertEqual('REPORT', interpret_model({'status': 'COMPLETED',
            'conclusion': 'VULNERABILITY_REPORTED'}, 'real'))
        self.assertEqual('NO_REPORT', interpret_model({'status': 'COMPLETED',
            'conclusion': 'NO_CONFIRMED_FINDINGS'}, 'real'))
        self.assertEqual('UNKNOWN', interpret_model({'status': 'FAILED',
            'conclusion': 'NO_CONFIRMED_FINDINGS'}, 'real'))
        self.assertEqual('UNKNOWN', interpret_model({'status': 'COMPLETED',
            'conclusion': 'NO_CONFIRMED_FINDINGS'}, 'offline'))

    def test_无唯一风险事实时保留软配对与显式缺口(self):
        before = {'caseId': 'a', 'chunkId': 'a', 'pairId': 'p', 'role': 'VULNERABLE',
                  'mechanism': 'REENTRANCY', 'text': '旧代码', 'denseScore': .9, 'conditions': []}
        after = {**before, 'caseId': 'b', 'chunkId': 'b', 'role': 'DEFENSE', 'text': '新代码', 'denseScore': .8}
        result = soft_without_risk({'candidates': [before, after]}, 'REENTRANCY')
        self.assertEqual(['a', 'b'], [row['candidate']['chunkId'] for row in result['selected']])
        self.assertIn('无唯一风险事实', result['gaps'][0])

    def test_自动知识字段基线仅按类别字段而非_d1_绑定筛选(self):
        candidate = {'caseId': 'a', 'chunkId': 'a', 'mechanism': 'REENTRANCY',
                     'role': 'VULNERABLE', 'conditions': [], 'text': '调用前未写状态'}
        other = {**candidate, 'caseId': 'b', 'chunkId': 'b',
                 'mechanism': 'ACCESS_CONTROL', 'text': '权限检查'}
        view = {'pool': {'schemaVersion': 'auto-1', 'candidates': [candidate, other]},
                'd1': {'evaluations': {}}, 'targetMechanism': 'REENTRANCY'}
        selected = select_strategy(view, 'FIELD_FILTER')['d1']['selected']
        self.assertEqual(['a'], [row['candidate']['chunkId'] for row in selected])

    def test_失败正文原样落盘且结果保留请求次数(self):
        with TemporaryDirectory() as directory:
            runtime = BenchmarkRuntime.__new__(BenchmarkRuntime)
            runtime.root = Path(directory)
            runtime.preview = lambda target: {'pool': {'candidates': []}, 'd1': {'selected': []}}
            raw = '```json\n{"bad":true}\n```'
            runtime.model_runner = lambda *args: {'status': 'FAILED', 'conclusion': 'UNRESOLVED',
                'errorCategory': 'MODEL_OUTPUT_INVALID', 'requestAttempts': 2, '_rawResponse': raw}
            result = runtime.run({'groundTruth': {'hasVulnerability': True}}, 'D1', 'real')
            self.assertEqual('UNKNOWN', result['prediction'])
            self.assertEqual(2, result['requestAttempts'])
            self.assertEqual(raw, (runtime.root / result['diagnosticPath']).read_text())
            self.assertNotIn('_rawResponse', result['model'])


if __name__ == '__main__':
    unittest.main()
