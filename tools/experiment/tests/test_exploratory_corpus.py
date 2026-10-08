"""探索性候选知识的身份、句法配对和只读 Milvus 核对。"""
import tempfile
import unittest
from pathlib import Path

from exploratory_corpus import load_corpus, verify_remote, candidate_metadata
from r1_candidate_corpus import documents
from storage import atomic_json, encode, fingerprint


class FakeIndex:
    def __init__(self, rows):
        self.rows = rows

    def request(self, endpoint, payload):
        if endpoint == 'collections/has':
            return {'has': True}
        if endpoint == 'entities/query':
            return self.rows[payload['offset']:payload['offset'] + payload['limit']]
        raise AssertionError(endpoint)


class ExploratoryCorpusTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pair = {'id': 'am_1', 'source': 'AutoMESC', 'project': 'https://example.test/project',
                     'categoryHint': 'REENTRANCY', 'reviewStatus': 'PENDING',
                     'patchStatus': 'UNVERIFIED', 'before': 'function take() external { target.call(""); }',
                     'after': 'function take() external nonReentrant { target.call(""); }'}
        self.forge = {'id': 'forge_vfp_1', 'source': 'FORGE-Curated', 'project': 'another',
                      'categoryHint': 'ACCESS_CONTROL', 'reviewStatus': 'PENDING',
                      'patchStatus': 'MISSING', 'text': '审计报告与源码'}
        self.docs = documents([self.pair], [self.forge])
        self.vectors = {row['id']: [1.0, 0.0] if row['id'].endswith('before') else [0.0, 1.0]
                        for row in self.docs}
        embedding = {'model': 'test', 'revision': 'r', 'dimension': 2}
        identity = fingerprint({'rows': self.docs, 'embedding': {'model': 'test', 'revision': 'r'},
                                'vectors': self.vectors})
        receipt = {'collection': 'r1pending_' + identity[:32], 'identity': identity,
                   'candidateOnly': True, 'formalD1Enabled': False, 'vectorCount': 3,
                   'automescPairs': 1, 'forgeVfp': 1, 'embedding': embedding}
        for name, value in [('automesc-selected.json', [self.pair]), ('forge-selected.json', [self.forge]),
                            ('vectors.json', self.vectors), ('receipt.json', receipt)]:
            atomic_json(self.root / name, value)

    def test_只有句法可核变化构成暂定对照(self):
        corpus = load_corpus(self.root)
        before = candidate_metadata(corpus, self.docs[0])
        after = candidate_metadata(corpus, self.docs[1])
        reference = candidate_metadata(corpus, self.docs[2])
        self.assertEqual(('VULNERABLE', 'DEFENSE'), (before['role'], after['role']))
        self.assertFalse(before['reviewed'])
        self.assertEqual('NON_REENTRANT', before['conditions'][0]['predicate'])
        self.assertEqual([], reference['conditions'])
        self.assertEqual('REFERENCE', reference['role'])
        self.pair['after'] = 'function take() external { target.call(""); }'
        corpus['pairs'][self.pair['id']] = self.pair
        self.assertEqual('REFERENCE', candidate_metadata(corpus, self.docs[0])['role'])

    def test_远端正文和向量必须逐条一致且不写库(self):
        corpus = load_corpus(self.root)
        rows = [{'id': row['id'], 'payload': encode(row).decode(), 'vector': self.vectors[row['id']]}
                for row in self.docs]
        self.assertEqual(3, verify_remote(corpus, FakeIndex(rows)))
        with self.assertRaises(ValueError):
            verify_remote(corpus, FakeIndex(rows[:-1]))
        damaged = [dict(row) for row in rows]
        damaged[0]['payload'] = '{}'
        with self.assertRaises(ValueError):
            verify_remote(corpus, FakeIndex(damaged))

    def test_收据身份变化时拒绝候选库(self):
        receipt = __import__('json').loads((self.root / 'receipt.json').read_text())
        receipt['identity'] = '0' * 64
        atomic_json(self.root / 'receipt.json', receipt)
        with self.assertRaises(ValueError):
            load_corpus(self.root)


if __name__ == '__main__':
    unittest.main()
