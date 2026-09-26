"""首批真实候选的固定源码与分组门禁离线回归。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from first_batch import prepare


class FirstBatchTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / 'sources'
        source.mkdir()
        self.cases = []
        for identifier, project, body in (
                ('AC-1', 'project-a', 'contract A { function a() external { require(msg.sender == owner); } }'),
                ('RE-1', 'project-b', 'contract B { function b() external { balance = 0; msg.sender.call(""); } }'),
                ('AC-2', 'project-c', 'contract C { function c() external { owner = msg.sender; } }')):
            raw = body.encode()
            (source / (identifier + '.sol')).write_bytes(raw)
            self.cases.append({'id': identifier, 'direction': '重入' if identifier.startswith('RE') else '访问控制',
                               'projectId': project, 'eventId': identifier + '-event',
                               'sourceUrl': 'https://github.com/example/repo/blob/' + 'a' * 40 + '/' + identifier + '.sol',
                               'sourceSha256': hashlib.sha256(raw).hexdigest()})
        self.intake = {'schemaVersion': '1', 'cases': self.cases}
        self.assignment = {'schemaVersion': '1', 'assignments': [
            {'id': 'AC-1', 'split': 'knowledge', 'reason': '知识候选'},
            {'id': 'RE-1', 'split': 'development', 'reason': '检测目标'},
            {'id': 'AC-2', 'split': 'excluded', 'reason': '待排除'}]}

    def test_fixed_bytes_and_excluded_are_reported_without_admitting_labels(self):
        ledger, report = prepare(self.intake, self.assignment, self.root, 'sources')
        self.assertTrue(report['ok'])
        self.assertEqual(report['splitCounts']['knowledge'], 1)
        self.assertEqual(report['splitCounts']['development'], 1)
        self.assertEqual(report['excluded'], ['AC-2'])
        self.assertEqual(report['pendingSamples'], ['AC-1', 'RE-1'])
        self.assertFalse(report['readyForFormalSnapshot'])
        self.assertTrue(all(row['labelStatus'] == 'PENDING' for row in ledger['samples']))

    def test_source_drift_and_missing_assignment_fail(self):
        (self.root / 'sources/AC-1.sol').write_text('篡改')
        with self.assertRaisesRegex(ValueError, '源码摘要'):
            prepare(self.intake, self.assignment, self.root, 'sources')
        (self.root / 'sources/AC-1.sol').write_bytes(
            b'contract A { function a() external { require(msg.sender == owner); } }')
        self.assignment['assignments'].pop()
        with self.assertRaisesRegex(ValueError, '分配'):
            prepare(self.intake, self.assignment, self.root, 'sources')

    def test_same_project_across_splits_is_rejected(self):
        self.cases[1]['projectId'] = 'project-a'
        _, report = prepare(self.intake, self.assignment, self.root, 'sources')
        self.assertFalse(report['ok'])
        self.assertTrue(any(error['kind'] == 'PROJECT' for error in report['errors']))

    def test_report_and_patch_must_match_bytes_and_inherit_event_group(self):
        (self.root / 'reports').mkdir()
        (self.root / 'patches').mkdir()
        report = b'original finding'
        patch = b'contract A { function a() external { require(msg.sender == owner); } }'
        (self.root / 'reports/AC-1.md').write_bytes(report)
        (self.root / 'patches/AC-1.sol').write_bytes(patch)
        row = self.assignment['assignments'][0]
        row['reportEvidence'] = {'url': 'https://example.test/report', 'path': 'reports/AC-1.md',
                                 'sha256': hashlib.sha256(report).hexdigest()}
        row['patchEvidence'] = {'url': 'https://example.test/patch', 'path': 'patches/AC-1.sol',
                                'sha256': hashlib.sha256(patch).hexdigest()}
        ledger, result = prepare(self.intake, self.assignment, self.root, 'sources')
        self.assertTrue(result['ok'])
        self.assertEqual([item['kind'] for item in ledger['samples'][0]['artifacts']], ['SOURCE', 'REPORT', 'PATCH'])
        self.assertEqual({item['groupId'] for item in ledger['samples'][0]['artifacts']}, {'AC-1-event'})
        self.assertEqual(ledger['sources'][0]['patchStatus'], 'VERIFIED')
        self.assertIn('AC-1', result['pendingSamples'])
        (self.root / 'patches/AC-1.sol').write_text('已改变')
        with self.assertRaisesRegex(ValueError, '原件摘要'):
            prepare(self.intake, self.assignment, self.root, 'sources')

    def test_near_clone_across_splits_is_rejected(self):
        original = ('contract Alpha { uint balance; function withdraw() external { '
                    'require(balance > 0); balance -= 1; msg.sender.call(""); } }')
        clone = ('contract Beta { uint amount; function take() external { '
                 'require(amount > 0); amount -= 1; msg.sender.call(""); } }')
        for identifier, body, case in [('AC-1', original, self.cases[0]), ('RE-1', clone, self.cases[1])]:
            raw = body.encode()
            (self.root / 'sources' / (identifier + '.sol')).write_bytes(raw)
            case['sourceSha256'] = hashlib.sha256(raw).hexdigest()
        _, report = prepare(self.intake, self.assignment, self.root, 'sources')
        self.assertFalse(report['ok'])
        self.assertTrue(any(error['kind'] == 'NEAR_CLONE_CANDIDATE' for error in report['errors']))


if __name__ == '__main__':
    unittest.main()
