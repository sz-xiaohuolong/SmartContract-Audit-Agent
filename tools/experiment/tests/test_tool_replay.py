"""派生候选核验必须保护原件、缓存配置身份且绝不追加模型调用。"""
import hashlib
import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from copy import deepcopy


SOURCE = 'pragma solidity ^0.8.20; contract C { uint x; function f() public { x = 1; } }'


class ToolReplayTest(unittest.TestCase):
    def test_未知比例以全部保存假设为分母且逐条保留迁移(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            source_path = original / 'samples.jsonl'
            rows = [json.loads(line) for line in source_path.read_text().splitlines()]
            for row in rows:
                row['model']['hypotheses'] = [{'contract': 'C', 'function': 'f', 'riskLine': 1,
                    'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL'}]
                row['d2'] = {'assessments': [{'hypothesisIndex': 0, 'verdict': 'UNKNOWN'}]}
            source_path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            before = source_path.read_bytes()
            outcomes = [{'status': 'COMPLETED', 'verdict': verdict, 'assessments': [
                {'hypothesisIndex': 0, 'verdict': verdict, 'note': '本地接缝夹具'}]}
                for verdict in ('SUPPORTED', 'REFUTED', 'UNKNOWN')]
            with patch('tool_replay.assess', side_effect=outcomes):
                summary = self.module().replay(root, original, root / 'derived',
                    tool_runner=lambda *args: [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}],
                    environment_resolver=lambda source: {'status': 'OK', 'configHash': 'cfg'},
                    code_identity={'commit': 'fixture'})
            comparison = summary['unknownComparison']
            self.assertEqual(3, comparison['denominator'])
            self.assertEqual(3, comparison['beforeUnknown'])
            self.assertEqual(1, comparison['afterUnknown'])
            self.assertEqual(1 / 3, comparison['afterRate'])
            self.assertEqual(before, source_path.read_bytes())
            self.assertEqual(3, len((root / 'derived/assessments.jsonl').read_text().splitlines()))

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('tool_replay'), '尚未提供保护原件的工具派生重放')
        return importlib.import_module('tool_replay')

    def original(self, root):
        path = root / 'original'
        path.mkdir()
        source_hash = hashlib.sha256(SOURCE.encode()).hexdigest()
        rows = [{'sampleId': 'case', 'strategy': strategy, 'source': SOURCE, 'sourceHash': source_hash,
                 'model': {'status': 'COMPLETED', 'hypotheses': [], 'conclusion': 'NO_CONFIRMED_FINDINGS',
                           'inputTokens': None, 'outputTokens': 7, 'requestAttempts': 1},
                 'modelPrediction': 'NO_REPORT', 'poolHash': 'fixed-pool', 'snapshotId': 'fixed-kb'}
                for strategy in ('DENSE', 'FIELD_FILTER', 'D1')]
        (path / 'samples.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        (path / 'plan.json').write_text(json.dumps({'batchId': 'original-batch'}))
        return path

    def add_blocked(self, original, *, only_blocked=False):
        path = original / 'samples.jsonl'
        eligible = [json.loads(line) for line in path.read_text().splitlines()]
        blocked_hash = hashlib.sha256('未进入模型的完整输入'.encode()).hexdigest()
        reason = '完整源码超出预算；需要显式范围'
        blocked = [{'sampleId': 'blocked', 'strategy': strategy, 'sourceHash': blocked_hash,
                    'status': 'FAILED', 'pipelineStatus': 'FAILED', 'prediction': 'UNKNOWN',
                    'modelPrediction': 'UNKNOWN', 'conclusion': 'UNRESOLVED',
                    'errorCategory': 'EVALUATION_INPUT_BLOCKED', 'inputReason': reason,
                    'inputTokens': None, 'outputTokens': None, 'requestAttempts': 0,
                    'model': {}, 'tools': [], 'd2': {'verdict': 'UNKNOWN', 'assessments': [],
                        'errorCategory': 'EVALUATION_INPUT_BLOCKED'}}
                   for strategy in ('DENSE', 'FIELD_FILTER', 'D1')]
        rows = blocked if only_blocked else eligible + blocked
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        plan = {'batchId': 'original-batch', 'sourceHashes': {
            'case': eligible[0]['sourceHash'], 'blocked': blocked_hash},
            'inputEligibility': {'case': {'runnable': True, 'reason': None},
                                 'blocked': {'runnable': False, 'reason': reason}}}
        (original / 'plan.json').write_text(json.dumps(plan))
        return rows, plan

    def test_输入阻断保留计划分母和原模型且不调用工具接缝(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            rows, _ = self.add_blocked(original)
            before = {file.name: file.read_bytes() for file in original.iterdir()}
            environment = Mock(return_value={'status': 'OK', 'configHash': 'cfg'})
            compilation = Mock(return_value=None)
            tools = Mock(return_value=[{'engine': 'SLITHER', 'status': 'OK', 'issues': []}])
            with patch('audit_run.model_runner', side_effect=AssertionError('不得新增模型请求')):
                summary = self.module().replay(root, original, root / 'derived', tool_runner=tools,
                    environment_resolver=environment, compilation_resolver=compilation,
                    code_identity={'commit': 'fixture'})
            self.assertEqual(6, summary['units'])
            self.assertEqual(3, summary['inputBlockedUnits'])
            self.assertEqual(0, summary['newModelRequests'])
            self.assertEqual(1, summary['toolExecutions'])
            self.assertEqual(3, environment.call_count)
            self.assertEqual(3, compilation.call_count)
            self.assertEqual(1, tools.call_count)
            self.assertTrue(all(call.args[0]['sampleId'] == 'case' for call in compilation.call_args_list))
            derived = [json.loads(line) for line in (root / 'derived/samples.jsonl').read_text().splitlines()]
            self.assertEqual(6, len(derived))
            for prior, current in zip(rows, derived):
                self.assertEqual(prior['model'], current['model'])
                if prior['sampleId'] == 'blocked':
                    self.assertNotIn('source', current)
                    self.assertEqual(prior['d2'], current['d2'])
                    self.assertEqual(prior['inputTokens'], current['inputTokens'])
                    self.assertEqual(prior['outputTokens'], current['outputTokens'])
                    self.assertEqual('SKIPPED', current['facts']['status'])
                    self.assertEqual('FAILED', current['pipelineStatus'])
                    self.assertEqual('UNRESOLVED', current['conclusion'])
                    self.assertEqual([], current['tools'])
                    self.assertIsNone(current['compilerBinding'])
                    self.assertIsNone(current['environment'])
            self.assertEqual(before, {file.name: file.read_bytes() for file in original.iterdir()})
            manifest = json.loads((root / 'derived/manifest.json').read_text())
            self.assertEqual('COMPLETED', manifest['status'])
            self.assertEqual(6, manifest['plannedUnits'])
            self.assertEqual(6, manifest['completedUnits'])

    def test_全部输入阻断无需工具配置仍可封口(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            self.add_blocked(original, only_blocked=True)
            tools = Mock(side_effect=AssertionError('输入阻断不得执行工具'))
            compilation = Mock(side_effect=AssertionError('输入阻断不得编译'))
            with patch('tool_environment._configuration', side_effect=AssertionError('无需工具配置')):
                summary = self.module().replay(root, original, root / 'derived', tool_runner=tools,
                    compilation_resolver=compilation, code_identity={'commit': 'fixture'})
            self.assertEqual(3, summary['units'])
            self.assertEqual(3, summary['inputBlockedUnits'])
            self.assertEqual(0, summary['toolExecutions'])
            self.assertEqual(0, summary['hypotheses'])
            self.assertEqual({'UNKNOWN': 3}, summary['d2Verdicts'])
            tools.assert_not_called(); compilation.assert_not_called()

    def test_伪造或矛盾的输入阻断仍在发布前拒绝(self):
        mutations = [
            ('未登记阻断', lambda rows, plan: plan.pop('inputEligibility')),
            ('计划仍可运行', lambda rows, plan: plan['inputEligibility']['blocked'].update(runnable=True)),
            ('摘要错绑', lambda rows, plan: rows[0].update(sourceHash='0' * 64)),
            ('请求已发生', lambda rows, plan: rows[0].update(requestAttempts=1)),
            ('布尔冒充零请求', lambda rows, plan: rows[0].update(requestAttempts=False)),
            ('模型已有结果', lambda rows, plan: rows[0].update(model={'hypotheses': []})),
            ('缺失不等于空源码', lambda rows, plan: rows[0].update(source='')),
            ('伪造安全结论', lambda rows, plan: rows[0].update(conclusion='HYPOTHESES_REFUTED')),
        ]
        for title, mutate in mutations:
            with self.subTest(title=title), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); original = self.original(root)
                rows, plan = self.add_blocked(original, only_blocked=True)
                rows, plan = deepcopy(rows), deepcopy(plan)
                mutate(rows, plan)
                (original / 'samples.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
                (original / 'plan.json').write_text(json.dumps(plan))
                with self.assertRaises(ValueError):
                    self.module().replay(root, original, root / 'derived',
                        tool_runner=lambda *args: self.fail('不应执行工具'),
                        code_identity={'commit': 'fixture'})
                self.assertFalse((root / 'derived').exists())

    def test_same_source_and_config_runs_tool_once_and_preserves_raw_model(self):
        replay = self.module().replay
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.original(root)
            before = (original / 'samples.jsonl').read_bytes()
            calls = []
            def tools(task_root, target, mode):
                self.assertEqual('real', mode)
                calls.append(target['sampleId'])
                return [{'engine': 'SLITHER', 'status': 'OK', 'issues': [],
                         'sourceHash': target['sourceHash'], 'sourceFile': 'Contract.sol'}]
            with patch('audit_run.model_runner', side_effect=AssertionError('重放不得调用模型')):
                result = replay(root, original, root / 'derived', tool_runner=tools,
                                environment_resolver=lambda source: {'status': 'OK', 'configHash': 'cfg-one'},
                                code_identity={'commit': 'fixture', 'artifactHash': 'jar-one'})
            self.assertEqual(['case'], calls)
            self.assertEqual(before, (original / 'samples.jsonl').read_bytes())
            self.assertEqual(0, result['newModelRequests'])
            self.assertEqual(3, result['units'])
            derived = [json.loads(line) for line in (root / 'derived/samples.jsonl').read_text().splitlines()]
            self.assertTrue(all(row['model']['inputTokens'] is None for row in derived))
            self.assertTrue(all(row['model']['outputTokens'] == 7 for row in derived))
            self.assertTrue(all(row['provenance']['originalBatchId'] == 'original-batch' for row in derived))
            self.assertTrue(all(row['d2']['verdict'] == 'UNKNOWN' for row in derived))

    def test_different_environment_cannot_reuse_old_tool_result(self):
        replay = self.module().replay
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            counter = iter(('cfg-first', 'cfg-second', 'cfg-second'))
            calls = []
            def tools(task_root, target, mode):
                calls.append(target['_toolEnvironment']['configHash'])
                return [{'engine': 'SLITHER', 'status': 'PROCESS_ERROR', 'issues': [],
                         'sourceHash': target['sourceHash']}]
            result = replay(root, original, root / 'derived', tool_runner=tools,
                            environment_resolver=lambda source: {'status': 'OK', 'configHash': next(counter)},
                            code_identity={'commit': 'fixture'})
            self.assertEqual(['cfg-first', 'cfg-second'], calls)
            self.assertEqual({'PROCESS_ERROR': 3}, result['toolStatuses'])
            self.assertEqual({'UNKNOWN': 3}, result['d2Verdicts'])

    def test_source_hash_mismatch_rejected_before_any_output_or_process(self):
        replay = self.module().replay
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            path = original / 'samples.jsonl'
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[1]['sourceHash'] = '0' * 64
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            with self.assertRaisesRegex(ValueError, '源码摘要'):
                replay(root, original, root / 'derived', tool_runner=lambda *args: self.fail('不应执行工具'))
            self.assertFalse((root / 'derived').exists())

    def test_output_directory_must_not_overwrite_original_or_existing_derived(self):
        replay = self.module().replay
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            with self.assertRaises(ValueError):
                replay(root, original, original)
            output = root / 'derived'; output.mkdir()
            (output / 'keep.txt').write_text('已保存结果')
            with self.assertRaises(FileExistsError):
                replay(root, original, output)
            self.assertEqual('已保存结果', (output / 'keep.txt').read_text())

    def test_D2异常保持流水线失败且原模型仍保留(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            with patch('tool_replay.assess', side_effect=ValueError('不可裁决')):
                self.module().replay(root, original, root / 'derived',
                    tool_runner=lambda *args: [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}],
                    environment_resolver=lambda source: {'status': 'OK', 'configHash': 'cfg'},
                    code_identity={'commit': 'fixture'})
            derived = [json.loads(line) for line in (root / 'derived/samples.jsonl').read_text().splitlines()]
            self.assertTrue(all(row['pipelineStatus'] == 'FAILED' for row in derived))
            self.assertTrue(all(row['conclusion'] == 'UNRESOLVED' for row in derived))
            self.assertTrue(all(row['model']['status'] == 'COMPLETED' for row in derived))

    def test_原计划或目标清单变化不能封口为完成(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            def tools(*args):
                (original / 'plan.json').write_text('{"batchId":"changed"}')
                return [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}]
            with self.assertRaisesRegex(ValueError, '原批次'):
                self.module().replay(root, original, root / 'derived', tool_runner=tools,
                    environment_resolver=lambda source: {'status': 'OK', 'configHash': 'cfg'},
                    code_identity={'commit': 'fixture'})
            manifest = json.loads((root / 'derived/manifest.json').read_text())
            self.assertEqual('INTERRUPTED', manifest['status'])

    def test_实际目标绑定依赖变化改变代码身份(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = root / 'tools/experiment/audit_target.py'
            module.parent.mkdir(parents=True)
            module.write_text('版本一')
            before = self.module()._code_identity(root)
            module.write_text('版本二')
            after = self.module()._code_identity(root)
            self.assertNotEqual(before, after)

    def test_编译提供器接入共享评估并保留原候选(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            manifest = {'provider': 'solc-standard-json', 'expectedSourceHash': hashlib.sha256(SOURCE.encode()).hexdigest()}
            bundle = {'sourceHash': manifest['expectedSourceHash'], 'environmentHash': 'compiled-env',
                      'manifestDigest': 'manifest-one', 'receiptDigest': 'receipt-one'}
            compiled = {'status': 'PARTIAL', 'facts': [], 'provider': 'solc-standard-json'}
            result = {'status': 'COMPLETED', 'verdict': 'UNKNOWN', 'assessments': []}
            calls = []
            def tools(task_root, target, mode):
                self.assertEqual(manifest, target['compilerManifest'])
                calls.append(target['sampleId'])
                return [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}]
            with patch('tool_replay.load_bound_compilation', return_value=bundle), \
                 patch('tool_replay.extract_compiler_facts', return_value=compiled), \
                 patch('tool_replay.assess', return_value=result) as assessment:
                self.module().replay(root, original, root / 'derived', tool_runner=tools,
                    environment_resolver=lambda source: {'status': 'OK', 'configHash': 'cfg'},
                    compilation_resolver=lambda target: manifest, code_identity={'commit': 'fixture'})
            self.assertEqual(['case'], calls)
            for call in assessment.call_args_list:
                self.assertEqual(manifest, call.kwargs['compilation_manifest'])
                self.assertEqual(root.resolve(), call.kwargs['root'])
            derived = [json.loads(line) for line in (root / 'derived/samples.jsonl').read_text().splitlines()]
            self.assertTrue(all(row['compiledFacts'] == compiled for row in derived))
            self.assertTrue(all(row['model']['inputTokens'] is None for row in derived))

    def test_结构化D2失败进入重放失败分母(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            with patch('tool_replay.assess', return_value={'status': 'FAILED', 'verdict': 'UNKNOWN', 'assessments': []}):
                self.module().replay(root, original, root / 'derived',
                    tool_runner=lambda *args: [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}],
                    environment_resolver=lambda source: {'status': 'OK', 'configHash': 'cfg'},
                    code_identity={'commit': 'fixture'})
            derived = [json.loads(line) for line in (root / 'derived/samples.jsonl').read_text().splitlines()]
            self.assertTrue(all(row['pipelineStatus'] == 'FAILED' for row in derived))
            self.assertTrue(all(row['conclusion'] == 'UNRESOLVED' for row in derived))

    def test_编译源码身份不一致不能退回词法判定(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original = self.original(root)
            with patch('tool_replay.load_bound_compilation', return_value={'sourceHash': '0' * 64}), \
                 patch('tool_replay.assess') as assessment:
                self.module().replay(root, original, root / 'derived',
                    tool_runner=lambda *args: [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}],
                    environment_resolver=lambda source: {'status': 'OK', 'configHash': 'cfg'},
                    compilation_resolver=lambda target: {'provider': 'solc-standard-json'},
                    code_identity={'commit': 'fixture'})
            assessment.assert_not_called()
            derived = [json.loads(line) for line in (root / 'derived/samples.jsonl').read_text().splitlines()]
            self.assertTrue(all(row['pipelineStatus'] == 'FAILED' for row in derived))
            self.assertTrue(all(row['d2']['verdict'] == 'UNKNOWN' for row in derived))


if __name__ == '__main__':
    unittest.main()
