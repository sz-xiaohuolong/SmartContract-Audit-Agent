"""派生候选核验必须保护原件、缓存配置身份且绝不追加模型调用。"""
import hashlib
import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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
