"""真实批量审计的报告级预测与无风险事实软对比。"""
import unittest
import copy
import hashlib

from benchmark_runtime import BenchmarkRuntime, interpret_model, soft_without_risk, _risk_fact
from program_facts import extract_facts
from benchmark_targets import _record
from snapshots import build_snapshot, activate_snapshot
from storage import atomic_json
from pathlib import Path
from tempfile import TemporaryDirectory
from formal_recall import select_strategy


class LocalIndex:
    def build(self, collection, payload):
        self.rows = payload['rows']

    def read(self, collection):
        return list(self.rows)

    def search(self, collection, query, limit):
        return [{'id': row['id'], 'distance': 1.0} for row in self.rows[:limit]]


class BenchmarkRuntimeTest(unittest.TestCase):
    def runtime(self, root, knowledge_hash='a' * 64):
        store = root / '.local/d1-kb-snapshots'
        manifest = {'schema_version': '1', 'categories': ['REENTRANCY'], 'samples': [{
            'id': 'a', 'path': 'a.sol', 'source_hash': knowledge_hash, 'exact_group': knowledge_hash,
            'project_group': '知识项目', 'clone_groups': [], 'origin': '夹具/a', 'split': 'knowledge',
            'types': ['REENTRANCY'], 'review_status': 'AUTO_LABELED', 'evidence_tier': 'HEURISTIC',
            'label_rule': '夹具自动标签'}]}
        documents = [{'id': 'before', 'sample_id': 'a', 'text': '调用后写入余额'},
                     {'id': 'after', 'sample_id': 'a', 'text': '调用前写入余额'}]
        snapshot = build_snapshot(store, manifest, documents,
            {'model': 'fixture', 'revision': 'r', 'dimension': 2}, {'version': 'fixture'},
            {'before': [1.0, 0.0], 'after': [1.0, 0.0]})
        index = LocalIndex()
        activate_snapshot(store, snapshot, index)
        cases = {row['id']: {'caseId': row['id'], 'pairId': 'pair',
            'role': 'VULNERABLE' if row['id'] == 'before' else 'DEFENSE', 'mechanism': 'REENTRANCY',
            'riskKind': 'CALL', 'conditions': [], 'reviewed': False} for row in documents}
        (store / 'catalogs').mkdir()
        atomic_json(store / 'catalogs' / (snapshot + '.json'), {'snapshotId': snapshot, 'cases': cases})
        self.queries = []

        def encoder(texts):
            self.queries.extend(texts)
            return [[1.0, 0.0] for _ in texts]

        return BenchmarkRuntime(root, index, encoder)

    def discovery_target(self):
        source = ('// <yes> <report> REENTRANCY\ncontract C {\n function a() public {\n'
                  ' msg.sender.call("");\n msg.sender.call("");\n }\n}')
        return _record('c', source, 'REENTRANCY', 'a', None, True, '标签', '目标项目')

    def test_消费前拒绝源码或模型摘要错绑(self):
        with TemporaryDirectory() as directory:
            runtime = self.runtime(Path(directory))
            for field in ('sourceHash', 'fullSourceHash', 'modelSourceHash', 'originalSourceHash'):
                target = self.discovery_target()
                target[field] = 'f' * 64
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, '摘要'):
                    runtime.preview(target)

    def test_原件与清理全文无法替换成另一份合法摘要源码(self):
        with TemporaryDirectory() as directory:
            runtime = self.runtime(Path(directory))
            target = self.discovery_target()
            target['fullSource'] = target['fullSource'].replace('contract C', 'contract D')
            target['modelSource'] = target['fullSource']
            digest = hashlib.sha256(target['fullSource'].encode()).hexdigest()
            target.update(sourceHash=digest, fullSourceHash=digest, modelSourceHash=digest)
            with self.assertRaisesRegex(ValueError, '原件'):
                runtime.preview(target)

    def test_清理回执摘要必须绑定实际消费文本(self):
        with TemporaryDirectory() as directory:
            runtime = self.runtime(Path(directory))
            for field in ('originalSourceHash', 'fullSourceHash', 'modelSourceHash'):
                target = self.discovery_target()
                target['inputGovernanceReceipt'][field] = 'f' * 64
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, '摘要'):
                    runtime.preview(target)

    def test_发现查询和风险不随评分字段变化(self):
        with TemporaryDirectory() as directory:
            runtime = self.runtime(Path(directory))
            target = self.discovery_target()
            target['vulnerableLines'] = [4]
            first = runtime.preview(target)
            changed = copy.deepcopy(target)
            changed['groundTruth'] = {'hasVulnerability': False, 'vulnerabilityType': 'ACCESS_CONTROL'}
            changed['vulnerableLines'] = [5]
            second = runtime.preview(changed)
            self.assertEqual(first, second)
            self.assertEqual([target['modelSource']], self.queries)
            self.assertNotIn('<yes>', self.queries[0])
            self.assertIn('无唯一风险事实', first['d1']['gaps'][0])

    def test_消费前拒绝模型片段与全文范围不一致(self):
        with TemporaryDirectory() as directory:
            runtime = self.runtime(Path(directory))
            target = self.discovery_target()
            target['modelSource'] = 'contract Different {}'
            target['modelSourceHash'] = hashlib.sha256(target['modelSource'].encode()).hexdigest()
            with self.assertRaisesRegex(ValueError, '范围'):
                runtime.preview(target)

    def test_清理后摘要变化不能绕过原件知识隔离(self):
        with TemporaryDirectory() as directory:
            target = self.discovery_target()
            runtime = self.runtime(Path(directory), target['originalSourceHash'])
            with self.assertRaisesRegex(ValueError, '知识'):
                runtime.preview(target)

    def test_超长未选择范围的发现输入明确阻断(self):
        with TemporaryDirectory() as directory:
            runtime = self.runtime(Path(directory))
            source = 'contract C {\n' + 'uint value;\n' * 600 + 'function a() public {}\n}'
            target = _record('c', source, 'REENTRANCY', 'a', None, True, '标签', '目标项目')
            with self.assertRaisesRegex(ValueError, '显式选择'):
                runtime.preview(target)

    def test_发现风险选择不读取评分真值行(self):
        source = ('contract C {\n function a() public {\n msg.sender.call("");\n'
                  ' msg.sender.call("");\n }\n}')
        facts = extract_facts(source)
        for task in ({}, {'taskKind': 'DISCOVERY'}):
            for line in (3, 4):
                target = {'mechanism': 'REENTRANCY', 'function': 'a',
                          'vulnerableLines': [line], 'groundTruth': {'hasVulnerability': line == 3}, **task}
                self.assertIsNone(_risk_fact(facts, target))

    def test_全文发现风险不局限于首个函数(self):
        source = ('contract C {\n function a() public { msg.sender.call(""); }\n'
                  ' function b() public { msg.sender.call(""); }\n}')
        target = {'mechanism': 'REENTRANCY', 'function': 'a', 'scope': 'FULL', 'taskKind': 'DISCOVERY'}
        self.assertIsNone(_risk_fact(extract_facts(source), target))

    def test_全文发现不把默认合约名称当作缩小范围(self):
        source = ('contract C { function a() public { msg.sender.call(""); } }\n'
                  'contract D { function b() public { msg.sender.call(""); } }')
        target = {'mechanism': 'REENTRANCY', 'function': 'a', 'contract': 'C',
                  'scope': 'FULL', 'taskKind': 'DISCOVERY'}
        self.assertIsNone(_risk_fact(extract_facts(source), target))

    def test_候选核验仅采用明确声明的风险位置(self):
        source = ('contract C {\n function a() public {\n msg.sender.call("");\n'
                  ' msg.sender.call("");\n }\n}')
        target = {'mechanism': 'REENTRANCY', 'function': 'a', 'taskKind': 'CLAIM_VALIDATION',
                  'riskLine': 4, 'vulnerableLines': [3]}
        self.assertEqual(4, _risk_fact(extract_facts(source), target)['line'])
        del target['riskLine']
        self.assertIsNone(_risk_fact(extract_facts(source), target))

    def test_全文候选核验仍绑定候选的合约和函数(self):
        source = ('contract C { function a() public { msg.sender.call(""); } } '
                  'contract D { function b() public { msg.sender.call(""); } }')
        target = {'mechanism': 'REENTRANCY', 'function': 'a', 'contract': 'C', 'scope': 'FULL',
                  'taskKind': 'CLAIM_VALIDATION', 'riskLine': 1}
        risk = _risk_fact(extract_facts(source), target)
        self.assertIsNotNone(risk)
        self.assertTrue(risk['scope'].startswith('C.a@'))

    def test_正式登记范围核验可绑定唯一操作_多操作仍未知(self):
        source = ('contract C {\n function a() public { msg.sender.call(""); }\n'
                  ' function b() public { msg.sender.call(""); }\n}')
        target = {'mechanism': 'REENTRANCY', 'function': 'a', 'contract': 'C',
                  'scope': 'FUNCTION', 'lineStart': 2, 'lineEnd': 2,
                  'taskKind': 'CLAIM_VALIDATION', 'claimOrigin': 'REGISTERED_FUNCTION_SCOPE'}
        risk = _risk_fact(extract_facts(source), target)
        self.assertIsNotNone(risk)
        self.assertTrue(risk['scope'].startswith('C.a@'))
        changed = source.replace('function a() public { msg.sender.call(""); }',
            'function a() public { msg.sender.call(""); msg.sender.call(""); }')
        self.assertIsNone(_risk_fact(extract_facts(changed), target))

    def test_失败和离线空假设不变成阴性预测(self):
        self.assertEqual('REPORT', interpret_model({'status': 'COMPLETED',
            'conclusion': 'VULNERABILITY_REPORTED'}, 'real'))
        self.assertEqual('NO_REPORT', interpret_model({'status': 'COMPLETED',
            'conclusion': 'NO_CONFIRMED_FINDINGS'}, 'real'))
        self.assertEqual('UNKNOWN', interpret_model({'status': 'FAILED',
            'conclusion': 'NO_CONFIRMED_FINDINGS'}, 'real'))
        self.assertEqual('UNKNOWN', interpret_model({'status': 'COMPLETED',
            'conclusion': 'NO_CONFIRMED_FINDINGS'}, 'offline'))

    def test_无唯一风险事实时保留软配对与显式缺口(self):
        before = {'caseId': 'a', 'chunkId': 'a', 'pairId': 'p', 'role': 'VULNERABLE',
                  'mechanism': 'REENTRANCY', 'text': '旧代码', 'denseScore': .9, 'conditions': []}
        after = {**before, 'caseId': 'b', 'chunkId': 'b', 'role': 'DEFENSE', 'text': '新代码', 'denseScore': .8}
        result = soft_without_risk({'candidates': [before, after]}, 'REENTRANCY')
        self.assertEqual(['a', 'b'], [row['candidate']['chunkId'] for row in result['selected']])
        self.assertIn('无唯一风险事实', result['gaps'][0])

    def test_自动知识字段基线仅按类别字段而非_d1_绑定筛选(self):
        candidate = {'caseId': 'a', 'chunkId': 'a', 'mechanism': 'REENTRANCY',
                     'role': 'VULNERABLE', 'conditions': [], 'text': '调用前未写状态'}
        other = {**candidate, 'caseId': 'b', 'chunkId': 'b',
                 'mechanism': 'ACCESS_CONTROL', 'text': '权限检查'}
        view = {'pool': {'schemaVersion': 'auto-1', 'candidates': [candidate, other]},
                'd1': {'evaluations': {}}, 'targetMechanism': 'REENTRANCY'}
        selected = select_strategy(view, 'FIELD_FILTER')['d1']['selected']
        self.assertEqual(['a'], [row['candidate']['chunkId'] for row in selected])

    def test_失败正文原样落盘且结果保留请求次数(self):
        with TemporaryDirectory() as directory:
            runtime = BenchmarkRuntime.__new__(BenchmarkRuntime)
            runtime.root = Path(directory)
            runtime.preview = lambda target: {'pool': {'candidates': []}, 'd1': {'selected': []}}
            raw = '```json\n{"bad":true}\n```'
            runtime.model_runner = lambda *args: {'status': 'FAILED', 'conclusion': 'UNRESOLVED',
                'errorCategory': 'MODEL_OUTPUT_INVALID', 'requestAttempts': 2, '_rawResponse': raw}
            result = runtime.run({'groundTruth': {'hasVulnerability': True}}, 'D1', 'real')
            self.assertEqual('UNKNOWN', result['prediction'])
            self.assertEqual(2, result['requestAttempts'])
            self.assertEqual(raw, (runtime.root / result['diagnosticPath']).read_text())
            self.assertNotIn('_rawResponse', result['model'])

    def test_工具失败与_d2_异常不改写原模型统计(self):
        with TemporaryDirectory() as directory:
            runtime = BenchmarkRuntime.__new__(BenchmarkRuntime)
            runtime.root = Path(directory)
            runtime.preview = lambda target: {'pool': {'candidates': []}, 'd1': {'selected': []}, 'facts': {}}
            runtime.model_runner = lambda *args: {'status': 'COMPLETED', 'conclusion': 'VULNERABILITY_REPORTED',
                'hypotheses': [{'riskLine': 0}], 'inputTokens': None, 'outputTokens': None}
            runtime.tool_runner = lambda *args: [{'engine': 'SLITHER', 'status': 'TIMEOUT', 'issues': []}]
            result = runtime.run({'groundTruth': {'hasVulnerability': True}}, 'D1', 'real')
            self.assertEqual('COMPLETED', result['status'])
            self.assertEqual('REPORT', result['prediction'])
            self.assertEqual('FAILED', result['pipelineStatus'])
            self.assertEqual('UNRESOLVED', result['conclusion'])
            self.assertEqual('UNKNOWN', result['d2']['verdict'])
            self.assertEqual('VULNERABILITY_REPORTED', result['model']['conclusion'])


if __name__ == '__main__':
    unittest.main()
