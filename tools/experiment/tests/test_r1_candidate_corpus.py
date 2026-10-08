"""待审语料的状态隔离与 Milvus 完整读回测试。"""
import json
import tempfile
import unittest
from pathlib import Path

from r1_candidate_corpus import documents, select_forge, upload_candidates


class FakeIndex:
    def __init__(self, corrupt=False):
        self.rows = []
        self.corrupt = corrupt
        self.exists = False

    def request(self, endpoint, payload):
        if endpoint == 'collections/has':
            return {'has': self.exists}
        if endpoint == 'collections/create':
            self.exists = True
            return {}
        if endpoint == 'collections/load':
            return {}
        if endpoint == 'entities/insert':
            self.rows.extend(payload['data'])
            return {'insertCount': len(payload['data'])}
        if endpoint == 'entities/query':
            rows = self.rows[payload['offset']:payload['offset'] + payload['limit']]
            if self.corrupt and rows:
                rows = [dict(rows[0], payload='{}')] + rows[1:]
            return rows
        raise AssertionError(endpoint)


class CandidateCorpusTest(unittest.TestCase):
    def test_待审状态不会被写成已审核知识(self):
        pair = {'id': 'am_' + 'a' * 40, 'source': 'AutoMESC', 'project': 'https://example.test/p',
                'categoryHint': 'REENTRANCY', 'before': 'old code', 'after': 'new code'}
        forge = {'id': 'forge_vfp_1', 'source': 'FORGE-Curated', 'project': 'audit.pdf',
                 'categoryHint': 'ACCESS_CONTROL', 'text': 'source'}
        rows = documents([pair], [forge])
        self.assertEqual(3, len(rows))
        self.assertEqual({'PENDING'}, {row['reviewStatus'] for row in rows})
        self.assertEqual({'UNVERIFIED', 'MISSING'}, {row['patchStatus'] for row in rows})
        self.assertEqual({'before', 'after', 'audit_source'}, {row['side'] for row in rows})

    def test_仅提取有原始源码的相关审计候选(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = {'vfp_id': 'vfp_00001', 'project_name': 'audit.pdf',
                    'findings': [{'title': 'Missing access control', 'description': 'Anyone can call.'}],
                    'affected_files': {'A.sol': 'contract A { function f() public {} }'}}
            bad = {'vfp_id': 'vfp_00002', 'project_name': 'other.pdf',
                   'findings': [{'title': 'Precision loss'}], 'affected_files': {'B.sol': 'contract B {}'}}
            (root / 'vfp_00001.json').write_text(json.dumps(good))
            (root / 'vfp_00002.json').write_text(json.dumps(bad))
            rows = select_forge(root)
            self.assertEqual(1, len(rows))
            self.assertEqual('PENDING', rows[0]['reviewStatus'])
            self.assertEqual('MISSING', rows[0]['patchStatus'])

    def test_写入后逐条读回且拒绝损坏(self):
        row = {'id': 'candidate1', 'text': 'contract A {}', 'reviewStatus': 'PENDING'}
        vectors = {'candidate1': [1.0] + [0.0] * 383}
        name = 'r1pending_' + 'a' * 32
        index = FakeIndex()
        upload_candidates(index, name, [row], vectors)
        upload_candidates(index, name, [row], vectors)
        self.assertEqual(1, len(index.rows))
        with self.assertRaises(ValueError):
            upload_candidates(FakeIndex(corrupt=True), name, [row], vectors)
        with self.assertRaises(ValueError):
            upload_candidates(FakeIndex(), 's1b_' + 'a' * 32, [row], vectors)


if __name__ == '__main__':
    unittest.main()
