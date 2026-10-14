"""独立复核错引用、伪收据、另一资源及回滚，不复写原候选。"""
import copy
import unittest
import test_compiler_facts as fixtures


class EvidenceReviewTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompilerFactsTest(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.bundle = self.fixture.load()
        self.hypothesis = {'contract': 'C', 'function': 'f()', 'riskOperation': 'WRITE', 'riskLine': 2,
                           'vulnerabilityType': 'ACCESS_CONTROL'}
        from compiler_facts import source_span
        self.span = source_span(self.bundle['nodes'][21], self.bundle['units'])
        self.result = {'verdict': 'SUPPORTED', 'binding': {key: self.bundle[key] for key in
            ['sourceHash', 'environmentHash', 'receiptDigest']}, 'toolBinding': {'status': 'MATCH'},
            'riskBinding': {'nodeId': 21, 'span': self.span},
            'references': [{'nodeId': 21, 'span': self.span, 'sourceHash': self.bundle['sourceHash'],
                            'environmentHash': self.bundle['environmentHash']}],
            'proofScope': {'complete': False, 'gaps': []}, 'cfg': {'nodes': [
                {'nodeId': 21, 'resource': ['resource', 2, []]}]},
            'pathEvidence': {'status': 'FEASIBLE', 'normalExit': True,
                             'witness': {'location': {'resource': ['resource', 2, []]}}}}

    def review(self, result):
        from evidence_review import review_evidence
        return review_evidence(self.hypothesis, result, self.bundle)

    def test_错源码字节与伪收据分项报告冲突(self):
        changed = copy.deepcopy(self.result); changed['references'][0]['span']['start'] = 999
        self.assertEqual('CONFLICT', self.review(changed)['checks'][0]['status'])
        changed = copy.deepcopy(self.result); changed['binding']['receiptDigest'] = '0' * 64
        self.assertEqual('CONFLICT', self.review(changed)['checks'][1]['status'])

    def test_另一key或非正常提交不能获复核通过(self):
        changed = copy.deepcopy(self.result)
        changed['pathEvidence']['witness']['location']['resource'][2] = ['key-B']
        self.assertEqual('CONFLICT', self.review(changed)['checks'][3]['status'])
        changed = copy.deepcopy(self.result); changed['pathEvidence']['normalExit'] = False
        self.assertEqual('CONFLICT', self.review(changed)['checks'][5]['status'])

    def test_合法局部反例不要求全入口反驳闭包也不改裁决(self):
        original = copy.deepcopy(self.result)
        review = self.review(self.result)
        self.assertNotEqual('CONFLICT', review['status'])
        self.assertFalse(review['gateApplied'])
        self.assertEqual(original, self.result)
        changed = copy.deepcopy(self.result); changed['verdict'] = 'REFUTED'
        self.assertEqual('UNRESOLVED', self.review(changed)['checks'][4]['status'])

    def test_伪入口操作事实与来源文件必须独立拒绝(self):
        for key, value in [('function', 'notExisting()'), ('riskOperation', 'CALL'),
                           ('riskFactId', 'forged'), ('sourceFile', 'other.sol')]:
            with self.subTest(key=key):
                from evidence_review import review_evidence
                hypothesis = {**self.hypothesis, key: value}
                report = review_evidence(hypothesis, self.result, self.bundle)
                self.assertEqual('CONFLICT', report['checks'][2]['status'])

    def test_同时伪造CFG和见证资源不能相互自证(self):
        changed = copy.deepcopy(self.result)
        changed['cfg']['nodes'][0]['resource'] = ['resource', 999, ['fake-key']]
        changed['pathEvidence']['witness']['location']['resource'] = ['resource', 999, ['fake-key']]
        self.assertEqual('CONFLICT', self.review(changed)['checks'][3]['status'])
