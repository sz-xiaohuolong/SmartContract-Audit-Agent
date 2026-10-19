"""显式绑定 solc standard-json 原产物，提取 AST 事实；不把静态结构当安全证明。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from storage import read_artifact


class CompilationBindingError(ValueError):
    """编译产物或声明身份不满足绑定契约。"""


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _fail(message):
    raise CompilationBindingError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail(f'JSON 存在重复键：{key}')
        result[key] = value
    return result


def _parse_json(data, label):
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=lambda value: _fail(f'JSON 非有限数值：{value}'))
        if not isinstance(value, dict):
            _fail(f'JSON 顶层必须为对象：{label}')
        return value
    except (UnicodeError, json.JSONDecodeError) as error:
        _fail(f'不能读取 JSON：{label}：{error}')


def _read_json(path):
    try:
        data = read_artifact(path, max_bytes=64 * 1024 * 1024)
        return _parse_json(data, path), data
    except OSError as error:
        _fail(f'不能读取 JSON：{path}：{error}')


def _path(root, value):
    if not isinstance(value, str) or not value:
        _fail('绑定路径不能为空')
    path = Path(value)
    return path if path.is_absolute() else root / path


def _check_hash(data, expected, label):
    if not isinstance(expected, str) or len(expected) != 64 or _digest(data) != expected:
        _fail(f'{label} 摘要不匹配')


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _walk(value):
    if isinstance(value, dict):
        if 'nodeType' in value:
            yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def source_span(node, units):
    """只按编译器的 UTF-8 字节跨度定位，不通过源码文本判断语义。"""
    try:
        raw = node['src']
        if not isinstance(raw, str) or len(raw.split(':')) != 3:
            _fail('AST src 格式无效')
        start, length, unit_id = (int(part) for part in raw.split(':'))
        unit = units[unit_id]
        content = unit['content'].encode('utf-8')
        if start < 0 or length < 0 or start + length > len(content):
            _fail('AST 字节跨度超出源码')
        content[:start].decode('utf-8')
        selected = content[start:start + length]
        selected.decode('utf-8')
        return {'start': start, 'length': length, 'sourceUnitId': unit_id,
                'sourceUnit': unit['sourceUnit'], 'line': content[:start].count(b'\n') + 1,
                'contentSha256': _digest(selected)}
    except (KeyError, ValueError, TypeError, UnicodeError) as error:
        if isinstance(error, CompilationBindingError):
            raise
        _fail(f'AST 字节跨度或源码单元无效：{error}')


def _builtin(node):
    """内置符号由编译器类型和标识共同确定；已有真实声明的同名函数不进入此分支。"""
    if node.get('nodeType') != 'Identifier':
        return None
    name = node.get('name')
    identity = node.get('typeDescriptions', {}).get('typeIdentifier', '')
    magic = {'msg': 't_magic_message', 'block': 't_magic_block', 'tx': 't_magic_transaction', 'abi': 't_magic_abi'}
    if name in magic and identity == magic[name]:
        return name
    if name == 'this' and identity.startswith('t_contract'):
        return name
    if name == 'super' and identity.startswith('t_type$_t_super'):
        return name
    if name == 'type' and identity.startswith('t_function_metatype_'):
        return name
    if name == 'now' and identity == 't_uint256':
        return name
    if name in {'sha3', 'keccak256'} and identity.startswith('t_function_sha3_'):
        # 旧 solc 的 sha3 内置别名具有独立类型标识，语义归一为 keccak256。
        return 'keccak256'
    if name in {'selfdestruct', 'suicide'} and identity.startswith('t_function_selfdestruct_'):
        # 旧 suicide 名称可绑定 selfdestruct 类型；同名真实函数仍按声明处理。
        return 'selfdestruct'
    functions = {'require', 'assert', 'revert', 'keccak256', 'sha256', 'ripemd160', 'ecrecover',
                 'addmod', 'mulmod', 'blockhash', 'gasleft', 'selfdestruct', 'suicide'}
    if name in functions and identity.startswith(f't_function_{name}_'):
        return name
    return None


def _type_name(node, nodes, visiting=None):
    """从编译 AST 类型结构生成 ABI 参数类型；未支持类型保留缺口。"""
    visiting = set() if visiting is None else visiting
    if not isinstance(node, dict):
        return None
    kind = node.get('nodeType')
    if kind == 'ElementaryTypeName':
        name = node.get('name')
        return {'uint': 'uint256', 'int': 'int256', 'byte': 'bytes1', 'address payable': 'address'}.get(name, name)
    if kind == 'UserDefinedTypeName':
        identity = node.get('referencedDeclaration')
        declaration = nodes.get(identity)
        if declaration is None or identity in visiting:
            return None
        visiting = visiting | {identity}
        if declaration['nodeType'] == 'ContractDefinition':
            return 'address'
        if declaration['nodeType'] == 'EnumDefinition':
            return 'uint8' if len(declaration.get('members', [])) <= 256 else None
        if declaration['nodeType'] == 'UserDefinedValueTypeDefinition':
            return _type_name(declaration.get('underlyingType'), nodes, visiting)
        if declaration['nodeType'] == 'StructDefinition':
            types = [_type_name(member.get('typeName'), nodes, visiting) for member in declaration.get('members', [])]
            return '(' + ','.join(types) + ')' if all(types) else None
    if kind == 'ArrayTypeName':
        base = _type_name(node.get('baseType'), nodes, visiting)
        length = node.get('length')
        if length is None:
            return base + '[]' if base else None
        if length.get('nodeType') == 'Literal' and length.get('kind') == 'number' and str(length.get('value', '')).isdigit():
            return base + '[' + length['value'] + ']' if base else None
    return None


def _function_kind(node):
    """旧 compact AST 用 isConstructor 与空名称标记入口，不按源码文本猜测。"""
    if node.get('nodeType') == 'ModifierDefinition':
        return 'modifier'
    if node.get('kind') is not None:
        return node['kind']
    if node.get('isConstructor') is True:
        return 'constructor'
    return 'fallback' if node.get('name') == '' else 'function'


def _signature(node, nodes):
    kind = _function_kind(node)
    if node.get('nodeType') == 'FunctionDefinition' and kind in {'fallback', 'receive', 'constructor'}:
        return kind + '()'
    parameters = node.get('parameters', {}).get('parameters', [])
    types = [_type_name(parameter.get('typeName'), nodes) for parameter in parameters]
    return node.get('name', '') + '(' + ','.join(types) + ')' if all(types) else None


def _abi_type(item):
    name = item.get('type')
    if not isinstance(name, str):
        _fail('ABI 参数缺少类型')
    if name.startswith('tuple'):
        components = item.get('components')
        if not isinstance(components, list):
            _fail('ABI tuple 缺少 components')
        return '(' + ','.join(_abi_type(component) for component in components) + ')' + name[5:]
    return name


def _getter_inputs(type_node, nodes):
    result = []
    while isinstance(type_node, dict) and type_node.get('nodeType') in {'Mapping', 'ArrayTypeName'}:
        if type_node['nodeType'] == 'Mapping':
            key = _type_name(type_node.get('keyType'), nodes)
            if not key:
                return None
            result.append(key)
            type_node = type_node.get('valueType')
        else:
            result.append('uint256')
            type_node = type_node.get('baseType')
    return result


def _getter_outputs(type_node, nodes):
    while isinstance(type_node, dict) and type_node.get('nodeType') in {'Mapping', 'ArrayTypeName'}:
        type_node = type_node.get('valueType') if type_node['nodeType'] == 'Mapping' else type_node.get('baseType')
    if not isinstance(type_node, dict):
        return None
    declaration = nodes.get(type_node.get('referencedDeclaration'), {})
    if declaration.get('nodeType') == 'StructDefinition':
        result = []
        for member in declaration.get('members', []):
            member_type = member.get('typeName')
            if member_type.get('nodeType') in {'Mapping', 'ArrayTypeName'}:
                continue
            canonical = _type_name(member_type, nodes)
            if canonical is None:
                return None
            result.append(canonical)
        return result
    canonical = _type_name(type_node, nodes)
    return [canonical] if canonical else None


def _declaration_type(node):
    return node.get('nodeType') in {'ContractDefinition', 'FunctionDefinition', 'ModifierDefinition',
                                   'VariableDeclaration', 'StructDefinition', 'EnumDefinition', 'EnumValue',
                                   'EventDefinition', 'ErrorDefinition', 'UserDefinedValueTypeDefinition',
                                   'ImportDirective'}


def _contract_indices(nodes, units):
    contracts = {}
    functions = {}
    for identity, node in nodes.items():
        if node['nodeType'] != 'ContractDefinition':
            continue
        order = node.get('linearizedBaseContracts')
        if not isinstance(order, list) or not order or order[0] != identity or len(set(order)) != len(order):
            _fail('合约 linearizedBaseContracts 无效')
        if any(nodes.get(base, {}).get('nodeType') != 'ContractDefinition' for base in order):
            _fail('继承声明身份不存在')
        contracts[identity] = {'node': node, 'linearizedBaseContracts': order,
                               'effectiveFunctions': [], 'effectiveModifiers': [], 'effectiveStateVariables': [], 'gaps': []}
        for member in node.get('nodes', []):
            if member.get('nodeType') in {'FunctionDefinition', 'ModifierDefinition'}:
                member_id = member['id']
                span = source_span(member, units)
                functions[member_id] = {
                    'id': member_id, 'node': member, 'signature': _signature(member, nodes),
                    'canonicalName': node['name'] + '.' + (_signature(member, nodes) or f'<声明:{member_id}>'),
                    'contractId': identity, 'body': member.get('body'),
                    'parameters': member.get('parameters', {}).get('parameters', []),
                    'returnParameters': member.get('returnParameters', {}).get('parameters', []),
                    'modifiers': member.get('modifiers', []), 'visibility': member.get('visibility'),
                    'stateMutability': member.get('stateMutability'), 'kind': _function_kind(member),
                    'sourceUnit': span['sourceUnit'], 'span': span}
    for identity, contract in contracts.items():
        seen = {'effectiveFunctions': set(), 'effectiveModifiers': set(), 'effectiveStateVariables': set()}
        for base in contract['linearizedBaseContracts']:
            for member in nodes[base].get('nodes', []):
                kind = member.get('nodeType')
                if kind == 'FunctionDefinition':
                    if _function_kind(member) == 'constructor' or (base != identity and member.get('visibility') == 'private'):
                        continue
                    group, key = 'effectiveFunctions', functions[member['id']]['signature']
                elif kind == 'ModifierDefinition':
                    group, key = 'effectiveModifiers', functions[member['id']]['signature']
                elif kind == 'VariableDeclaration' and member.get('stateVariable'):
                    group, key = 'effectiveStateVariables', member['id']
                else:
                    continue
                if key is None:
                    contract['gaps'].append(f'声明 {member["id"]} 的 ABI 类型尚未支持')
                    contract[group].append(member['id'])
                elif key not in seen[group]:
                    seen[group].add(key)
                    contract[group].append(member['id'])
    return contracts, functions


def _entry_indices(abi, contract, functions, nodes, units):
    entries, constructors, gaps, seen = [], [], list(contract['gaps']), set()
    candidates = {}
    for identity in contract['effectiveFunctions']:
        function = functions[identity]
        node = function['node']
        if function['visibility'] not in {'public', 'external'} and function['kind'] not in {'fallback', 'receive'}:
            continue
        signature = function['signature']
        if signature:
            candidates.setdefault(signature, []).append(('function', identity))
    for identity in contract['effectiveStateVariables']:
        node = nodes[identity]
        if node.get('visibility') != 'public':
            continue
        arguments = _getter_inputs(node.get('typeName'), nodes)
        if arguments is None:
            gaps.append(f'getter 声明 {identity} 的输入类型尚未支持')
            continue
        signature = node['name'] + '(' + ','.join(arguments) + ')'
        candidates.setdefault(signature, []).append(('getter', identity))
    for item in abi:
        if not isinstance(item, dict):
            _fail('ABI 元素必须为对象')
        kind = item.get('type')
        if kind == 'constructor':
            constructors.append({'abi': item, 'kind': 'constructor'})
            continue
        if kind in {'event', 'error'}:
            continue
        if kind not in {'function', 'fallback', 'receive'}:
            _fail('ABI 入口类型无效')
        if kind == 'function':
            if not isinstance(item.get('name'), str) or not isinstance(item.get('inputs'), list):
                _fail('ABI 函数入口缺少名称或参数')
            signature = item['name'] + '(' + ','.join(_abi_type(parameter) for parameter in item['inputs']) + ')'
        else:
            signature = kind + '()'
        if signature in seen:
            _fail('ABI 入口签名重复')
        seen.add(signature)
        matches = candidates.get(signature, [])
        matched = len(matches) == 1
        entry = {'kind': matches[0][0] if matched and kind == 'function' else kind,
                 'signature': signature, 'abi': item, 'matched': matched,
                 'declarationId': matches[0][1] if matched else None, 'span': None}
        if matched:
            declaration = nodes[entry['declarationId']]
            entry['span'] = source_span(declaration, units)
            if entry['kind'] == 'getter':
                entry['resource'] = {'declarationId': declaration['id'], 'typeName': declaration.get('typeName')}
                expected_returns = _getter_outputs(declaration.get('typeName'), nodes)
                expected_mutability = 'view'
            else:
                expected_returns = [_type_name(parameter.get('typeName'), nodes)
                                    for parameter in declaration.get('returnParameters', {}).get('parameters', [])]
                expected_mutability = declaration.get('stateMutability')
            actual_returns = [_abi_type(parameter) for parameter in item.get('outputs', [])]
            if kind == 'function' and (expected_returns is None or None in expected_returns or expected_returns != actual_returns):
                entry['matched'] = False
                gaps.append(f'ABI 入口 {signature} 返回类型与 AST 不一致或尚未支持')
            if expected_mutability is not None and expected_mutability != item.get('stateMutability'):
                entry['matched'] = False
                gaps.append(f'ABI 入口 {signature} 状态可变性与 AST 不一致')
        else:
            gaps.append(f'ABI 入口 {signature} 无法唯一绑定声明')
        entries.append(entry)
    for signature in candidates.keys() - seen:
        gaps.append(f'公开声明 {signature} 未出现在目标 ABI')
    return entries, constructors, gaps


def _load_bound_compilation(manifest, root):
    """核验固定产物、实际重新编译对照后构建声明与入口索引。"""
    root = Path(root).resolve()
    if isinstance(manifest, (str, Path)):
        path = Path(manifest)
        manifest, manifest_bytes = _read_json(path if path.is_absolute() else root / path)
    elif isinstance(manifest, dict):
        manifest = json.loads(_canonical(manifest))
        manifest_bytes = _canonical(manifest)
    else:
        _fail('manifest 必须为对象或路径')
    required = ('bindingPath', 'bindingSha256', 'inputPath', 'outputPath',
                'targetSourceUnit', 'targetContract', 'expectedSourceHash')
    if manifest.get('schemaVersion') != '1' or manifest.get('provider') != 'solc-standard-json' or any(not manifest.get(key) for key in required):
        _fail('manifest 缺少显式编译产物绑定')
    binding, binding_bytes = _read_json(_path(root, manifest['bindingPath']))
    _check_hash(binding_bytes, manifest['bindingSha256'], '编译收据')
    compiler_input, input_bytes = _read_json(_path(root, manifest['inputPath']))
    compiler_output, output_bytes = _read_json(_path(root, manifest['outputPath']))
    _check_hash(input_bytes, binding.get('inputSha256'), '编译输入')
    _check_hash(output_bytes, binding.get('outputSha256'), '编译输出')
    if compiler_input.get('language') != 'Solidity' or _canonical(binding.get('settings')) != _canonical(compiler_input.get('settings')):
        _fail('编译语言或设置不匹配')
    statuses = [binding[key] for key in ('exitCode', 'returnCode') if key in binding]
    if not statuses or any(not _integer(code) or code != 0 for code in statuses):
        _fail('编译收据没有成功退出证据')
    if binding.get('status') not in (None, 'COMPILED') or binding.get('errors') or any(
            error.get('severity') == 'error' for error in compiler_output.get('errors', [])):
        _fail('编译存在错误')
    compiler = _path(root, binding.get('compiler'))
    try:
        compiler_bytes = compiler.read_bytes()
    except OSError as error:
        _fail(f'固定编译器不可读：{error}')
    _check_hash(compiler_bytes, binding.get('compilerSha256'), '固定编译器')
    command = binding.get('command')
    if not isinstance(command, list) or len(command) != 2 or _path(root, command[0]).resolve() != compiler.resolve() or command[1] != '--standard-json':
        _fail('编译命令未绑定固定 standard-json 二进制')
    try:
        result = subprocess.run([str(compiler.resolve()), '--version'], capture_output=True, timeout=5, check=False)
        actual_version = result.stdout.decode('utf-8').strip()
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        _fail(f'固定编译器版本查询失败：{error}')
    if result.returncode != 0 or actual_version != str(binding.get('compilerVersion', '')).strip() or 'Version: ' not in actual_version:
        _fail('固定编译器版本不匹配')
    _check_hash(compiler.read_bytes(), binding.get('compilerSha256'), '版本查询后的固定编译器')
    version = actual_version.split('Version: ', 1)[1].split('+', 1)[0].split()[0]
    sources = compiler_input.get('sources')
    source_receipts = binding.get('sourceUnits')
    output_sources = compiler_output.get('sources')
    if not isinstance(sources, dict) or not sources or not isinstance(source_receipts, dict) or not isinstance(output_sources, dict):
        _fail('缺少完整源码闭包')
    if set(sources) != set(source_receipts) or set(sources) != set(output_sources):
        _fail('输入、输出及收据源码闭包不一致')
    source_hashes = {}
    units = {}
    for source_unit, source in sources.items():
        if not isinstance(source, dict) or not isinstance(source.get('content'), str) or 'urls' in source:
            _fail('编译输入必须内嵌完整源码 content')
        receipt = source_receipts[source_unit]
        if not isinstance(receipt, dict):
            _fail('源码收据无效')
        content = source['content'].encode('utf-8')
        _check_hash(content, receipt.get('sha256'), f'内嵌源码 {source_unit}')
        source_path = _path(root, receipt.get('path'))
        try:
            disk = source_path.read_bytes()
        except OSError as error:
            _fail(f'源码文件不可读：{error}')
        _check_hash(disk, receipt.get('sha256'), f'磁盘源码 {source_unit}')
        if receipt.get('resolvedPath') and _path(root, receipt['resolvedPath']).resolve() != source_path.resolve():
            _fail('源码解析路径与收据不一致')
        output_source = output_sources[source_unit]
        unit_id = output_source.get('id')
        ast = output_source.get('ast')
        if not _integer(unit_id) or unit_id < 0 or unit_id in units or not isinstance(ast, dict) or ast.get('nodeType') != 'SourceUnit':
            _fail('输出缺少唯一源码单元 AST')
        if ast.get('absolutePath') != source_unit:
            _fail('AST 源码单元路径不匹配')
        units[unit_id] = {'sourceUnit': source_unit, 'path': str(source_path.resolve()),
                          'content': source['content'], 'sha256': receipt['sha256'], 'ast': ast}
        source_hashes[source_unit] = receipt['sha256']
    _check_hash(_canonical(source_hashes), binding.get('sourceClosureSha256'), '源码闭包')
    main = manifest['targetSourceUnit']
    if binding.get('mainSource') != main or main not in sources:
        _fail('目标源码未绑定主源码')
    _check_hash(sources[main]['content'].encode('utf-8'), manifest['expectedSourceHash'], '目标源码')
    # 只有完整的内嵌源码及磁盘闭包核验通过，才执行标准输入编译。
    try:
        compiled = subprocess.run([str(compiler.resolve()), '--standard-json'], input=input_bytes,
                                  capture_output=True, timeout=120, check=False, cwd=root)
    except (OSError, subprocess.TimeoutExpired) as error:
        _fail(f'固定编译器重新编译失败：{error}')
    _check_hash(compiler.read_bytes(), binding.get('compilerSha256'), '重新编译后的固定编译器')
    if compiled.returncode != 0:
        _fail(f'固定编译器重新编译退出失败：{compiled.returncode}')
    observed_output = _parse_json(compiled.stdout, '固定编译器重新编译输出')
    if _canonical(observed_output) != _canonical(compiler_output):
        _fail('固定编译器重新编译结果与绑定输出不一致')
    nodes, declarations, builtin_references = {}, {}, {}
    for unit_id, unit in units.items():
        for node in _walk(unit['ast']):
            if 'src' not in node:
                _fail('AST 节点缺少字节跨度')
            if source_span(node, units)['sourceUnitId'] != unit_id:
                _fail('AST 节点引用了其他源码单元跨度')
            identity = node.get('id')
            if identity is None and node['nodeType'].startswith('Yul'):
                continue
            if not _integer(identity) or identity < 0 or identity in nodes:
                _fail('AST 节点 ID 缺失或重复')
            nodes[identity] = node
            if _declaration_type(node):
                declarations[identity] = node
    for node in nodes.values():
        identity = node.get('referencedDeclaration')
        if identity is None:
            continue
        if not _integer(identity):
            _fail('referencedDeclaration 必须为整数')
        if identity in nodes:
            if not _declaration_type(nodes[identity]):
                _fail('引用目标不是声明')
            continue
        builtin = _builtin(node)
        if not builtin or (identity >= 0 and not version.startswith(('0.4.', '0.5.'))):
            _fail(f'无法解析声明引用：{identity}')
        if identity in builtin_references and builtin_references[identity] != builtin:
            _fail('同一内置声明 ID 对应不同语义')
        builtin_references[identity] = builtin
    for node in nodes.values():
        scope = node.get('scope')
        if scope is not None and (not _integer(scope) or scope not in nodes):
            _fail('声明 scope 不存在')
        if node.get('nodeType') == 'ImportDirective':
            referenced = nodes.get(node.get('sourceUnit'), {})
            if referenced.get('nodeType') != 'SourceUnit' or referenced.get('absolutePath') != node.get('absolutePath'):
                _fail('import 源码闭包声明不匹配')
        if node.get('nodeType') == 'UserDefinedTypeName' and declarations.get(node.get('referencedDeclaration'), {}).get('nodeType') not in {
                'ContractDefinition', 'StructDefinition', 'EnumDefinition', 'UserDefinedValueTypeDefinition'}:
            _fail('自定义类型引用没有绑定类型声明')
        if node.get('nodeType') == 'ModifierInvocation' and declarations.get(node.get('modifierName', {}).get('referencedDeclaration'), {}).get('nodeType') not in {
                'ModifierDefinition', 'ContractDefinition'}:
            _fail('修饰器调用没有绑定修饰器或构造声明')
        expected_kinds = {'baseFunctions': 'FunctionDefinition', 'baseModifiers': 'ModifierDefinition',
                          'contractDependencies': 'ContractDefinition'}
        for key, expected_kind in expected_kinds.items():
            if any(not _integer(identity) or declarations.get(identity, {}).get('nodeType') != expected_kind for identity in node.get(key, [])):
                _fail(f'{key} 含悬空声明或错误声明类型')
        for exported in node.get('exportedSymbols', {}).values():
            if not isinstance(exported, list) or any(not _integer(identity) or identity not in declarations for identity in exported):
                _fail('导出符号含悬空声明')
        if 'functionReturnParameters' in node and nodes.get(node['functionReturnParameters'], {}).get('nodeType') != 'ParameterList':
            _fail('返回语句引用的参数声明不存在')
        if any(identity is not None and declarations.get(identity, {}).get('nodeType') != 'VariableDeclaration'
               for identity in node.get('assignments', [])):
            _fail('局部声明赋值引用无效')
        for identity in node.get('overloadedDeclarations', []):
            if identity not in declarations and identity not in builtin_references and not _builtin(node):
                _fail('重载候选包含悬空声明')
    contracts, functions = _contract_indices(nodes, units)
    main_ast = output_sources[main]['ast']
    matches = [node for node in main_ast.get('nodes', []) if node.get('nodeType') == 'ContractDefinition' and node.get('name') == manifest['targetContract']]
    if len(matches) != 1:
        _fail('目标合约无法唯一绑定')
    target_id = matches[0]['id']
    artifact = compiler_output.get('contracts', {}).get(main, {}).get(manifest['targetContract'])
    if not isinstance(artifact, dict) or not isinstance(artifact.get('abi'), list):
        _fail('目标合约缺少 ABI')
    entries, constructors, gaps = _entry_indices(artifact['abi'], contracts[target_id], functions, nodes, units)
    receipt_digest = _digest(binding_bytes)
    environment = {'receiptDigest': receipt_digest, 'inputSha256': _digest(input_bytes),
                   'outputSha256': _digest(output_bytes), 'compilerSha256': _digest(compiler_bytes),
                   'sourceClosureSha256': binding['sourceClosureSha256'], 'settings': compiler_input['settings']}
    return {'provider': 'solc-standard-json', 'verificationStatus': 'RECOMPILED_MATCH',
            'verifiedOutputSha256': _digest(_canonical(observed_output)),
            'manifest': manifest, 'manifestDigest': _digest(manifest_bytes),
            'receiptDigest': receipt_digest, 'environmentHash': _digest(_canonical(environment)),
            'sourceHash': source_hashes[main], 'targetSourceUnit': main, 'targetContract': manifest['targetContract'],
            'targetContractId': target_id, 'compilerVersion': version, 'input': compiler_input,
            'output': compiler_output, 'binding': binding, 'units': units, 'nodes': nodes,
            'declarations': declarations, 'builtinReferences': builtin_references, 'contracts': contracts,
            'functions': functions, 'entries': entries, 'constructors': constructors,
            'entryGaps': gaps, 'status': 'PARTIAL',
            'limitations': ['编译 AST 为结构证据；交易可行性、动态实现和相关入口语义覆盖须另行证明'] + gaps}


def load_bound_compilation(manifest, root):
    """所有不合法结构统一失败，避免解析异常被调用者误当成空事实。"""
    try:
        return _load_bound_compilation(manifest, root)
    except CompilationBindingError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
        _fail(f'编译产物结构不合法：{error}')


def _resource(expression, declarations):
    if not isinstance(expression, dict):
        return None
    kind = expression.get('nodeType')
    if kind == 'Identifier':
        identity = expression.get('referencedDeclaration')
        declaration = declarations.get(identity, {})
        if declaration.get('nodeType') == 'VariableDeclaration' and declaration.get('stateVariable'):
            return {'declarationId': identity, 'expression': expression, 'segments': []}
    if kind in {'IndexAccess', 'MemberAccess'}:
        base = expression.get('baseExpression') if kind == 'IndexAccess' else expression.get('expression')
        resource = _resource(base, declarations)
        if resource:
            segment = {'kind': 'index', 'expression': expression.get('indexExpression')} if kind == 'IndexAccess' else {
                'kind': 'member', 'declarationId': expression.get('referencedDeclaration'), 'name': expression.get('memberName')}
            return dict(resource, expression=expression, segments=resource['segments'] + [segment])
    return None


def call_operation(node, bundle):
    """按编译类型识别调用结构；标签不说明授权、外部效果或交易可行性。"""
    if not isinstance(node, dict) or node.get('nodeType') != 'FunctionCall' or node.get('kind') == 'typeConversion':
        return None
    expression = node.get('expression', {})
    options = []
    if expression.get('nodeType') == 'FunctionCallOptions':
        options.extend(expression.get('options', []))
        expression = expression.get('expression', {})
    # 旧 solc 的 address.call.value(v)(data) 仍使用最外层调用的原始跨度。
    while expression.get('nodeType') == 'FunctionCall':
        setter = expression.get('expression', {})
        if (setter.get('nodeType') == 'MemberAccess' and setter.get('memberName') in {'value', 'gas'}
                and setter.get('typeDescriptions', {}).get('typeIdentifier', '').startswith(
                    ('t_function_setvalue_', 't_function_setgas_'))):
            options = list(expression.get('arguments', [])) + options
            expression = setter.get('expression', {})
        else:
            break
    reference = expression.get('referencedDeclaration')
    identity = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
    builtin = bundle['builtinReferences'].get(reference)
    if (expression.get('nodeType') == 'Identifier' and reference not in bundle['declarations']
            and builtin in {'selfdestruct', 'suicide'} and identity.startswith(f't_function_{builtin}_')):
        return {'callKind': 'CALL', 'semanticTags': ['TERMINATION']}
    if identity.startswith('t_function_external'):
        static = '_view' in identity or '_pure' in identity
        return {'callKind': 'STATICCALL' if static else 'CALL',
                'semanticTags': ['EXTERNAL_CALL', 'STATIC_CALL'] if static else ['EXTERNAL_CALL']}
    if expression.get('nodeType') != 'MemberAccess' or reference in bundle['declarations']:
        return None
    kinds = {'transfer': ('transfer', 'CALL', 'NATIVE_TRANSFER'),
             'send': ('send', 'CALL', 'NATIVE_TRANSFER'),
             'call': ('barecall', 'CALL', 'LOW_LEVEL_CALL'),
             'delegatecall': ('baredelegatecall', 'DELEGATECALL', 'DELEGATE_EXECUTION'),
             'callcode': ('barecallcode', 'CALLCODE', 'DELEGATE_EXECUTION'),
             'staticcall': ('barestaticcall', 'STATICCALL', 'STATIC_CALL')}
    spec = kinds.get(expression.get('memberName'))
    if spec is None or not identity.startswith(f't_function_{spec[0]}_'):
        return None
    return {'callKind': spec[1], 'semanticTags': [spec[2]], 'native': True,
            'receiver': expression.get('expression'), 'options': options}


def _call_semantics(node, bundle):
    expression = node.get('expression', {})
    if expression.get('nodeType') == 'FunctionCallOptions':
        expression = expression.get('expression', {})
    reference = expression.get('referencedDeclaration')
    if reference in bundle['builtinReferences']:
        return 'builtin', bundle['builtinReferences'][reference], reference
    declaration = bundle['declarations'].get(reference, {})
    type_identity = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
    if type_identity.startswith('t_function_internal'):
        return 'internal', None, reference
    if type_identity.startswith('t_function_external'):
        return 'external', None, reference
    if type_identity.startswith('t_function_'):
        return 'low-level-or-builtin', None, reference
    if declaration.get('nodeType') == 'FunctionDefinition':
        return 'unresolved', None, reference
    return 'unresolved', None, reference


def extract_compiler_facts(bundle):
    """导出 AST 观察事实，保留调用与修饰器身份；不伪造 CFG 完整性。"""
    facts, scopes = [], []
    limitations = list(bundle['limitations'])
    unsupported = {'InlineAssembly', 'ForStatement', 'WhileStatement', 'DoWhileStatement',
                   'TryStatement', 'FunctionCallOptions', 'NewExpression'}
    for identity, function in bundle['functions'].items():
        scope = function['canonicalName'] + f'@{identity}'
        gaps = []
        body = function['body']
        if body is None:
            gaps.append('没有实现函数体')
        for node in _walk(body):
            kind = node['nodeType']
            if kind in unsupported:
                gaps.append(f'{kind} 尚未取得路径语义证明')
            resource, fact_kind, extras = None, None, {}
            if kind == 'FunctionCall' and node.get('kind', 'functionCall') == 'functionCall':
                call_kind, builtin, reference = _call_semantics(node, bundle)
                if builtin in {'require', 'assert'}:
                    fact_kind = 'CHECK'
                    extras = {'condition': node.get('arguments', [None])[0], 'abortOnFalse': True, 'builtin': builtin}
                else:
                    fact_kind = 'CALL'
                    extras = {'callKind': call_kind, 'targetDeclarationId': reference,
                              'arguments': node.get('arguments', []), 'builtin': builtin}
            elif kind == 'Assignment':
                resource = _resource(node.get('leftHandSide'), bundle['declarations'])
                if resource:
                    fact_kind = 'WRITE'
                    extras = {'operator': node.get('operator'), 'value': node.get('rightHandSide')}
                else:
                    fact_kind = 'EXPRESSION'
                    extras = {'resourceUnresolved': True}
            elif kind == 'UnaryOperation' and node.get('operator') in {'++', '--', 'delete'}:
                resource = _resource(node.get('subExpression'), bundle['declarations'])
                fact_kind = 'WRITE' if resource else 'EXPRESSION'
                extras = {'operator': node.get('operator')}
            elif kind == 'BinaryOperation':
                fact_kind = 'EXPRESSION'
                extras = {'operator': node.get('operator')}
            elif kind in {'IfStatement', 'Conditional'}:
                fact_kind = 'BRANCH'
                extras = {'condition': node.get('condition')}
            elif kind in {'Return', 'RevertStatement', 'PlaceholderStatement'}:
                fact_kind = {'Return': 'RETURN', 'RevertStatement': 'REVERT', 'PlaceholderStatement': 'PLACEHOLDER'}[kind]
            if fact_kind:
                span = source_span(node, bundle['units'])
                facts.append({'kind': fact_kind, 'sourceHash': bundle['sourceHash'], 'scope': scope,
                              'id': _digest(f'{bundle["environmentHash"]}:{identity}:{node["id"]}:{fact_kind}'.encode()),
                              'nodeId': node['id'], 'functionDeclarationId': identity, 'line': span['line'],
                              'sourceUnit': span['sourceUnit'], 'sourceUnitHash': bundle['units'][span['sourceUnitId']]['sha256'],
                              'span': span, 'resource': resource,
                              'expression': node, **extras})
        scopes.append({'id': scope, 'declarationId': identity, 'contract': bundle['contracts'][function['contractId']]['node']['name'],
                       'name': function['node'].get('name'), 'signature': function['signature'],
                       'modifiers': function['modifiers'], 'complete': False, 'limitations': sorted(set(gaps))})
        limitations.extend(f'{scope}: {gap}' for gap in sorted(set(gaps)))
    return {'schemaVersion': 'compiler-1', 'provider': bundle['provider'],
            'verificationStatus': bundle['verificationStatus'], 'sourceHash': bundle['sourceHash'],
            'environmentHash': bundle['environmentHash'], 'receiptDigest': bundle['receiptDigest'], 'status': 'PARTIAL',
            'targetContractId': bundle['targetContractId'], 'entries': bundle['entries'], 'entryGaps': bundle['entryGaps'],
            'stateVariables': [{'declarationId': identity, 'node': declaration,
                                'span': source_span(declaration, bundle['units'])}
                               for identity, declaration in bundle['declarations'].items()
                               if declaration.get('nodeType') == 'VariableDeclaration' and declaration.get('stateVariable')],
            'scopes': scopes, 'facts': facts, 'limitations': limitations}


def main():
    parser = argparse.ArgumentParser(description='核验固定 standard-json 编译产物并提取结构事实，不调用模型')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    try:
        bundle = load_bound_compilation(args.manifest, args.root)
        result = extract_compiler_facts(bundle)
        result['bindingSummary'] = {'sourceUnits': len(bundle['units']), 'astNodes': len(bundle['nodes']),
                                    'declarations': len(bundle['declarations']), 'abiEntries': len(bundle['entries']),
                                    'matchedEntries': sum(entry['matched'] for entry in bundle['entries']),
                                    'paidModelRequests': 0}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except CompilationBindingError as error:
        print(json.dumps({'provider': 'solc-standard-json', 'status': 'FAILED', 'facts': [],
                          'limitations': [str(error)], 'paidModelRequests': 0}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
