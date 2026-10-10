"""固定本机编译器选择与环境绑定的离线验证。"""

import hashlib
import tempfile
import unittest
import os
from unittest.mock import patch
from pathlib import Path

try:
    from tool_environment import resolve_environment
except ModuleNotFoundError as error:
    if error.name != 'tool_environment':
        raise
    resolve_environment = None


class ToolEnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def compiler(self, version, body=None):
        binary = self.directory / ('solc-' + version) / ('solc-' + version)
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text(body or '#!/bin/sh\nprintf "Version: ' + version + '+commit.fixture\\n"\n')
        binary.chmod(0o755)
        return binary

    def resolve(self, source, config=None):
        self.assertIsNotNone(resolve_environment, '缺少固定编译器环境解析接口')
        try:
            return resolve_environment(source, config=config, compiler_dir=self.directory)
        except Exception as error:
            self.fail('环境解析应返回明确状态而不是抛出 ' + type(error).__name__)

    def test_selects_highest_compiler_satisfying_every_caret_pragma(self):
        self.compiler('0.4.18')
        selected = self.compiler('0.4.25')
        self.compiler('0.5.17')
        source = 'pragma solidity ^0.4.0; pragma solidity ^0.4.20; contract C {}'
        result = self.resolve(source)
        self.assertEqual('OK', result['status'])
        self.assertIsNone(result['errorCategory'])
        self.assertEqual(str(selected.resolve()), result['compiler']['path'])
        self.assertEqual('0.4.25', result['compiler']['version'])
        self.assertEqual(hashlib.sha256(selected.read_bytes()).hexdigest(), result['compiler']['sha256'])
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), result['sourceHash'])

    def test_intersects_ranges_with_exact_versions_and_ignores_comments_and_strings(self):
        selected = self.compiler('0.4.25')
        self.compiler('0.4.26')
        source = '''// pragma solidity ^0.8.0;
pragma solidity >= 0.4.20 < 0.5.0;
pragma solidity =0.4.25;
contract C { string label = "pragma solidity 0.8.30;"; }
/* pragma solidity 0.3.0; */'''
        result = self.resolve(source)
        self.assertEqual('OK', result['status'])
        self.assertEqual(str(selected.resolve()), result['compiler']['path'])

    def test_zero_minor_caret_cannot_choose_next_patch(self):
        self.compiler('0.0.3')
        self.compiler('0.0.4')
        self.assertEqual('0.0.3', self.resolve('pragma solidity ^0.0.3;')['compiler']['version'])

    def test_bare_exact_version_does_not_select_newer_patch(self):
        self.compiler('0.5.16')
        self.compiler('0.5.17')
        self.assertEqual('0.5.16', self.resolve('pragma solidity 0.5.16;')['compiler']['version'])

    def test_conflicting_pragmas_and_incompatible_installed_version_keep_error(self):
        self.compiler('0.4.25')
        for source in ('pragma solidity ^0.5.0;', 'pragma solidity ^0.4.0; pragma solidity >=0.5.0;'):
            with self.subTest(source=source):
                result = self.resolve(source)
                self.assertEqual('ERROR', result['status'])
                self.assertEqual('NO_MATCHING_COMPILER', result['errorCategory'])
                self.assertIsNone(result['compiler'])

    def test_no_pragma_requires_explicit_compiler_configuration(self):
        selected = self.compiler('0.8.30')
        result = self.resolve('contract C {}')
        self.assertEqual('NO_PRAGMA', result['errorCategory'])
        self.assertIsNone(result['compiler'])
        result = self.resolve('contract C {}', {'tools.slither.solc': str(selected)})
        self.assertEqual('OK', result['status'])
        self.assertEqual('0.8.30', result['compiler']['version'])

    def test_unsupported_or_incomplete_pragma_is_not_silently_ignored(self):
        self.compiler('0.4.25')
        for expression in ('~0.4.25', '0.4.*', '^0.4.0 || ^0.5.0', '>=0.4', '>=0.4.0 trailing'):
            with self.subTest(expression=expression):
                result = self.resolve('pragma solidity ' + expression + ';')
                self.assertEqual('UNSUPPORTED_PRAGMA', result['errorCategory'])
        self.assertEqual('UNSUPPORTED_PRAGMA', self.resolve('pragma solidity ^0.4.0')['errorCategory'])

    def test_explicit_compiler_must_match_constraints_and_exist(self):
        selected = self.compiler('0.8.30')
        result = self.resolve('pragma solidity ^0.4.0;', {'tools.slither.solc': str(selected)})
        self.assertEqual('COMPILER_MISMATCH', result['errorCategory'])
        self.assertEqual('0.8.30', result['compiler']['version'])
        result = self.resolve('pragma solidity ^0.4.0;', {'tools.slither.solc': str(self.directory / 'missing')})
        self.assertEqual('COMPILER_UNAVAILABLE', result['errorCategory'])

    def test_failed_probe_preserves_bounded_redacted_diagnostics(self):
        self.compiler('0.4.25', '#!/bin/sh\necho "api_key=fixture-secret https://user:password@example.invalid/?token=secret-token" >&2\nexit 7\n')
        result = self.resolve('pragma solidity ^0.4.0;')
        self.assertEqual('COMPILER_PROBE_FAILED', result['errorCategory'])
        serialized = str(result)
        for secret in ('fixture-secret', 'password', 'secret-token'):
            self.assertNotIn(secret, serialized)
        self.assertEqual(7, result['diagnostics'][0]['exitCode'])

    def test_config_hash_binds_unknown_configuration_and_actual_binary(self):
        selected = self.compiler('0.4.25')
        config = {'tools.slither.solc': str(selected), 'providers.ark.api-key': 'private-fixture',
                  'custom.future-setting': 'A'}
        first = self.resolve('pragma solidity ^0.4.0;', config)
        repeated = self.resolve('pragma solidity ^0.4.0;', dict(reversed(list(config.items()))))
        self.assertEqual(first['configHash'], repeated['configHash'])
        self.assertNotIn('private-fixture', str(first))
        self.assertNotIn('providers.ark.api-key', str(first['configSummary']))
        config['custom.future-setting'] = 'B'
        changed = self.resolve('pragma solidity ^0.4.0;', config)
        self.assertNotEqual(first['configHash'], changed['configHash'])
        selected.write_text(selected.read_text() + '# 二进制内容已变化\n')
        self.assertNotEqual(changed['configHash'], self.resolve('pragma solidity ^0.4.0;', config)['configHash'])

    def test_accepts_properties_file_and_reports_invalid_configuration(self):
        selected = self.compiler('0.4.25')
        config = self.directory / 'tools.properties'
        config.write_text('# 仅工具配置\ntools.slither.solc=' + str(selected) + '\n')
        self.assertEqual('OK', self.resolve('pragma solidity ^0.4.0;', config)['status'])
        self.assertEqual('CONFIG_ERROR', self.resolve('pragma solidity ^0.4.0;', 42)['errorCategory'])

    def test_empty_directory_is_unavailable_instead_of_using_global_default(self):
        result = self.resolve('pragma solidity ^0.4.0;')
        self.assertEqual('COMPILER_UNAVAILABLE', result['errorCategory'])

    def test_default_discovery_finds_preinstalled_solcx_binary(self):
        binary = self.directory / '.solcx' / 'solc-v0.4.25'
        binary.parent.mkdir()
        binary.write_text('#!/bin/sh\necho "Version: 0.4.25+commit.fixture"\n')
        binary.chmod(0o755)
        with patch('tool_environment.Path.home', return_value=self.directory):
            result = resolve_environment('pragma solidity 0.4.25;')
        self.assertEqual('OK', result['status'])
        self.assertEqual(str(binary.resolve()), result['compiler']['path'])

    def test_properties_reject_ambiguous_semantics_instead_of_loading_different_java_values(self):
        from tool_environment import _configuration
        config = self.directory / 'tools.properties'
        for text in ('tools.slither.executable=A\ntools.slither.executable=B\n',
                     'tools.slither.executable=A\\\n B\n', 'tools.slither.executable=C\\:\\folder\n',
                     'tools\\.slither.executable=A\n', 'tools.slither.executable A\n'):
            with self.subTest(text=text):
                config.write_text(text)
                with self.assertRaises(ValueError):
                    _configuration(config)
        for config in ({'tools.slither.executable': 42}, {42: 'tool'}, {'custom': None},
                       {'tools\\.slither.executable': 'tool'}, {'x\ntools.slither.solc': 'tool'},
                       {'tools.slither.executable': 'tool\x00'}):
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    _configuration(config)

    def test_directory_or_nonexecutable_path_is_not_an_available_compiler(self):
        binary = self.compiler('0.4.25')
        binary.chmod(0o644)
        for path in (binary, self.directory):
            with self.subTest(path=path):
                result = self.resolve('pragma solidity ^0.4.0;', {'tools.slither.solc': str(path)})
                self.assertEqual('COMPILER_UNAVAILABLE', result['errorCategory'])

    def test_dependency_settings_accept_only_whitelisted_compiler_arguments_and_absolute_remaps(self):
        self.compiler('0.4.25')
        directory = str(self.directory.resolve())
        config = {'tools.slither.solc-remaps': 'lib/=' + directory,
                  'tools.slither.solc-args': '--base-path ' + directory + ' --include-path ' + directory + ' --optimize'}
        result = self.resolve('pragma solidity ^0.4.0;', config)
        self.assertEqual('OK', result['status'])
        self.assertEqual(config, result['configSummary'])
        for value in ('--output-dir /tmp/unapproved', '--base-path relative', '--optimize; curl remote',
                      '--optimize-runs invalid', '--include-path /not-installed'):
            with self.subTest(value=value):
                self.assertEqual('CONFIG_ERROR', self.resolve('pragma solidity ^0.4.0;',
                    {'tools.slither.solc-args': value})['errorCategory'])
        self.assertEqual('CONFIG_ERROR', self.resolve('pragma solidity ^0.4.0;',
            {'tools.slither.solc-remaps': 'lib/=relative'})['errorCategory'])

    def test_probe_cache_reuses_only_same_path_binary_and_configuration(self):
        counter = self.directory / 'probe-count'
        selected = self.compiler('0.4.25', '#!/bin/sh\necho probe >> "' + str(counter)
            + '"\necho "Version: 0.4.25+commit.fixture"\n')
        first = self.resolve('pragma solidity ^0.4.0;')
        repeated = self.resolve('pragma solidity ^0.4.20;')
        self.assertEqual(1, len(counter.read_text().splitlines()))
        self.assertTrue(repeated['diagnostics'][0]['probeCached'])
        self.assertEqual(first['compiler'], repeated['compiler'])
        selected.write_text(selected.read_text() + '# 字节已变化\n')
        changed = self.resolve('pragma solidity ^0.4.0;')
        self.assertEqual(2, len(counter.read_text().splitlines()))
        self.assertNotEqual(first['compiler']['sha256'], changed['compiler']['sha256'])
        self.resolve('pragma solidity ^0.4.0;', {'custom': 'changed'})
        self.assertEqual(3, len(counter.read_text().splitlines()))

    def test_compiler_changed_during_probe_is_unavailable_and_never_cached(self):
        binary = self.compiler('0.4.25', '#!/bin/sh\necho "Version: 0.4.25+commit.fixture"\necho "# 已改变" >> "$0"\n')
        before = hashlib.sha256(binary.read_bytes()).hexdigest()
        result = self.resolve('pragma solidity ^0.4.0;')
        self.assertEqual('ERROR', result['status'])
        self.assertEqual('ENVIRONMENT_CHANGED', result['errorCategory'])
        self.assertIsNone(result['compiler'])
        self.assertEqual(before, result['diagnostics'][0]['beforeSha256'])
        self.assertNotEqual(before, result['diagnostics'][0]['afterSha256'])

    def test_named_tool_is_frozen_to_path_and_actual_binary_changes_configuration_hash(self):
        from tool_environment import _configuration
        self.compiler('0.4.25')
        tool = self.directory / 'fixture-slither'
        tool.write_text('#!/bin/sh\necho fixture-tool\n')
        tool.chmod(0o755)
        config = {'tools.slither.executable': 'fixture-slither'}
        with patch.dict(os.environ, {'PATH': str(self.directory)}):
            frozen = _configuration(config)
            first = self.resolve('pragma solidity ^0.4.0;', config)
            tool.write_text(tool.read_text() + '# 工具字节改变\n')
            changed = self.resolve('pragma solidity ^0.4.0;', config)
        self.assertEqual(str(tool.resolve()), frozen['tools.slither.executable'])
        self.assertEqual('fixture-slither', config['tools.slither.executable'])
        self.assertEqual(str(tool.resolve()), first['configSummary']['tools.slither.executable'])
        self.assertNotEqual(first['configHash'], changed['configHash'])

    def test_unresolved_named_tool_keeps_tool_unavailable_state(self):
        self.compiler('0.4.25')
        with patch.dict(os.environ, {'PATH': str(self.directory)}):
            result = self.resolve('pragma solidity ^0.4.0;', {'tools.slither.executable': 'missing-tool'})
        self.assertEqual('ERROR', result['status'])
        self.assertEqual('TOOL_UNAVAILABLE', result['errorCategory'])

    def test_dependency_file_bytes_change_configuration_binding_without_changing_paths(self):
        self.compiler('0.4.25')
        dependencies = self.directory / 'dependencies'
        dependencies.mkdir()
        imported = dependencies / 'Library.sol'
        imported.write_text('library Library { function value() internal returns(uint) { return 1; } }')
        config = {'tools.slither.solc-remaps': 'lib/=' + str(dependencies),
                  'tools.slither.solc-args': '--include-path ' + str(dependencies)}
        first = self.resolve('pragma solidity ^0.4.0; import "lib/Library.sol";', config)
        imported.write_text('library Library { function value() internal returns(uint) { return 2; } }')
        changed = self.resolve('pragma solidity ^0.4.0; import "lib/Library.sol";', config)
        self.assertEqual('OK', changed['status'])
        self.assertNotEqual(first['configHash'], changed['configHash'])
        self.assertEqual(1, changed['dependencies']['fileCount'])
        self.assertNotIn('return 2;', str(changed))

    def test_dependency_snapshot_rejects_oversized_source_instead_of_returning_partial_hash(self):
        self.compiler('0.4.25')
        dependencies = self.directory / 'dependencies'
        dependencies.mkdir()
        with (dependencies / 'Large.sol').open('wb') as source:
            source.truncate(5 * 1024 * 1024)
        result = self.resolve('pragma solidity ^0.4.0;',
            {'tools.slither.solc-args': '--include-path ' + str(dependencies)})
        self.assertEqual('ERROR', result['status'])
        self.assertEqual('DEPENDENCY_LIMIT', result['errorCategory'])
        self.assertIsNone(result['configHash'])

    def test_unreadable_dependency_directory_cannot_be_bound_as_empty(self):
        self.compiler('0.4.25')
        dependencies = self.directory / 'dependencies'
        blocked = dependencies / 'blocked'
        blocked.mkdir(parents=True)
        (blocked / 'Library.sol').write_text('library Library {}')
        blocked.chmod(0o000)
        self.addCleanup(blocked.chmod, 0o755)
        result = self.resolve('pragma solidity ^0.4.0;',
            {'tools.slither.solc-args': '--include-path ' + str(dependencies)})
        self.assertEqual('ERROR', result['status'])
        self.assertEqual('DEPENDENCY_UNAVAILABLE', result['errorCategory'])
        self.assertIsNone(result['configHash'])


if __name__ == '__main__':
    unittest.main()
