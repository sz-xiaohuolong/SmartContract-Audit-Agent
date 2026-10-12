"""固定 solc 的真实 Slither 双收据；重放核验身份，不直接生成安全裁决。"""

import argparse
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from compiler_facts import load_bound_compilation


_SCHEMA = 'bound-slither-1'
_EVIDENCE = Path('.evidence/R2-20261010/S11-resolution/tool-bridge')
_MAX_JSON = 64 * 1024 * 1024


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _json(path):
    data = path.read_bytes()
    if len(data) > _MAX_JSON:
        raise ValueError('工具证据超过 64 MiB')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('工具证据包含重复 JSON 键')
            result[key] = value
        return result

    def invalid(value):
        raise ValueError('工具证据包含非有限 JSON 数值')

    value = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError('工具证据必须为 JSON 对象')
    return value, data


def _path(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def _artifact(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError('工具证据路径缺失')
    path = _path(root, value).resolve()
    if not path.is_relative_to((root / _EVIDENCE).resolve()):
        raise ValueError('工具原件必须位于指定证据目录，且不能通过链接越界')
    return path


def _resolve_python(root, explicit=None):
    """发现已安装工具解释器；不安装依赖、不切换全局工具环境。"""
    if explicit:
        candidate = Path(os.path.abspath(Path(explicit).expanduser()))
    else:
        executable = shutil.which('slither')
        if executable is None:
            raise ValueError('已安装的 Slither 可执行文件不可用')
        first_line = Path(executable).read_bytes().splitlines()[0].decode('utf-8')
        if not first_line.startswith('#!') or len(first_line[2:].split()) != 1:
            raise ValueError('Slither 入口没有唯一固定 Python 解释器，须显式提供')
        # 保留虚拟环境入口，解析符号链接后执行会丢失其 site-packages。
        candidate = Path(os.path.abspath(first_line[2:]))
    if not candidate.is_file() or not os.access(candidate, os.X_OK) or not re.fullmatch(r'python(?:\d+(?:\.\d+)*)?', candidate.name):
        raise ValueError('固定工具 Python 解释器不可用')
    return candidate


def _failure(category, error, status='PROCESS_ERROR'):
    return {'engine': 'SLITHER', 'status': status, 'issues': [], 'errorCategory': category,
            'error': str(error), 'paidModelRequests': 0}


def _invoke_worker(manifest_path, *, root, python_executable, directory):
    directory.mkdir(parents=True, exist_ok=True)
    command = [str(python_executable), str(Path(__file__).resolve()), '--worker',
               '--root', str(root), '--manifest', str(manifest_path), '--directory', str(directory)]
    # 原始输出写证据文件，避免进程输出无界增长或混入返回的 JSON。
    with (directory / 'worker-stdout.log').open('wb') as stdout, (directory / 'worker-stderr.log').open('wb') as stderr:
        run = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, timeout=240, check=False)
    result_path = directory / 'tool-result.json'
    if not result_path.is_file():
        return _failure('WORKER_FAILED', f'真实工具子进程未产生结果，退出码 {run.returncode}')
    result, _ = _json(result_path)
    if run.returncode != 0 and result.get('status') == 'OK':
        return _failure('WORKER_FAILED', f'真实工具子进程异常退出，退出码 {run.returncode}')
    return result


def analyze_bound(manifest, *, root, python_executable=None):
    """从固定编译输入执行官方 Slither，并保留真实告警及编译第二收据。"""
    root = Path(root).resolve()
    try:
        python = _resolve_python(root, python_executable)
    except (OSError, ValueError, IndexError, UnicodeError) as error:
        return _failure('DEPENDENCY_UNAVAILABLE', error)
    directory = root / _EVIDENCE / ('analysis-' + uuid.uuid4().hex)
    try:
        directory.mkdir(parents=True, exist_ok=False)
        if isinstance(manifest, dict):
            manifest_path = directory / 'manifest.json'
            manifest_path.write_bytes(_canonical(manifest))
        else:
            manifest_path = _path(root, manifest).resolve()
        result = _invoke_worker(manifest_path, root=root, python_executable=python, directory=directory)
        if not isinstance(result, dict) or result.get('engine') != 'SLITHER' or not isinstance(result.get('issues'), list):
            raise ValueError('真实工具返回结构不合法')
        if result.get('status') == 'OK':
            # 成功标记必须有可读真实原件；缺收据不能留待裁决时再当成功处理。
            _read_tool(result, root)
        return result
    except (subprocess.TimeoutExpired, TimeoutError) as error:
        return _failure('TIMEOUT', error, 'TIMEOUT')
    except (OSError, ValueError, TypeError, KeyError) as error:
        return _failure('WORKER_FAILED', error)


def _read_tool(tool, root):
    if not isinstance(tool, dict) or tool.get('engine') != 'SLITHER' or tool.get('status') != 'OK':
        raise ValueError('工具没有成功的真实 Slither 结果')
    issues = tool.get('issues')
    if (not isinstance(issues, list) or any(not isinstance(issue, dict)
            or not isinstance(issue.get('check'), str) or not issue['check'] for issue in issues)):
        raise ValueError('真实 Slither 告警必须为带原始检测器名称的对象')
    receipt_ref = tool.get('compilationReceipt')
    if not isinstance(receipt_ref, dict) or receipt_ref.get('schemaVersion') != _SCHEMA:
        raise ValueError('工具缺少真实编译第二收据；配置摘要不能代替收据')
    receipt_path = _artifact(root, receipt_ref.get('path'))
    raw_path = _artifact(root, tool.get('rawResultPath'))
    receipt, receipt_bytes = _json(receipt_path)
    raw, raw_bytes = _json(raw_path)
    if _digest(receipt_bytes) != receipt_ref.get('sha256') or _digest(raw_bytes) != tool.get('rawResultSha256'):
        raise ValueError('工具原件字节摘要不匹配')
    if receipt.get('status') != 'MATCH' or receipt.get('rawResultCanonicalSha256') != _digest(_canonical(raw)):
        raise ValueError('工具第二收据未匹配原始告警')
    raw_results = raw.get('results')
    if (raw.get('success') is not True or raw.get('error') is not None
            or not isinstance(raw_results, dict)
            or _canonical(raw_results.get('detectors')) != _canonical(issues)):
        raise ValueError('调用者告警与真实原件不一致')
    identity = receipt.get('identity')
    if not isinstance(identity, dict) or identity.get('schemaVersion') != _SCHEMA:
        raise ValueError('工具第二收据身份不合法')
    if any(tool.get(key) != identity.get(key) for key in ('sourceHash', 'sourceFile')):
        raise ValueError('工具顶层源码身份与第二收据不一致')
    return receipt, raw


def verify_bound_tool(tool, bundle, *, root):
    """重跑真实后端，拒绝复制环境摘要、重封假收据与实际检测结果漂移。"""
    root = Path(root).resolve()
    try:
        receipt, raw = _read_tool(tool, root)
        identity = receipt['identity']
        if bundle.get('verificationStatus') != 'RECOMPILED_MATCH':
            raise ValueError('编译第一收据尚未真实重编译核验')
        for tool_key, bundle_key in [('sourceHash', 'sourceHash'), ('sourceFile', 'targetSourceUnit')]:
            if tool.get(tool_key) != bundle.get(bundle_key) or identity.get(tool_key) != bundle.get(bundle_key):
                raise ValueError('工具源码身份与编译第一收据不一致')
        if identity.get('manifestDigest') != bundle.get('manifestDigest') or identity.get('compilerReceiptDigest') != bundle.get('receiptDigest'):
            raise ValueError('工具清单或编译第一收据身份不一致')
        python = _resolve_python(root, identity.get('pythonExecutable'))
        directory = root / _EVIDENCE / ('verification-' + uuid.uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        manifest_path = directory / 'manifest.json'
        manifest_bytes = identity['manifestUtf8'].encode('utf-8') if 'manifestUtf8' in identity else _canonical(bundle['manifest'])
        if _digest(manifest_bytes) != bundle['manifestDigest'] or json.loads(manifest_bytes) != bundle['manifest']:
            raise ValueError('重放清单原件与编译第一收据不一致')
        manifest_path.write_bytes(manifest_bytes)
        replay = _invoke_worker(manifest_path, root=root, python_executable=python, directory=directory)
        replay_receipt, replay_raw = _read_tool(replay, root)
        # JSON 类型也是收据身份的一部分，Python 的 False == 0 不能用于证据对账。
        if (_canonical(replay_receipt['identity']) != _canonical(identity)
                or _canonical(replay_raw) != _canonical(raw)):
            raise ValueError('实际工具重放的编译身份、IR 摘要或检测告警发生漂移')
        return {'status': 'MATCH', 'reason': '实际固定 solc 与官方 Slither 双收据及独立重放均匹配',
                'effectSummaries': copy.deepcopy(identity.get('effectSummaries', [])),
                'receipt': copy.deepcopy(tool['compilationReceipt']),
                'replayReceipt': replay['compilationReceipt'], 'paidModelRequests': 0}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.TimeoutExpired, TimeoutError) as error:
        return {'status': 'UNKNOWN', 'errorCategory': 'TOOL_BINDING_UNVERIFIED', 'reason': str(error),
                'effectSummaries': [], 'paidModelRequests': 0}


def _tree_digest(module):
    directory = Path(module.__file__).resolve().parent
    files = {str(path.relative_to(directory)): _digest(path.read_bytes()) for path in sorted(directory.rglob('*.py'))}
    return {'path': str(directory), 'pythonSourceTreeSha256': _digest(_canonical(files)), 'fileCount': len(files)}


def _source_bindings(bundle):
    """仅用完整路径和准确跨度连接 Slither 对象、声明与编译 AST。"""
    unit_names = {str(Path(unit['path']).resolve()): unit['sourceUnit'] for unit in bundle['units'].values()}
    declarations, nodes = {}, {}
    for identity, node in bundle['declarations'].items():
        start, length, source_id = map(int, node['src'].split(':'))
        location = (bundle['units'][source_id]['sourceUnit'], start, length)
        declarations.setdefault(location, []).append(identity)
    for identity, node in bundle.get('nodes', {}).items():
        if not isinstance(node.get('src'), str):
            continue
        start, length, source_id = map(int, node['src'].split(':'))
        if source_id in bundle['units']:
            nodes.setdefault((bundle['units'][source_id]['sourceUnit'], start, length), []).append(identity)

    def span(value):
        source = getattr(value, 'source_mapping', None)
        if source is None or getattr(source, 'filename', None) is None:
            return {'sourceUnit': None, 'start': None, 'length': None}
        filename = str(Path(source.filename.absolute).resolve())
        name = unit_names.get(filename)
        if name is None:
            name = next((unit['sourceUnit'] for unit in bundle['units'].values()
                         if (Path(bundle['binding']['environment']) / unit['sourceUnit']).resolve() == Path(filename)), None)
        return {'sourceUnit': name, 'start': source.start, 'length': source.length}

    def declaration(value):
        location = span(value)
        identities = declarations.get((location['sourceUnit'], location['start'], location['length']), [])
        if len(identities) == 1:
            return identities[0]
        if identities or not type(value).__name__.startswith('LocalVariable'):
            return None
        # 0.4.x 的 Slither 局部变量映射常覆盖声明语句；只连接唯一真实子声明。
        statement = ast_node(value, 'VariableDeclarationStatement')
        children = statement.get('declarations', []) if statement else []
        if len(children) != 1 or not isinstance(children[0], dict):
            return None
        identity = children[0].get('id')
        child = bundle['declarations'].get(identity)
        if not child or child.get('stateVariable') or statement.get('assignments') != [identity]:
            return None
        start, length, source_id = map(int, child['src'].split(':'))
        if (bundle['units'][source_id]['sourceUnit'] != location['sourceUnit']
                or start < location['start'] or start + length > location['start'] + location['length']):
            return None
        return identity

    def ast_node(value, kind=None):
        location = span(value)
        identities = nodes.get((location['sourceUnit'], location['start'], location['length']), [])
        if kind:
            identities = [identity for identity in identities if bundle['nodes'][identity]['nodeType'] == kind]
        return bundle['nodes'][identities[0]] if len(identities) == 1 else None

    return span, declaration, ast_node


def _type_text(value):
    """没有稳定类型文本时留空，禁止把进程内存地址写进收据身份。"""
    if value is None or type(value).__str__ is object.__str__:
        return None
    return str(value)


def _ir_state_facts(operations, bundle):
    """独立记录直接 IR 引用与读写；序号只表示静态 IR 排列，不证明执行顺序。"""
    span, declaration, ast_node = _source_bindings(bundle)
    definitions = {}
    expression_kinds = {'AssignmentOperation': 'Assignment', 'IndexAccess': 'IndexAccess',
        'MemberAccess': 'MemberAccess', 'BinaryOperation': 'BinaryOperation', 'Identifier': 'Identifier',
        'CallExpression': 'FunctionCall', 'UnaryOperation': 'UnaryOperation', 'Literal': 'Literal'}

    def storage_alias(value):
        if not type(value).__name__.startswith('LocalVariable') or not getattr(value, 'is_storage', False):
            return False
        node = bundle['declarations'].get(declaration(value), {})
        return (node.get('storageLocation') == 'storage'
                or '_storage' in node.get('typeDescriptions', {}).get('typeIdentifier', ''))

    for index, operation in enumerate(operations):
        kind = type(operation).__name__
        value = getattr(operation, 'lvalue', None)
        if kind in {'Index', 'Member'} or (kind == 'Assignment' and storage_alias(value)):
            definitions.setdefault(id(value), []).append((index, operation))

    def key_fact(value, expression):
        node = ast_node(expression)
        kind = type(value).__name__
        actual = {'kind': 'UNKNOWN'}
        matches = False
        if kind in {'SolidityVariableComposed', 'SolidityVariable'}:
            actual = {'kind': 'BUILTIN', 'name': value.name}
            if node:
                ast_name = node.get('name') if node['nodeType'] == 'Identifier' else (
                    node.get('expression', {}).get('name', '') + '.' + node.get('memberName', ''))
                matches = ast_name == value.name
        elif kind == 'Constant' and isinstance(getattr(value, 'value', None), (str, int, bool)):
            actual = {'kind': 'LITERAL', 'value': value.value}
            matches = bool(node and node['nodeType'] == 'Literal' and str(node.get('value')).lower() == str(value.value).lower()
                           and not node.get('subdenomination'))
        elif (identity := declaration(value)) is not None:
            actual = {'kind': 'DECLARATION', 'declarationId': identity}
            matches = bool(node and node['nodeType'] == 'Identifier' and node.get('referencedDeclaration') == identity)
        return {'value': actual, 'astNodeId': node.get('id') if node else None,
                'span': span(expression), 'type': _type_text(getattr(value, 'type', None)),
                'bindingStatus': 'BOUND' if matches else 'UNRESOLVED'}

    def unresolved(reason, path=None):
        return {'rootDeclarationId': None, 'path': path or [], 'bindingStatus': 'UNRESOLVED', 'reason': reason}

    def resolve(value, pending=None):
        pending = set() if pending is None else set(pending)
        if id(value) in pending:
            return unresolved('引用定义存在循环')
        pending.add(id(value))
        identity = declaration(value)
        if bundle['declarations'].get(identity, {}).get('stateVariable'):
            return {'rootDeclarationId': identity, 'path': [], 'bindingStatus': 'BOUND'}
        choices = definitions.get(id(value), [])
        if len(choices) != 1:
            return unresolved('引用没有唯一直接定义')
        _, operation = choices[0]
        kind = type(operation).__name__
        if kind == 'Assignment':
            return resolve(operation.rvalue, pending)
        base = resolve(operation.variable_left, pending)
        path = copy.deepcopy(base['path'])
        if kind == 'Index':
            key = key_fact(operation.variable_right, getattr(operation.expression, 'expression_right', None))
            path.append({'kind': 'INDEX', 'key': key})
            valid = key['bindingStatus'] == 'BOUND'
        else:
            field_name = getattr(operation.variable_right, 'value', None)
            struct = getattr(getattr(operation.variable_left, 'type', None), 'type', None)
            field = getattr(struct, 'elems', {}).get(field_name)
            field_id = declaration(field)
            node = ast_node(getattr(operation, 'expression', None), 'MemberAccess')
            valid = field_id is not None and node is not None and node.get('referencedDeclaration') == field_id
            path.append({'kind': 'MEMBER', 'memberDeclarationId': field_id if valid else None,
                         'memberName': field_name, 'span': span(getattr(operation, 'expression', None))})
        bound = base['bindingStatus'] == 'BOUND' and valid
        return {'rootDeclarationId': base['rootDeclarationId'], 'path': path,
                'bindingStatus': 'BOUND' if bound else 'UNRESOLVED',
                **({} if bound else {'reason': '引用根、索引 key 或结构字段未唯一绑定'})}

    def related(value, pending=None):
        pending = set() if pending is None else set(pending)
        if id(value) in pending:
            return False
        pending.add(id(value))
        if bundle['declarations'].get(declaration(value), {}).get('stateVariable') or storage_alias(value):
            return True
        return any(related(operation.variable_left, pending) for _, operation in definitions.get(id(value), [])
                   if type(operation).__name__ in {'Index', 'Member'})

    bindings, accesses, gaps = [], [], []
    for choices in definitions.values():
        index, operation = choices[0]
        value = operation.lvalue
        if not related(value):
            continue
        expression = getattr(operation, 'expression', None)
        node = ast_node(expression, expression_kinds.get(type(expression).__name__))
        binding = {'irVariable': getattr(value, 'name', None), 'irIndex': index,
                   'irKind': type(operation).__name__, 'definitionCount': len(choices),
                   'declarationId': declaration(value), 'astNodeId': node.get('id') if node else None,
                   'expressionSpan': span(expression), 'statementSpan': span(getattr(operation, 'node', None)),
                   **resolve(value)}
        bindings.append(binding)
        if binding['bindingStatus'] != 'BOUND':
            gaps.append('SlithIR storage 引用没有完整绑定')
    for index, operation in enumerate(operations):
        kind = type(operation).__name__
        if kind in {'Index', 'Member'} or (kind == 'Assignment' and storage_alias(getattr(operation, 'lvalue', None))):
            continue  # 定义指针或 storage 别名没有写入原存储值。
        expression = getattr(operation, 'expression', None)
        node = ast_node(expression, expression_kinds.get(type(expression).__name__))
        values = [('READ', value) for value in getattr(operation, 'read', [])]
        values.append(('WRITE', getattr(operation, 'lvalue', None)))
        seen = set()
        for mode, value in values:
            if (mode, id(value)) in seen or not related(value):
                continue
            seen.add((mode, id(value)))
            fact = resolve(value)
            if node is None or span(expression)['sourceUnit'] is None:
                fact['bindingStatus'] = 'UNRESOLVED'
                fact['reason'] = '实际 IR 操作没有唯一 AST 表达式跨度'
            accesses.append({'mode': mode, 'irKind': kind, 'irIndex': index,
                'irVariable': getattr(value, 'name', None), 'astNodeId': node.get('id') if node else None,
                'expressionSpan': span(expression), 'statementSpan': span(getattr(operation, 'node', None)), **fact})
            if fact['bindingStatus'] != 'BOUND':
                gaps.append('SlithIR 状态访问没有完整绑定')
    return {'referenceBindings': bindings, 'stateAccesses': accesses,
            'stateAccessCoverage': 'DIRECT_FUNCTION_OPERATIONS', 'gaps': sorted(set(gaps))}


def _effects(slither, bundle):
    """从真实 SlithIR 提取传递读写；未绑定声明或动态语义显式保留缺口。"""
    span, declaration, _ = _source_bindings(bundle)

    def state_id(value):
        identity = declaration(value)
        return identity if bundle['declarations'].get(identity, {}).get('stateVariable') else None

    def state_ids(values, gaps):
        result = []
        for value in values:
            identity = state_id(value)
            if identity is None:
                gaps.append('SlithIR 状态变量未绑定 AST 声明')
            else:
                result.append(identity)
        return sorted(set(result))

    def root_id(value):
        origin = getattr(value, 'points_to_origin', value)
        if origin is None or not hasattr(origin, 'source_mapping'):
            return None
        return state_id(origin)

    def call_evidence(operation, gaps):
        kind = type(operation).__name__
        if kind not in {'InternalCall', 'InternalDynamicCall', 'HighLevelCall', 'LowLevelCall',
                        'LibraryCall', 'Send', 'Transfer', 'NewContract'}:
            return None
        target = getattr(operation, 'function', None)
        target_id = getattr(target, 'id', None)
        target_id = int(target_id) if target_id is not None else None
        storage = []
        if target_id in bundle['functions']:
            parameters = bundle['functions'][target_id]['parameters']
            arguments = getattr(operation, 'arguments', [])
            for position, parameter in enumerate(parameters):
                if parameter.get('storageLocation') == 'storage':
                    argument = arguments[position] if position < len(arguments) else None
                    storage.append({'position': position, 'targetParameterDeclarationId': parameter['id'],
                                    'passedStorageRootDeclarationId': root_id(argument)})
            if storage:
                gaps.append('调用 storage 参数的别名读写须另行绑定')
        if kind == 'LowLevelCall':
            name = str(operation.function_name).lower()
            semantics = {'call': 'CALL', 'staticcall': 'STATICCALL', 'delegatecall': 'DELEGATECALL',
                         'callcode': 'CALLCODE'}.get(name, 'UNKNOWN')
            if semantics != 'STATICCALL':
                gaps.append('非静态低级调用的完整存储效果未知')
        elif kind == 'HighLevelCall':
            semantics = 'STATICCALL' if operation.is_static_call() else 'CALL'
            if semantics != 'STATICCALL':
                gaps.append('非静态外部调用的完整存储效果未知')
        elif kind == 'LibraryCall':
            # SlithIR 类别本身没有提供最终字节码调用 opcode 的证明。
            semantics = 'LIBRARY_CALL_OPCODE_UNVERIFIED'
            gaps.append('库调用最终 opcode 尚未证明')
        elif kind == 'InternalCall':
            semantics = 'INTERNAL'
            if target_id is None:
                gaps.append('内部调用没有绑定函数声明')
        else:
            semantics = {'InternalDynamicCall': 'INTERNAL_DYNAMIC', 'Send': 'CALL',
                         'Transfer': 'CALL', 'NewContract': 'CREATE'}.get(kind, 'UNKNOWN')
            gaps.append('动态调用、创建或转账的完整存储效果未知')
        location = span(operation.node)
        if location['sourceUnit'] is None:
            gaps.append('调用 IR 没有绑定源码跨度')
        return {'irKind': kind, 'semantics': semantics, 'targetDeclarationId': target_id,
                'destinationStateRootDeclarationId': root_id(getattr(operation, 'destination', None)),
                'storageArguments': storage, 'span': location,
                'expressionSpan': span(getattr(operation, 'expression', None))}

    result, seen = [], set()
    for contract in slither.contracts:
        for function in contract.functions_declared + contract.modifiers_declared:
            identity = function.id
            try:
                identity = int(identity)
            except (ValueError, TypeError):
                continue  # Slither 生成的初始化函数不冒充 Solidity 函数声明。
            if identity in seen or identity not in bundle['functions']:
                continue
            seen.add(identity)
            location = span(function)
            bound = bundle['functions'][identity]
            if (location['sourceUnit'], location['start'], location['length']) != (
                    bound['sourceUnit'], bound['span']['start'], bound['span']['length']):
                raise ValueError('SlithIR 函数 ID 与源码跨度不一致')
            gaps = []
            if bound['body'] is None:
                gaps.append('声明没有实现函数体')
            calls = function.all_internal_calls()
            internal = sorted({int(call.function.id) for call in calls
                               if getattr(getattr(call, 'function', None), 'id', None) is not None})
            operations = function.all_slithir_operations()
            if any(type(operation).__name__ == 'InternalDynamicCall' for operation in operations):
                gaps.append('存在内部动态调用')
            closure, pending = set(), [function]
            while pending:
                current = pending.pop()
                if current in closure:
                    continue
                closure.add(current)
                for call in current.internal_calls + current.library_calls:
                    target = getattr(call, 'function', None)
                    if hasattr(target, 'internal_calls'):
                        pending.append(target)
                pending.extend(modifier for modifier in current.modifiers if hasattr(modifier, 'internal_calls'))
            if any(current.contains_assembly for current in closure):
                gaps.append('存在汇编语义')
            external = function.all_high_level_calls()
            low = function.all_low_level_calls()
            call_details = [detail for operation in operations if (detail := call_evidence(operation, gaps)) is not None]
            call_details.sort(key=_canonical)
            direct_facts = _ir_state_facts(getattr(function, 'slithir_operations', operations), bundle)
            gaps.extend(direct_facts.pop('gaps'))
            item = {'declarationId': identity, 'canonicalName': bound['canonicalName'], **location,
                    'directStateReads': state_ids(function.state_variables_read, gaps),
                    'directStateWrites': state_ids(function.state_variables_written, gaps),
                    'transitiveStateReads': state_ids(function.all_state_variables_read(), gaps),
                    'transitiveStateWrites': state_ids(function.all_state_variables_written(), gaps),
                    'internalTargets': internal,
                    'externalCallCount': len(external), 'lowLevelCallCount': len(low),
                    'containsAssembly': function.contains_assembly,
                    'irOperations': sorted({type(operation).__name__ for operation in operations}),
                    'calls': call_details, 'coverage': 'INTERNAL_LIBRARY_MODIFIER_CLOSURE',
                    **direct_facts,
                    'closureDeclarationIds': sorted({int(current.id) for current in closure if current.id is not None}),
                    'gaps': sorted(set(gaps)), 'complete': not gaps}
            result.append(item)
    return sorted(result, key=lambda item: item['declarationId'])


def _worker(manifest_path, root, directory):
    """在工具解释器内执行官方解析与检测；不使用工具 CLI 的二次编译默认值。"""
    import importlib.metadata
    import logging
    import crytic_compile
    import slither as slither_package
    from crytic_compile import CryticCompile
    from crytic_compile.compilation_unit import CompilationUnit
    from crytic_compile.compiler.compiler import CompilerVersion
    from crytic_compile.platform.solc_standard_json import SolcStandardJson, parse_standard_json_output
    from slither.slither import Slither
    from slither.detectors import all_detectors
    from slither.detectors.abstract_detector import AbstractDetector

    started = time.monotonic()
    producer_hash = _digest(Path(__file__).read_bytes())
    tool_identity = {'pythonExecutableSha256': _digest(Path(sys.executable).resolve().read_bytes()),
                     'pythonVersion': sys.version,
                     'version': importlib.metadata.version('slither-analyzer'),
                     'cryticCompileVersion': importlib.metadata.version('crytic-compile'),
                     'slitherSource': _tree_digest(slither_package), 'cryticSource': _tree_digest(crytic_compile)}
    bundle = load_bound_compilation(manifest_path, root)
    binding = bundle['binding']
    actual_input = _path(root, bundle['manifest']['inputPath']).read_bytes()
    binary = _path(root, binding['compiler']).resolve()
    cwd = _path(root, binding['environment']).resolve()

    class FixedInput(SolcStandardJson):
        def __init__(self):
            super().__init__(copy.deepcopy(bundle['input']))
            self.observed_output = None
            self.execution = None

        def compile(self, cc, **kwargs):
            before = _digest(binary.read_bytes())
            probe = subprocess.run([str(binary), '--version'], capture_output=True, timeout=5, check=False)
            match = re.search(rb'(?m)^\s*Version:\s*(\d+\.\d+\.\d+)(?:\+|\s|$)', probe.stdout)
            if probe.returncode != 0 or match is None:
                raise ValueError('实际固定 solc 版本查询失败')
            version = match.group(1).decode('ascii')
            command = [str(binary), '--standard-json']
            run = subprocess.run(command, input=actual_input, cwd=cwd, capture_output=True, timeout=120, check=False)
            (directory / 'slither-compiler-stdout.json').write_bytes(run.stdout)
            (directory / 'slither-compiler-stderr.txt').write_bytes(run.stderr)
            if run.returncode != 0:
                raise ValueError(f'实际固定 solc 编译失败，退出码 {run.returncode}')
            self.observed_output, _ = _json(directory / 'slither-compiler-stdout.json')
            if any(error.get('severity') == 'error' for error in self.observed_output.get('errors', [])):
                raise ValueError('实际固定 solc 返回编译错误')
            after = _digest(binary.read_bytes())
            if before != after or before != binding['compilerSha256'] or version != bundle['compilerVersion']:
                raise ValueError('实际固定 solc 二进制或版本身份发生漂移')
            settings = json.loads(actual_input)['settings']
            optimizer = settings.get('optimizer', {})
            unit = CompilationUnit(cc, 'bound_standard_json_execution')
            unit.compiler_version = CompilerVersion(compiler='solc', version=version,
                                                    optimized=optimizer.get('enabled', False), optimize_runs=optimizer.get('runs'))
            parse_standard_json_output(self.observed_output, unit, solc_working_dir=str(cwd))
            self.execution = {'binaryPath': str(binary), 'binarySha256Before': before, 'binarySha256After': after,
                              'version': version, 'versionStdoutSha256': _digest(probe.stdout), 'command': command,
                              'cwd': str(cwd), 'inputSha256': _digest(actual_input),
                              'outputSha256': _digest(run.stdout), 'canonicalOutputSha256': _digest(_canonical(self.observed_output)),
                              'settings': settings, 'settingsSha256': _digest(_canonical(settings)), 'exitCode': run.returncode,
                              'sourceUnits': {name: _digest(value['content'].encode()) for name, value in bundle['input']['sources'].items()},
                              'platformAddedDefaults': self.to_dict()['settings'] != settings}

    adapter = FixedInput()
    cc = CryticCompile(adapter, cwd=str(cwd))
    analyzer = Slither(cc, codex=False, generate_patches=False, triage_mode=False, disallow_partial=True)
    analyzer._previous_results_filename = str(directory / 'unused-triage.json')
    observed = {}
    for unit in cc.compilation_units.values():
        for source_unit in unit.source_units.values():
            ast = source_unit.ast
            name = ast['absolutePath']
            code = cc.src_content[source_unit.filename.absolute]
            observed[name] = {'sha256': _digest(code.encode()), 'astSha256': _digest(_canonical(ast)),
                              'contractAbi': {name: _digest(_canonical(value)) for name, value in source_unit.abis.items()},
                              'contractBytecodeInit': {name: _digest(value.encode()) for name, value in source_unit.bytecodes_init.items()},
                              'contractBytecodeRuntime': {name: _digest(value.encode()) for name, value in source_unit.bytecodes_runtime.items()}}
    if (set(observed) != set(bundle['input']['sources'])
            or _canonical(adapter.observed_output) != _canonical(bundle['output'])):
        raise ValueError('实际 Slither 编译产物与第一收据不一致')
    for name, source in bundle['input']['sources'].items():
        if observed[name]['sha256'] != _digest(source['content'].encode()) or observed[name]['astSha256'] != _digest(_canonical(bundle['output']['sources'][name]['ast'])):
            raise ValueError('实际 Slither 解析的源码或 AST 闭包不一致')
    classes = {getattr(all_detectors, name) for name in dir(all_detectors) if inspect.isclass(getattr(all_detectors, name))}
    detectors = sorted([value for value in classes if issubclass(value, AbstractDetector) and value != AbstractDetector
                        and value.ARGUMENT != 'codex'], key=lambda value: value.ARGUMENT)
    for detector in detectors:
        analyzer.register_detector(detector)
    logging.getLogger('Detectors').setLevel(logging.ERROR)
    issues = []
    for group in analyzer.run_detectors():
        issues.extend(group)
    issues.sort(key=_canonical)
    raw = {'success': True, 'error': None, 'results': {'detectors': issues}}
    raw_path = directory / 'slither-detectors.json'
    raw_path.write_bytes(_canonical(raw))
    identity = {'schemaVersion': _SCHEMA, 'producerCodeSha256': producer_hash,
                'manifestDigest': bundle['manifestDigest'], 'compilerReceiptDigest': bundle['receiptDigest'],
                'manifestUtf8': manifest_path.read_text(encoding='utf-8'),
                'sourceHash': bundle['sourceHash'], 'sourceFile': bundle['targetSourceUnit'],
                'pythonExecutable': str(Path(sys.executable).absolute()),
                'toolIdentity': tool_identity,
                'compilerExecution': adapter.execution,
                'parsedCompilation': {'sourceUnits': observed, 'compilerVersions': [
                    {'language': unit.compiler_version.compiler, 'version': unit.compiler_version.version,
                     'optimized': unit.compiler_version.optimized, 'optimizeRuns': unit.compiler_version.optimize_runs}
                    for unit in cc.compilation_units.values()]},
                'detectorsRun': [detector.ARGUMENT for detector in detectors],
                'effectSummaries': _effects(analyzer, bundle)}
    if (producer_hash != _digest(Path(__file__).read_bytes())
            or tool_identity['pythonExecutableSha256'] != _digest(Path(sys.executable).resolve().read_bytes())
            or tool_identity['slitherSource'] != _tree_digest(slither_package)
            or tool_identity['cryticSource'] != _tree_digest(crytic_compile)):
        raise ValueError('工具实现或解释器在运行期间发生漂移')
    receipt = {'identity': identity, 'status': 'MATCH', 'elapsedSeconds': time.monotonic() - started,
               'rawResultCanonicalSha256': _digest(_canonical(raw))}
    receipt_path = directory / 'receipt.json'
    receipt_path.write_bytes(_canonical(receipt))
    return {'engine': 'SLITHER', 'status': 'OK', 'sourceHash': bundle['sourceHash'], 'sourceFile': bundle['targetSourceUnit'],
            'issues': issues, 'version': identity['toolIdentity']['version'],
            'compiler': {'path': str(binary), 'version': bundle['compilerVersion'], 'sha256': binding['compilerSha256']},
            'rawResultPath': str(raw_path.relative_to(root)), 'rawResultSha256': _digest(raw_path.read_bytes()),
            'compilationReceipt': {'schemaVersion': _SCHEMA, 'path': str(receipt_path.relative_to(root)),
                                   'sha256': _digest(receipt_path.read_bytes())}, 'paidModelRequests': 0}


def main():
    parser = argparse.ArgumentParser(description='真实固定编译身份的 Slither 后端')
    parser.add_argument('--worker', action='store_true', required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    directory = _artifact(root, str(args.directory))
    directory.mkdir(parents=True, exist_ok=True)
    try:
        result = _worker(args.manifest, root, directory)
    except (ImportError, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        category = 'DEPENDENCY_UNAVAILABLE' if isinstance(error, ImportError) else 'WORKER_FAILED'
        result = _failure(category, error)
    (directory / 'tool-result.json').write_bytes(_canonical(result))
    return 0 if result['status'] == 'OK' else 1


if __name__ == '__main__':
    sys.exit(main())
