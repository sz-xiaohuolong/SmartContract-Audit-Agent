"""从已验证编译闭包生成候选目录；目录识别操作，不证明漏洞或保护充分。"""
from collections import defaultdict
from pathlib import Path
import subprocess

from compiler_facts import (CompilationBindingError, _entry_indices, call_operation, extract_compiler_facts,
                            load_bound_compilation, source_span)
from reentrancy_proofs import _ReentrancyGraph, _low_spec


def _capability(status, gaps=()):
    return {'status': status, 'gaps': sorted(set(gaps))}


def _structural_nodes(facts, closure, bundle):
    """结构位置不要求路径图可证明；仅接纳编译事实确定的状态写入或外部调用。"""
    for fact in facts:
        if fact['functionDeclarationId'] not in closure:
            continue
        kind, call_kind, value_call = fact['kind'], None, False
        if kind == 'CALL':
            ast = fact['expression']
            operation = call_operation(ast, bundle)
            value_call = _low_spec(ast) is not None
            if operation is None:
                # internal、require、纯 builtin 和无法识别的动态值都不是已确定的外部调用位置。
                continue
            call_kind = operation['callKind']
        elif kind != 'WRITE':
            continue
        yield {'kind': kind, 'nodeId': fact['nodeId'], 'span': fact['span'],
               'callKind': call_kind, 'lowLevelValueCall': value_call, 'structuralOnly': True}


def build_risk_catalog(bundle):
    """接收 load_bound_compilation 的预编译 bundle，枚举全部合约而非仅 targetContract。"""
    if (not isinstance(bundle, dict) or bundle.get('provider') != 'solc-standard-json'
            or bundle.get('verificationStatus') != 'RECOMPILED_MATCH'):
        raise CompilationBindingError('风险目录须来自实际重新编译匹配的 bundle')
    facts = extract_compiler_facts(bundle)
    by_node = defaultdict(list)
    for fact in facts['facts']:
        by_node[fact['nodeId']].append(fact)
    contracts, operations, gaps = [], [], list(facts['limitations'])
    for identity, contract in sorted(bundle['contracts'].items()):
        declaration = contract['node']
        span = source_span(declaration, bundle['units'])
        artifact = bundle['output'].get('contracts', {}).get(span['sourceUnit'], {}).get(declaration['name'])
        record = {'declarationId': identity, 'contract': declaration['name'],
                  'sourceUnit': span['sourceUnit'], 'sourceUnitHash': bundle['units'][span['sourceUnitId']]['sha256'],
                  'span': span, 'entries': [], 'constructors': []}
        if not isinstance(artifact, dict) or not isinstance(artifact.get('abi'), list):
            record['capability'] = _capability('UNAVAILABLE', ['合约 ABI 未输出，运行期入口目录不完整'])
            contracts.append(record)
            gaps.extend(record['capability']['gaps'])
            continue
        entries, constructors, entry_gaps = _entry_indices(artifact['abi'], contract,
            bundle['functions'], bundle['nodes'], bundle['units'])
        record['constructors'] = [{**constructor, 'capability': _capability('INITIALIZATION_ONLY')}
                                  for constructor in constructors]
        record['capability'] = _capability('PARTIAL' if entry_gaps else 'STRUCTURAL_ONLY', entry_gaps)
        local = {**bundle, 'targetContractId': identity, 'targetContract': declaration['name'], 'entries': entries}
        for entry in entries:
            function = bundle['functions'].get(entry.get('declarationId'))
            name = (function['kind'] if function and function['kind'] in {'fallback', 'receive'}
                    else function['node'].get('name') if function else entry['signature'].split('(', 1)[0])
            item = {'signature': entry['signature'], 'function': name, 'kind': entry['kind'],
                    'matched': entry['matched'], 'declarationId': entry['declarationId'], 'span': entry['span']}
            item['capability'] = _capability('STRUCTURAL_ONLY' if entry['matched'] else 'UNAVAILABLE')
            if not entry['matched']:
                item['capability']['gaps'].append('ABI 入口未唯一绑定 AST，不能生成已绑定操作')
            record['entries'].append(item)
            if not entry['matched'] or entry['kind'] == 'getter' or function is None:
                continue
            try:
                graph = _ReentrancyGraph(local, entry)
            except (CompilationBindingError, KeyError, TypeError, ValueError, IndexError, RecursionError):
                graph = None
                item['capability'] = _capability('UNAVAILABLE', ['入口控制流提取失败，仅保留编译结构位置'])
            if graph is not None:
                item['capability'] = _capability('BUDGET_EXHAUSTED' if graph.exhausted else 'PARTIAL'
                                                if graph.gaps else 'STRUCTURAL_ONLY', graph.gaps)
            closure = graph.closure if graph is not None else {entry['declarationId']}
            structural = list(_structural_nodes(facts['facts'], closure, local))
            seen = set()
            for node in (graph.nodes if graph is not None else []) + structural:
                if node['kind'] not in {'CALL', 'WRITE'} or 'span' not in node:
                    continue
                matches = by_node[node['nodeId']]
                preferred = [fact for fact in matches if fact['kind'] == node['kind']]
                if len(preferred or matches) != 1:
                    item['capability']['gaps'].append('操作不能唯一关联编译事实标识')
                    item['capability']['status'] = 'PARTIAL'
                    continue
                fact = (preferred or matches)[0]
                semantics = call_operation(fact['expression'], local) if node['kind'] == 'CALL' else None
                if fact['id'] in seen:
                    continue
                seen.add(fact['id'])
                status = 'STRUCTURAL_ONLY'
                if node['kind'] == 'CALL':
                    status = ('VALUE_CALL_STRUCTURAL_ONLY' if node.get('lowLevelValueCall') else
                              'EXTERNAL_IMPLEMENTATION_REQUIRED' if node.get('callKind') == 'CALL' else
                              'STATICCALL_STRUCTURAL_ONLY' if node.get('callKind') == 'STATICCALL' else
                              'MECHANISM_UNSUPPORTED')
                if node.get('structuralOnly'):
                    status = 'MECHANISM_UNSUPPORTED'
                operations.append({'contract': declaration['name'], 'contractDeclarationId': identity,
                    'function': name, 'entrySignature': entry['signature'], 'entryDeclarationId': entry['declarationId'],
                    'factId': fact['id'], 'nodeId': node['nodeId'], 'riskOperation': node['kind'],
                    'line': node['span']['line'], 'span': dict(node['span']),
                    'sourceUnit': node['span']['sourceUnit'], 'sourceUnitHash': fact['sourceUnitHash'],
                    'callKind': semantics['callKind'] if semantics else node.get('callKind'),
                    'semanticTags': semantics['semanticTags'] if semantics else ['STATE_WRITE'] if node['kind'] == 'WRITE' else [],
                    'candidateEligible': True,
                    'origin': 'AST_STRUCTURAL_ONLY' if node.get('structuralOnly') else 'BOUND_CONTROL_FLOW',
                    'capability': _capability(status, item['capability']['gaps'])})
            item['capability']['gaps'] = sorted(set(item['capability']['gaps']))
            gaps.extend(item['capability']['gaps'])
        contracts.append(record)
        gaps.extend(entry_gaps)
    operations.sort(key=lambda row: (row['contractDeclarationId'], row['entrySignature'],
                                     row['sourceUnit'], row['span']['start'], row['factId']))
    return {'schemaVersion': 'compiler-risk-1', 'semanticTagsVersion': 'operation-semantics-1', 'provider': bundle['provider'],
            'verificationStatus': bundle['verificationStatus'], 'sourceHash': bundle['sourceHash'],
            'targetSourceUnit': bundle['targetSourceUnit'], 'environmentHash': bundle['environmentHash'],
            'receiptDigest': bundle['receiptDigest'], 'sourceClosureSha256': bundle['binding']['sourceClosureSha256'],
            'status': 'PARTIAL', 'contracts': contracts, 'operations': operations,
            'sourceUnits': [{'sourceUnit': unit['sourceUnit'], 'sourceUnitId': identity, 'sha256': unit['sha256']}
                            for identity, unit in sorted(bundle['units'].items())],
            'limitations': ['目录只提供实际编译结构位置与能力范围，不能证明安全或可行漏洞'] + sorted(set(gaps))}


