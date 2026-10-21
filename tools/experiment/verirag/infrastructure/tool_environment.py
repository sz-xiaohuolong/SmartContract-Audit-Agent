"""逐源码选择固定 solc；不修改全局编译器或安装任何依赖。"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import copy
import shutil
from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path


_SUMMARY_KEYS = {'tools.slither.executable', 'tools.slither.solc', 'tools.mythril.executable',
                 'tools.compiler.directory', 'tools.slither.timeout-seconds', 'tools.mythril.timeout-seconds',
                 'tools.slither.solc-remaps', 'tools.slither.solc-args'}
_MASKED_TEXT = re.compile(r'//[^\r\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
_CONSTRAINT = re.compile(r'(\^|>=|<=|>|<|=)?\s*(\d+)\.(\d+)\.(\d+)')
_SECRET_KEY = re.compile(r'api[-_]?key|token|secret|password|authorization', re.I)
_PROBE_CACHE = OrderedDict()


class _DependencyLimit(ValueError):
    """依赖扫描超过固定范围时保持未知，不生成部分配置摘要。"""


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _configuration(config):
    if config is None:
        return {}
    if isinstance(config, Mapping):
        values = dict(config)
    elif isinstance(config, (str, os.PathLike)):
        values = {}
        for line in Path(config).read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith(('#', '!')):
                key, separator, value = line.partition('=')
                key = key.strip()
                if not separator or '\\' in line or not re.fullmatch(r'[A-Za-z0-9_.-]+', key) or key in values:
                    raise ValueError('配置须使用无转义、无续行、无重复键的 key=value 格式')
                values[key] = value.strip()
    else:
        raise ValueError('配置必须是属性映射或文件路径')
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()):
        raise ValueError('配置键和值必须是字符串')
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+', key) or '\x00' in value for key, value in values.items()):
        raise ValueError('配置键须无转义或换行，配置值不能包含空字节')
    _validate_compilation_configuration(values)
    for key in ('tools.slither.executable', 'tools.mythril.executable'):
        value = values.get(key)
        if value:
            path = value if '/' in value else shutil.which(value)
            if path:
                values[key] = str(Path(path).expanduser().resolve())
    json.dumps(values, sort_keys=True, allow_nan=False)
    return values


def _validate_compilation_configuration(configuration):
    def directories(value):
        if any(not Path(path).is_absolute() or not Path(path).is_dir() for path in value.split(',')):
            raise ValueError('编译依赖路径须为已存在的绝对目录')

    arguments = configuration.get('tools.slither.solc-args', '').split()
    position = 0
    while position < len(arguments):
        argument = arguments[position]
        position += 1
        if argument == '--optimize':
            continue
        if argument not in {'--base-path', '--include-path', '--allow-paths', '--optimize-runs', '--evm-version'} or position == len(arguments):
            raise ValueError('编译参数不在白名单内或缺少值')
        value = arguments[position]
        position += 1
        if not re.fullmatch(r'[A-Za-z0-9_./@,:+-]+', value):
            raise ValueError('编译参数存在不支持的字符')
        if argument in {'--base-path', '--include-path', '--allow-paths'}:
            directories(value)
        elif argument == '--optimize-runs' and (not value.isdigit() or not 1 <= int(value) <= 1_000_000):
            raise ValueError('优化次数无效')
        elif argument == '--evm-version' and value not in {'homestead', 'tangerineWhistle', 'spuriousDragon',
                'byzantium', 'constantinople', 'petersburg', 'istanbul', 'berlin', 'london', 'paris',
                'shanghai', 'cancun', 'prague', 'osaka'}:
            raise ValueError('EVM 版本无效')
    for mapping in configuration.get('tools.slither.solc-remaps', '').split():
        prefix, separator, directory = mapping.partition('=')
        if not separator or not re.fullmatch(r'[A-Za-z0-9_./@:-]+', prefix) or not re.fullmatch(r'[A-Za-z0-9_./@:+-]+', directory):
            raise ValueError('remap 语法无效')
        directories(directory)


def _redact(value, configuration):
    text = str(value)
    for key, secret in configuration.items():
        if _SECRET_KEY.search(key) and isinstance(secret, str) and secret:
            text = text.replace(secret, '<redacted>')
    text = re.sub(r'(?i)(https?://)[^\s/@]+(?::[^\s/@]*)?@', r'\1<redacted>@', text)
    text = re.sub(r'(?i)\b(authorization\s*[:=]\s*(?:bearer\s+)?|bearer\s+)[^\s,;"\']+',
                  r'\1<redacted>', text)
    text = re.sub(r'(?i)((?:api[-_]?key|token|secret|password)["\']?\s*[=:]\s*["\']?)[^\s&,;"\']+',
                  r'\1<redacted>', text)
    return text


def _constraints(source):
    masked = _MASKED_TEXT.sub(lambda match: ' ' * len(match.group()), source)
    pragmas = re.findall(r'\bpragma\s+solidity\s+([^;]*);', masked)
    if len(pragmas) != len(re.findall(r'\bpragma\s+solidity\b', masked)):
        raise ValueError('存在未结束的 Solidity pragma')
    constraints = []
    for expression in pragmas:
        position, count = 0, 0
        while position < len(expression):
            if expression[position].isspace():
                position += 1
                continue
            match = _CONSTRAINT.match(expression, position)
            if not match:
                raise ValueError('存在未支持的 Solidity 版本表达式')
            operation = match.group(1) or '='
            version = tuple(map(int, match.groups()[1:]))
            if operation == '^':
                upper = ((version[0] + 1, 0, 0) if version[0] else
                         ((0, version[1] + 1, 0) if version[1] else (0, 0, version[2] + 1)))
                constraints.extend([('>=', version), ('<', upper)])
            else:
                constraints.append((operation, version))
            count += 1
            position = match.end()
        if not count:
            raise ValueError('版本表达式不能为空')
    return [expression.strip() for expression in pragmas], constraints


def _matches(version, constraints):
    for operation, expected in constraints:
        if not {'=': version == expected, '>=': version >= expected, '<=': version <= expected,
                '>': version > expected, '<': version < expected}[operation]:
            return False
    return True


def _probe_uncached(binary, configuration):
    start = time.monotonic()
    diagnostic = {'path': _redact(binary, configuration), 'status': 'START_ERROR', 'exitCode': None,
                  'durationMs': 0, 'stdout': '', 'stderr': '', 'truncated': False}
    try:
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                process = subprocess.run([str(binary), '--version'], stdout=stdout, stderr=stderr,
                                         timeout=3, check=False)
                diagnostic['exitCode'] = process.returncode
                diagnostic['status'] = 'OK' if process.returncode == 0 else 'NONZERO_EXIT'
            except subprocess.TimeoutExpired:
                diagnostic['status'] = 'TIMEOUT'
            for name, stream in (('stdout', stdout), ('stderr', stderr)):
                stream.seek(0)
                raw = stream.read(4097)
                diagnostic['truncated'] |= len(raw) > 4096
                diagnostic[name] = _redact(raw[:4096].decode('utf-8', errors='replace'), configuration)
        match = re.search(r'(?m)^\s*Version:\s*(\d+)\.(\d+)\.(\d+)(?:\+|\s|$)', diagnostic['stdout'])
        if diagnostic['status'] == 'OK' and match and not diagnostic['truncated']:
            version = tuple(map(int, match.groups()))
            compiler = {'path': str(binary), 'version': '.'.join(map(str, version)),
                        'sha256': _sha256(binary.read_bytes())}
            return (version, compiler), diagnostic
        if diagnostic['status'] == 'OK':
            diagnostic['status'] = 'INVALID_VERSION'
    except (OSError, ValueError):
        diagnostic['status'] = 'START_ERROR'
    finally:
        diagnostic['durationMs'] = int((time.monotonic() - start) * 1000)
    return None, diagnostic


def _probe(binary, configuration):
    try:
        binary_hash = _sha256(binary.read_bytes())
        config_hash = _sha256(json.dumps(configuration, sort_keys=True).encode('utf-8'))
        identity = (str(binary), binary_hash, config_hash)
    except OSError:
        return _probe_uncached(binary, configuration)
    if identity in _PROBE_CACHE:
        candidate, diagnostic = copy.deepcopy(_PROBE_CACHE[identity])
        _PROBE_CACHE.move_to_end(identity)
        diagnostic['probeCached'] = True
        return candidate, diagnostic
    candidate, diagnostic = _probe_uncached(binary, configuration)
    diagnostic['probeCached'] = False
    if candidate and candidate[1]['sha256'] != binary_hash:
        diagnostic['status'] = 'ENVIRONMENT_CHANGED'
        diagnostic['beforeSha256'] = binary_hash
        diagnostic['afterSha256'] = candidate[1]['sha256']
        return None, diagnostic
    if candidate:
        _PROBE_CACHE[identity] = copy.deepcopy((candidate, diagnostic))
        while len(_PROBE_CACHE) > 128:
            _PROBE_CACHE.popitem(last=False)
    return candidate, diagnostic


def _binaries(directory, explicit):
    if explicit:
        return [Path(explicit).expanduser().resolve()]
    roots = ([Path(directory).expanduser()] if directory else
             [Path.home() / '.solc-select' / 'artifacts', Path.home() / '.solcx', Path('/opt/homebrew/Cellar/solidity'),
              Path('/usr/local/Cellar/solidity')])
    return sorted({path.resolve() for root in roots if root.is_dir()
                   for path in root.rglob('solc*') if path.is_file() and os.access(path, os.X_OK)})


def _dependency_identity(configuration):
    def read_error(error):
        raise error

    roots = set()
    arguments = configuration.get('tools.slither.solc-args', '').split()
    for index, argument in enumerate(arguments[:-1]):
        if argument in {'--base-path', '--include-path', '--allow-paths'}:
            roots.update(Path(path).resolve() for path in arguments[index + 1].split(','))
    for remap in configuration.get('tools.slither.solc-remaps', '').split():
        roots.add(Path(remap.partition('=')[2]).resolve())
    directories, sources = set(), {}
    byte_count = 0
    for root in sorted(roots):
        for current, children, files in os.walk(root, followlinks=True, onerror=read_error):
            canonical = Path(current).resolve()
            if canonical in directories:
                children.clear()
                continue
            directories.add(canonical)
            if len(directories) > 20_000:
                raise _DependencyLimit('依赖目录超过 20000 项')
            children.sort()
            for name in sorted(files):
                if not name.endswith('.sol'):
                    continue
                source = (Path(current) / name).resolve()
                if source in sources:
                    continue
                size = source.stat().st_size
                if size > 4 * 1024 * 1024 or byte_count > 64 * 1024 * 1024 or len(sources) >= 4096:
                    raise _DependencyLimit('依赖源码超过单文件 4 MiB、总计 64 MiB 或 4096 文件的范围')
                with source.open('rb') as stream:
                    data = stream.read(4 * 1024 * 1024 + 1)
                byte_count += len(data)
                if len(data) > 4 * 1024 * 1024 or byte_count > 64 * 1024 * 1024:
                    raise _DependencyLimit('依赖源码内容超过固定范围')
                sources[source] = _sha256(data)
    manifest = [(str(path), digest) for path, digest in sorted(sources.items())]
    return {'fileCount': len(manifest), 'sha256': _sha256(json.dumps(manifest).encode('utf-8'))}


def resolve_environment(source, config=None, compiler_dir=None):
    """支持 ^、比较区间、精确版本；未知属性参与摘要，仅白名单工具字段展示。"""
    result = {'status': 'ERROR', 'errorCategory': None, 'compiler': None, 'sourceHash': None,
              'configHash': None, 'diagnostics': [], 'pragmas': [], 'configSummary': {}}
    configuration = {}
    try:
        configuration = _configuration(config)
        if not isinstance(source, str) or not source.strip():
            raise ValueError('源码不能为空')
        result['sourceHash'] = _sha256(source.encode('utf-8'))
        explicit = configuration.get('tools.slither.solc')
        directory = compiler_dir or configuration.get('tools.compiler.directory')
        if explicit is not None and (not isinstance(explicit, str) or not explicit.strip()):
            raise ValueError('固定 solc 路径无效')
        result['configSummary'] = {key: _redact(value, configuration)
                                   for key, value in sorted(configuration.items()) if key in _SUMMARY_KEYS}
        if any(not Path(value).is_file() or not os.access(value, os.X_OK)
               for key, value in configuration.items() if key in {'tools.slither.executable', 'tools.mythril.executable'}):
            result['errorCategory'] = 'TOOL_UNAVAILABLE'
            return result
        try:
            pragmas, constraints = _constraints(source)
            result['pragmas'] = pragmas
        except ValueError:
            result['errorCategory'] = 'UNSUPPORTED_PRAGMA'
            return result
        if not pragmas and not explicit:
            result['errorCategory'] = 'NO_PRAGMA'
            return result
        candidates = _binaries(directory, explicit)
        if not candidates or (explicit and (not candidates[0].is_file() or not os.access(candidates[0], os.X_OK))):
            result['errorCategory'] = 'COMPILER_UNAVAILABLE'
            return result
        available, matching = [], []
        for binary in candidates:
            candidate, diagnostic = _probe(binary, configuration)
            result['diagnostics'].append(diagnostic)
            if candidate:
                available.append(candidate)
                if _matches(candidate[0], constraints):
                    matching.append(candidate)
        if not matching:
            result['errorCategory'] = ('ENVIRONMENT_CHANGED' if any(item['status'] == 'ENVIRONMENT_CHANGED' for item in result['diagnostics']) else
                                      ('COMPILER_PROBE_FAILED' if not available else
                                       ('COMPILER_MISMATCH' if explicit else 'NO_MATCHING_COMPILER'))
                                      )
            if explicit and available:
                result['compiler'] = available[0][1]
            return result
        result['compiler'] = sorted(matching, key=lambda item: (item[0], item[1]['path']))[-1][1]
        result['status'], result['errorCategory'] = 'OK', None
    except (OSError, ValueError, TypeError):
        result['errorCategory'] = 'CONFIG_ERROR'
    finally:
        # 未知配置保留在摘要输入中；绝不直接输出其值或供应商凭证。
        tool_binaries = {}
        for key in ('tools.slither.executable', 'tools.mythril.executable'):
            value = configuration.get(key)
            if isinstance(value, str) and '/' in value:
                try:
                    path = Path(value).expanduser().resolve()
                    tool_binaries[key] = {'path': str(path), 'sha256': _sha256(path.read_bytes())}
                except OSError:
                    tool_binaries[key] = {'path': value, 'sha256': None}
        binding = {'configuration': configuration, 'compiler': result['compiler'],
                   'compilerDirectory': str(compiler_dir) if compiler_dir else None,
                   'toolBinaries': tool_binaries}
        dependency_error = False
        try:
            result['dependencies'] = _dependency_identity(configuration)
            binding['dependencies'] = result['dependencies']
        except (OSError, ValueError) as error:
            dependency_error = True
            result['status'] = 'ERROR'
            result['errorCategory'] = 'DEPENDENCY_LIMIT' if isinstance(error, _DependencyLimit) else 'DEPENDENCY_UNAVAILABLE'
            result['diagnostics'].append({'status': result['errorCategory'], 'message': '依赖源码未能在固定范围内完整绑定。'})
        try:
            result['configHash'] = None if dependency_error else _sha256(json.dumps(binding, sort_keys=True, allow_nan=False).encode('utf-8'))
        except (TypeError, ValueError):
            result['configHash'] = None
    return result
