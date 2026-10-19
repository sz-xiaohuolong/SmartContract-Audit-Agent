"""冻结分母、预算和身份比较的回归。"""
import unittest


class R3ProtocolTest(unittest.TestCase):
    def test_双向证据配对保留未知失败及未运行分母(self):
        from r3_protocol import paired_evidence_coverage
        pairs = [{'pairId': 'p1', 'before': 'a', 'after': 'b'}, {'pairId': 'p2', 'before': 'c', 'after': 'd'}]
        rows = [{'sampleId': sample, 'strategy': 'D1', 'd2': {'verdict': verdict}}
                for sample, verdict in [('a', 'SUPPORTED'), ('b', 'REFUTED'), ('c', 'UNKNOWN')]]
        result = paired_evidence_coverage(pairs, rows, ['D1'])['D1']
        self.assertEqual(2, result['plannedPairs'])
        self.assertEqual(1, result['supportedRefutedPairs'])
        self.assertEqual(0.5, result['evidenceCoverage'])
        self.assertIsNone(result['independentAccuracy'])

    def test_五条件协议冻结完整预算且未审核保持探索状态(self):
        from r3_protocol import freeze_plan
        from benchmark_batch import make_plan
        plan = make_plan(['a'], ['VANILLA', 'R3_CODE', 'R3_CARD', 'R3_DENSE', 'R3_FUSION'],
                         'real', [{'sampleId': 'a', 'runnable': True, 'sourceHash': 'a' * 64,
                                   'groundTruth': {'hasVulnerability': True}}], 'b' * 64, {'model': 'fixture'})
        result = freeze_plan(plan, {'registryHash': 'c' * 64}, {'artifactHash': 'd' * 64},
                             {'a': {s: {'requestSha256': 'e' * 64} for s in plan['strategies']}}, 32768)
        self.assertEqual(5, result['requestBounds']['maxRequests'])
        self.assertEqual(163840, result['requestBounds']['maxPromptBytesTotal'])
        self.assertIsNone(result['requestBounds']['maxInputTokens'])
        self.assertFalse(result['researchEligible'])
        self.assertEqual([], result['evaluationPairs'])

    def test_双向核验缺失或失败不能从分母删除或变为成功(self):
        from r3_protocol import paired_evidence_coverage
        pairs = [{'pairId': 'p', 'before': 'a', 'after': 'b'}]
        rows = [{'sampleId': key, 'strategy': 'D1', 'status': 'COMPLETED'} for key in ('a', 'b')]
        self.assertEqual(0, paired_evidence_coverage(pairs, rows, ['D1'])['D1']['supportedRefutedPairs'])
        rows[0]['d2'] = {'verdict': 'SUPPORTED'}
        rows[1]['d2'] = {'verdict': 'REFUTED', 'status': 'FAILED'}
        result = paired_evidence_coverage(pairs, rows, ['D1'])['D1']
        self.assertEqual(1, result['plannedPairs'])
        self.assertEqual(0, result['evidenceCoverage'])
        self.assertIsNone(paired_evidence_coverage([], [], ['D1'])['D1']['evidenceCoverage'])
        with self.assertRaises(ValueError):
            paired_evidence_coverage(pairs, rows + rows, ['D1'])

    def test_配对主分母包含失败与未运行(self):
        from r3_protocol import paired_accuracy
        pairs = [{'pairId': 'p1', 'before': 'a', 'after': 'b'},
                 {'pairId': 'p2', 'before': 'c', 'after': 'd'}]
        rows = [{'sampleId': 'a', 'strategy': 'R3_CARD', 'status': 'COMPLETED', 'prediction': 'REPORT'},
                {'sampleId': 'b', 'strategy': 'R3_CARD', 'status': 'COMPLETED', 'prediction': 'NO_REPORT'},
                {'sampleId': 'c', 'strategy': 'R3_CARD', 'status': 'FAILED', 'prediction': 'UNKNOWN'}]
        result = paired_accuracy(pairs, rows, ['R3_CARD'])['R3_CARD']
        self.assertEqual({'plannedPairs': 2, 'correctPairs': 1, 'completePairs': 1, 'accuracy': 0.5}, result)

    def test_不同池按表达和排序组分别校验(self):
        from r3_protocol import comparison_audit
        rows = [{'sampleId': 'a', 'strategy': strategy, 'poolHash': pool,
                 'retrieval': {'r3Receipt': {'selectedPairs': ['p']}}}
                for strategy, pool in [('R3_CODE', 'old'), ('R3_CARD', 'old'),
                                       ('R3_DENSE', 'new'), ('R3_FUSION', 'new')]]
        self.assertEqual([], comparison_audit(rows))
        rows[1]['retrieval']['r3Receipt']['selectedPairs'] = ['q']
        self.assertTrue(comparison_audit(rows))

    def test_五条件使用原批量平台回放且不同实验组不误报池冲突(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from benchmark_batch import make_plan, replay_batch, run_batch
        from r3_protocol import CONDITIONS, freeze_plan
        plan = make_plan(['a'], CONDITIONS, 'real', [{'sampleId': 'a', 'runnable': True,
            'sourceHash': 'a' * 64, 'groundTruth': {'hasVulnerability': True}}], 'b' * 64)
        plan = freeze_plan(plan, {'registryHash': 'c' * 64}, {'artifactHash': 'd' * 64},
                           {'a': {s: {'requestSha256': 'e' * 64} for s in CONDITIONS}}, 32768)
        def runner(sample, strategy, mode):
            pool = 'old' if strategy == 'VANILLA' else 'expression' if strategy in ('R3_CODE', 'R3_CARD') else 'union'
            return {'status': 'COMPLETED', 'prediction': 'REPORT', 'poolHash': pool,
                    'retrieval': {'r3Receipt': {'selectedPairs': ['p']}},
                    'model': {}, 'inputTokens': None, 'outputTokens': None}
        with TemporaryDirectory() as directory:
            key = run_batch(Path(directory), plan, runner)
            report = replay_batch(Path(directory), key)
            self.assertEqual(5, report['denominators']['completed'])
            self.assertEqual([], report['poolConflicts'])
            self.assertEqual([], report['comparisonAudit'])
            self.assertIsNone(report['pairAccuracy']['R3_CARD']['accuracy'])
            self.assertEqual(0, report['pairEvidenceCoverage']['R3_CARD']['plannedPairs'])
            self.assertIsNone(report['pairEvidenceCoverage']['R3_CARD']['independentAccuracy'])
