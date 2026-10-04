"""正式 D1 知识快照准入与成对文档的离线测试。"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from d1_kb import stage_snapshot
from snapshots import verify_snapshot


def digest(data):
    return hashlib.sha256(data.encode()).hexdigest()


class D1KnowledgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = 'contract A {\nfunction pull() public { transfer(); off = true; }\n}\n'
        self.patched = 'contract A {\nfunction pull() public { off = true; transfer(); }\n}\n'
        for name, value in [('source.sol', self.original), ('patch.sol', self.patched),
                            ('report.md', '独立审计指出外部调用早于状态更新。')]:
            (self.root / name).write_text(value)
        group = 'event-1'
        artifacts = [{'id': kind, 'kind': kind.upper(), 'path': path,
                      'sha256': digest((self.root / path).read_text()), 'groupId': group}
                     for kind, path in [('source', 'source.sol'), ('report', 'report.md'), ('patch', 'patch.sol')]]
        self.ledger = {'schemaVersion': '1', 'sources': [{'id': 'case', 'url': 'https://example.invalid/source',
            'revision': 'a' * 40, 'licenseStatus': 'VERIFIED', 'license': 'MIT',
            'sourceStatus': 'VERIFIED', 'reportStatus': 'VERIFIED', 'patchStatus': 'VERIFIED'}],
            'samples': [{'id': 'case', 'sourceId': 'case', 'path': 'source.sol',
                'sourceHash': digest(self.original), 'split': 'knowledge', 'projectId': 'project-1',
                'eventId': group, 'patchPairId': group, 'cloneGroups': [], 'originType': 'REAL_PATCH',
                'labelStatus': 'REVIEWED', 'vulnerabilityType': 'REENTRANCY', 'vulnerabilityLine': 2,
                'truthReviewerType': 'INDEPENDENT', 'truthReviewer': 'fixture-reviewer',
                'truthReviewVersion': '1', 'truthEvidence': ['report', 'patch'], 'artifacts': artifacts}],
            'edges': []}
        self.pairs = [{'sampleId': 'case', 'function': 'pull', 'sourceLines': [2, 2], 'patchLines': [2, 2],
                       'mechanism': 'REENTRANCY', 'riskKind': 'CALL', 'predicate': 'STATE_WRITE_BEFORE',
                       'subject': '$actor', 'resource': '$resource', 'reviewed': True,
                       'reviewerType': 'INDEPENDENT', 'reviewer': 'fixture-reviewer',
                       'evidence': ['report', 'patch']}]
        self.vectors = {'case-original': [1.0, 0.0], 'case-patch': [0.0, 1.0]}
        self.embedding = {'model': 'fixture', 'dimension': 2, 'revision': '1'}

    def stage(self):
        return stage_snapshot(self.ledger, self.root, self.pairs, self.vectors,
                              self.embedding, self.root / 'snapshots')

    def test_reviewed_pair_stages_two_documents_without_activation(self):
        result = self.stage()
        payload = verify_snapshot(self.root / 'snapshots', result['snapshotId'])
        self.assertEqual(['case-original', 'case-patch'], [d['id'] for d in payload['documents']])
        self.assertEqual('knowledge', payload['manifest']['samples'][0]['split'])
        self.assertEqual({'VULNERABLE', 'DEFENSE'},
                         {c['role'] for c in result['catalog']['cases'].values()})
        self.assertFalse((self.root / 'snapshots' / 'active.json').exists())

    def test_pending_label_and_pending_pair_cannot_stage(self):
        self.ledger['samples'][0]['labelStatus'] = 'PENDING'
        with self.assertRaisesRegex(ValueError, '待审'):
            self.stage()
        self.ledger['samples'][0]['labelStatus'] = 'REVIEWED'
        self.pairs[0]['reviewed'] = False
        with self.assertRaisesRegex(ValueError, '待审'):
            self.stage()

    def test_patch_tamper_and_missing_pair_cannot_stage(self):
        (self.root / 'patch.sol').write_text('contract Broken {}')
        with self.assertRaises(ValueError): self.stage()
        (self.root / 'patch.sol').write_text(self.patched)
        with self.assertRaises(ValueError):
            stage_snapshot(self.ledger, self.root, [], self.vectors, self.embedding,
                           self.root / 'snapshots')

    def test_duplicate_patch_artifact_cannot_select_arbitrary_file(self):
        self.ledger['samples'][0]['artifacts'].append(dict(self.ledger['samples'][0]['artifacts'][-1]))
        with self.assertRaisesRegex(ValueError, '重复'):
            self.stage()

    def test_invalid_pair_shape_fails_closed(self):
        self.pairs[0] = '无效配对'
        with self.assertRaises(ValueError):
            self.stage()
