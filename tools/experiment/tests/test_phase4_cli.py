"""用本地假模型走完整命令行，核对请求计数、冻结与失败停止。"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from verirag.experiments.r3_cli import DEFAULT_TARGETS, main
from verirag.experiments.r3_protocol import condition_target, condition_view
from verirag.infrastructure.storage import atomic_json, fingerprint


class Phase4CliTest(unittest.TestCase):
    def execute(self, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config'; config.mkdir()
            (config / 'providers.local.properties').write_text(
                'providers.ark.base-url=https://ark.cn-beijing.volces.com/api/coding/v3\n'
                'providers.ark.model=deepseek-v4-flash\nproviders.ark.api-key=fixture-only\n')
            (config / 'tools.local.properties').write_text('fixture=true\n')
            store = root / 'research-artifacts/snapshots/nomic'
            (store / 'catalogs').mkdir(parents=True)
            (root / '.local').mkdir()
            snapshot = {'fixture': True}; snapshot_id = fingerprint(snapshot)
            pointer = {'snapshot_id': snapshot_id}
            atomic_json(store / 'active.json', pointer)
            atomic_json(store / 'catalogs' / (snapshot_id + '.json'), {})
            source_hash = hashlib.sha256(b'contract C {}').hexdigest()
            target = {'sampleId': DEFAULT_TARGETS[0], 'runnable': True, 'sourceHash': source_hash,
                      'groundTruth': {'hasVulnerability': True, 'labelSource': '夹具'}}
            base = {'pool': {'candidates': []}, 'd1': {'context': '历史知识', 'selected': []}}
            runtime = SimpleNamespace(store=store, pointer=pointer, catalog={}, preview=lambda target: base)
            calls = []
            def model(root, target, view, mode):
                if mode == 'real':
                    calls.append((view['strategy'], target['factGuidanceEnabled']))
                    self.assertEqual(0o600, Path(target['_providerConfigPath']).stat().st_mode & 0o777)
                receipt = {'requestSha256': hashlib.sha256(view['strategy'].encode()).hexdigest(),
                    'sourceHash': source_hash, 'modelSourceHash': source_hash,
                    'contextSha256': hashlib.sha256(view['d1']['context'].encode()).hexdigest(),
                    'evidenceIds': [], 'requestAttempts': int(mode == 'real')}
                if target['factGuidanceEnabled']:
                    receipt['factGuidance'] = {'textSha256': '相同事实'}
                failed = fail and mode == 'real'
                return {'status': 'FAILED' if failed else 'COMPLETED',
                    'requestConsumptionReceipt': receipt, 'requestAttempts': int(mode == 'real')}
            def run(target, strategy, mode):
                current, _ = condition_target(target, strategy)
                view = condition_view(base, strategy)
                model_result = runtime.model_runner(root, current, view, mode)
                failed = model_result['status'] == 'FAILED'
                return {'status': model_result['status'], 'prediction': 'UNKNOWN' if failed else 'REPORT',
                    'model': model_result, 'poolHash': view['poolHash'], 'retrieval': view,
                    'inputTokens': None, 'outputTokens': None, 'd2': {'verdict': 'UNKNOWN'}}
            runtime.run = run
            args = ['r3_cli', '--phase4', '--execute', '--allow-unreviewed', '--sample-ids', target['sampleId'],
                    '--batch-id', '1' * 32, '--preflight-output', 'preflight.json']
            with patch('verirag.experiments.r3_cli.Path.cwd', return_value=root), patch('verirag.experiments.r3_cli.prepare_runtime', return_value=([target], runtime)), \
                 patch('verirag.experiments.r3_cli._configuration', return_value={}), patch('verirag.experiments.r3_cli._code_identity', return_value={'artifactHash': 'a' * 64}), \
                 patch('verirag.experiments.r3_cli.prepare_model_context'), patch('verirag.experiments.r3_cli.model_runner', side_effect=model), \
                 patch('verirag.experiments.r3_cli.verify_snapshot', return_value=snapshot), patch('sys.argv', args), \
                 contextlib.redirect_stdout(io.StringIO()):
                main()
            batch = root / 'research-artifacts/runs/benchmarks' / ('1' * 32)
            summary = json.loads((batch / 'summary.json').read_text())
            complete = json.loads((batch / 'execution-complete.json').read_text())
            return calls, summary, complete

    def test_完整CLI按四条件只调用四次并通过消费比较(self):
        calls, summary, complete = self.execute()
        self.assertEqual([('P4_BASELINE', False), ('P4_FACTS', True), ('P4_D1', False), ('P4_FACTS_D1', True)], calls)
        self.assertEqual(4, summary['denominators']['completed'])
        self.assertEqual([], summary['comparisonAudit'])
        self.assertEqual(4, complete['paidUnitsAttempted'])
        self.assertIsNone(complete['stopped'])

    def test_首次模型失败后其余三条件零调用且保留分母(self):
        calls, summary, complete = self.execute(fail=True)
        self.assertEqual(1, len(calls))
        self.assertEqual(4, summary['denominators']['planned'])
        self.assertEqual(4, summary['denominators']['failed'])
        self.assertEqual(1, complete['paidUnitsAttempted'])
        self.assertIsNotNone(complete['stopped'])
