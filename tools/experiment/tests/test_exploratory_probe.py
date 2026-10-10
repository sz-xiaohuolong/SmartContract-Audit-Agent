"""探索性三策略必须共享候选池与暂定成对补全。"""
import tempfile
import unittest
import hashlib
from pathlib import Path

from exploratory_probe import build_pool, compare_target, run_probe, replay_probe
from evaluation_input import clean_evaluation_source
from exploratory_corpus import load_corpus
from formal_recall import select_strategy
from storage import atomic_json, fingerprint
from r1_candidate_corpus import documents


class SearchIndex:
    def search(self, collection, vector, limit):
        return [{'id': 'am_1_before', 'distance': 1.0},
                {'id': 'forge_vfp_1', 'distance': 0.0},
                {'id': 'am_1_after', 'distance': 0.0}][:limit]


class ExploratoryProbeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        pair = {'id': 'am_1', 'source': 'AutoMESC', 'project': 'project-a', 'categoryHint': 'REENTRANCY',
                'reviewStatus': 'PENDING', 'patchStatus': 'UNVERIFIED',
                'before': 'function take() external { msg.sender.call(""); }',
                'after': 'function take() external nonReentrant { msg.sender.call(""); }'}
        forge = {'id': 'forge_vfp_1', 'source': 'FORGE-Curated', 'project': 'project-b',
                 'categoryHint': 'ACCESS_CONTROL', 'reviewStatus': 'PENDING',
                 'patchStatus': 'MISSING', 'text': '审计参考'}
        rows = documents([pair], [forge])
        vectors = {'am_1_before': [1.0, 0.0], 'am_1_after': [0.0, 1.0], 'forge_vfp_1': [0.0, 1.0]}
        identity = fingerprint({'rows': rows, 'embedding': {'model': 'test', 'revision': 'r'}, 'vectors': vectors})
        for name, data in [('automesc-selected.json', [pair]), ('forge-selected.json', [forge]),
                           ('vectors.json', vectors), ('receipt.json',
                            {'collection': 'r1pending_' + identity[:32], 'identity': identity,
                             'candidateOnly': True, 'formalD1Enabled': False, 'vectorCount': 3,
                             'automescPairs': 1, 'forgeVfp': 1,
                             'embedding': {'model': 'test', 'revision': 'r', 'dimension': 2}})]:
            atomic_json(self.root / name, data)
        self.corpus = load_corpus(self.root)

    def test_召回补齐同对另一侧且拒绝伪造分数(self):
        target = {'sourceHash': 'a' * 64, 'mechanism': 'REENTRANCY'}
        pool = build_pool(self.corpus, target, [1.0, 0.0], SearchIndex(), 1)
        self.assertEqual('exploratory-1', pool['schemaVersion'])
        self.assertEqual({'am_1_before', 'am_1_after'}, {x['chunkId'] for x in pool['candidates']})
        self.assertTrue(all(x['reviewed'] is False for x in pool['candidates']))
        class Corrupt(SearchIndex):
            def search(self, collection, vector, limit):
                return [{'id': 'am_1_before', 'distance': 0.5}]
        with self.assertRaises(ValueError):
            build_pool(self.corpus, target, [1.0, 0.0], Corrupt(), 1)

    def test_逐样本失败保持未知且续跑不重复(self):
        targets = [{'sampleId': 'A', 'sourceHash': 'a' * 64}, {'sampleId': 'B', 'sourceHash': 'b' * 64}]
        calls = []
        def runner(target):
            calls.append(target['sampleId'])
            if target['sampleId'] == 'B':
                raise ValueError('事实缺失')
            return {'sampleId': 'A', 'status': 'COMPLETED', 'poolHash': 'p',
                    'selected': {'DENSE': ['a'], 'FIELD_FILTER': [], 'D1': []},
                    'riskStatus': 'BOUND'}
        batch_id = run_probe(self.root / 'reports', targets, self.corpus['receipt'], runner, batch_id='c' * 32)
        report = replay_probe(self.root / 'reports', batch_id)
        self.assertEqual({'planned': 2, 'completed': 1, 'failed': 1, 'unknown': 1}, report['denominators'])
        self.assertIsNone(report['metrics']['detectionRecall'])
        self.assertEqual(['A', 'B'], calls)
        run_probe(self.root / 'reports', targets, self.corpus['receipt'], runner, batch_id='c' * 32)
        self.assertEqual(['A', 'B'], calls)

    def test_字段过滤不把未定性参考当作适用证据(self):
        reference = {'caseId': 'reference', 'chunkId': 'reference', 'role': 'REFERENCE',
                     'conditions': [], 'text': '仅供参考'}
        view = {'pool': {'candidates': [reference]},
                'd1': {'evaluations': {'reference': {'applicability': 'SUPPORTED'}}}}
        self.assertEqual([], select_strategy(view, 'FIELD_FILTER')['d1']['selected'])
        self.assertEqual(1, len(select_strategy(view, 'DENSE')['d1']['selected']))

    def test_默认发现清理查询且评分行变化不改变风险选择(self):
        source = '// 答案：第3行重入漏洞\ncontract C {\nfunction take() external { msg.sender.call(""); }\n}'
        cleaned = clean_evaluation_source(source)
        queries, requests = [], []
        def encoder(values):
            queries.extend(values)
            return [[1.0, 0.0]]
        def java(source, request):
            requests.append((source, request))
            return {'results': [{'strategy': 'D1', 'sourceHash': cleaned['sourceHash'],
                'snapshotId': self.corpus['receipt']['identity'], 'selected': [], 'context': '',
                'evaluations': {}, 'gaps': []}]}
        target = {'sampleId': 'target', 'source': source,
            'sourceHash': hashlib.sha256(source.encode()).hexdigest(),
            'mechanism': 'REENTRANCY', 'vulnerableLines': [3]}
        first = compare_target(self.root, self.corpus, target, SearchIndex(), encoder, java, 1)
        second = compare_target(self.root, self.corpus, dict(target, vulnerableLines=[1]),
            SearchIndex(), encoder, java, 1)
        self.assertEqual('COMPLETED', first['status'])
        self.assertEqual(first, second)
        self.assertEqual([cleaned['source'], cleaned['source']], queries)
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(cleaned['source'], requests[0][0])

    def test_默认发现多风险保持未知_显式候选行独立于评分行(self):
        source = 'contract C {\nfunction take() external {\nmsg.sender.call("");\nmsg.sender.call("");\n}\n}'
        target = {'sampleId': 'two', 'source': source,
            'sourceHash': hashlib.sha256(source.encode()).hexdigest(),
            'mechanism': 'REENTRANCY', 'vulnerableLines': [3]}
        def java(source, request):
            return {'results': [{'strategy': 'D1', 'sourceHash': target['sourceHash'],
                'snapshotId': self.corpus['receipt']['identity'], 'selected': [], 'context': '',
                'evaluations': {}, 'gaps': []}]}
        unknown = compare_target(self.root, self.corpus, target, SearchIndex(), lambda v: [[1.0, 0.0]], java, 1)
        self.assertEqual('UNKNOWN', unknown['status'])
        claim = dict(target, taskKind='CLAIM_VALIDATION', riskLine=4, claimOrigin='USER_RISK_LINE')
        answer = compare_target(self.root, self.corpus, claim, SearchIndex(), lambda v: [[1.0, 0.0]], java, 1)
        self.assertEqual('COMPLETED', answer['status'])
        self.assertEqual('CLAIM_VALIDATION', answer['taskKind'])

    def test_计划绑定清理摘要与原件_不传评分行给执行器(self):
        source = '// vulnerable line 2\ncontract C {}'
        cleaned = clean_evaluation_source(source)
        target = {'sampleId': 'A', 'source': source,
            'sourceHash': hashlib.sha256(source.encode()).hexdigest(), 'vulnerableLines': [2]}
        consumed = []
        def runner(row):
            consumed.append(row)
            return {'sampleId': 'A', 'status': 'UNKNOWN'}
        batch = run_probe(self.root / 'reports', [target], self.corpus['receipt'], runner)
        plan = replay_probe(self.root / 'reports', batch)['plan']
        self.assertEqual(cleaned['sourceHash'], plan['targetHashes']['A'])
        self.assertEqual(cleaned['originalSourceHash'], plan['targetMetadata']['A']['originalSourceHash'])
        self.assertNotIn('vulnerableLines', consumed[0])
        self.assertEqual(cleaned['source'], consumed[0]['source'])


if __name__ == '__main__':
    unittest.main()
