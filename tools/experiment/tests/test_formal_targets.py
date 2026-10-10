"""正式知识快照外的开发目标准入与函数范围离线测试。"""
import hashlib
import copy
import tempfile
import unittest
from pathlib import Path

from storage import atomic_json
from storage import decode
from formal_targets import list_targets, load_target


class FormalTargetsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'data/audit/r1/first-batch').mkdir(parents=True)
        (self.root / '.local/first-batch/sources').mkdir(parents=True)
        (self.root / '.local/d1-kb-v1').mkdir(parents=True)
        self.sources = {
            'AC-ASE-006': 'contract Basin { function upgrade() external { require(msg.sender == owner); } }',
            'AC-ASE-009': 'contract Gondi { function distribute() external { uint owed = 3; if (owed > 0) { owner = msg.sender; } } }',
            'RE-SCRUBD-001': ('\n' * 604 + 'contract Dex {\nfunction matchOrderWithReserve() internal {\nuint beforeCall = 1;\nmsg.sender.call("");\n}\n}').replace('\n', '\r\n'),
            'RE-SCRUBD-002': 'contract Monkey { /* ' + ('长' * 12000) + ' */ function determinePID() external { uint v = 1; } }',
        }
        self.cases = []
        self.assignments = []
        for identifier, source in self.sources.items():
            raw = source.encode()
            (self.root / '.local/first-batch/sources' / (identifier + '.sol')).write_bytes(raw)
            self.cases.append({'id': identifier, 'direction': '重入' if identifier.startswith('RE') else '访问控制',
                               'projectId': identifier, 'eventId': identifier + '-event',
                               'function': 'matchOrderWithReserve' if identifier == 'RE-SCRUBD-001' else 'target',
                               'sourceUrl': 'https://github.com/example/repo/blob/' + 'a' * 40 + '/' + identifier + '.sol',
                               'sourceSha256': hashlib.sha256(raw).hexdigest()})
            self.assignments.append({'id': identifier, 'split': 'development', 'reason': '工程测试'})
        self.intake_path = self.root / 'data/audit/r1/first-batch/first-batch-intake.json'
        self.assignment_path = self.root / 'data/audit/r1/first-batch/first-batch-assignment.json'
        atomic_json(self.intake_path, {'schemaVersion': '1', 'cases': self.cases})
        atomic_json(self.assignment_path, {'schemaVersion': '1', 'assignments': self.assignments})
        knowledge_path = self.root / '.local/first-batch/sources/KNOWLEDGE.sol'
        knowledge = b'contract Knowledge { mapping(address => uint) balances; function withdraw() external { balances[msg.sender] = 0; msg.sender.call(""); } }'
        knowledge_path.write_bytes(knowledge)
        digest = hashlib.sha256(knowledge).hexdigest()
        atomic_json(self.root / '.local/d1-kb-v1/ledger.json', {
            'schemaVersion': '1', 'sources': [{'id': 'KNOWLEDGE', 'url': 'https://example.test/knowledge',
                'revision': 'a' * 40, 'licenseStatus': 'PENDING', 'license': None,
                'sourceStatus': 'VERIFIED', 'reportStatus': 'PENDING', 'patchStatus': 'PENDING'}],
            'samples': [{'id': 'KNOWLEDGE', 'sourceId': 'KNOWLEDGE',
                'path': '.local/first-batch/sources/KNOWLEDGE.sol', 'sourceHash': digest,
                'split': 'knowledge', 'projectId': 'knowledge-project', 'eventId': 'knowledge-event',
                'patchPairId': 'knowledge-event', 'cloneGroups': [], 'originType': 'REAL_UNPAIRED',
                'labelStatus': 'PENDING', 'artifacts': [{'id': 'knowledge-source', 'kind': 'SOURCE',
                    'path': '.local/first-batch/sources/KNOWLEDGE.sol', 'sha256': digest,
                    'groupId': 'knowledge-event'}]}], 'edges': []})

    def test_four_registered_targets_and_scope(self):
        rows = {row['sampleId']: row for row in list_targets(self.root)}
        self.assertEqual(set(rows), set(self.sources))
        self.assertEqual(rows['AC-ASE-006']['scope'], 'FULL')
        self.assertEqual(rows['AC-ASE-009']['scope'], 'FULL')
        self.assertEqual(rows['RE-SCRUBD-001']['scope'], 'FUNCTION')
        self.assertTrue(rows['RE-SCRUBD-001']['runnable'])
        self.assertFalse(rows['RE-SCRUBD-002']['runnable'])
        selected = load_target(self.root, 'RE-SCRUBD-001')
        self.assertEqual(selected['lineStart'], 606)
        self.assertEqual(selected['lineEnd'], 609)
        self.assertIn('msg.sender.call', selected['modelSource'])
        self.assertEqual(selected['fullSourceHash'], self.cases[2]['sourceSha256'])
        self.assertEqual(hashlib.sha256(selected['fullSource'].encode()).hexdigest(), selected['fullSourceHash'])
        self.assertIn('\r\n', selected['fullSource'])
        self.assertEqual(selected['modelSourceHash'], hashlib.sha256(selected['modelSource'].encode()).hexdigest())
        self.assertFalse(selected['researchEligible'])

    def test_source_hash_and_group_mismatch_fail_closed(self):
        path = self.root / '.local/first-batch/sources/AC-ASE-006.sol'
        path.write_text('篡改')
        with self.assertRaisesRegex(ValueError, '摘要'):
            load_target(self.root, 'AC-ASE-006')
        path.write_text(self.sources['AC-ASE-006'])
        self.cases[0]['projectId'] = 'knowledge-project'
        atomic_json(self.intake_path, {'schemaVersion': '1', 'cases': self.cases})
        with self.assertRaisesRegex(ValueError, '隔离|同组'):
            load_target(self.root, 'AC-ASE-006')
        with self.assertRaisesRegex(ValueError, '未登记'):
            load_target(self.root, 'NOT-LISTED')

    def test_validation_function_is_registered_without_entering_knowledge(self):
        source = 'contract Vault { function mintYieldFee() external { balance = 1; } uint balance; }'
        path = self.root / '.local/first-batch/sources/AC-ASE-040.sol'
        path.write_text(source)
        digest = hashlib.sha256(source.encode()).hexdigest()
        ledger = copy.deepcopy(decode((self.root / '.local/d1-kb-v1/ledger.json').read_bytes()))
        ledger['sources'].append({'id': 'AC-ASE-040', 'url': 'https://example.test/validation',
            'revision': 'b'*40, 'licenseStatus': 'VERIFIED', 'license': 'MIT',
            'sourceStatus': 'VERIFIED', 'reportStatus': 'VERIFIED', 'patchStatus': 'VERIFIED'})
        ledger['samples'].append({'id': 'AC-ASE-040', 'sourceId': 'AC-ASE-040',
            'path': '.local/first-batch/sources/AC-ASE-040.sol', 'sourceHash': digest,
            'split': 'validation', 'projectId': 'independent-vault', 'eventId': 'vault-fee',
            'patchPairId': 'vault-fee', 'cloneGroups': [], 'originType': 'REAL_PATCH',
            'labelStatus': 'REVIEWED', 'vulnerabilityType': 'ACCESS_CONTROL',
            'artifacts': [{'id': 'vault-source', 'kind': 'SOURCE',
                'path': '.local/first-batch/sources/AC-ASE-040.sol', 'sha256': digest,
                'groupId': 'vault-fee'}]})
        target = self.root / '.local/r1-s5/formal-v2/ledger.json'
        target.parent.mkdir(parents=True)
        atomic_json(target, ledger)
        selected = load_target(self.root, 'AC-ASE-040')
        self.assertEqual('validation', selected['split'])
        self.assertEqual('FUNCTION', selected['scope'])
        self.assertEqual('mintYieldFee', selected['function'])
        self.assertFalse(selected['researchEligible'])

    def test_new_validation_target_uses_reviewed_function_name(self):
        source = 'contract MoreVault { function auditEntry() external { balance = 1; } uint balance; }'
        path = self.root / '.local/first-batch/sources/AC-NEW-001.sol'
        path.write_text(source)
        digest = hashlib.sha256(source.encode()).hexdigest()
        ledger = copy.deepcopy(decode((self.root / '.local/d1-kb-v1/ledger.json').read_bytes()))
        ledger['sources'].append({'id': 'AC-NEW-001', 'url': 'https://example.test/new',
            'revision': 'c'*40, 'licenseStatus': 'VERIFIED', 'license': 'MIT',
            'sourceStatus': 'VERIFIED', 'reportStatus': 'VERIFIED', 'patchStatus': 'VERIFIED'})
        ledger['samples'].append({'id': 'AC-NEW-001', 'sourceId': 'AC-NEW-001',
            'path': '.local/first-batch/sources/AC-NEW-001.sol', 'sourceHash': digest,
            'split': 'validation', 'projectId': 'more-vault', 'eventId': 'more-vault-event',
            'patchPairId': 'more-vault-event', 'cloneGroups': [], 'originType': 'REAL_PATCH',
            'labelStatus': 'REVIEWED', 'vulnerabilityType': 'ACCESS_CONTROL',
            'evaluationFunction': 'auditEntry',
            'artifacts': [{'id': 'new-source', 'kind': 'SOURCE',
                'path': '.local/first-batch/sources/AC-NEW-001.sol', 'sha256': digest,
                'groupId': 'more-vault-event'}]})
        target = self.root / '.local/r1-s5/formal-v2/ledger.json'
        target.parent.mkdir(parents=True)
        atomic_json(target, ledger)
        selected = load_target(self.root, 'AC-NEW-001')
        self.assertEqual('auditEntry', selected['function'])
        self.assertEqual('FUNCTION', selected['scope'])


if __name__ == '__main__':
    unittest.main()
