"""候选身份与审核准备只读导出，不把缺失、错误或来源标签写成安全证明。"""
import copy
import csv
import gzip
import io
import tempfile
import unittest
from pathlib import Path

from verirag.infrastructure.storage import encode, fingerprint, read_artifact
from verirag.evaluation.research_review import (review_batch, resolve_candidate, write_review,
                             inventory_sources, split_audit, sha, benchmark_provenance)


class ResearchReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = 'contract C { function f() public {} }\n'
        self.hypothesis = {'contract': 'C', 'function': 'f', 'riskLine': 1,
                           'riskOperation': 'CALL', 'vulnerabilityType': 'REENTRANCY',
                           'reason': '需要独立审核的原始理由', 'evidenceIds': []}

    def batch(self, batch_id='a' * 32, hypotheses=None, assessment=True):
        directory = self.root / 'research-artifacts/runs/benchmarks' / batch_id
        directory.mkdir(parents=True)
        plan = {'sampleIds': ['x', 'safe'], 'strategies': ['D1'],
                'sourceHashes': {key: sha(self.source.encode()) for key in ['x', 'safe']},
                'snapshotId': 'f' * 64, 'labels': {
                    'x': {'hasVulnerability': True, 'labelSource': '来源类别'},
                    'safe': {'hasVulnerability': False, 'labelSource': '来源对照'}},
                'researchEligible': False}
        plan['planHash'] = fingerprint(plan)
        events = [{'kind': 'PLAN', 'planHash': plan['planHash']}] + [
            {'kind': 'STARTED', 'sampleId': key, 'strategy': 'D1'} for key in ['x', 'safe']]
        rows = []
        for key in ['x', 'safe']:
            candidates = (hypotheses if hypotheses is not None else [self.hypothesis]) if key == 'x' else []
            rows.append({'sampleId': key, 'strategy': 'D1', 'source': self.source,
                         'sourceHash': plan['sourceHashes'][key], 'snapshotId': plan['snapshotId'],
                         'status': 'COMPLETED', 'pipelineStatus': 'COMPLETED',
                         'model': {'status': 'COMPLETED', 'hypotheses': candidates},
                         'prediction': 'REPORT' if candidates else 'NO_REPORT',
                         'inputTokens': 20, 'outputTokens': None, 'requestAttempts': 1,
                         'd2': {'assessments': [
                             {'hypothesisIndex': index, 'verdict': 'UNKNOWN',
                              'candidateProof': {'proofScope': {'gaps': ['初态未核验']}}}
                             for index in range(len(candidates))] if assessment else []}})
        for name, data in [('plan.json', encode(plan)), ('events.jsonl', b'\n'.join(map(encode, events))),
                           ('samples.jsonl', b'\n'.join(map(encode, rows))), ('summary.json', encode({'samples': rows}))]:
            (directory / (name + '.gz')).write_bytes(gzip.compress(data, mtime=0))
        return directory, rows

    def rewrite_rows(self, directory, rows):
        (directory / 'samples.jsonl.gz').write_bytes(gzip.compress(b'\n'.join(map(encode, rows)), mtime=0))

    def test_归档读取原件不变且候选可精确回读(self):
        directory, _ = self.batch()
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        report = review_batch(self.root, 'a' * 32)
        candidate = report['candidates'][0]
        self.assertEqual(self.hypothesis, resolve_candidate(self.root, candidate))
        self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})
        self.assertEqual(report['originalHashesBefore'], report['originalHashesAfter'])
        self.assertFalse(report['researchEligible'])
        self.assertNotIn('reason', candidate)
        self.assertEqual(1, report['reviewCandidateVerdicts']['UNKNOWN'])

    def test_重复候选仍有不同出现身份且双批次分母不混(self):
        self.batch(hypotheses=[self.hypothesis, copy.deepcopy(self.hypothesis)])
        self.batch('b' * 32)
        old, new = [review_batch(self.root, key * 32) for key in 'ab']
        self.assertEqual((2, 1), (old['counts']['candidates'], new['counts']['candidates']))
        ids = [row['candidateId'] for r in [old, new] for row in r['candidates']]
        self.assertEqual(3, len(set(ids)))
        self.assertEqual(old['candidates'][0]['candidateHash'], old['candidates'][1]['candidateHash'])

    def test_缺失核验或流水线失败保持未知不算安全(self):
        directory, rows = self.batch(assessment=False)
        report = review_batch(self.root, 'a' * 32)
        self.assertEqual('MISSING_ASSESSMENT', report['candidates'][0]['triageCode'])
        rows[0]['pipelineStatus'] = 'FAILED'
        rows[0]['compilationError'] = '编译器缺失'
        rows[0]['d2']['assessments'] = [{'hypothesisIndex': 0, 'verdict': 'REFUTED'}]
        self.rewrite_rows(directory, rows)
        report = review_batch(self.root, 'a' * 32)
        self.assertEqual('UNKNOWN', report['candidates'][0]['verdict'])
        self.assertEqual('REFUTED', report['candidates'][0]['savedVerdict'])
        self.assertEqual(0, report['reviewCandidateVerdicts']['REFUTED'])
        self.assertEqual(1, report['savedCandidateVerdicts']['REFUTED'])
        self.assertEqual(1, report['counts']['pipelineFailed'])

    def test_重复单元和重复核验均拒绝(self):
        directory, rows = self.batch()
        self.rewrite_rows(directory, rows + [rows[0]])
        with self.assertRaisesRegex(ValueError, '重复'):
            review_batch(self.root, 'a' * 32)
        rows[0]['d2']['assessments'] *= 2
        self.rewrite_rows(directory, rows)
        with self.assertRaisesRegex(ValueError, '重复'):
            review_batch(self.root, 'a' * 32)

    def test_源码或候选指针篡改拒绝(self):
        directory, rows = self.batch()
        report = review_batch(self.root, 'a' * 32)
        candidate = report['candidates'][0]
        candidate['candidateHash'] = '0' * 64
        with self.assertRaises(ValueError):
            resolve_candidate(self.root, candidate)
        rows[0]['source'] += '变更'
        self.rewrite_rows(directory, rows)
        with self.assertRaisesRegex(ValueError, '源码摘要'):
            review_batch(self.root, 'a' * 32)

    def test_缺失单元保留计划分母且usage缺失保留null(self):
        directory, rows = self.batch()
        self.rewrite_rows(directory, rows[:1])
        report = review_batch(self.root, 'a' * 32)
        self.assertEqual(2, report['counts']['plannedUnits'])
        self.assertEqual(1, report['counts']['missingUnits'])
        self.assertIsNone(report['usage']['inputTokens']['total'])
        self.assertEqual(20, report['usage']['inputTokens']['observedSubtotal'])
        self.assertIsNone(report['usage']['outputTokens']['total'])
        self.assertIsNone(report['usage']['cost'])

    def test_审核字段空白且CSV只按需生成且不可覆盖(self):
        self.batch()
        report = review_batch(self.root, 'a' * 32)
        output = self.root / 'derived'
        write_review(output, [report], {'events': [], 'controls': []})
        self.assertFalse(list(output.glob('*.csv')))
        self.assertTrue(all(value is None for value in report['candidates'][0]['independentReview'].values()))
        csv_output = self.root / 'csv'
        write_review(csv_output, [report], {'events': [], 'controls': []}, csv_export=True)
        records = list(csv.DictReader(io.StringIO((csv_output / 'candidate-review.csv').read_text())))
        self.assertEqual('', records[0]['reviewer1'])
        self.assertEqual('', records[0]['candidateTruth'])
        with self.assertRaisesRegex(ValueError, '覆盖'):
            write_review(csv_output, [report], {'events': [], 'controls': []})

    def test_跨划分项目和克隆冲突显式输出且不将未核分组当无泄漏(self):
        rows = [{'id': 'a', 'projectId': 'p', 'sourceHash': '1', 'cloneGroups': ['c'], 'split': 'knowledge'},
                {'id': 'b', 'projectId': 'p', 'sourceHash': '2', 'cloneGroups': ['c'], 'split': 'validation'},
                {'id': 'c', 'projectId': None, 'sourceHash': '3', 'cloneGroups': None, 'split': None}]
        audit = split_audit(rows)
        self.assertEqual({'project', 'clone'}, {r['kind'] for r in audit['conflicts']})
        self.assertEqual(['c'], audit['unresolvedIds'])
        self.assertFalse(audit['researchEligible'])

    def test_来源原件摘要冲突与真实补丁缺失不能获得研究准入(self):
        (self.root / 'source.sol').write_text(self.source)
        registry = {'events': [{'id': 'p', 'projectId': 'p', 'eventId': 'e', 'split': None,
                    'artifacts': [{'kind': 'SOURCE', 'path': 'source.sol', 'expectedSha256': '0' * 64},
                                  {'kind': 'PATCH', 'path': None, 'expectedSha256': None}]}],
                    'controls': []}
        result = inventory_sources(self.root, registry, {'samples': []})
        event = result['events'][0]
        self.assertEqual('HASH_MISMATCH', event['artifacts'][0]['status'])
        self.assertEqual('MISSING', event['artifacts'][1]['status'])
        self.assertFalse(event['researchEligible'])
        self.assertIsNone(event['independentReview']['candidateTruth'])

    def test_来源定位不以当前输入替换冻结输入且OZ保留同一上游(self):
        from verirag.experiments.exploratory_targets import _sample_id
        dataset = self.root / 'smartbugs-curated'
        (dataset / 'dataset/reentrancy').mkdir(parents=True)
        (dataset / 'dataset/reentrancy/C.sol').write_text(self.source)
        (dataset / 'vulnerabilities.json').write_bytes(encode([
            {'path': 'dataset/reentrancy/C.sol', 'source': 'https://github.com/o/r/blob/main/C.sol',
             'vulnerabilities': [{'category': 'reentrancy', 'lines': [1]}]}]))
        rows = [{'sampleId': _sample_id('reentrancy', 'dataset/reentrancy/C.sol'), 'sourceHash': '0' * 64},
                {'sampleId': 'safe_23_Ownable', 'sourceHash': '1' * 64},
                {'sampleId': 'safe_24_Ownable2Step', 'sourceHash': '2' * 64}]
        mapped = benchmark_provenance(self.root, rows)
        self.assertEqual('0' * 64, rows[0]['sourceHash'])
        self.assertEqual('PENDING_REVIEW', mapped[0]['lineageStatus'])
        self.assertEqual('https://github.com/o/r', mapped[0]['proposedProjectGroup'])
        self.assertEqual(mapped[1]['proposedProjectGroup'], mapped[2]['proposedProjectGroup'])
        self.assertFalse(mapped[0]['currentRawBytesMatchFrozen'])

    def test_CSV候选文本不执行公式(self):
        hypothesis = {**self.hypothesis, 'function': '=1+1'}
        self.batch(hypotheses=[hypothesis])
        output = self.root / 'spreadsheet'
        write_review(output, [review_batch(self.root, 'a' * 32)], {'events': [], 'controls': []}, True)
        rows = list(csv.DictReader(io.StringIO((output / 'candidate-review.csv').read_text())))
        self.assertEqual("'=1+1", rows[0]['function'])


if __name__ == '__main__':
    unittest.main()
