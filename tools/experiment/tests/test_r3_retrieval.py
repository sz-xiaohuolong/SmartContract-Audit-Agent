"""机制卡片、多路检索与实际消费的行为回归。"""
import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import test_benchmark_runtime as fixtures
from verirag.infrastructure.storage import fingerprint


class R3RetrievalTest(unittest.TestCase):
    def setup_runtime(self, directory):
        helper = fixtures.BenchmarkRuntimeTest()
        runtime = helper.runtime(Path(directory))
        from verirag.retrieval.r3_retrieval import R3Retrieval
        runtime.r3 = R3Retrieval(runtime.store, runtime.pointer['snapshot_id'], runtime.catalog)
        runtime.r3_allow_unreviewed = True
        return runtime, helper.discovery_target()

    def test_卡片回读绑定原件且不能自称审核通过(self):
        from verirag.retrieval.r3_retrieval import verify_cards
        with TemporaryDirectory() as directory:
            runtime, _ = self.setup_runtime(directory)
            cards = runtime.r3.registry
            self.assertEqual('UNREVIEWED', cards['cards'][0]['semanticReview'])
            verify_cards(cards, runtime.snapshot, runtime.catalog)
            bad = copy.deepcopy(cards)
            bad['cards'][0]['sources'][0]['textHash'] = '0' * 64
            bad['registryHash'] = fingerprint({k: v for k, v in bad.items() if k != 'registryHash'})
            with self.assertRaisesRegex(ValueError, '原件|卡片'):
                verify_cards(bad, runtime.snapshot, runtime.catalog)
            with self.assertRaisesRegex(ValueError, '审核'):
                runtime.r3.select(runtime.preview(runtime_target(runtime)), 'R3_CARD', allow_unreviewed=False)

    def test_同案例表达保留顺序且不存在静默回退(self):
        with TemporaryDirectory() as directory:
            runtime, target = self.setup_runtime(directory)
            base = runtime.preview(target)
            code = runtime.r3.select(base, 'R3_CODE', allow_unreviewed=True)
            card = runtime.r3.select(base, 'R3_CARD', allow_unreviewed=True)
            self.assertTrue(code['d1']['context'])
            self.assertEqual(code['r3Receipt']['selectedPairs'], card['r3Receipt']['selectedPairs'])
            self.assertNotEqual(code['d1']['context'], card['d1']['context'])
            self.assertEqual(code['poolHash'], card['poolHash'])
            self.assertIn('未审核', card['d1']['context'])
            runtime.r3.registry['cards'].clear()
            with self.assertRaises(ValueError):
                runtime.r3.select(base, 'R3_CARD', allow_unreviewed=True)

    def test_BM25可从向量候选外召回且融合从名次一开始(self):
        from verirag.retrieval.r3_retrieval import bm25, reciprocal_fusion
        ranked = bm25({'a': 'withdraw balance', 'b': 'grantRole onlyRole'}, 'grantRole', 1)
        self.assertEqual(['b'], ranked)
        fused = reciprocal_fusion({'dense': ['a'], 'code': ['b', 'a'], 'purpose': ['b']})
        self.assertEqual(2.0, fused['b'])
        self.assertEqual(1.5, fused['a'])

    def test_真实多路并集包含向量八十片段之外的完整对(self):
        from verirag.experiments.benchmark_runtime import BenchmarkRuntime
        from verirag.experiments.benchmark_targets import _record
        from verirag.retrieval.r3_retrieval import R3Retrieval
        from verirag.knowledge.snapshots import activate_snapshot, build_snapshot
        from verirag.infrastructure.storage import atomic_json
        with TemporaryDirectory() as directory:
            store = Path(directory) / 'snapshots'
            samples, docs, vectors, cases = [], [], {}, {}
            for index in range(42):
                key = f'k{index:02}'
                samples.append({'id': key, 'path': key + '.sol', 'source_hash': fingerprint(key),
                    'exact_group': fingerprint(key), 'project_group': key, 'clone_groups': [],
                    'origin': '夹具/' + key, 'split': 'knowledge', 'types': ['REENTRANCY'],
                    'review_status': 'AUTO_LABELED', 'evidence_tier': 'HEURISTIC', 'label_rule': '夹具'})
                function = 'zebraWithdraw' if index == 41 else 'withdraw'
                for role in ('VULNERABLE', 'DEFENSE'):
                    doc_id = key + role
                    body = 'msg.sender.call(""); credit[msg.sender] = 0;' if role == 'VULNERABLE' else 'credit[msg.sender] = 0; msg.sender.call("");'
                    docs.append({'id': doc_id, 'sample_id': key, 'text': f'function {function}() public {{ {body} }}'})
                    vectors[doc_id] = [0.0, 1.0] if index == 41 else [1.0, 0.0]
                    cases[doc_id] = {'caseId': doc_id, 'pairId': key, 'role': role, 'mechanism': 'REENTRANCY',
                                     'riskKind': 'CALL', 'conditions': [], 'reviewed': False}
            snapshot = build_snapshot(store, {'schema_version': '1', 'categories': ['REENTRANCY'], 'samples': samples},
                docs, {'model': 'fixture', 'revision': 'r', 'dimension': 2}, {'version': 'fixture'}, vectors)
            index = fixtures.LocalIndex()
            activate_snapshot(store, snapshot, index)
            (store / 'catalogs').mkdir()
            catalog = {'snapshotId': snapshot, 'cases': cases}
            atomic_json(store / 'catalogs' / (snapshot + '.json'), catalog)
            runtime = BenchmarkRuntime(Path(directory), index, lambda texts: [[1.0, 0.0]], snapshot_root=store)
            runtime.r3 = R3Retrieval(store, snapshot, catalog)
            target = _record('target', 'contract C { function zebraWithdraw() public { msg.sender.call(""); msg.sender.call(""); } }',
                             'REENTRANCY', 'zebraWithdraw', None, True, '夹具', '目标')
            base = runtime.preview(target)
            dense = runtime.r3.select(base, 'R3_DENSE', allow_unreviewed=True)
            fusion = runtime.r3.select(base, 'R3_FUSION', allow_unreviewed=True)
            self.assertNotIn('k41', fusion['r3Receipt']['routes']['dense'])
            self.assertIn('k41', fusion['r3Receipt']['routes']['code'])
            self.assertEqual(2, sum(c['pairId'] == 'k41' for c in fusion['pool']['candidates']))
            self.assertEqual(dense['poolHash'], fusion['poolHash'])

    def test_共同预算不足时两种表达同时拒绝整对(self):
        with TemporaryDirectory() as directory:
            runtime, target = self.setup_runtime(directory)
            base = runtime.preview(target)
            for strategy in ('R3_CODE', 'R3_CARD'):
                view = runtime.r3.select(base, strategy, allow_unreviewed=True, max_bytes=1)
                self.assertEqual('', view['d1']['context'])
                self.assertEqual([], view['r3Receipt']['selectedPairs'])
                self.assertTrue(view['r3Receipt']['rejected'])

    def test_错资源被排除而缺路径条件保持未知(self):
        from verirag.retrieval.r3_retrieval import bind_conditions
        binding = bind_conditions({'resourceKey': 'msg.sender'}, {'resourceKey': 'tx.origin'})
        self.assertEqual('CONTRADICTED', binding['applicability'])
        binding = bind_conditions({'resourceKey': 'msg.sender'}, {'resourceKey': 'msg.sender'})
        self.assertEqual('UNKNOWN', binding['applicability'])
        self.assertIsNone(binding['stateVersion'])
        self.assertIsNone(binding['path'])

    def test_互补选择优先新增保护差异而非重复案例(self):
        from verirag.retrieval.r3_retrieval import complementary_order
        rows = [{'pairId': 'a', 'features': ['ORDER'], 'score': 1.0},
                {'pairId': 'b', 'features': ['ORDER'], 'score': 0.99},
                {'pairId': 'c', 'features': ['MUTEX'], 'score': 0.98}]
        selected = complementary_order(rows)
        self.assertEqual(['a', 'c', 'b'], [row['pairId'] for row in selected])
        self.assertEqual(['MUTEX'], selected[1]['newCoverage'])

    def test_新策略进入真实编排且模型实际收到卡片(self):
        with TemporaryDirectory() as directory:
            runtime, target = self.setup_runtime(directory)
            received = []
            runtime.model_runner = lambda root, target, view, mode: (received.append(view) or {
                'status': 'COMPLETED', 'conclusion': 'NO_CONFIRMED_FINDINGS', 'hypotheses': []})
            runtime.tool_runner = lambda *args: [{'engine': 'SLITHER', 'status': 'SKIPPED', 'issues': []}]
            result = runtime.run(target, 'R3_FUSION', 'real')
            self.assertIn('机制卡片', received[0]['d1']['context'])
            self.assertEqual('R3_FUSION', result['retrieval']['strategy'])
            self.assertEqual('UNKNOWN', result['d2']['verdict'])
            self.assertIsNone(result['inputTokens'])

    def test_评估按同一案例恢复卡片正文且拒绝伪造(self):
        import hashlib
        from verirag.evaluation.eval_ragas import normalize_row
        with TemporaryDirectory() as directory:
            runtime, target = self.setup_runtime(directory)
            for strategy in ('R3_CODE', 'R3_CARD'):
                view = runtime.r3.select(runtime.preview(target), strategy, allow_unreviewed=True)
                context = view['d1']['context']
                ids = [s['candidate']['chunkId'] for s in view['d1']['selected']]
                raw = {'sampleId': target['sampleId'], 'strategy': strategy, 'source': target['fullSource'],
                       'sourceHash': target['sourceHash'], 'snapshotId': view['snapshotId'], 'poolHash': view['poolHash'],
                       'retrieval': view, 'model': {'status': 'COMPLETED', 'hypotheses': [],
                           'requestConsumptionReceipt': {'schemaVersion': 'request-consumption-1',
                               'sourceHash': target['sourceHash'], 'modelSourceHash': target['modelSourceHash'],
                               'contextSha256': hashlib.sha256(context.encode()).hexdigest(), 'evidenceIds': ids}}}
                row = normalize_row(raw, registry=runtime.r3.registry)
                self.assertEqual('READY', row['inputStatus'], row.get('reason'))
                self.assertEqual(['pair'], row['retrieved_context_ids'])
                self.assertEqual('CASE_PAIR', row['rankingUnit'])
                if strategy == 'R3_CARD':
                    view['d1']['context'] += '伪造的防御证明'
                    raw['model']['requestConsumptionReceipt']['contextSha256'] = hashlib.sha256(view['d1']['context'].encode()).hexdigest()
                    self.assertEqual('INVALID_INPUT', normalize_row(raw, registry=runtime.r3.registry)['inputStatus'])


def runtime_target(runtime):
    return fixtures.BenchmarkRuntimeTest().discovery_target()
