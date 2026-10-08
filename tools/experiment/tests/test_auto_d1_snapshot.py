"""自动标注知识层保留来源与标签等级，并在完整读回后激活。"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from auto_d1_snapshot import stage_auto_snapshot
from recall import _recall_candidates
from snapshots import activate_snapshot, verify_snapshot


class FakeIndex:
    def build(self, collection, payload):
        self.rows = payload['rows']

    def read(self, collection):
        return list(self.rows)


class AutoSnapshotTest(unittest.TestCase):
    def test_自动标注不是人工审核且前后向量完整(self):
        pair = {'id': 'am_1', 'source': 'AutoMESC', 'sourceRevision': 'revision',
                'project': 'https://example.test/a', 'commit': 'abc',
                'commitUrl': 'https://example.test/a/commit/abc', 'file': 'Vault.sol',
                'categoryHint': 'REENTRANCY', 'reviewStatus': 'PENDING',
                'patchStatus': 'UNVERIFIED',
                'before': 'contract Vault { function take() external { msg.sender.call(""); } }',
                'after': 'contract Vault { function take() external nonReentrant { msg.sender.call(""); } }'}
        before = {'id': 'am_1_before', 'pairId': 'am_1', 'source': 'AutoMESC',
                  'project': pair['project'], 'categoryHint': 'REENTRANCY',
                  'reviewStatus': 'PENDING', 'patchStatus': 'UNVERIFIED',
                  'side': 'before', 'text': pair['before']}
        after = dict(before, id='am_1_after', side='after', text=pair['after'])
        corpus = {'pairs': {'am_1': pair}, 'rows': {row['id']: row for row in (before, after)},
                  'vectors': {'am_1_before': [1.0, 0.0], 'am_1_after': [0.0, 1.0]},
                  'receipt': {'identity': hashlib.sha256(b'corpus').hexdigest(),
                              'embedding': {'model': 'test', 'revision': 'r', 'dimension': 2}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = stage_auto_snapshot(corpus, root)
            snapshot = verify_snapshot(root, result['snapshotId'])
            self.assertEqual(2, len(snapshot['documents']))
            self.assertEqual('AUTO_LABELED', snapshot['manifest']['samples'][0]['review_status'])
            self.assertEqual('NON_REENTRANT', result['catalog']['cases']['am_1_after']['conditions'][0]['predicate'])
            self.assertFalse(result['catalog']['cases']['am_1_after']['reviewed'])
            pointer = activate_snapshot(root, result['snapshotId'], FakeIndex())
            self.assertEqual(result['snapshotId'], pointer['snapshot_id'])
            recalled = _recall_candidates(root, result['snapshotId'], result['catalog'],
                [1.0, 0.0], 'contract Target {}', 1, None, 'b' * 64, allow_external=True)
            self.assertEqual('auto-1', recalled['pool']['schemaVersion'])
            self.assertEqual({'am_1_before', 'am_1_after'},
                             {row['chunkId'] for row in recalled['pool']['candidates']})


if __name__ == '__main__':
    unittest.main()
