"""批量审计只从真实逐项结论计算指标，失败保持未知。"""
import tempfile
import unittest
from pathlib import Path

from benchmark_batch import make_plan, run_batch, replay_batch, export_csv


class BenchmarkBatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name)
        self.targets = [{'sampleId': key, 'sourceHash': key * 64, 'runnable': True,
                         'groundTruth': {'hasVulnerability': key in ('a', 'b'),
                                         'vulnerabilityType': 'REENTRANCY' if key in ('a', 'b') else None,
                                         'labelSource': 'fixture'}} for key in 'abcd']

    def test_真实完成项计算混淆矩阵且失败不当作安全(self):
        plan = make_plan(list('abcd'), ['DENSE'], 'real', self.targets, 'f' * 64)
        def runner(sample, strategy, mode):
            if sample == 'd':
                raise TimeoutError('超时')
            prediction = {'a': 'REPORT', 'b': 'NO_REPORT', 'c': 'REPORT'}[sample]
            return {'status': 'COMPLETED', 'prediction': prediction, 'categoryHit': sample != 'b',
                    'selectedEvidence': 2, 'inputTokens': 10, 'outputTokens': 5,
                    'durationMs': 100, 'model': {'status': 'COMPLETED'}}
        batch_id = run_batch(self.store, plan, runner, 'e' * 32)
        report = replay_batch(self.store, batch_id)
        row = report['metrics']['DENSE']
        self.assertEqual((1, 1, 1, 0), (row['tp'], row['fp'], row['fn'], row['tn']))
        self.assertEqual(0.5, row['precision'])
        self.assertEqual(0.5, row['recall'])
        self.assertEqual(0.5, row['f1'])
        self.assertEqual(1, row['unknown'])
        self.assertEqual(10.0, row['avgInputTokens'])
        self.assertEqual(0.5, row['retrievalHitAtK'])
        self.assertIn('NO_REPORT', export_csv(report))
        self.assertIn('poolHash', export_csv(report).splitlines()[0])

    def test_断点续跑不重复已发出的模型请求(self):
        plan = make_plan(['a'], ['D1'], 'real', self.targets, 'f' * 64)
        calls = []
        def runner(sample, strategy, mode):
            calls.append(sample)
            return {'status': 'COMPLETED', 'prediction': 'REPORT', 'categoryHit': True,
                    'selectedEvidence': 2, 'inputTokens': None, 'outputTokens': None,
                    'durationMs': 100, 'model': {}}
        run_batch(self.store, plan, runner, 'e' * 32)
        run_batch(self.store, plan, runner, 'e' * 32)
        self.assertEqual(['a'], calls)
        self.assertIsNone(replay_batch(self.store, 'e' * 32)['metrics']['D1']['avgInputTokens'])

    def test_零精确率和零召回率对应零_f1(self):
        plan = make_plan(['a', 'c'], ['D1'], 'real', self.targets, 'f' * 64)
        run_batch(self.store, plan, lambda sample, strategy, mode: {
            'status': 'COMPLETED', 'prediction': 'NO_REPORT' if sample == 'a' else 'REPORT',
            'categoryHit': False, 'selectedEvidence': 0, 'inputTokens': None,
            'outputTokens': None, 'durationMs': 1, 'model': {}}, 'a' * 32)
        self.assertEqual(0.0, replay_batch(self.store, 'a' * 32)['metrics']['D1']['f1'])

    def test_共同有效目标使用相同分母(self):
        plan = make_plan(['a', 'b'], ['DENSE', 'D1'], 'real', self.targets, 'f' * 64)
        def runner(sample, strategy, mode):
            failed = sample == 'b' and strategy == 'D1'
            return {'status': 'FAILED' if failed else 'COMPLETED',
                    'prediction': 'UNKNOWN' if failed else 'REPORT', 'categoryHit': True,
                    'selectedEvidence': 1, 'inputTokens': None, 'outputTokens': None,
                    'durationMs': 1, 'model': {}}
        run_batch(self.store, plan, runner, 'b' * 32)
        report = replay_batch(self.store, 'b' * 32)
        self.assertEqual(['a'], report['pairedSamples'])
        self.assertEqual(1, report['pairedMetrics']['DENSE']['samples'])
        self.assertEqual(1, report['pairedMetrics']['D1']['tp'])


if __name__ == '__main__':
    unittest.main()
