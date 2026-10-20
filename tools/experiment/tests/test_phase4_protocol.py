"""四条件探索的开关隔离、消费公平性与完整分母。"""
import copy
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from benchmark_batch import make_plan, replay_batch, run_batch


class Phase4ProtocolTest(unittest.TestCase):
    def test_本次四条件仅允许已授权coding入口和既定模型(self):
        from r3_cli import _validate_provider
        coding = {'endpoint': 'https://ark.cn-beijing.volces.com/api/coding/v3', 'model': 'deepseek-v4-flash'}
        plan = {**coding, 'endpoint': 'https://ark.cn-beijing.volces.com/api/plan/v3'}
        _validate_provider(coding, True)
        _validate_provider(plan, False)
        for provider, phase4 in ((plan, True), (coding, False), ({**coding, 'model': 'other'}, True)):
            with self.subTest(provider=provider, phase4=phase4), self.assertRaises(ValueError):
                _validate_provider(provider, phase4)

    def test_实际运行按条件消费且无检索命中率不适用(self):
        from benchmark_runtime import BenchmarkRuntime
        from r3_protocol import P4_CONDITIONS
        runtime = BenchmarkRuntime.__new__(BenchmarkRuntime)
        runtime.root = Path('/不存在的测试根目录')
        runtime.preview = lambda target: {'pool': {'candidates': []},
            'd1': {'selected': [], 'context': '同一知识'}, 'facts': {}}
        seen = []
        def model(root, target, view, mode):
            seen.append((target['factGuidanceEnabled'], view['strategy'], view['d1']['context']))
            return {'status': 'COMPLETED', 'hypotheses': [], 'conclusion': 'NO_CONFIRMED_FINDINGS'}
        runtime.model_runner = model
        runtime.tool_runner = lambda *args: [{'engine': 'SLITHER', 'status': 'SKIPPED', 'issues': []}]
        target = {'factGuidanceEnabled': True, 'groundTruth': {'hasVulnerability': True}, 'mechanism': 'ACCESS_CONTROL'}
        for strategy in P4_CONDITIONS:
            result = runtime.run(target, strategy, 'real')
            if strategy in ('P4_BASELINE', 'P4_FACTS'):
                self.assertIsNone(result['categoryHit'])
        self.assertEqual([(False, 'P4_BASELINE', ''), (True, 'P4_FACTS', ''),
                          (False, 'P4_D1', '同一知识'), (True, 'P4_FACTS_D1', '同一知识')], seen)
        self.assertTrue(target['factGuidanceEnabled'])

    def test_共同预检阻断不付费且不删除原计划目标(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from r3_cli import preflight
        from r3_protocol import P4_CONDITIONS, freeze_phase4_plan
        runtime = SimpleNamespace(preview=lambda target: {'pool': {}, 'd1': {'selected': [], 'context': ''}})
        target = {'sampleId': 'a'}
        def model(root, current, view, mode):
            self.assertEqual('preflight', mode)
            if current['factGuidanceEnabled']:
                raise ValueError('事实超出预算')
            return {'status': 'COMPLETED', 'requestConsumptionReceipt': {'requestAttempts': 0, 'requestSha256': 'hash'}}
        with patch('r3_cli.model_runner', side_effect=model), patch('r3_cli.prepare_model_context'):
            receipts = preflight(Path('.'), runtime, [target], 32768, P4_CONDITIONS)
        self.assertEqual('FAILED', receipts['a']['P4_FACTS']['status'])
        self.assertEqual(4, len(receipts['a']))
        self.assertNotIn('factGuidanceEnabled', target)
        base = make_plan(['a'], P4_CONDITIONS, 'real', [{'sampleId': 'a', 'runnable': False,
            'sourceHash': 'a' * 64, 'groundTruth': {'hasVulnerability': True}, 'inputReason': '预检阻断'}],
            'b' * 64, include_blocked=True)
        frozen = freeze_phase4_plan(base, {'artifactHash': 'c' * 64}, receipts, 32768)
        self.assertEqual(['a'], frozen['sampleIds'])
        self.assertEqual(0, frozen['requestBounds']['maxRequests'])

    def test_预检子进程超时应保留四条件而非退出整批(self):
        from subprocess import TimeoutExpired
        from unittest.mock import patch
        from types import SimpleNamespace
        from r3_cli import preflight
        from r3_protocol import P4_CONDITIONS
        runtime = SimpleNamespace(preview=lambda target: {'pool': {}, 'd1': {'selected': [], 'context': ''}})
        with patch('r3_cli.model_runner', side_effect=TimeoutExpired('java', 390)), patch('r3_cli.prepare_model_context'):
            receipts = preflight(Path('.'), runtime, [{'sampleId': 'a'}], 32768, P4_CONDITIONS)
        self.assertEqual(set(P4_CONDITIONS), set(receipts['a']))
        self.assertTrue(all(row['status'] == 'FAILED' and row['requestAttempts'] == 0 for row in receipts['a'].values()))

    def receipts(self):
        from r3_protocol import P4_CONDITIONS
        return {'a': {s: {'requestSha256': str(i) * 64, 'contextSha256': 'd1' if i > 1 else hashlib.sha256(b'').hexdigest(),
            'sourceHash': 'a' * 64, 'modelSourceHash': 'a' * 64,
            'evidenceIds': ['p'] if i > 1 else [], 'poolHash': 'pool',
            **({'factGuidance': {'textSha256': 'facts'}} if i % 2 else {})}
            for i, s in enumerate(P4_CONDITIONS)}}

    def plan(self, preflight=None):
        from r3_protocol import P4_CONDITIONS, freeze_phase4_plan
        base = make_plan(['a'], P4_CONDITIONS, 'real', [{'sampleId': 'a', 'runnable': True,
            'sourceHash': 'a' * 64, 'groundTruth': {'hasVulnerability': True}}], 'b' * 64)
        return freeze_phase4_plan(base, {'artifactHash': 'c' * 64}, preflight or self.receipts(), 32768)

    def test_四条件只修改副本且保留同一D1文本(self):
        from r3_protocol import condition_target, condition_view, P4_CONDITIONS
        original = {'factGuidanceEnabled': True, 'sampleId': 'a'}
        base = {'pool': {'candidates': []}, 'd1': {'selected': [], 'context': '同一历史知识'}}
        for strategy, expected in zip(P4_CONDITIONS, [False, True, False, True]):
            target, underlying = condition_target(original, strategy)
            self.assertIsNot(target, original)
            self.assertEqual(expected, target['factGuidanceEnabled'])
            view = condition_view(base, strategy)
            self.assertEqual(strategy, view['strategy'])
            self.assertEqual(underlying, view['baseStrategy'])
            self.assertEqual('同一历史知识' if underlying == 'D1' else '', view['d1']['context'])
        self.assertTrue(original['factGuidanceEnabled'])
        self.assertEqual('同一历史知识', base['d1']['context'])

    def test_冻结四条件预算且拒绝不同事实或案例(self):
        from r3_protocol import freeze_phase4_plan
        plan = self.plan()
        self.assertEqual('phase4-v1', plan['pipelineVersion'])
        self.assertEqual(4, plan['requestBounds']['maxRequests'])
        self.assertEqual(131072, plan['requestBounds']['maxPromptBytesTotal'])
        self.assertIsNone(plan['requestBounds']['maxInputTokens'])
        for field in ('factGuidance', 'evidenceIds', 'poolHash', 'contextSha256', 'sourceHash', 'modelSourceHash'):
            receipts = self.receipts()
            receipts['a']['P4_FACTS_D1'][field] = {'textSha256': 'other'} if field == 'factGuidance' else 'other'
            with self.subTest(field=field), self.assertRaises(ValueError):
                freeze_phase4_plan(plan, {'artifactHash': 'c' * 64}, receipts, 32768)

    def test_报告按实际消费回执核对并保留缺失单元(self):
        from r3_protocol import comparison_audit
        plan = self.plan()
        receipts = self.receipts()['a']
        rows = [{'sampleId': 'a', 'strategy': s, 'poolHash': 'pool',
                 'model': {'requestConsumptionReceipt': receipt}}
                for s, receipt in receipts.items()]
        self.assertEqual([], comparison_audit(rows, plan))
        self.assertTrue(comparison_audit(rows[:-1], plan))
        changed = copy.deepcopy(rows)
        changed[3]['model']['requestConsumptionReceipt']['requestSha256'] = 'wrong'
        self.assertTrue(comparison_audit(changed, plan))

    def test_四条件复用批量平台且失败留在分母(self):
        plan = self.plan()
        def runner(sample, strategy, mode):
            failed = strategy == 'P4_FACTS_D1'
            return {'status': 'FAILED' if failed else 'COMPLETED',
                'prediction': 'UNKNOWN' if failed else 'REPORT', 'poolHash': 'pool',
                'inputTokens': None, 'outputTokens': None,
                'model': {} if failed else {'requestConsumptionReceipt': self.receipts()['a'][strategy]}}
        with TemporaryDirectory() as directory:
            key = run_batch(Path(directory), plan, runner)
            report = replay_batch(Path(directory), key)
        self.assertEqual(4, report['denominators']['planned'])
        self.assertEqual(1, report['denominators']['failed'])
        self.assertEqual([], report['pairedSamples'])
        self.assertTrue(report['comparisonAudit'])
        self.assertIsNone(report['pairEvidenceCoverage']['P4_D1']['independentAccuracy'])
