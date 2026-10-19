"""单样本运行必须先持久化计划，重放不重新调用模型。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from audit_run import EXPERIMENT_MAX_OUTPUT_TOKENS, RunDependencies, run_once, replay, selected_ids, model_runner, tool_runner
from storage import decode


class AuditRunTest(unittest.TestCase):
    def test_显式事实提示缺少编译原件时必须在模型前拒绝(self):
        target = {'factGuidanceEnabled': True, 'fullSource': 'contract C {}', 'fullSourceHash': 'a' * 64,
            'modelSource': 'contract C {}', 'scope': 'FULL', 'lineStart': 1, 'lineEnd': 1,
            'mechanism': 'ACCESS_CONTROL', 'function': ''}
        with tempfile.TemporaryDirectory() as directory, patch('audit_run.subprocess.run') as launch:
            with self.assertRaisesRegex(ValueError, '事实提示'):
                model_runner(Path(directory), target, {'d1': {'selected': []}}, 'preflight')
            launch.assert_not_called()

    def test_事实提示开关复核索引并保留原全文(self):
        import test_compiler_facts as fixtures
        from focus_context import build_focus_context, build_fact_guidance
        from risk_catalog import build_risk_catalog
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bundle = fixture.load()
        context, catalog = build_focus_context(bundle), build_risk_catalog(bundle)
        target = {'factGuidanceEnabled': True, 'fullSource': fixture.source, 'fullSourceHash': bundle['sourceHash'],
            'modelSource': fixture.source, 'scope': 'FULL', 'lineStart': 1, 'lineEnd': 2,
            'mechanism': 'ACCESS_CONTROL', 'function': 'f'}
        view = {'focusContext': context, 'riskCatalog': catalog, 'discoveryCompilation': fixture.manifest,
                'd1': {'selected': [], 'context': ''}}
        def capture(command, **kwargs):
            request = decode(Path(command[command.index('--request') + 1]).read_bytes())
            self.assertEqual(fixture.source, request['modelSource'])
            self.assertEqual(target['factGuidanceEnabled'], 'factGuidance' in request)
            if target['factGuidanceEnabled']:
                self.assertEqual(build_fact_guidance(context, catalog), request['factGuidance'])
            return SimpleNamespace(returncode=0, stdout=b'{"status":"COMPLETED"}')
        with patch('risk_catalog.load_risk_catalog', return_value=catalog), \
                patch('compiler_facts.load_bound_compilation', return_value=bundle), \
                patch('audit_run.subprocess.run', side_effect=capture) as launch:
            model_runner(fixture.root, target, view, 'preflight')
            target['factGuidanceEnabled'] = False
            model_runner(fixture.root, target, view, 'preflight')
            target['factGuidanceEnabled'] = True
            context['permissionFacts']['complete'] = True
            with self.assertRaisesRegex(ValueError, '发生变化'):
                model_runner(fixture.root, target, view, 'preflight')
            self.assertEqual(2, launch.call_count)

    def test_完整请求预检使用本机重放且不读取真实凭证(self):
        from benchmark_targets import _record
        target = _record('fixture', 'contract C { uint x; function f() public { x = 1; } }',
                         'ACCESS_CONTROL', 'f', None, True, '夹具', '夹具')
        target['_maxPromptBytes'] = 32768
        with tempfile.TemporaryDirectory() as directory:
            def capture(command, **kwargs):
                self.assertIn('--replay-response', command)
                self.assertNotIn('--config', command)
                request = decode(Path(command[command.index('--request') + 1]).read_bytes())
                self.assertEqual(32768, request['maxPromptBytes'])
                self.assertEqual('机制卡片', request['context'])
                return SimpleNamespace(returncode=0, stdout=b'{"status":"COMPLETED"}')
            with patch('audit_run.subprocess.run', side_effect=capture):
                self.assertEqual('COMPLETED', model_runner(Path(directory), target,
                    {'d1': {'context': '机制卡片', 'selected': []}}, 'preflight')['status'])

    def test_offline_fixture_does_not_claim_safe_result(self):
        result = model_runner(Path('.'), {}, {}, 'offline')
        self.assertEqual('UNRESOLVED', result['conclusion'])
        self.assertIsNone(result['inputTokens'])

    def test_d1_selection_ids_follow_java_result_shape(self):
        self.assertEqual(['chunk-1'], selected_ids([{'candidate': {'chunkId': 'chunk-1'}, 'use': 'SUPPORT'}]))
        with self.assertRaises(ValueError): selected_ids([{'chunkId': 'wrong-level'}])

    def test_imported_source_without_configuration_keeps_unresolved(self):
        target = {'fullSource': 'pragma solidity 0.8.17;\nimport "src/Well.sol";\ncontract C {}'}
        with tempfile.TemporaryDirectory() as directory:
            result = tool_runner(Path(directory), target, 'real')
        self.assertEqual('NOT_CONFIGURED', result[0]['status'])
        self.assertEqual([], result[0]['issues'])

    def test_once_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = {'sampleId': 'fixture', 'fullSource': 'contract C {}', 'modelSource': 'contract C {}',
                      'fullSourceHash': 'a' * 64, 'modelSourceHash': 'b' * 64, 'assignmentHash': 'c' * 64,
                      'formalLedgerHash': 'd' * 64, 'scope': 'FULL', 'lineStart': 1, 'lineEnd': 1,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f', 'groupId': 'g', 'researchEligible': False}
            calls = []
            preview = {'snapshotId': 's' * 64, 'collection': 's1b_'+'f'*32, 'sourceHash': 'a'*64,
                       'modelSourceHash': 'b'*64, 'pool': {}, 'facts': {'facts': []},
                       'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': ''}}
            def model(*args):
                calls.append('model')
                return {'status': 'COMPLETED', 'conclusion': 'NO_CONFIRMED_FINDINGS',
                        'hypotheses': [], 'inputTokens': None, 'outputTokens': None}
            deps = RunDependencies(None, None, None, model, lambda *args: [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}])
            with patch('audit_run.load_target', return_value=target), patch('audit_run.preview', return_value=preview):
                result = run_once(root, 'fixture', 'offline', deps)
            self.assertEqual('COMPLETED', result['status'])
            self.assertEqual(['model'], calls)
            self.assertIsNone(result['model']['inputTokens'])
            self.assertEqual(result, replay(root, result['runId']))
            self.assertEqual(['model'], calls)
            run_dir = root / 'research-artifacts/runs/audits' / result['runId']
            self.assertEqual(1, len((run_dir / 'sample.jsonl').read_text().splitlines()))
            self.assertGreater(len((run_dir / 'events.jsonl').read_text().splitlines()), 2)
            (run_dir / 'plan.json').write_text('{}')
            with self.assertRaises(ValueError): replay(root, result['runId'])

    def test_failure_never_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            target = {'sampleId': 'fixture', 'fullSource': 'contract C {}', 'modelSource': 'contract C {}',
                      'fullSourceHash': 'a'*64, 'modelSourceHash': 'b'*64, 'assignmentHash': 'c'*64,
                      'formalLedgerHash': 'd'*64, 'scope': 'FULL', 'lineStart': 1, 'lineEnd': 1,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f', 'groupId': 'g', 'researchEligible': False}
            deps = RunDependencies(None, None, None, lambda *args: (_ for _ in ()).throw(RuntimeError('secret')),
                                   lambda *args: [])
            view = {'snapshotId': 's'*64, 'collection': 's1b_'+'f'*32, 'sourceHash': 'a'*64,
                    'modelSourceHash': 'b'*64, 'pool': {}, 'facts': {'facts': []},
                    'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': ''}}
            with patch('audit_run.load_target', return_value=target), patch('audit_run.preview', return_value=view):
                result = run_once(Path(directory), 'fixture', 'offline', deps)
            self.assertEqual('FAILED', result['status'])
            self.assertEqual('UNRESOLVED', result['conclusion'])
            self.assertNotIn('secret', str(result))
            diagnostic_deps = RunDependencies(None, None, None,
                lambda *args: {'status': 'FAILED', 'errorCategory': 'MODEL_OUTPUT_INVALID',
                               'validationIssue': 'CONTRACT_MISMATCH', 'inputTokens': 8,
                               'outputTokens': 4, 'requestConsumptionReceipt': {'factGuidance': {'text': '事实原文'}},
                               '_rawResponse': 'private diagnostic'},
                lambda *args: [{'engine': 'SLITHER', 'status': 'SKIPPED', 'issues': []}])
            with patch('audit_run.load_target', return_value=target), patch('audit_run.preview', return_value=view):
                diagnostic_result = run_once(Path(directory), 'fixture', 'offline', diagnostic_deps)
            self.assertEqual('CONTRACT_MISMATCH', diagnostic_result['model']['validationIssue'])
            self.assertEqual({'factGuidance': {'text': '事实原文'}},
                             diagnostic_result['model']['requestConsumptionReceipt'])
            self.assertEqual(diagnostic_result, replay(Path(directory), diagnostic_result['runId']))
            self.assertNotIn('private diagnostic', str(diagnostic_result))
            self.assertEqual('private diagnostic', (Path(directory) / 'research-artifacts/runs/audits' /
                diagnostic_result['runId'] / 'raw-response.txt').read_text())

    def test_source_change_before_model_rejects_without_request(self):
        with tempfile.TemporaryDirectory() as directory:
            target = {'sampleId': 'fixture', 'fullSource': 'contract C {}', 'modelSource': 'contract C {}',
                      'fullSourceHash': 'a'*64, 'modelSourceHash': 'b'*64, 'assignmentHash': 'c'*64,
                      'formalLedgerHash': 'd'*64, 'scope': 'FULL', 'lineStart': 1, 'lineEnd': 1,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f', 'groupId': 'g', 'researchEligible': False}
            changed = {**target, 'fullSourceHash': 'e'*64}
            view = {'snapshotId': 's'*64, 'collection': 's1b_'+'f'*32, 'sourceHash': 'a'*64,
                    'modelSourceHash': 'b'*64, 'pool': {}, 'facts': {'facts': []},
                    'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': ''}}
            calls = []
            deps = RunDependencies(None, None, None, lambda *args: calls.append(1), lambda *args: [])
            with patch('audit_run.load_target', side_effect=[target, changed]), patch('audit_run.preview', return_value=view):
                with self.assertRaises(ValueError): run_once(Path(directory), 'fixture', 'offline', deps)
            self.assertEqual([], calls)

    def test_长源码不受本地输入上限阻断(self):
        with tempfile.TemporaryDirectory() as directory:
            target = {'sampleId': 'fixture', 'fullSource': 'contract C {}', 'modelSource': 'x'*9900,
                      'fullSourceHash': 'a'*64, 'modelSourceHash': 'b'*64, 'assignmentHash': 'c'*64,
                      'formalLedgerHash': 'd'*64, 'scope': 'FUNCTION', 'lineStart': 1, 'lineEnd': 1,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f', 'groupId': 'g', 'researchEligible': False}
            view = {'snapshotId': 's'*64, 'collection': 's1b_'+'f'*32, 'sourceHash': 'a'*64,
                    'modelSourceHash': 'b'*64, 'pool': {}, 'facts': {'facts': []},
                    'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': 'y'*2048}}
            calls = []
            deps = RunDependencies(None, None, None, lambda *args: calls.append(1) or {
                'status': 'COMPLETED', 'conclusion': 'NO_CONFIRMED_FINDINGS', 'hypotheses': [],
                'inputTokens': None, 'outputTokens': None}, lambda *args: [])
            with patch('audit_run.load_target', return_value=target), patch('audit_run.preview', return_value=view):
                result = run_once(Path(directory), 'fixture', 'offline', deps)
            self.assertEqual([1], calls)
            self.assertIsNone(result['plan']['maxInputBytes'])
            self.assertGreater(result['plan']['actualInputBytes'], 10_000)

    def test_真实模型入口保留全文并启用思考(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config/providers.local.properties'
            config.parent.mkdir()
            config.write_text('providers.ark.base-url=https://ark.cn-beijing.volces.com/api/plan/v3\n'
                              'providers.ark.model=deepseek-v4-flash\nproviders.ark.api-key=fixture\n')
            source = 'contract C {\n' + ' uint value;\n' * 3000 + '}'
            target = {'fullSource': source, 'fullSourceHash': 'a' * 64, 'modelSource': source,
                      'scope': 'FULL', 'lineStart': 1, 'lineEnd': 3002,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f'}
            view = {'d1': {'selected': [], 'context': ''}}
            catalog = {'sourceHash': 'a' * 64, 'operations': [{'contract': 'Other', 'riskOperation': 'WRITE'}]}
            view.update(riskCatalog=catalog, discoveryCompilation={'fixture': True})
            def capture(command, **kwargs):
                request = decode(Path(command[command.index('--request') + 1]).read_bytes())
                self.assertEqual(catalog, request['riskCatalog'])
                self.assertEqual(source, request['modelSource'])
                self.assertEqual(source.encode(), Path(command[command.index('--source') + 1]).read_bytes())
                properties = Path(command[command.index('--config') + 1]).read_text()
                self.assertIn('providers.ark.max-retries=0', properties)
                self.assertIn('providers.ark.thinking=enabled', properties)
                self.assertIn('providers.ark.reasoning-effort=low', properties)
                self.assertIn(f'providers.ark.max-output-tokens={EXPERIMENT_MAX_OUTPUT_TOKENS}', properties)
                self.assertIn('providers.ark.timeout-seconds=360', properties)
                return SimpleNamespace(returncode=0, stdout=b'{"status":"COMPLETED","conclusion":"NO_CONFIRMED_FINDINGS"}')
            with patch('audit_run.subprocess.run', side_effect=capture), \
                    patch('risk_catalog.load_risk_catalog', return_value=catalog):
                self.assertEqual('COMPLETED', model_runner(root, target, view, 'real')['status'])
            with patch('audit_run.subprocess.run') as launch, \
                    patch('risk_catalog.load_risk_catalog', return_value={**catalog, 'sourceHash': 'b' * 64}):
                with self.assertRaisesRegex(ValueError, '发生变化'):
                    model_runner(root, target, view, 'real')
                launch.assert_not_called()


if __name__ == '__main__': unittest.main()
