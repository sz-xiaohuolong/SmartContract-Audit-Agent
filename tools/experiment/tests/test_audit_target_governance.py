"""粘贴与旧预置输入的原件、发现任务和候选核验隔离。"""
import copy
import hashlib
import unittest

from audit_target import pasted_target, normalize_target, hypothesis_matches_target


SOURCE = ('// <yes> <report> ACCESS_CONTROL https://example.test/answer\n'
          'contract Vault {\n uint balance;\n'
          ' string label = "<yes> /* report */ https://example.test/answer";\n'
          ' function withdraw() public {\n balance = 1; // @vulnerable_at_lines 6\n }\n}')


class AuditTargetGovernanceTest(unittest.TestCase):
    def test_粘贴默认发现只消费清理源码并保留原件(self):
        target = pasted_target(SOURCE, 'ACCESS_CONTROL')
        self.assertNotIn('<yes>', target['fullSource'].splitlines()[0])
        self.assertEqual(SOURCE, target['originalSource'])
        self.assertEqual('DISCOVERY', target['taskKind'])
        self.assertEqual([], target['vulnerableLines'])
        self.assertEqual(SOURCE.splitlines()[3], target['fullSource'].splitlines()[3])
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(), target['originalSourceHash'])
        self.assertEqual(hashlib.sha256(target['fullSource'].encode()).hexdigest(), target['fullSourceHash'])
        self.assertEqual(target['fullSourceHash'], target['syntax']['sourceHash'])

    def test_显式风险行是候选位置而非评分真值(self):
        target = pasted_target(SOURCE, 'ACCESS_CONTROL', risk_line=6)
        self.assertEqual([], target['vulnerableLines'])
        self.assertEqual(6, target['riskLine'])
        self.assertEqual('CLAIM_VALIDATION', target['taskKind'])
        self.assertEqual(('FUNCTION', 5, 7), (target['scope'], target['lineStart'], target['lineEnd']))
        self.assertEqual(target['modelSourceHash'], target['inputGovernanceReceipt']['modelSourceHash'])
        self.assertNotIn('@vulnerable_at_lines', target['modelSource'])
        hypothesis = {'vulnerabilityType': 'ACCESS_CONTROL', 'contract': 'Vault',
                      'function': 'withdraw', 'riskLine': 6}
        self.assertTrue(hypothesis_matches_target(hypothesis, target, target['fullSource']))

    def test_只指定函数仍是发现任务并同步范围回执(self):
        target = pasted_target(SOURCE, 'ACCESS_CONTROL', 'withdraw')
        self.assertNotIn('@vulnerable_at_lines', target['modelSource'])
        self.assertEqual('DISCOVERY', target['taskKind'])
        self.assertIsNone(target['riskLine'])
        receipt = target['inputGovernanceReceipt']
        self.assertEqual(('FUNCTION', 5, 7), (receipt['scope'], receipt['lineStart'], receipt['lineEnd']))
        self.assertEqual(target['modelSourceHash'], receipt['modelSourceHash'])

    def test_旧预置真值行不转换成发现候选位置(self):
        digest = hashlib.sha256(SOURCE.encode()).hexdigest()
        target = {'sampleId': 'old', 'fullSource': SOURCE, 'modelSource': SOURCE,
                  'fullSourceHash': digest, 'modelSourceHash': digest, 'scope': 'FULL',
                  'lineStart': 1, 'lineEnd': 8, 'function': 'withdraw', 'mechanism': 'ACCESS_CONTROL',
                  'vulnerableLines': [6], 'groundTruth': {'hasVulnerability': True}, 'runnable': True}
        before = copy.deepcopy(target)
        normalized = normalize_target(target)
        self.assertNotIn('@vulnerable_at_lines', normalized['modelSource'])
        self.assertEqual('DISCOVERY', normalized['taskKind'])
        self.assertIsNone(normalized.get('riskLine'))
        self.assertEqual([6], normalized['vulnerableLines'])
        self.assertEqual(SOURCE, normalized['originalSource'])
        self.assertEqual(before, target)
        self.assertEqual(normalized, normalize_target(normalized))

    def test_预置模型片段错绑在清理前就拒绝(self):
        target = pasted_target(SOURCE, 'ACCESS_CONTROL', 'withdraw')
        target['modelSource'] = 'balance = 2;'
        target['modelSourceHash'] = hashlib.sha256(target['modelSource'].encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, '范围'):
            normalize_target(target)

    def test_预置全文范围不能伪装为局部行范围(self):
        target = pasted_target(SOURCE, 'ACCESS_CONTROL')
        target.update(lineStart=5, lineEnd=7)
        with self.assertRaisesRegex(ValueError, '范围'):
            normalize_target(target)


if __name__ == '__main__':
    unittest.main()
