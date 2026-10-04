"""工程 MVP 的离线、确定性回归。"""
import unittest
from unittest.mock import patch
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import mvp_runtime


class FakeIndex:
    def __init__(self, rows):
        self.rows = rows
        self.name = None

    def build(self, name, payload):
        self.name = name
        self.rows = payload['rows']

    def read(self, name):
        if name != self.name:
            raise ValueError('集合不存在')
        return self.rows

    def search(self, name, query, limit):
        if name != self.name:
            raise ValueError('集合不存在')
        return [{'id': row['id'], 'distance': 1.0} for row in self.rows[:limit]]


class MvpRuntimeTest(unittest.TestCase):
    def test_failed_reply_keeps_local_raw_diagnostic_without_retry(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sources').mkdir()
            source = 'contract C {}'
            (root / 'sources/AC-ASE-006.sol').write_text(source, encoding='utf-8')
            source_hash = hashlib.sha256(source.encode()).hexdigest()
            (root / 'intake.json').write_text(json.dumps({'cases': [{'id': 'AC-ASE-006', 'sourceSha256': source_hash}]}))
            config = root / 'config.properties'
            config.write_text('fixture=value\n')
            calls = []
            def executor(command):
                calls.append(1)
                provider_config = Path(command[command.index('--config') + 1]).read_text()
                self.assertIn('providers.ark.response-format=json_schema', provider_config)
                self.assertIn('providers.ark.thinking=disabled', provider_config)
                diagnostic = Path(command[command.index('--diagnostic-output') + 1])
                diagnostic.write_text('{"hasVulnerability":false}', encoding='utf-8')
                result = {'status': 'FAILED', 'conclusion': 'UNRESOLVED', 'sourceHash': source_hash,
                          'inputTokens': 12, 'outputTokens': 8, 'errorCategory': 'MODEL_OUTPUT_INVALID'}
                return SimpleNamespace(returncode=1, stdout=json.dumps(result).encode())
            with patch.object(mvp_runtime, 'INTAKE', mvp_runtime.ROOT / 'intake.json'), \
                    patch.object(mvp_runtime, 'SOURCE_DIR', 'sources'), \
                    patch.object(mvp_runtime, '_config_values', return_value={
                        'providers.ark.model': 'deepseek-v4-flash',
                        'providers.ark.base-url': 'https://ark.cn-beijing.volces.com/api/plan/v3'}), \
                    patch.object(mvp_runtime, 'active', return_value=({'snapshotId': 's', 'collection': 'c'}, {}, None)), \
                    patch.object(mvp_runtime, 'select_context', return_value=('案例', ['d'])):
                report = mvp_runtime.run_once(root=root, config=config, jar=root / 'fake.jar', executor=executor)
            self.assertEqual(calls, [1])
            self.assertEqual(report['status'], 'FAILED')
            self.assertEqual(report['plan']['responseFormat'], 'json_schema_strict')
            self.assertEqual((root / '.local/mvp-runs' / report['plan']['runId'] / 'raw-response.txt').read_text(),
                             '{"hasVulnerability":false}')
    def test_embedding_is_deterministic_and_normalized(self):
        first = mvp_runtime.embed('function claimRewards address sender')
        self.assertEqual(first, mvp_runtime.embed('function claimRewards address sender'))
        self.assertEqual(len(first), 128)
        self.assertAlmostEqual(sum(value * value for value in first), 1, places=5)
        with self.assertRaises(ValueError):
            mvp_runtime.embed('   ')

    def test_snapshot_only_activates_after_complete_readback(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        docs = [{'id': 'one', 'document': {'id': 'one', 'text': 'a'}, 'vector': mvp_runtime.embed('a')},
                {'id': 'two', 'document': {'id': 'two', 'text': 'b'}, 'vector': mvp_runtime.embed('b')}]
        payload = {'purpose': 'ENGINEERING_MVP', 'researchEligible': False,
                   'embedding': {'dimension': 128}, 'rows': docs}
        class BrokenIndex(FakeIndex):
            def read(self, name):
                return self.rows[:1]
        with TemporaryDirectory() as directory, patch.object(mvp_runtime, 'candidate_payload', return_value=payload):
            store = Path(directory) / 'store'
            with self.assertRaises(ValueError):
                mvp_runtime.build(root=directory, store=store, index=BrokenIndex([]))
            self.assertFalse((store / 'active.json').exists())
            index = FakeIndex([])
            pointer = mvp_runtime.build(root=directory, store=store, index=index)
            self.assertEqual(pointer['documentCount'], 2)
            self.assertEqual(mvp_runtime.active(root=directory, store=store, index=index)[0], pointer)

    def test_context_never_exceeds_hard_limit(self):
        rows = []
        for number in range(3):
            rows.append({'id': str(number), 'document': {'id': str(number), 'role': 'VULNERABLE',
                         'groupId': 'g', 'text': 'contract A ' * 90}})
        index = FakeIndex(rows)
        index.name = 'mvp_' + 'a' * 32
        context, selected = mvp_runtime.select_context('contract A', {'collection': index.name}, {'rows': rows}, index)
        self.assertLessEqual(len(context.encode('utf-8')), 2048)
        self.assertEqual(selected, ['0', '1'])


if __name__ == '__main__':
    unittest.main()
