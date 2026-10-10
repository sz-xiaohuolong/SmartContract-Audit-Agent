"""冻结配置的消费、凭证清理及执行前漂移回归。"""
import json
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_run import tool_runner
from audit_workbench import AuditWorkbench
from mvp_runtime import _configuration_values
from test_audit_workbench import Runtime, SOURCE


class ConfigurationTest(unittest.TestCase):
    def test_空白环境凭证拒绝且冻结后不保留环境回退(self):
        text = ('providers.ark.base-url=https://ark.cn-beijing.volces.com/api/plan/v3\n'
                'providers.ark.model=deepseek-v4-flash\nproviders.ark.api-key-env=S9_FIXTURE_KEY\n')
        with self.assertRaises(ValueError):
            _configuration_values(text, {'S9_FIXTURE_KEY': ' \t\n'})
        values = _configuration_values(text, {'S9_FIXTURE_KEY': 'fixture-env-A'})
        self.assertEqual('fixture-env-A', values['providers.ark.api-key'])
        self.assertNotIn('providers.ark.api-key-env', values)

    def test_配置不允许冒号覆写转义键或反斜杠续行(self):
        normal = ('providers.ark.base-url=https://ark.cn-beijing.volces.com/api/plan/v3\n'
                  'providers.ark.model=deepseek-v4-flash\nproviders.ark.api-key=fixture-only\n')
        for extra in ('providers.ark.base-url:https://example.test\n',
                      'providers.ark.base\\u002durl=https://example.test\n',
                      'providers.ark.api-key=fixture-\\u0041\n', 'irrelevant=end\\'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                _configuration_values(normal + extra)

    def test_模型等待期间配置变化仍消费冻结配置并清理凭证(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'S9_FIXTURE_KEY': 'fixture-env-A'}):
            root = Path(directory)
            config = root / 'config'
            config.mkdir()
            (config / 'providers.local.properties').write_text(
                'providers.ark.base-url=https://ark.cn-beijing.volces.com/api/plan/v3\n'
                'providers.ark.model=deepseek-v4-flash\nproviders.ark.api-key-env=S9_FIXTURE_KEY\n')
            tools = config / 'tools.local.properties'
            compiler = root / 'solc-fixture'
            compiler.write_text('#!/bin/sh\necho "Version: 0.8.24+fixture"\n')
            compiler.chmod(0o700)
            tool_a, tool_b = root / 'tool-a', root / 'tool-b'
            for script in (tool_a, tool_b):
                script.write_text('#!/bin/sh\necho "fixture tool 1.0"\n')
                script.chmod(0o700)
            tools.write_text(f'tools.slither.executable={tool_a}\ntools.slither.solc={compiler}\n')
            runtime = Runtime()
            consumed = []
            private_paths = []
            def model(root, target, view, mode):
                provider_path = Path(target['_providerConfigPath'])
                private_paths.append(provider_path)
                self.assertEqual(0o600, provider_path.stat().st_mode & 0o777)
                self.assertIn('providers.ark.api-key=', provider_path.read_text())
                os.environ['S9_FIXTURE_KEY'] = 'fixture-env-B'
                tools.write_text(f'tools.slither.executable={tool_b}\n')
                return runtime.model(root, target, view, mode)
            runtime.model_runner = model
            original_process = subprocess.run
            def process(command, **kwargs):
                if command[0] != 'java':
                    return original_process(command, **kwargs)
                path = Path(command[command.index('--config') + 1])
                private_paths.append(path)
                self.assertEqual(0o600, path.stat().st_mode & 0o777)
                consumed.append(path.read_text().encode().decode('unicode_escape'))
                source = Path(command[command.index('--source') + 1]).read_bytes()
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    'engine': 'SLITHER', 'status': 'OK', 'issues': [], 'durationMs': 0,
                    'configHash': 'a' * 64,
                    'sourceHash': hashlib.sha256(source).hexdigest(), 'sourceFile': 'Contract.sol',
                    'compiler': {'path': str(compiler.resolve()), 'version': '0.8.24',
                                 'sha256': hashlib.sha256(compiler.read_bytes()).hexdigest()}}).encode(), b'')
            workbench = AuditWorkbench(root, runtime_factory=lambda profile: runtime,
                                       target_loader=lambda: [], tool=tool_runner)
            choice = {'source': SOURCE, 'mechanism': 'REENTRANCY', 'function': 'withdraw', 'mode': 'real'}
            preview = workbench.preview(choice)
            prepared = workbench.prepare({**choice, 'planHash': preview['planHash']})
            with patch('audit_run.subprocess.run', side_effect=process):
                result = workbench.execute(prepared)
            self.assertEqual('COMPLETED', result['status'], result)
            self.assertEqual(1, len(consumed))
            self.assertIn(f'tools.slither.executable={tool_a.resolve()}\n', consumed[0])
            self.assertIn(f'tools.slither.solc={compiler.resolve()}\n', consumed[0])
            self.assertTrue(all(not path.exists() for path in private_paths))
            self.assertNotIn('fixture-env-', str(result))
            self.assertNotIn('_providerConfigPath', str(result))
            self.assertNotIn('_toolConfigPath', str(result))
            self.assertNotIn('_configuration', prepared)
            for path in (workbench.store / result['runId']).iterdir():
                self.assertNotIn('fixture-env-', path.read_text())
            self.assertEqual(result, workbench.read(result['runId']))


if __name__ == '__main__':
    unittest.main()
