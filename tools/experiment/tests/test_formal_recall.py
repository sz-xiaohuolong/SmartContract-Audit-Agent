"""正式快照的工程目标召回与 D1 缺口离线测试。"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_isolation import manifest
from snapshots import build_snapshot, activate_snapshot
from storage import atomic_json, fingerprint
from d1_embed import MODEL, REVISION, DIMENSION
from formal_recall import preview


class FakeIndex:
    def __init__(self):
        self.rows = []
        self.hits = None
        self.after_search = None

    def build(self, collection, payload): self.rows = copy.deepcopy(payload['rows'])
    def read(self, collection): return copy.deepcopy(self.rows)
    def search(self, collection, query, limit):
        if self.after_search: self.after_search()
        return self.hits if self.hits is not None else [
            {'id': row['id'], 'distance': 1.0} for row in self.rows[:limit]]


class FormalRecallTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        store = self.root / '.local/d1-kb-snapshots'
        docs = [{'id': f'd{i}', 'sample_id': 'a', 'text': f'审计代码案例 {i}'} for i in range(4)]
        vector = [1.0] + [0.0] * (DIMENSION - 1)
        self.snapshot = build_snapshot(store, manifest(), docs,
            {'model': MODEL, 'dimension': DIMENSION, 'revision': REVISION},
            {'version': 'fixture'}, {doc['id']: vector for doc in docs})
        self.index = FakeIndex()
        self.pointer = activate_snapshot(store, self.snapshot, self.index)
        catalog = {'snapshotId': self.snapshot, 'cases': {}}
        for i, doc in enumerate(docs):
            catalog['cases'][doc['id']] = {
                'caseId': f'case-{i // 2}', 'pairId': f'pair-{i // 2}',
                'role': 'VULNERABLE' if i % 2 == 0 else 'DEFENSE',
                'mechanism': 'REENTRANCY' if i < 2 else 'ACCESS_CONTROL', 'riskKind': 'CALL',
                'conditions': [{'predicate': 'STATE_WRITE_BEFORE' if i < 2 else 'CHECK_BEFORE',
                                'subject': '$actor', 'resource': '$resource' if i < 2 else '$authority',
                                'expected': i % 2 == 1}], 'reviewed': True}
        (store / 'catalogs').mkdir()
        atomic_json(store / 'catalogs' / (self.snapshot + '.json'), catalog)
        source = '\n' * 604 + 'contract Dex {\nfunction matchOrderWithReserve() public {\nuint checked = 1;\nif (true) { msg.sender.call(""); }\n}\n}'
        self.target = {'sampleId': 'RE-SCRUBD-001', 'fullSource': source, 'modelSource': source,
            'fullSourceHash': __import__('hashlib').sha256(source.encode()).hexdigest(),
            'modelSourceHash': __import__('hashlib').sha256(source.encode()).hexdigest(),
            'scope': 'FUNCTION', 'function': 'matchOrderWithReserve',
            'mechanism': 'REENTRANCY', 'lineStart': 606, 'lineEnd': 610,
            'assignmentHash': 'f' * 64, 'formalLedgerHash': 'e' * 64, 'groupId': 'g'}
        self.java_calls = []

    def java(self, source, request):
        self.java_calls.append(request)
        return {'facts': {'status': 'PARTIAL'}, 'results': [{
            'strategy': 'D1', 'selected': [], 'context': '',
            'sourceHash': self.target['fullSourceHash'], 'snapshotId': self.snapshot,
            'gaps': ['条件未知：d0'], 'evaluations': {'d0': {'applicability': 'UNKNOWN'}}}]}

    def test_formal_pair_pool_and_unknown_binding(self):
        with patch('formal_recall.load_target', return_value=self.target):
            result = preview(self.root, self.target, self.index,
                             lambda texts: [[1.0] + [0.0] * (DIMENSION - 1)], self.java)
        self.assertEqual(result['snapshotId'], self.snapshot)
        self.assertEqual(result['collection'], self.pointer['collection'])
        self.assertEqual(len(result['pool']['candidates']), 4)
        self.assertEqual({row['role'] for row in result['pool']['candidates']}, {'VULNERABLE', 'DEFENSE'})
        self.assertEqual(result['d1']['evaluations']['d0']['applicability'], 'UNKNOWN')
        self.assertEqual(self.java_calls[0]['target']['riskFactId'],
                         __import__('program_facts').extract_facts(self.target['fullSource'])['facts'][0]['id'])
        self.assertEqual(result['researchEligible'], False)

    def test_no_compatible_risk_fact_is_visible_without_forging_one(self):
        target = dict(self.target, sampleId='AC-ASE-006', mechanism='ACCESS_CONTROL', function='a',
                      fullSource='contract Basin { function a() external { require(msg.sender == owner); } }',
                      scope='FULL')
        target['fullSourceHash'] = __import__('hashlib').sha256(target['fullSource'].encode()).hexdigest()
        target['modelSource'] = target['fullSource']
        target['modelSourceHash'] = target['fullSourceHash']
        with patch('formal_recall.load_target', return_value=target):
            result = preview(self.root, target, self.index,
                             lambda texts: [[1.0] + [0.0] * (DIMENSION - 1)], self.java)
        self.assertEqual(result['d1']['status'], 'NO_RISK_FACT')
        self.assertEqual(len(self.java_calls), 0)
        self.assertEqual(len(result['pool']['candidates']), 4)

    def test_bad_milvus_model_or_pointer_is_rejected(self):
        vector = [1.0] + [0.0] * (DIMENSION - 1)
        with patch('formal_recall.load_target', return_value=self.target):
            self.index.hits = [{'id': 'unknown', 'distance': 1.0}] * 4
            with self.assertRaises(ValueError): preview(self.root, self.target, self.index, lambda texts: [vector], self.java)
            self.index.hits = [{'id': row['id'], 'distance': 0.5} for row in self.index.rows]
            with self.assertRaises(ValueError): preview(self.root, self.target, self.index, lambda texts: [vector], self.java)
            self.index.hits = None
            with self.assertRaises(ValueError): preview(self.root, self.target, self.index, lambda texts: [[1.0] * 128], self.java)
            pointer = self.root / '.local/d1-kb-snapshots/active.json'
            self.index.after_search = lambda: atomic_json(pointer, dict(
                snapshot_id=self.snapshot, backend='milvus', collection='mvp_' + '0' * 32))
            with self.assertRaises(ValueError): preview(self.root, self.target, self.index, lambda texts: [vector], self.java)

    def test_java_result_must_bind_target_and_snapshot(self):
        def stale_java(source, request):
            result = self.java(source, request)
            result['results'][0]['snapshotId'] = '0' * 64
            return result
        with patch('formal_recall.load_target', return_value=self.target):
            with self.assertRaisesRegex(ValueError, 'D1'):
                preview(self.root, self.target, self.index,
                        lambda texts: [[1.0] + [0.0] * (DIMENSION - 1)], stale_java)


if __name__ == '__main__':
    unittest.main()
