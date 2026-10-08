"""待审候选逐项准入清单的确定性测试。"""
import unittest

from candidate_admission_queue import build_queue


class CandidateAdmissionQueueTest(unittest.TestCase):
    def test_没有独立证据不能批量转正(self):
        automesc = [{'id': 'am_1', 'source': 'AutoMESC', 'project': 'https://github.com/a/b',
                     'commit': 'a' * 40, 'commitUrl': 'https://github.com/a/b/commit/' + 'a' * 40,
                     'file': 'A.sol', 'categoryHint': 'REENTRANCY', 'sourceRevision': 'r',
                     'reviewStatus': 'PENDING', 'patchStatus': 'UNVERIFIED',
                     'before': 'old', 'after': 'new'}]
        forge = [{'id': 'forge_vfp_1', 'source': 'FORGE-Curated', 'project': 'audit.pdf',
                  'reportFile': 'vfp_1.json', 'rawHash': 'b' * 64, 'categoryHint': 'ACCESS_CONTROL',
                  'sourceRevision': 'r', 'reviewStatus': 'PENDING', 'patchStatus': 'MISSING',
                  'text': 'report and code', 'findingCount': 1}]
        report = build_queue(automesc, forge)
        self.assertEqual({'candidateGroups': 2, 'admittedGroups': 0, 'pendingGroups': 2,
                          'candidateVectors': 3, 'admittedVectors': 0}, report['summary'])
        self.assertEqual(['INDEPENDENT_REPORT', 'FULL_SOURCE_BEFORE', 'FULL_SOURCE_AFTER',
                          'SECURITY_PATCH_REVIEW', 'LINEAGE_GROUP', 'CONDITION_WITNESS'],
                         report['entries'][0]['missingEvidence'])
        self.assertIn('PATCH', report['entries'][1]['missingEvidence'])
        self.assertNotIn('before', report['entries'][0])
        self.assertEqual('PENDING', report['entries'][0]['decision'])

    def test_篡改和重复记录拒绝生成清单(self):
        pair = {'id': 'am_1', 'source': 'AutoMESC', 'project': 'p', 'commit': 'c',
                'commitUrl': 'u', 'file': 'A.sol', 'categoryHint': 'REENTRANCY',
                'sourceRevision': 'r', 'reviewStatus': 'PENDING', 'patchStatus': 'UNVERIFIED',
                'before': 'old', 'after': 'new'}
        with self.assertRaises(ValueError):
            build_queue([pair, pair], [])
        with self.assertRaises(ValueError):
            build_queue([{**pair, 'reviewStatus': 'REVIEWED'}], [])


if __name__ == '__main__':
    unittest.main()
