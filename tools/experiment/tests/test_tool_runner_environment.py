"""工具执行必须消费与缓存身份相同的固定编译环境。"""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_run import tool_runner
from tool_environment import resolve_environment


SOURCE = 'pragma solidity ^0.8.20; contract C { uint x; function f() public { x = 1; } }'


class ToolRunnerEnvironmentTest(unittest.TestCase):
    def setup_tools(self, root):
        compiler = root / 'solc-fixture'
        compiler.write_text('#!/bin/sh\necho "Version: 0.8.24+fixture"\n')
        compiler.chmod(0o700)
        engine = root / 'slither-fixture'
        engine.write_text('#!/bin/sh\necho local-fixture\n')
        engine.chmod(0o700)
        config = root / 'config/tools.local.properties'
        config.parent.mkdir()
        config.write_text(f'tools.slither.executable={engine}\ntools.slither.solc={compiler}\n')
        return config, compiler

    def test_执行网关使用选定编译器并绑定源码配置(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config, compiler = self.setup_tools(root)
            source_hash = hashlib.sha256(SOURCE.encode()).hexdigest()
            seen = []
            # 编译器探测保留真实本地子进程；仅以夹具代替 Java 网关。
            original = subprocess.run
            def process(command, **kwargs):
                if command[0] != 'java':
                    return original(command, **kwargs)
                selected = Path(command[command.index('--config') + 1])
                seen.append(selected.read_text())
                self.assertEqual(0o600, selected.stat().st_mode & 0o777)
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    'engine': 'SLITHER', 'status': 'OK', 'issues': [],
                    'sourceHash': source_hash, 'sourceFile': 'Contract.sol',
                    'configHash': 'java-configuration', 'compiler': {
                        'path': str(compiler.resolve()), 'version': '0.8.24',
                        'sha256': hashlib.sha256(compiler.read_bytes()).hexdigest()}}).encode(), b'')
            with patch('audit_run.subprocess.run', side_effect=process):
                result = tool_runner(root, {'fullSource': SOURCE, 'fullSourceHash': source_hash}, 'real')
            self.assertEqual(1, len(seen))
            self.assertIn(f'tools.slither.solc={compiler.resolve()}', seen[0].encode().decode('unicode_escape'))
            self.assertEqual('0.8.24', result[0]['environment']['compiler']['version'])
            self.assertEqual(resolve_environment(SOURCE, config)['configHash'], result[0]['configHash'])
            self.assertEqual(source_hash, result[0]['sourceHash'])
            self.assertEqual('java-configuration', result[0]['executionConfigHash'])

    def test_网关实际编译器偏离已绑定环境不得接受(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.setup_tools(root)
            source_hash = hashlib.sha256(SOURCE.encode()).hexdigest()
            original = subprocess.run
            def process(command, **kwargs):
                if command[0] != 'java': return original(command, **kwargs)
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    'engine': 'SLITHER', 'status': 'OK', 'issues': [], 'sourceHash': source_hash,
                    'compiler': {'path': '/different-solc', 'version': '0.8.25', 'sha256': '0'*64},
                    'configHash': 'actual-configuration'}).encode(), b'')
            with patch('audit_run.subprocess.run', side_effect=process):
                result = tool_runner(root, {'fullSource': SOURCE}, 'real')
            self.assertEqual('PROCESS_ERROR', result[0]['status'])
            self.assertEqual('ENVIRONMENT_CHANGED', result[0].get('errorCategory'))

    def test_执行期间依赖改变不能封口成功缓存(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config, compiler = self.setup_tools(root)
            dependency = root / 'dependencies'
            dependency.mkdir()
            library = dependency / 'Library.sol'
            library.write_text('library Library {}')
            with config.open('a') as output:
                output.write(f'tools.slither.solc-remaps=lib/={dependency}\n')
            source_hash = hashlib.sha256(SOURCE.encode()).hexdigest()
            original = subprocess.run
            def process(command, **kwargs):
                if command[0] != 'java': return original(command, **kwargs)
                library.write_text('library Library { function f() internal {} }')
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    'engine': 'SLITHER', 'status': 'OK', 'issues': [{'check': 'fixture'}],
                    'sourceHash': source_hash, 'configHash': 'a'*64,
                    'compiler': {'path': str(compiler.resolve()), 'version': '0.8.24',
                        'sha256': hashlib.sha256(compiler.read_bytes()).hexdigest()}}).encode(), b'')
            with patch('audit_run.subprocess.run', side_effect=process):
                result = tool_runner(root, {'fullSource': SOURCE}, 'real')
            self.assertEqual('PROCESS_ERROR', result[0]['status'])
            self.assertEqual('ENVIRONMENT_CHANGED', result[0].get('errorCategory'))
            self.assertEqual([], result[0]['issues'])

    def test_源码或环境改变在执行网关前拒绝(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config, compiler = self.setup_tools(root)
            environment = resolve_environment(SOURCE, config)
            compiler.write_text('#!/bin/sh\necho "Version: 0.8.25+changed"\n')
            result = tool_runner(root, {'fullSource': SOURCE, '_toolEnvironment': environment}, 'real')
            self.assertEqual('ENVIRONMENT_CHANGED', result[0].get('errorCategory'))
            result = tool_runner(root, {'fullSource': SOURCE, 'fullSourceHash': '0' * 64}, 'real')
            self.assertEqual('SOURCE_HASH_MISMATCH', result[0].get('errorCategory'))

    def test_版本不匹配保留具体诊断且不假装跳过(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.setup_tools(root)
            source = SOURCE.replace('^0.8.20', '0.5.8')
            result = tool_runner(root, {'fullSource': source}, 'real')
            self.assertEqual('COMPILER_MISMATCH', result[0].get('errorCategory'))
            self.assertEqual('PROCESS_ERROR', result[0]['status'])
            self.assertTrue(result[0]['environment']['diagnostics'])

    def test_导入依赖交给固定工具环境解析(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.setup_tools(root)
            source = SOURCE.replace('contract C', 'import "missing.sol"; contract C')
            source_hash = hashlib.sha256(source.encode()).hexdigest()
            original = subprocess.run
            def process(command, **kwargs):
                if command[0] != 'java': return original(command, **kwargs)
                return subprocess.CompletedProcess(command, 1, json.dumps({
                    'engine': 'SLITHER', 'status': 'PROCESS_ERROR', 'issues': [],
                    'sourceHash': source_hash, 'errorCategory': 'DEPENDENCY_MISSING'}).encode(), b'')
            with patch('audit_run.subprocess.run', side_effect=process):
                result = tool_runner(root, {'fullSource': source}, 'real')
            self.assertEqual('DEPENDENCY_MISSING', result[0].get('errorCategory'))


if __name__ == '__main__': unittest.main()
