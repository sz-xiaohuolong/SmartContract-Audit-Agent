"""编译路径显式接入、源码身份与离线命令行失败边界。"""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from verirag.audit.audit_workbench import assess
from verirag.analysis import d2_verify
import test_compiler_facts as compiler_fixture
import test_audit_workbench as workbench_fixture
from verirag.audit.audit_target import pasted_target
from verirag.audit.audit_workbench import AuditWorkbench


def unknown_result():
    return {'schemaVersion': '2', 'provider': 'solc-standard-json', 'verdict': 'UNKNOWN',
            'protectionVerdict': 'UNKNOWN', 'references': [],
            'pathEvidence': {'status': 'UNKNOWN', 'references': [], 'reason': '路径缺口'},
            'obligations': [{'name': name, 'status': 'UNKNOWN', 'references': [], 'reason': '缺口'}
                            for name in d2_verify.OBLIGATIONS], 'note': '有限路径'}


class CompiledIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.source = 'contract C { function f() public {} }'
        self.hypothesis = {'contract': 'C', 'function': 'f', 'riskLine': 1,
                           'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL'}
        self.worker = Mock(return_value=unknown_result())
        self.module = SimpleNamespace(evaluate_compiled=self.worker)
        self.manifest = {'provider': 'solc-standard-json'}

    def test_显式编译输入不用外部填写的词法事实作证明(self):
        with patch.dict(sys.modules, {'verirag.analysis.compiled_d2': self.module}):
            result = d2_verify.evaluate(self.hypothesis, {'status': 'COMPLETE', 'facts': ['伪造']}, [],
                                        source=self.source, compilation_manifest=self.manifest, root='.')
        self.assertEqual('solc-standard-json', result['provider'])
        bound = self.worker.call_args.args[0]
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(), bound['sourceHash'])
        self.assertEqual(self.manifest, self.worker.call_args.args[1])
        self.assertNotIn('sourceHash', self.hypothesis)

    def test_调用方摘要与实际源码不同时不消费编译产物(self):
        with patch.dict(sys.modules, {'verirag.analysis.compiled_d2': self.module}):
            result = d2_verify.evaluate({**self.hypothesis, 'sourceHash': '0' * 64}, {}, [],
                                        source=self.source, compilation_manifest=self.manifest, root='.')
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('FAILED', result['status'])
        self.assertEqual('SOURCE_HASH_MISMATCH', result['errorCategory'])
        self.worker.assert_not_called()

    def test_编译产物失败不静默回退成词法保护结论(self):
        failed = unknown_result()
        failed['status'] = 'FAILED'
        self.worker.return_value = failed
        with patch.dict(sys.modules, {'verirag.analysis.compiled_d2': self.module}), patch.object(d2_verify, 'extract_facts') as lexical:
            result = d2_verify.evaluate(self.hypothesis, {}, [], compilation_manifest=self.manifest, root='.')
        lexical.assert_not_called()
        self.assertEqual(('FAILED', 'UNKNOWN'), (result['status'], result['verdict']))

    def test_共享评估入口保留模型未知与usage原值(self):
        model = {'status': 'COMPLETED', 'hypotheses': [self.hypothesis], 'inputTokens': None}
        with patch.dict(sys.modules, {'verirag.analysis.compiled_d2': self.module}):
            result = assess(model, {}, [], self.source, compilation_manifest=self.manifest, root='.')
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('solc-standard-json', result['assessments'][0]['provider'])
        self.assertIsNone(model['inputTokens'])

    def test_离线命令行使用保存假设且不发模型请求(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'hypothesis.json').write_text(json.dumps(self.hypothesis))
            arguments = ['d2_verify.py', '--manifest', 'manifest.json', '--hypothesis',
                         str(root / 'hypothesis.json'), '--root', directory]
            output = io.StringIO()
            with patch.dict(sys.modules, {'verirag.analysis.compiled_d2': self.module}), patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(output):
                exit_code = d2_verify.main()
            result = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual(0, result['paidModelRequests'])
            self.assertEqual('UNKNOWN', result['verdict'])
            self.assertEqual([], self.worker.call_args.args[2])

    def test_无效假设文件产生结构化失败而不是安全结论(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hypothesis.json'
            path.write_text('{"riskLine": 1, "riskLine": 2}')
            output = io.StringIO()
            with patch.object(sys, 'argv', ['d2_verify.py', '--manifest', 'missing.json', '--hypothesis', str(path)]), contextlib.redirect_stdout(output):
                exit_code = d2_verify.main()
            result = json.loads(output.getvalue())
            self.assertEqual(1, exit_code)
            self.assertEqual(('FAILED', 'UNKNOWN'), (result['status'], result['verdict']))

    def compiled_workbench(self):
        fixture = compiler_fixture.CompilerFactsTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = fixture.source.replace('// 中文', '       ')
        fixture.source = source
        fixture.input['sources']['contracts/C.sol']['content'] = source
        (fixture.root / 'contracts/C.sol').write_bytes(source.encode())
        fixture.binding['sourceUnits']['contracts/C.sol']['sha256'] = compiler_fixture.digest(source.encode())
        fixture.manifest['expectedSourceHash'] = compiler_fixture.digest(source.encode())
        start = len(source.splitlines(keepends=True)[0].encode())
        def spans(value):
            if isinstance(value, dict):
                if 'nodeType' in value:
                    value['src'] = f'{start}:{len(source.encode()) - start}:0'
                for child in value.values():
                    spans(child)
            elif isinstance(value, list):
                for child in value:
                    spans(child)
        spans(fixture.output)
        fixture.seal()
        target = {**pasted_target(source, 'ACCESS_CONTROL'), 'compilerManifest': str(fixture.root / 'manifest.json')}
        runtime = workbench_fixture.Runtime()
        runtime.model_runner = Mock(return_value={'status': 'COMPLETED', 'fixture': True, 'hypotheses': [
            {**self.hypothesis, 'riskLine': 2}]})
        workbench = AuditWorkbench(fixture.root, runtime_factory=lambda profile: runtime,
            target_loader=lambda: [target], tool=lambda *args: [{'status': 'SKIPPED', 'engine': 'SLITHER', 'issues': []}])
        return fixture, runtime, workbench, {'sampleId': target['sampleId']}

    def test_登记的编译清单贯通预览执行与只读回放(self):
        _, runtime, workbench, choice = self.compiled_workbench()
        preview = workbench.preview(choice)
        self.assertEqual('RECOMPILED_MATCH', preview['retrieval']['compiledFacts']['verificationStatus'])
        self.assertEqual('solc-standard-json', preview['plan']['factsProvider'])
        result = workbench.execute(workbench.prepare({**choice, 'planHash': preview['planHash']}))
        self.assertEqual('solc-standard-json', result['d2']['assessments'][0]['provider'])
        self.assertEqual(result, workbench.read(result['runId']))
        self.assertEqual(1, runtime.model_runner.call_count)

    def test_准备后产物漂移在模型前终止(self):
        fixture, runtime, workbench, choice = self.compiled_workbench()
        preview = workbench.preview(choice)
        prepared = workbench.prepare({**choice, 'planHash': preview['planHash']})
        (fixture.root / 'output.json').write_text('{}')
        result = workbench.execute(prepared)
        self.assertEqual('FAILED', result['status'])
        self.assertEqual('UNRESOLVED', result['conclusion'])
        runtime.model_runner.assert_not_called()

    def test_清理输入没有对应编译原件时拒绝混用(self):
        fixture, runtime, workbench, _ = self.compiled_workbench()
        target = {**pasted_target('contract C { function f() public {} }', 'ACCESS_CONTROL'),
                  'compilerManifest': str(fixture.root / 'manifest.json')}
        workbench.target_loader = lambda: [target]
        with self.assertRaisesRegex(ValueError, '消费源码字节'):
            workbench.preview({'sampleId': target['sampleId']})
        runtime.model_runner.assert_not_called()

    def test_批量编排也在模型前拒绝编译绑定漂移(self):
        fixture, runtime, workbench, _ = self.compiled_workbench()
        target = {**workbench.target_loader()[0], 'groundTruth': {'hasVulnerability': False}}
        (fixture.root / 'output.json').write_text('{}')
        from verirag.experiments.benchmark_runtime import BenchmarkRuntime
        runner = BenchmarkRuntime.__new__(BenchmarkRuntime)
        runner.root = fixture.root
        runner.preview = runtime.preview
        runner.model_runner = runtime.model_runner
        with self.assertRaises(ValueError):
            runner.run(target, 'D1', 'offline')
        runtime.model_runner.assert_not_called()

    def test_工具阶段后编译漂移计入D2失败分母(self):
        fixture, _, workbench, choice = self.compiled_workbench()
        preview = workbench.preview(choice)
        prepared = workbench.prepare({**choice, 'planHash': preview['planHash']})
        def tool(*args):
            (fixture.root / 'output.json').write_text('{}')
            return [{'status': 'SKIPPED', 'engine': 'SLITHER', 'issues': []}]
        workbench.tool = tool
        result = workbench.execute(prepared)
        self.assertEqual('FAILED', result['status'])
        self.assertEqual('FAILED', result['d2']['status'])
        self.assertEqual(1, result['denominators']['failed'])
        self.assertEqual('UNKNOWN', result['d2']['verdict'])

    def test_工作台范围校验保留完整签名供编译器绑定(self):
        _, runtime, workbench, choice = self.compiled_workbench()
        runtime.model_runner.return_value['hypotheses'][0]['function'] = 'f()'
        preview = workbench.preview(choice)
        result = workbench.execute(workbench.prepare({**choice, 'planHash': preview['planHash']}))
        self.assertEqual('solc-standard-json', result['d2']['assessments'][0]['provider'])
        self.assertEqual('f()', result['d2']['assessments'][0]['proofScope']['candidate']['function'])


if __name__ == '__main__':
    unittest.main()
