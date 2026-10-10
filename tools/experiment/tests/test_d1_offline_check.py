"""固定保存候选池离线检查，不发模型或嵌入请求。"""
import hashlib
import json
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from benchmark_batch import make_plan, run_batch
from snapshots import build_snapshot
from storage import atomic_json, fingerprint
from d1_offline_check import inspect_batch, pair_summary, run_check


class D1OfflineCheckTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = self.root / 'snapshots'
        self.source = '// <yes> <report> REENTRANCY\ncontract Target { function take() public { msg.sender.call(""); } }'
        source_hash = hashlib.sha256(self.source.encode()).hexdigest()
        sample_hash = hashlib.sha256(b'knowledge original').hexdigest()
        manifest = {'schema_version': '1', 'categories': ['REENTRANCY'], 'samples': [{
            'id': 'knowledge', 'path': 'knowledge.sol', 'source_hash': sample_hash,
            'exact_group': sample_hash, 'project_group': 'https://example.test/knowledge',
            'clone_groups': [], 'origin': 'fixture/knowledge', 'split': 'knowledge',
            'types': ['REENTRANCY'], 'review_status': 'AUTO_LABELED', 'evidence_tier': 'HEURISTIC',
            'label_rule': 'fixture'}]}
        documents, cases, candidates = [], {}, []
        for pair in ('explicit', 'soft'):
            for side, role in (('before', 'VULNERABLE'), ('after', 'DEFENSE')):
                identifier = pair + '_' + side
                text = pair + ('调用后写入状态' if side == 'before' else '调用前写入状态')
                conditions = [{'predicate': 'NON_REENTRANT', 'subject': '$actor', 'resource': '$resource',
                               'expected': side == 'after'}] if pair == 'explicit' else []
                metadata = {'caseId': identifier, 'pairId': pair, 'role': role, 'mechanism': 'REENTRANCY',
                            'riskKind': 'CALL', 'conditions': conditions, 'reviewed': False}
                cases[identifier] = metadata
                documents.append({'id': identifier, 'sample_id': 'knowledge', 'text': text})
                candidates.append({**metadata, 'chunkId': identifier, 'text': text,
                    'denseScore': .9, 'lexicalScore': .2,
                    'provenance': 'fixture/knowledge@' + sample_hash})
        self.snapshot = build_snapshot(self.store, manifest, documents,
            {'model': 'fixture', 'revision': 'r', 'dimension': 2}, {'version': 'fixture'},
            {row['id']: [1.0, 0.0] for row in documents})
        (self.store / 'catalogs').mkdir()
        atomic_json(self.store / 'catalogs' / (self.snapshot + '.json'),
                    {'snapshotId': self.snapshot, 'cases': cases})
        self.pool = {'schemaVersion': 'auto-1', 'snapshotId': self.snapshot,
                     'sourceHash': source_hash, 'candidates': candidates}
        target = {'sampleId': 'target', 'sourceHash': source_hash, 'runnable': True,
                  'groundTruth': {'hasVulnerability': True, 'labelSource': 'fixture'}}
        self.plan = make_plan(['target'], ['DENSE', 'FIELD_FILTER', 'D1'], 'real', [target], self.snapshot,
                              {'model': 'fixture', 'endpoint': 'https://example.test/unused'})
        self.batch_id = 'b' * 32
        self.batch_dir = self.root / 'history' / self.batch_id
        def saved_result(sample, strategy, mode):
            selected = (candidates[:2] if strategy == 'FIELD_FILTER' else
                        candidates[2:] if strategy == 'D1' else [candidates[0], candidates[2]])
            d1 = {'selected': [{'candidate': row, 'use': 'SOFT_SUPPORT' if index == 0 else 'SOFT_CONTRAST',
                               'binding': {'applicability': 'UNKNOWN'}}
                              for index, row in enumerate(selected)], 'context': '保存上下文',
                  'gaps': ['无唯一风险事实；软配对'] if strategy == 'D1' else [],
                  'evaluations': {row['chunkId']: {'applicability': 'UNKNOWN'} for row in candidates}}
            prediction = 'NO_REPORT' if strategy == 'FIELD_FILTER' else 'REPORT'
            return {'status': 'COMPLETED', 'prediction': prediction, 'modelPrediction': prediction,
                'model': {'status': 'COMPLETED', 'hypotheses': []}, 'source': self.source,
                'retrieval': {'pool': self.pool, 'd1': d1, 'snapshotId': self.snapshot,
                              'sourceHash': source_hash, 'targetMechanism': 'REENTRANCY'},
                'poolHash': fingerprint(self.pool), 'selectedIds': [row['chunkId'] for row in selected],
                'selectedEvidence': len(selected), 'retrievalGaps': d1['gaps'],
                'inputTokens': None if strategy == 'D1' else 10,
                'outputTokens': 2, 'd2': {'verdict': 'UNKNOWN'}}
        run_batch(self.root / 'history', self.plan, saved_result, self.batch_id)

    def saved_inputs(self):
        rows = [json.loads(line) for line in (self.batch_dir / 'samples.jsonl').read_text().splitlines()]
        catalog = json.loads((self.store / 'catalogs' / (self.snapshot + '.json')).read_text())
        return rows, catalog

    def test_保存批次离线检查重算同池配对和标签指标且保护原件(self):
        output = self.root / 'output'
        script = Path(__file__).resolve().parents[1] / 'd1_offline_check.py'
        original = (self.batch_dir / 'samples.jsonl').read_bytes()
        completed = subprocess.run([sys.executable, str(script), '--batch-dir', str(self.batch_dir),
            '--snapshot-root', str(self.store), '--output', str(output)], capture_output=True, text=True)
        self.assertEqual(0, completed.returncode, completed.stderr)
        check = json.loads((output / 'check.json').read_text())
        self.assertTrue(check['samePool']['passed'])
        self.assertEqual({'total': 2, 'explicitConditionPairs': 1, 'softPairs': 1, 'incompletePairs': 0},
                         check['catalogPairs']['counts'])
        self.assertEqual(1, check['metrics']['DENSE']['model']['tp'])
        self.assertEqual(1, check['metrics']['FIELD_FILTER']['model']['fn'])
        self.assertEqual(1, check['metrics']['D1']['retrieval']['selectedSoftCompletePairs'])
        self.assertIsNone(check['metrics']['D1']['usage']['inputTokens'])
        self.assertFalse(check['researchEligible'])
        self.assertEqual(0, check['newModelRequests'])
        self.assertEqual('HISTORICAL_INPUT_UNCONTROLLED', check['historicalInput']['status'])
        self.assertEqual(original, (self.batch_dir / 'samples.jsonl').read_bytes())
        self.assertTrue((output / 'REPORT.md').is_file())
        self.assertTrue((output / 'metrics.csv').is_file())

    def test_池摘要一致也不能接受与冻结登记不同的候选条件(self):
        rows, catalog = self.saved_inputs()
        for row in rows:
            row['retrieval']['pool']['candidates'][0]['conditions'][0]['expected'] = True
            for selected in row['retrieval']['d1']['selected']:
                if selected['candidate']['chunkId'] == 'explicit_before':
                    selected['candidate']['conditions'][0]['expected'] = True
            row['poolHash'] = fingerprint(row['retrieval']['pool'])
        check = inspect_batch(self.plan, rows, catalog)
        self.assertFalse(check['samePool']['passed'])
        self.assertIn('CATALOG_METADATA_MISMATCH', {row['kind'] for row in check['samePool']['issues']})

    def test_三策略相同的残缺配对仍要报告完整性失败(self):
        rows, catalog = self.saved_inputs()
        for row in rows:
            pool = row['retrieval']['pool']
            pool['candidates'] = [candidate for candidate in pool['candidates'] if candidate['chunkId'] != 'soft_after']
            row['retrieval']['d1']['selected'] = [item for item in row['retrieval']['d1']['selected']
                                                  if item['candidate']['chunkId'] != 'soft_after']
            row['selectedIds'] = [item['candidate']['chunkId'] for item in row['retrieval']['d1']['selected']]
            row['selectedEvidence'] = len(row['selectedIds'])
            row['poolHash'] = fingerprint(pool)
        check = inspect_batch(self.plan, rows, catalog)
        self.assertFalse(check['samePool']['passed'])
        self.assertIn('INCOMPLETE_POOL_PAIR', {row['kind'] for row in check['samePool']['issues']})

    def test_结果选中编号必须对应保存的实际候选(self):
        rows, catalog = self.saved_inputs()
        rows[0]['selectedIds'] = ['不存在的候选']
        check = inspect_batch(self.plan, rows, catalog)
        self.assertFalse(check['samePool']['passed'])
        self.assertIn('SELECTED_IDS_MISMATCH', {row['kind'] for row in check['samePool']['issues']})

    def test_三策略池摘要相同也必须绑定冻结文档文本(self):
        rows, _ = self.saved_inputs()
        for row in rows:
            row['retrieval']['pool']['candidates'][0]['text'] = '替换后的非快照文本'
            for selected in row['retrieval']['d1']['selected']:
                if selected['candidate']['chunkId'] == 'explicit_before':
                    selected['candidate']['text'] = '替换后的非快照文本'
            row['poolHash'] = fingerprint(row['retrieval']['pool'])
        (self.batch_dir / 'samples.jsonl').write_text(
            '\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')
        output = self.root / 'output'
        script = Path(__file__).resolve().parents[1] / 'd1_offline_check.py'
        completed = subprocess.run([sys.executable, str(script), '--batch-dir', str(self.batch_dir),
            '--snapshot-root', str(self.store), '--output', str(output)], capture_output=True, text=True)
        self.assertEqual(1, completed.returncode, completed.stderr)
        check = json.loads((output / 'check.json').read_text())
        self.assertIn('SNAPSHOT_TEXT_MISMATCH', {row['kind'] for row in check['samePool']['issues']})

    def test_登记必须精确覆盖冻结知识文档(self):
        _, catalog = self.saved_inputs()
        for role in ('VULNERABLE', 'DEFENSE'):
            identifier = '伪造_' + role
            catalog['cases'][identifier] = {**catalog['cases']['soft_before'],
                'caseId': identifier, 'pairId': '不存在的文档对', 'role': role}
        atomic_json(self.store / 'catalogs' / (self.snapshot + '.json'), catalog)
        with self.assertRaisesRegex(ValueError, '精确覆盖'):
            run_check(self.batch_dir, self.store, self.root / 'output')

    def test_每个策略都须核验实际源码摘要(self):
        rows, catalog = self.saved_inputs()
        rows[-1]['source'] += '\ncontract Another {}'
        with self.assertRaisesRegex(ValueError, '保存源码'):
            inspect_batch(self.plan, rows, catalog)

    def test_未知标签与缺失用量不能折算阴性和零token(self):
        rows, catalog = self.saved_inputs()
        plan = copy.deepcopy(self.plan)
        plan['labels']['target']['hasVulnerability'] = None
        plan['planHash'] = fingerprint({key: value for key, value in plan.items() if key != 'planHash'})
        check = inspect_batch(plan, rows, catalog)
        self.assertEqual(1, check['metrics']['FIELD_FILTER']['model']['labelUnknown'])
        self.assertEqual(0, check['metrics']['FIELD_FILTER']['model']['tn'])
        self.assertIsNone(check['metrics']['D1']['usage']['inputTokens'])
        self.assertIsNone(check['formalAdmission']['tokenizer'])
        self.assertFalse(check['formalAdmission']['passed'])

    def test_评分标签变化只改变历史评分不改变清理发现探针(self):
        rows, catalog = self.saved_inputs()
        first = inspect_batch(self.plan, rows, catalog)
        plan = copy.deepcopy(self.plan)
        plan['labels']['target']['hasVulnerability'] = False
        plan['planHash'] = fingerprint({key: value for key, value in plan.items() if key != 'planHash'})
        changed = inspect_batch(plan, rows, catalog)
        self.assertEqual(first['historicalInput'], changed['historicalInput'])
        self.assertEqual(1, changed['metrics']['DENSE']['model']['fp'])

    def test_清理前后摘要不能绕过知识来源隔离(self):
        rows, catalog = self.saved_inputs()
        check = run_check(self.batch_dir, self.store, self.root / 'output')
        self.assertTrue(check.get('sourceIsolation', {}).get('exactSourceDisjoint', False))
        self.assertEqual('UNVERIFIED', check['sourceIsolation']['projectAndCloneIsolation'])

    def test_知识修复侧的实际全文重合也须报告污染(self):
        payload = json.loads((self.store / self.snapshot / 'snapshot.json').read_text())
        documents = copy.deepcopy(payload['documents'])
        documents[-1]['text'] = self.source
        documents[-2]['text'] = 'contract Truncated { /*'
        texts = {row['id']: row['text'] for row in documents}
        changed_snapshot = build_snapshot(self.store, payload['manifest'], documents, payload['embedding'],
            payload['chunking'], {row['id']: [1.0, 0.0] for row in documents})
        rows, catalog = self.saved_inputs()
        catalog['snapshotId'] = changed_snapshot
        atomic_json(self.store / 'catalogs' / (changed_snapshot + '.json'), catalog)
        plan = {**self.plan, 'snapshotId': changed_snapshot}
        plan['planHash'] = fingerprint({key: value for key, value in plan.items() if key != 'planHash'})
        atomic_json(self.batch_dir / 'plan.json', plan)
        for row in rows:
            row['snapshotId'] = row['retrieval']['snapshotId'] = changed_snapshot
            row['retrieval']['pool']['snapshotId'] = changed_snapshot
            for candidate in row['retrieval']['pool']['candidates']:
                candidate['text'] = texts[candidate['chunkId']]
            for item in row['retrieval']['d1']['selected']:
                item['candidate']['text'] = texts[item['candidate']['chunkId']]
            row['poolHash'] = fingerprint(row['retrieval']['pool'])
        (self.batch_dir / 'samples.jsonl').write_text(
            '\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')
        events = [json.loads(line) for line in (self.batch_dir / 'events.jsonl').read_text().splitlines()]
        events[0]['planHash'] = plan['planHash']
        (self.batch_dir / 'events.jsonl').write_text(
            '\n'.join(json.dumps(row) for row in events) + '\n', encoding='utf-8')
        check = run_check(self.batch_dir, self.store, self.root / 'output')
        self.assertFalse(check['sourceIsolation']['exactSourceDisjoint'])
        self.assertEqual(['target'], check['sourceIsolation']['exactOverlaps'])
        self.assertFalse(check['sourceIsolation']['knowledgeCommentCleaning']['complete'])
        self.assertEqual(documents[-2]['id'], check['sourceIsolation']['knowledgeCommentCleaning']['failures'][0]['documentId'])

    def test_派生输出拒绝写入历史或正式知识目录(self):
        for output in (self.batch_dir, self.store / 'new-output'):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, '目录之外'):
                run_check(self.batch_dir, self.store, output)

    def test_保存结果没有对应启动事件时拒绝生成派生报告(self):
        atomic_json(self.batch_dir / 'events.jsonl', {'kind': 'PLAN', 'planHash': self.plan['planHash']})
        with self.assertRaisesRegex(ValueError, '启动事件'):
            run_check(self.batch_dir, self.store, self.root / 'output')


if __name__ == '__main__':
    unittest.main()
