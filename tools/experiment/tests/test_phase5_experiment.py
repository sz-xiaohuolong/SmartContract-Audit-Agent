"""真实探索的本机完整编码、操作聚合和付费停止边界。"""
import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import phase5_cli
from storage import fingerprint
from test_phase5_cli import dataset, run_fixture


class Phase5ExperimentTest(unittest.TestCase):
    def module(self):
        import phase5_experiment
        return phase5_experiment

    def transport(self, malformed=False):
        self.calls = []
        self.digest = 'a' * 64
        def call(path, payload):
            if path == '/api/tags':
                return {'models': [{'name': 'nomic-embed-text:latest', 'digest': self.digest,
                    'details': {'embedding_length': 768, 'context_length': 2048}}]}
            self.calls.append((path, payload))
            if '超长' in payload['input']:
                raise ValueError('完整输入超限')
            result = {'model': 'nomic-embed-text:latest', 'embeddings': [[1.0] + [0.0] * 767]}
            if not malformed: result['prompt_eval_count'] = 5
            return result
        return call

    def test_完整编码使用实际token并拒绝超限且不裁剪重试(self):
        encoder, config = self.module().strict_nomic_encoder('a' * 64, self.transport())
        result = encoder(['search_query: 原问题', 'search_document: 完整材料'])
        self.assertEqual([5, 5], result['tokenCounts'])
        self.assertEqual([False, False], result['truncated'])
        self.assertEqual(2048, config['maxInputTokens'])
        self.assertTrue(all(p['truncate'] is False for _, p in self.calls))
        with self.assertRaises(ValueError): encoder(['search_document: 超长'])
        self.assertEqual(3, len(self.calls))
        self.assertEqual('search_document: 超长', self.calls[-1][1]['input'])

    def test_缓存命中仍检查模型身份且缺token不可补造(self):
        encoder, _ = self.module().strict_nomic_encoder('a' * 64, self.transport())
        encoder(['相同材料']); self.digest = 'b' * 64
        with self.assertRaises(self.module().EncoderIdentityChanged): encoder(['相同材料'])
        encoder, _ = self.module().strict_nomic_encoder('a' * 64, self.transport(malformed=True))
        with self.assertRaises(ValueError): encoder(['完整材料'])

    def test_目标聚合包含全部有效操作而非仅第一项(self):
        data = dataset()
        second = copy.deepcopy(data['targets'][0]['queries']['queries'][0])
        second['operationKey'] = '操作二'; second['original'] = '另一个问题'
        data['targets'][0]['queries']['queries'].append(second)
        data = phase5_cli.seal_dataset(data)
        from test_phase5_retrieval import FixedEncoder, scoring_config
        class PerOperation:
            def __call__(self, texts):
                vectors = ([[0, 1], [1, 0], [1, 0], [0, 1]] if '另一个问题' in texts else
                           [[1, 0], [0, 1], [1, 0], [0, 1]])
                return FixedEncoder(vectors)(texts)
        run = phase5_cli.compare_dataset(data, PerOperation(), scoring_config())
        result = self.module().aggregate_target(run, data['targets'][0])
        self.assertEqual('SCORED', result['status'])
        self.assertEqual(2, len(result['operationKeys']))
        self.assertEqual([0.5, 0.5], [s['originalScore'] for s in result['scores']])
        self.assertEqual([0.0, 0.0], [s['margin'] for s in result['scores']])

    def test_缺对照或部分评分失败必须阻断整个目标(self):
        run = run_fixture(); target = run['dataset']['targets'][0]
        run['comparisons'][0]['scores']['status'] = 'FAILED'
        self.assertEqual('BLOCKED', self.module().aggregate_target(run, target)['status'])
        target['queries']['queries'] = []
        self.assertEqual('BLOCKED', self.module().aggregate_target(run, target)['status'])

    def test_请求失败后停止且预检漂移不产生付费(self):
        module = self.module(); paid = []
        receipt = {'requestSha256': '固定请求', 'sourceHash': '源码', 'contextSha256': '材料'}
        def model(root, target, view, mode):
            if mode == 'real': paid.append(target['sampleId'])
            return {'status': 'FAILED' if mode == 'real' else 'COMPLETED',
                    'requestConsumptionReceipt': receipt, 'requestAttempts': int(mode == 'real')}
        guard = module.PaidGuard({'目标': {'P5_MARGIN': receipt}}, 1, lambda: True, model)
        target = {'sampleId': '目标', '_phase5Condition': 'P5_MARGIN'}
        self.assertEqual('FAILED', guard(None, target, {}, 'real')['status'])
        with self.assertRaises(ValueError): guard(None, target, {}, 'real')
        self.assertEqual(['目标'], paid)
        guard = module.PaidGuard({'目标': {'P5_MARGIN': {**receipt, 'requestSha256': '被替换'}}},
                                 1, lambda: True, model)
        with self.assertRaises(ValueError): guard(None, target, {}, 'real')
        self.assertEqual(['目标'], paid)

    def test_来源身份改变时禁止新请求(self):
        def forbidden(*args): self.fail('身份变化不能调用模型')
        guard = self.module().PaidGuard({}, 24, lambda: False, forbidden)
        with self.assertRaises(ValueError): guard(None, {}, {}, 'real')

    def test_预检期间身份改变不能进入付费(self):
        identity = iter([True, False]); paid = []
        receipt = {'requestSha256': '原请求'}
        def model(root, target, view, mode):
            if mode == 'real': paid.append(mode)
            return {'status': 'COMPLETED', 'requestConsumptionReceipt': receipt}
        guard = self.module().PaidGuard({'目标': {'P5_MARGIN': receipt}}, 1, lambda: next(identity), model)
        with self.assertRaises(ValueError):
            guard(None, {'sampleId': '目标', '_phase5Condition': 'P5_MARGIN'}, {}, 'real')
        self.assertEqual([], paid)

    def test_实际回执不符不能进入有效分类且用量保留(self):
        receipt = {'requestSha256': '原请求'}
        def model(root, target, view, mode):
            return {'status': 'COMPLETED', 'conclusion': 'NO_CONFIRMED_FINDINGS',
                'inputTokens': 10, 'outputTokens': None,
                'requestConsumptionReceipt': receipt if mode == 'preflight' else {'requestSha256': '其他请求'}}
        guard = self.module().PaidGuard({'目标': {'P5_MARGIN': receipt}}, 1, lambda: True, model)
        result = guard(None, {'sampleId': '目标', '_phase5Condition': 'P5_MARGIN'}, {}, 'real')
        from benchmark_runtime import interpret_model
        self.assertEqual('UNKNOWN', interpret_model(result, 'real'))
        self.assertEqual(10, result['inputTokens']); self.assertIsNone(result['outputTokens'])
        self.assertTrue(guard.stopped)

    def test_更换批次编号不能重复消费单次授权(self):
        from benchmark_batch import make_plan
        target = {'sampleId': '目标', 'runnable': True, 'sourceHash': 'a' * 64,
                  'groundTruth': {'hasVulnerability': True}}
        plan = make_plan(['目标'], ['P5_MARGIN'], 'real', [target], 'b' * 64)
        with TemporaryDirectory() as directory:
            store = Path(directory)
            self.module().reserve_batch(store, plan, '1' * 32)
            with self.assertRaises(ValueError): self.module().reserve_batch(store, plan, '2' * 32)
            self.assertFalse((store / ('2' * 32)).exists())

    def test_编码身份漂移是整轮致命错误而非单操作失败(self):
        module = self.module()
        encoder, config = module.strict_nomic_encoder('a' * 64, self.transport())
        self.digest = 'b' * 64
        with self.assertRaises(module.EncoderIdentityChanged):
            phase5_cli.compare_dataset(dataset(), encoder, config)

    def test_候选支持未知失败与缺失分别保留(self):
        rows = [{'strategy': 'P5_MARGIN', 'model': {'hypotheses': [{}, {}, {}, {}]},
            'd2': {'assessments': [{'hypothesisIndex': 0, 'verdict': 'SUPPORTED', 'status': 'COMPLETED'},
                {'hypothesisIndex': 1, 'verdict': 'UNKNOWN', 'status': 'COMPLETED'},
                {'hypothesisIndex': 2, 'verdict': 'UNKNOWN', 'status': 'FAILED'}]}}]
        report = self.module().candidate_summary(rows)['P5_MARGIN']
        self.assertEqual(4, report['denominator'])
        self.assertEqual({'SUPPORTED': 1, 'REFUTED': 0, 'UNKNOWN': 1, 'FAILED': 2}, report['counts'])
        self.assertEqual(1, report['assessmentMissing'])
        self.assertIsNone(report['falseSupports'])


if __name__ == '__main__':
    unittest.main()
