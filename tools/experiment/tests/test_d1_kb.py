"""正式 D1 知识快照准入与成对文档的离线测试。"""
import hashlib
import io
import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from d1_kb import stage_snapshot
from d1_embed import candidate_vectors, load_encoder, verify_model_dir
from d1_admission import admit_candidates
from d1_model import MIRROR, fetch_model
from d1_embed import MODEL, REVISION, DIMENSION
from snapshots import verify_snapshot
from storage import fingerprint


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
                       'stateWitness': 'off = true', 'callWitness': 'transfer()',
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
        self.assertEqual('reviewed-function-pair-v1:' + fingerprint(result['catalog']['cases']),
                         payload['chunking']['version'])
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

    def test_existing_catalog_tamper_is_not_silently_overwritten(self):
        result = self.stage()
        Path(result['catalogPath']).write_text('{"tampered":true}')
        with self.assertRaisesRegex(ValueError, '元数据'):
            self.stage()

    def test_pending_pair_can_prepare_real_model_vectors_without_formal_activation(self):
        self.ledger['samples'][0]['labelStatus'] = 'PENDING'
        self.pairs[0]['reviewed'] = False
        calls = []
        def encode(texts):
            calls.extend(texts)
            return [[float(i + 1), 1.0] for i, _ in enumerate(texts)]
        output = candidate_vectors(self.ledger, self.root, self.pairs, encode, 'fixed-revision', 2)
        self.assertEqual({'case-original', 'case-patch'}, set(output['vectors']))
        self.assertEqual(2, len(calls))
        self.assertFalse((self.root / 'snapshots' / 'active.json').exists())

    def test_candidate_vectors_reject_missing_patch(self):
        self.ledger['sources'][0]['patchStatus'] = 'PENDING'
        with self.assertRaisesRegex(ValueError, '补丁'):
            candidate_vectors(self.ledger, self.root, self.pairs, lambda texts: [[1.0, 0.0]] * len(texts),
                              'fixed-revision', 2)

    def test_encoder_float_scalars_are_serialized_as_finite_vectors(self):
        output = candidate_vectors(self.ledger, self.root, self.pairs,
                                   lambda texts: [[Decimal('0.5'), Decimal('0.5')] for _ in texts],
                                   'fixed-revision', 2)
        self.assertEqual([0.5, 0.5], output['vectors']['case-original'])

    def test_model_download_failure_has_clear_message(self):
        def unavailable(*args, **kwargs):
            raise OSError('TLS 连接失败')
        with self.assertRaisesRegex(ValueError, '固定模型权重无法读取'):
            load_encoder(unavailable, self.root / 'model')

    def test_local_model_files_require_exact_hashes(self):
        path = self.root / 'model'
        path.mkdir()
        (path / 'model.safetensors').write_bytes(b'fixed weights')
        expected = {'model.safetensors': hashlib.sha256(b'fixed weights').hexdigest()}
        verify_model_dir(path, expected)
        (path / 'model.safetensors').write_bytes(b'changed weights')
        with self.assertRaisesRegex(ValueError, '摘要'):
            verify_model_dir(path, expected)

    def test_model_mirror_download_is_hash_checked_and_idempotent(self):
        raw = b'fixed weights'
        manifest = {'modelId': MODEL, 'revision': REVISION, 'dimension': DIMENSION, 'mirror': MIRROR,
                    'files': {'model.safetensors': hashlib.sha256(raw).hexdigest()}}
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            return io.BytesIO(raw)
        root = self.root / 'model'
        fetch_model(root, manifest, opener)
        fetch_model(root, manifest, opener)
        self.assertEqual(1, len(calls))
        (root / 'model.safetensors').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, '禁止覆盖'):
            fetch_model(root, manifest, opener)

    def test_access_control_pair_must_show_guard_added_by_patch(self):
        self.original = 'contract A {\nfunction run() public { write(); }\n}\n'
        self.patched = 'contract A {\nfunction run() public onlyOwner { write(); }\n}\n'
        (self.root / 'source.sol').write_text(self.original)
        (self.root / 'patch.sol').write_text(self.patched)
        self.ledger['samples'][0]['sourceHash'] = digest(self.original)
        self.ledger['samples'][0]['vulnerabilityType'] = 'ACCESS_CONTROL'
        self.ledger['samples'][0]['artifacts'][0]['sha256'] = digest(self.original)
        self.ledger['samples'][0]['artifacts'][2]['sha256'] = digest(self.patched)
        self.pairs[0].update(function='run', mechanism='ACCESS_CONTROL', riskKind='CALL',
                             predicate='CHECK_BEFORE', resource='$authority', guardWitness='onlyOwner')
        self.stage()
        self.patched = 'contract A {\nfunction run() public { writeFixed(); }\n}\n'
        (self.root / 'patch.sol').write_text(self.patched)
        self.ledger['samples'][0]['artifacts'][2]['sha256'] = digest(self.patched)
        with self.assertRaisesRegex(ValueError, '防护见证'):
            self.stage()

    def test_reentrancy_pair_must_reverse_call_and_state_order(self):
        self.stage()
        (self.root / 'patch.sol').write_text(self.original)
        self.ledger['samples'][0]['artifacts'][2]['sha256'] = digest(self.original)
        with self.assertRaisesRegex(ValueError, '顺序见证'):
            self.stage()

    def test_vector_bundle_must_match_exact_document_texts(self):
        texts = {'case-original': self.original.strip().splitlines()[1],
                 'case-patch': self.patched.strip().splitlines()[1]}
        bundle = {'candidateOnly': True, 'lineageHash': fingerprint(self.ledger), 'textsHash': fingerprint(texts),
                  'embedding': self.embedding, 'vectors': self.vectors}
        stage_snapshot(self.ledger, self.root, self.pairs, self.vectors, self.embedding,
                       self.root / 'snapshots', vector_bundle=bundle)
        bundle['textsHash'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '正文摘要'):
            stage_snapshot(self.ledger, self.root, self.pairs, self.vectors, self.embedding,
                           self.root / 'snapshots', vector_bundle=bundle)
        bundle['textsHash'] = fingerprint(texts)
        bundle['lineageHash'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '正文摘要'):
            stage_snapshot(self.ledger, self.root, self.pairs, self.vectors, self.embedding,
                           self.root / 'snapshots', vector_bundle=bundle)

    def test_admission_requires_pinned_external_report_and_license(self):
        (self.root / 'license.txt').write_text('MIT License\n')
        self.ledger['sources'][0]['licenseStatus'] = 'PENDING'
        self.ledger['samples'][0]['labelStatus'] = 'PENDING'
        decision = {'schemaVersion': '1', 'candidateLedgerHash': fingerprint(self.ledger),
                    'admissions': [{'sampleId': 'case', 'sourceHash': digest(self.original),
                                    'split': 'knowledge', 'vulnerabilityType': 'REENTRANCY',
                                    'vulnerabilityLine': 2, 'reviewerType': 'INDEPENDENT',
                                    'reviewer': '外部审计报告', 'reviewVersion': digest((self.root / 'report.md').read_text()),
                                    'licenseEvidence': {'path': 'license.txt', 'sha256': digest('MIT License\n'),
                                                        'license': 'MIT'}, 'pair': dict(self.pairs[0])}]}
        admitted, pairs, report = admit_candidates(self.ledger, decision, self.root)
        self.assertEqual([], report['pendingSamples'])
        self.assertEqual('REVIEWED', admitted['samples'][0]['labelStatus'])
        self.assertEqual('case', pairs[0]['sampleId'])
        decision['admissions'][0]['reviewVersion'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '外部审计'):
            admit_candidates(self.ledger, decision, self.root)

    def test_admission_accepts_exact_gpl_source_declaration(self):
        original = '// SPDX-License-Identifier: GPL-3.0\n' + self.original
        (self.root / 'source.sol').write_text(original)
        self.ledger['samples'][0].update(sourceHash=digest(original), labelStatus='PENDING', split='validation')
        self.ledger['samples'][0]['artifacts'][0]['sha256'] = digest(original)
        self.ledger['sources'][0]['licenseStatus'] = 'PENDING'
        decision = {'schemaVersion': '1', 'candidateLedgerHash': fingerprint(self.ledger),
                    'admissions': [{'sampleId': 'case', 'sourceHash': digest(original),
                                    'split': 'validation', 'vulnerabilityType': 'REENTRANCY',
                                    'vulnerabilityLine': 3, 'reviewerType': 'INDEPENDENT',
                                    'reviewer': '外部原始审计', 'reviewVersion': digest((self.root / 'report.md').read_text()),
                                    'licenseEvidence': {'path': 'source.sol', 'sha256': digest(original),
                                                        'license': 'GPL-3.0'}}]}
        admitted, pairs, report = admit_candidates(self.ledger, decision, self.root)
        self.assertEqual('GPL-3.0', admitted['sources'][0]['license'])
        self.assertEqual([], pairs)
        self.assertEqual([], report['pendingSamples'])
        decision['admissions'][0]['licenseEvidence']['license'] = 'MIT'
        with self.assertRaisesRegex(ValueError, '许可证'):
            admit_candidates(self.ledger, decision, self.root)

    def test_merge_admitted_rejects_same_project_across_knowledge_and_validation(self):
        from d1_admission import merge_admitted
        extension = copy.deepcopy(self.ledger)
        extension['sources'][0]['id'] = 'other-source'
        extension['samples'][0].update(id='other', sourceId='other-source', split='validation')
        extension['samples'][0]['artifacts'] = [dict(row, id='other-' + row['id'])
                                               for row in extension['samples'][0]['artifacts']]
        with self.assertRaisesRegex(ValueError, '谱系'):
            merge_admitted(self.ledger, self.pairs, extension, [], self.root)