def load_risk_catalog(manifest, root):
    """需要从文件恢复时先复核完整编译身份；不会调用模型或改变配置。"""
    return build_risk_catalog(load_bound_compilation(manifest, root))


def prepare_model_context(root, target, view, mode):
    """在模型前构造全合约目录；发现入口与模型后的候选绑定清单分别保存。"""
    manifest = target.get('compilerManifest')
    from focus_context import build_syntax_context, build_focus_context
    if isinstance(target.get('fullSource'), str):
        view['focusContext'] = build_syntax_context(target['fullSource'])
    try:
        if manifest is None:
            if mode != 'real':
                return
            from tool_environment import _configuration
            path = Path(target.get('_toolConfigPath', Path(root) / 'config/tools.local.properties'))
            configuration = target.get('_toolConfiguration')
            if configuration is None:
                configuration = _configuration(path) if path.is_file() else {}
            if not configuration.get('tools.compiler.directory') and not target.get('compilerTemplate'):
                view['riskCatalogDiagnostic'] = {'status': 'UNAVAILABLE', 'reason': '固定编译目录未配置'}
                return
            from compilation_runtime import prepare_discovery_compilation
            manifest = prepare_discovery_compilation(root, {**target, '_toolConfiguration': configuration})
        bundle = load_bound_compilation(manifest, root)
        if bundle['sourceHash'] != target.get('fullSourceHash'):
            raise ValueError('风险目录与模型全文输入字节不一致')
        view['riskCatalog'] = build_risk_catalog(bundle)
        view['discoveryCompilation'] = manifest
        view['compiledFacts'] = extract_compiler_facts(bundle)
        view['focusContext'] = build_focus_context(bundle)
        view['riskCatalogDiagnostic'] = {'status': 'BOUND', 'receiptDigest': bundle['receiptDigest']}
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        view.pop('riskCatalog', None)
        view.pop('discoveryCompilation', None)
        view['riskCatalogDiagnostic'] = {'status': 'UNAVAILABLE', 'reason': str(error)}
