"""768 维独立快照与逐条向量断点的离线验证。"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from nomic_snapshot import build_nomic_snapshot
from snapshots import active_snapshot, verify_snapshot


class Encoder:
    digest = 'a' * 64
    context_length = 2048
    def __init__(self):
        self.calls = 0
    def encode_document(self, text):
        self.calls += 1
        return ([1.0] + [0.0] * 767,
                {'originalChars': len(text), 'embeddedChars': len(text), 'truncated': False})


class Index:
    def __init__(self):
        self.rows = {}
    def build(self, collection, payload):
        self.rows[collection] = payload['rows']
    def read(self, collection):
        return list(self.rows[collection])


class NomicSnapshotTest(unittest.TestCase):
    def test_独立集合完整读回且重复构建复用断点(self):
        before = 'contract Vault { function take() external { msg.sender.call(""); } }'
        after = 'contract Vault { function take() external nonReentrant { msg.sender.call(""); } }'
        pair = {'id': 'am_1', 'source': 'AutoMESC', 'sourceRevision': 'revision',
                'project': 'https://example.test/a', 'commitUrl': 'https://example.test/a/commit/abc',
                'categoryHint': 'REENTRANCY', 'reviewStatus': 'PENDING',
                'patchStatus': 'UNVERIFIED', 'before': before, 'after': after}
        rows = {}
        for side, text in (('before', before), ('after', after)):
            key = 'am_1_' + side
            rows[key] = {'id': key, 'pairId': 'am_1', 'source': 'AutoMESC',
                         'project': pair['project'], 'categoryHint': 'REENTRANCY',
                         'reviewStatus': 'PENDING', 'patchStatus': 'UNVERIFIED',
                         'side': side, 'text': text}
        corpus = {'pairs': {'am_1': pair}, 'rows': rows,
                  'receipt': {'identity': hashlib.sha256(b'corpus').hexdigest()},
                  'vectors': {}}
        encoder, index = Encoder(), Index()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_nomic_snapshot(corpus, root / 'embeddings', root / 'nomic',
                                          encoder, index, activate=True)
            self.assertEqual(2, encoder.calls)
            self.assertTrue(result['active']['collection'].startswith('s1b_nomic_'))
            self.assertEqual(768, verify_snapshot(root / 'nomic', result['snapshotId'])['embedding']['dimension'])
            again = build_nomic_snapshot(corpus, root / 'embeddings', root / 'nomic',
                                         encoder, index, activate=True)
            self.assertEqual(2, encoder.calls)
            self.assertEqual(result['active'], again['active'])
            self.assertEqual(result['active'], active_snapshot(root / 'nomic', index))


if __name__ == '__main__':
    unittest.main()
