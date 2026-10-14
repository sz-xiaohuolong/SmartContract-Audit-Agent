"""新协议隔离消融和单次探索授权，不覆盖旧协议或伪造研究准入。"""
import unittest


class SynapseProtocolTest(unittest.TestCase):
    def plan(self):
        return {'sampleIds': ['a', 'b'], 'strategies': ['VANILLA', 'DENSE', 'D1'],
                'sourceHashes': {'a': 'a' * 64, 'b': 'b' * 64}, 'snapshotId': 'c' * 64,
                'provider': {'model': 'fixture'}, 'planHash': 'd' * 64}

    def test_单次探索预算包含冒烟且不自动执行三次六臂(self):
        from synapse_protocol import build_synapse_protocol
        report = build_synapse_protocol(self.plan(), {'commit': 'x'}, {'hash': 'y'})
        self.assertEqual(8, report['authorizedCollection']['maxRequests'])
        self.assertEqual(0, report['authorizedCollection']['retries'])
        self.assertEqual(1, report['authorizedCollection']['repetitions'])
        self.assertEqual(0, report['newModelRequests'])
        self.assertFalse(report['researchEligible'])
        self.assertEqual('UNVERIFIED', report['budget']['fairnessStatus'])
        self.assertIsNone(report['budget']['maxInputTokens'])

    def test_不完整来源或未知标签不能通过正式准入(self):
        from synapse_protocol import build_synapse_protocol
        result = build_synapse_protocol(self.plan(), {'commit': 'x'}, {'hash': 'y'},
            admission={'independentLabels': True, 'sourceAndSplitAudit': False, 'exactTokenFairness': False})
        self.assertFalse(result['researchEligible'])
        self.assertEqual(3, len(result['factorExperiments']))
        self.assertTrue(all(not factor['executionAuthorized'] for factor in result['factorExperiments']))

    def test_输入闭包缺失拒绝冻结(self):
        from synapse_protocol import build_synapse_protocol
        plan = self.plan(); plan['sourceHashes'].pop('b')
        with self.assertRaises(ValueError):
            build_synapse_protocol(plan, {'commit': 'x'}, {'hash': 'y'})
