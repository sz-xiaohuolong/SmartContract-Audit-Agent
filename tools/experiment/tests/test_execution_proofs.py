"""真实执行提供器与裁决之间的门槛；外部进程由收据夹具替代。"""
import copy
import unittest
from unittest.mock import patch

from verirag.analysis import compiled_d2
from verirag.analysis.d2_verify import OBLIGATIONS


class ExecutionProofTest(unittest.TestCase):
    def setUp(self):
        self.resource = ('resource', 9, ())
        self.span = {'start': 20, 'length': 4, 'sourceUnit': 'C.sol', 'sourceUnitId': 0, 'line': 2}
        self.proof = {'status': 'UNKNOWN', 'candidateBound': True,
            'proofKind': 'ACCESS_CONTROL_AUTHORITY_WRITE_CANDIDATE',
            'proofScope': {'complete': False, 'gaps': ['缺正常提交'], 'authorityResource': self.resource,
                           'riskSpan': self.span, 'authorityConsumers': [{'entry': 'withdraw()'}]},
            'pathEvidence': {'status': 'UNKNOWN'}, 'references': [],
            'obligations': [{'name': name, 'status': 'UNKNOWN', 'references': []} for name in OBLIGATIONS]}
        self.hypothesis = {'vulnerabilityType': 'ACCESS_CONTROL', 'riskOperation': 'WRITE'}
        self.binding = {'status': 'MATCH', 'matchedToolIndexes': []}
        self.receipt = {'status': 'MATCH', 'provider': 'bound-evm-1', 'receipts': [
            {'path': 'a.json', 'sha256': 'a' * 64}, {'path': 'b.json', 'sha256': 'b' * 64}],
            'witness': {'kind': 'ACCESS_CONTROL_AUTHORITY_WRITE', 'normalExit': True,
                'location': {'resource': self.resource}, 'assertion': {'valid': True,
                    'assertion': 'PERSISTENT_UNAUTHORIZED_AUTHORITY_WRITE'},
                'initialization': {'runtimeInitialized': True},
                'effectReferences': [{'engine': 'SLITHER', 'rootDeclarationId': 9}],
                'consumerExecution': {'valid': True, 'normalExit': True},
                'authorityConsumers': [{'entry': 'withdraw()'}]}}

    def augment(self, receipt=None, binding=None):
        with patch('verirag.analysis.evm_witness.execute_bound_witness', return_value=receipt or self.receipt):
            # 返回证明必须由本机执行接口产生，不能读取模型填写的“成功”字段。
            return compiled_d2._execution_proof(copy.deepcopy(self.proof), self.hypothesis,
                {}, None, {'span': self.span}, binding or self.binding, '.')

    def test_权限写入双执行与同资源证据进入正裁决(self):
        proof = self.augment()
        self.assertEqual('COUNTEREXAMPLE', proof['status'])
        self.assertFalse(proof['proofScope']['complete'])
        result = {'toolBinding': self.binding, 'verdict': 'UNKNOWN'}
        compiled_d2._apply_proof(result, proof, self.hypothesis, [], {}, '.')
        self.assertEqual('SUPPORTED', result['verdict'])
        self.assertEqual('REFUTED', result['protectionVerdict'])
        self.assertEqual(6, len(result['obligations']))

    def test_失败回滚错资源缺独立佐证均保持未知(self):
        cases = []
        for path, value in [('status', 'UNKNOWN'), ('witness.normalExit', False),
                            ('witness.location.resource', ('resource', 10, ())),
                            ('witness.effectReferences', []), ('receipts', []),
                            ('witness.consumerExecution', {'valid': False}),
                            ('witness.initialization.runtimeInitialized', False)]:
            bad = copy.deepcopy(self.receipt)
            parts = path.split('.')
            target = bad
            for part in parts[:-1]: target = target[part]
            target[parts[-1]] = value
            cases.append(bad)
        for bad in cases:
            with self.subTest(receipt=bad):
                self.assertEqual('UNKNOWN', self.augment(bad)['status'])
        self.assertEqual('UNKNOWN', self.augment(binding={'status': 'UNKNOWN'})['status'])

    def test_候选未绑定或普通公开setter不得尝试升级(self):
        for key, value in [('candidateBound', False), ('proofKind', None)]:
            original = self.proof[key]
            self.proof[key] = value
            self.assertEqual('UNKNOWN', self.augment()['status'])
            self.proof[key] = original
