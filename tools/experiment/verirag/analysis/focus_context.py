"""只读焦点索引：完整源码继续消费，结构闭包与防御证明分别记录。"""
import hashlib
import json

from verirag.analysis.compiler_facts import _walk, _entry_indices, _resource, source_span, extract_compiler_facts
from verirag.analysis.program_facts import _tokens
from verirag.infrastructure.storage import fingerprint, encode

_PERMISSION_RELATION_LIMIT = 4096


def build_permission_index(bundle, entries, facts, entry_gaps=()):
    """权限相关关系只作当前源码观察；局部支配关系不等于完整保护证明。"""
    from verirag.analysis.access_call_proofs import _AccessCallGraph
    relations, gaps, entry_records, unknown_edges = [], [], [], []
    omitted = 0
    by_node = {fact['nodeId']: fact for fact in facts['facts']}

    def reference(node, fact=None, **extra):
        span = source_span(node, bundle['units'])
        return {'nodeId': node['id'], 'span': span,
            'sourceUnitHash': bundle['units'][span['sourceUnitId']]['sha256'],
            'receiptDigest': bundle['receiptDigest'],
            **({'factId': fact['id']} if fact else {}), **extra}

    def relation(kind, refs, **fields):
        nonlocal omitted
        if len(relations) >= _PERMISSION_RELATION_LIMIT:
            omitted += 1
            return
        item = {'kind': kind, 'references': refs, 'evidenceLevel': 'STRUCTURAL_OBSERVATION', **fields}
        item['id'] = fingerprint(item)
        relations.append(item)

    def condition_reads(condition, contract_id):
        from verirag.analysis.candidate_proofs import _Effects
        dispatch = _Effects({**bundle, 'targetContractId': contract_id})
        resources, visited = {}, set()
        remaining = 4096

        def read(value, active=(), lvalue=False):
            nonlocal remaining
            if not isinstance(value, (dict, list)):
                return
            remaining -= 1
            if remaining < 0:
                gaps.append('条件读取索引预算不足，存在未展开的依赖')
                return
            if isinstance(value, list):
                for child in value:
                    read(child, active, lvalue)
                return
            kind = value.get('nodeType')
            if kind == 'Assignment':
                read(value.get('leftHandSide'), active, value.get('operator') == '=')
                read(value.get('rightHandSide'), active)
                return
            if kind == 'UnaryOperation' and value.get('operator') == 'delete':
                read(value.get('subExpression'), active, True)
                return
            resource = _resource(value, bundle['declarations'])
            if resource:
                if not lvalue:
                    key = fingerprint(resource)
                    resources.setdefault(key, (resource, []))[1].append(reference(value))
                # 寻址键本身也会求值；不把纯赋值的左值误记成状态读取。
                if kind == 'IndexAccess':
                    read(value.get('indexExpression'), active)
                    read(value.get('baseExpression'), active, True)
                elif kind == 'MemberAccess':
                    read(value.get('expression'), active, True)
                return
            if kind == 'FunctionCall':
                expression = value.get('expression', {})
                target = expression.get('referencedDeclaration')
                type_id = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
                if type_id.startswith('t_function_internal') and target in bundle['functions']:
                    resolved = dispatch.target(expression)
                    if resolved is None:
                        gaps.extend(dispatch.gaps or ['条件内部调用的实际覆盖实现未解析'])
                        return
                    target = resolved['id']
                    if target in active:
                        gaps.append('条件内部调用递归，状态读取尚未完整展开')
                    elif target not in visited:
                        visited.add(target)
                        read(bundle['functions'][target]['node'], active + (target,))
                elif type_id.startswith('t_function_internal'):
                    gaps.append('条件内部调用目标未解析，状态读取不完整')
            for key, child in value.items():
                if isinstance(child, (dict, list)):
                    read(child, active, lvalue)

        read(condition)
        return resources.values()

    for fact in facts['facts']:
        common = {'functionDeclarationId': fact['functionDeclarationId'], 'factId': fact['id'],
                  'nodeId': fact['nodeId']}
        refs = [reference(fact['expression'], fact)]
        if fact['kind'] == 'WRITE':
            resource = fact.get('resource')
            if resource:
                relation('FUNCTION_WRITES_STATE', refs, **common,
                    stateDeclarationId=resource['declarationId'], resource=resource,
                    stateVersion='REQUIRES_PATH_BINDING')
        if fact['kind'] in {'CHECK', 'BRANCH'}:
            owner = bundle['functions'][fact['functionDeclarationId']]['contractId']
            for contract_id, contract in sorted(bundle['contracts'].items()):
                if owner not in contract['linearizedBaseContracts']:
                    continue
                for resource, read_refs in condition_reads(fact.get('condition'), contract_id):
                    relation('CHECK_READS_STATE', refs + read_refs, **common,
                        contractDeclarationId=contract_id,
                        stateDeclarationId=resource['declarationId'], resource=resource)
        if fact['kind'] == 'CALL' and fact.get('callKind') in {'external', 'unresolved', 'low-level-or-builtin'}:
            from verirag.analysis.compiler_facts import call_operation
            operation = call_operation(fact['expression'], bundle)
            expression = fact['expression'].get('expression', {})
            declaration = bundle['declarations'].get(expression.get('referencedDeclaration'), {})
            type_id = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
            compiler_local = (declaration.get('nodeType') in {'EventDefinition', 'ErrorDefinition'}
                or type_id.startswith(('t_function_abiencode', 't_function_bytesconcat',
                                      't_function_stringconcat', 't_function_arraypush', 't_function_arraypop'))
                or expression.get('nodeType') == 'NewExpression'
                   and expression.get('typeName', {}).get('nodeType') == 'ArrayTypeName')
            if (not compiler_local and not fact.get('builtin')
                    and (not operation or 'TERMINATION' not in operation['semanticTags'])):
                unknown_edges.append({'kind': 'EXTERNAL_EFFECT', **common, 'references': refs,
                    'reason': '外部或动态调用的实现、回调及状态效果尚未证明'})
                gaps.append('外部调用或动态调用存在未证明的实现、回调与状态效果')
        if fact.get('resourceUnresolved'):
            unknown_edges.append({'kind': 'UNRESOLVED_EFFECT', **common, 'references': refs})

    for entry in entries:
        if entry['kind'] == 'getter':
            continue
        identity = {key: entry[key] for key in ('signature', 'declarationId', 'contractDeclarationId', 'contract')}
        if not entry['matched']:
            gaps.append(f'{entry["contract"]}.{entry["signature"]} 入口未唯一绑定')
            entry_records.append({**identity, 'indexed': False})
            continue
        local = {**bundle, 'targetContractId': entry['contractDeclarationId'], 'targetContract': entry['contract']}
        try:
            graph = _AccessCallGraph(local, entry)
        except (ValueError, KeyError, TypeError, IndexError, RecursionError) as error:
            gaps.append(f'{entry["contract"]}.{entry["signature"]} 权限关系图无法展开：{type(error).__name__}')
            entry_records.append({**identity, 'indexed': False})
            continue
        entry_records.append({**identity, 'indexed': True, 'gaps': list(graph.gaps),
            'callClosure': sorted(graph.closure), 'complete': False})
        gaps.extend(f'{entry["contract"]}.{entry["signature"]}：{gap}' for gap in graph.gaps)
        for function_id in sorted(graph.closure):
            function = bundle['functions'][function_id]
            relation('ENTRY_REACHES_FUNCTION', [reference(function['node'])],
                entry=identity, functionDeclarationId=function_id, functionKind=function['kind'])
        for operation in graph.nodes:
            if operation['kind'] not in {'CALL', 'WRITE'} or operation.get('nodeId') not in by_node:
                continue
            fact = by_node[operation['nodeId']]
            for guard, condition in graph.guards(operation):
                guard_fact = by_node.get(guard.get('nodeId'))
                if guard_fact is None:
                    continue
                relation('CHECK_DOMINATES_OPERATION',
                    [reference(guard_fact['expression'], guard_fact), reference(fact['expression'], fact)],
                    entry=identity, checkFactId=guard_fact['id'], operationFactId=fact['id'],
                    context=operation.get('context', []), condition=condition,
                    resource=operation.get('resource'), stateVersions=sorted(
                        [(repr(key), value) for key, value in operation.get('versionsBefore', {}).items()]),
                    evidenceLevelDetail='DOMINANCE_IN_PARTIAL_CFG')
        if graph.gaps:
            unknown_edges.append({'kind': 'INCOMPLETE_ENTRY', 'entry': identity, 'gaps': list(graph.gaps)})

    observations = []
    for node in bundle['nodes'].values():
        if node.get('nodeType') == 'InlineAssembly':
            observations.append({'kind': 'ASSEMBLY', 'references': [reference(node)]})
            gaps.append('汇编可能包含未解析的状态读写和调用')
        if node.get('nodeType') == 'MemberAccess':
            base = node.get('expression', {})
            builtin = bundle['builtinReferences'].get(base.get('referencedDeclaration'))
            if (builtin, node.get('memberName')) in {('msg', 'sender'), ('tx', 'origin')}:
                observations.append({'kind': 'IDENTITY_SOURCE', 'identity': builtin + '.' + node['memberName'],
                    'references': [reference(node)]})
    if omitted:
        gaps.append(f'权限关系预算不足，遗漏 {omitted} 条观察关系；完整源码仍保留')
    states = [{'declarationId': state['declarationId'], 'name': state['node'].get('name'),
        'references': [reference(state['node'])],
        'typeIdentifier': state['node'].get('typeDescriptions', {}).get('typeIdentifier'),
        'initialization': {'kind': 'DECLARATION' if state['node'].get('value') is not None else 'DEFAULT',
                           'executed': False}} for state in facts['stateVariables']]
    constructors = [{'declarationId': identity, 'contractDeclarationId': function['contractId'],
        'references': [reference(function['node'])], 'executed': False}
        for identity, function in sorted(bundle['functions'].items()) if function['kind'] == 'constructor']
    return json.loads(encode({'schemaVersion': 'permission-facts-1', 'sourceHash': bundle['sourceHash'],
        'receiptDigest': bundle['receiptDigest'], 'environmentHash': bundle['environmentHash'],
        'sourceClosureSha256': bundle['binding']['sourceClosureSha256'],
        'complete': False, 'protectionProved': False, 'states': states, 'constructors': constructors,
        'functions': [{'declarationId': identity, 'name': function['canonicalName'], 'kind': function['kind'],
            'references': [reference(function['node'])]}
            for identity, function in sorted(bundle['functions'].items())],
        'entries': entry_records, 'relations': relations, 'observations': observations,
        'unknownEdges': unknown_edges, 'omittedRelationCount': omitted,
        'gaps': sorted(set(gaps + list(entry_gaps)))}))


def build_fact_guidance(context, catalog, *, max_bytes=16384):
    """白名单生成确定的事实提示；整体超限时拒绝，不裁去检查或写入者。"""
    index = context.get('permissionFacts')
    if (not isinstance(index, dict) or index.get('schemaVersion') != 'permission-facts-1'
            or context.get('capability') != 'COMPILED_STRUCTURE'
            or type(max_bytes) is not int or max_bytes < 1
            or any(index.get(key) != catalog.get(key) for key in
                   ('sourceHash', 'receiptDigest', 'environmentHash', 'sourceClosureSha256'))):
        raise ValueError('事实提示缺少匹配的编译索引与目录身份')
    keys = ('schemaVersion', 'sourceHash', 'receiptDigest', 'environmentHash', 'sourceClosureSha256',
            'complete', 'protectionProved', 'omittedRelationCount', 'states', 'constructors', 'functions',
            'entries', 'relations', 'observations', 'unknownEdges', 'gaps')
    frozen = {key: sorted(index[key], key=fingerprint) if isinstance(index[key], list) else index[key]
              for key in keys}
    names = {item['declarationId']: item['name'] for item in index['functions']}
    labels = {'FUNCTION_WRITES_STATE': '函数写入状态', 'CHECK_READS_STATE': '检查读取状态',
              'ENTRY_REACHES_FUNCTION': '入口可到达函数', 'CHECK_DOMINATES_OPERATION': '局部图中检查先于操作'}
    payload = {'说明': '当前源码结构观察，不是授权、漏洞或安全证明；未索引到检查不等于没有保护。',
        '状态': [{key: state[key] for key in ('declarationId', 'name', 'typeIdentifier', 'initialization')}
                 for state in sorted(index['states'], key=lambda row: row['declarationId'])],
        '运行入口': sorted(index['entries'], key=fingerprint),
        '构造初始化': sorted(index['constructors'], key=fingerprint),
        '操作': [{key: operation.get(key) for key in ('contract', 'entrySignature', 'factId', 'sourceUnit',
                    'line', 'riskOperation', 'semanticTags')}
                 for operation in sorted(catalog['operations'], key=fingerprint)],
        '关系': [], '身份与汇编观察': sorted(index['observations'], key=fingerprint),
        '缺口': sorted(index['gaps']), '未知边': sorted(index['unknownEdges'], key=fingerprint),
        '未知边数量': len(index['unknownEdges']),
        '省略关系数量': index['omittedRelationCount'], '完整保护已证明': False}
    for row in sorted(index['relations'], key=lambda row: row['id']):
        payload['关系'].append({'关系': labels[row['kind']], '关系ID': row['id'],
            '函数': names.get(row.get('functionDeclarationId')),
            **{key: row[key] for key in ('entry', 'contractDeclarationId', 'stateDeclarationId', 'factId', 'checkFactId',
                'operationFactId', 'context', 'resource', 'stateVersion') if key in row},
            '来源': row['references']})
    text = encode(payload).decode('utf-8')
    if len(text.encode('utf-8')) > max_bytes:
        raise ValueError('事实提示超过字节预算；未裁剪检查、写入者或全文，未调用模型')
    return {'schemaVersion': 'permission-guidance-1',
        **{key: index[key] for key in ('sourceHash', 'receiptDigest', 'environmentHash', 'sourceClosureSha256')},
        'indexSha256': fingerprint(frozen), 'text': text,
        'textSha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'textBytes': len(text.encode('utf-8')),
        'includedRelationIds': sorted(row['id'] for row in index['relations']),
        'omittedRelationIds': [], 'indexOmittedRelationCount': index['omittedRelationCount'], 'complete': False}


def _block(text, span, declaration=None):
    raw = text.encode('utf-8')[span['start']:span['start'] + span['length']]
    return {'id': fingerprint({'sourceUnit': span['sourceUnit'], 'span': span,
                'sourceHash': hashlib.sha256(text.encode()).hexdigest(), 'declarationId': declaration}),
            'declarationId': declaration, 'sourceUnit': span['sourceUnit'],
            'sourceHash': hashlib.sha256(text.encode()).hexdigest(), 'span': span,
            'bytesSha256': hashlib.sha256(raw).hexdigest(), 'text': raw.decode('utf-8')}


def build_focus_context(bundle):
    """从重验 AST 组织 ff／fm／fi／fv；不将内部调用闭包宣称完整保护闭包。"""
    if bundle.get('verificationStatus') != 'RECOMPILED_MATCH':
        raise ValueError('焦点上下文需要实际重编译匹配的收据')
    blocks, edges, state_refs, local_gaps = {}, {}, {}, {}
    units = {unit['sourceUnit']: unit for unit in bundle['units'].values()}
    def add(identity):
        node = bundle['nodes'][identity]
        span = source_span(node, bundle['units'])
        text = bundle['input']['sources'][span['sourceUnit']]['content']
        block = _block(text, span, identity)
        blocks[block['id']] = block
        return block['id']
    for identity, function in bundle['functions'].items():
        calls, states, gaps = [], set(), []
        if function['body'] is None:
            gaps.append('声明缺少实现')
        for node in _walk(function['node']):
            reference = node.get('referencedDeclaration')
            declaration = bundle['declarations'].get(reference, {})
            if declaration.get('stateVariable'):
                states.add(reference)
            if node.get('nodeType') == 'FunctionCall':
                expression = node.get('expression', {})
                ref = expression.get('referencedDeclaration')
                type_id = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
                if ref in bundle['functions'] and 't_function_internal' in type_id:
                    calls.append(ref)
                elif 't_function_internal' in type_id:
                    gaps.append('间接内部调用目标未唯一绑定函数声明')
                elif 't_function_external' in type_id or ref is None:
                    gaps.append('外部或动态调用实现未纳入内部闭包')
            if node.get('nodeType') in {'InlineAssembly', 'YulBlock'}:
                gaps.append('assembly 语义需单独证明')
            if node.get('nodeType') == 'VariableDeclaration' and node.get('storageLocation') == 'storage':
                gaps.append('storage 别名需要工具和路径交叉核验')
        for invocation in function['modifiers']:
            ref = invocation.get('modifierName', {}).get('referencedDeclaration')
            if ref in bundle['functions']:
                calls.append(ref)
            else:
                gaps.append('修饰器未绑定实现')
        edges[identity], state_refs[identity], local_gaps[identity] = calls, states, gaps
    facts = extract_compiler_facts(bundle)
    records, all_entries, entry_gaps = [], [], []
    for contract_id, contract in sorted(bundle['contracts'].items()):
        contract_span = source_span(contract['node'], bundle['units'])
        artifact = bundle['output'].get('contracts', {}).get(contract_span['sourceUnit'], {}).get(contract['node']['name'])
        if not isinstance(artifact, dict) or not isinstance(artifact.get('abi'), list):
            entry_gaps.append('合约 ' + contract['node']['name'] + ' 缺少 ABI 入口'); continue
        entries, _, gaps = _entry_indices(artifact['abi'], contract, bundle['functions'], bundle['nodes'], bundle['units'])
        all_entries.extend({**entry, 'contract': contract['node']['name'], 'contractDeclarationId': contract_id} for entry in entries)
        entry_gaps.extend(gaps)
    for entry in all_entries:
        if entry.get('kind') == 'getter' or not entry.get('matched'):
            continue
        identity = entry['declarationId']
        reached, active, gaps = set(), set(), []
        def visit(current):
            if current in active:
                gaps.append('递归内部调用闭包未证明'); return
            if current in reached:
                return
            if len(reached) >= 256:
                gaps.append('内部调用索引预算不足'); return
            reached.add(current); active.add(current)
            gaps.extend(local_gaps[current])
            for child in edges[current]:
                visit(child)
            active.remove(current)
        visit(identity)
        states = set().union(*(state_refs[x] for x in reached))
        function = bundle['functions'][identity]
        modifier_ids = [x.get('modifierName', {}).get('referencedDeclaration') for x in function['modifiers']]
        modifiers = [add(x) for x in modifier_ids if x in bundle['functions']]
        related = []
        for other in all_entries:
            other_id = other.get('declarationId')
            # 相同声明的读写及潜在回调入口一并登记；这不是跨入口证明。
            pending, closure = [other_id], set()
            while pending and len(closure) < 256:
                child = pending.pop()
                if child in closure or child not in edges: continue
                closure.add(child); pending.extend(edges[child])
            resources = set().union(*(state_refs[x] for x in closure)) if closure else set()
            if states & resources:
                related.append({'signature': other['signature'], 'declarationId': other_id,
                    'stateDeclarations': sorted(states & resources),
                    'writeFactIds': [f['id'] for f in facts['facts'] if f['kind'] == 'WRITE'
                                    and f['functionDeclarationId'] in closure]})
        records.append({'signature': entry['signature'], 'declarationId': identity,
            'contract': entry['contract'], 'contractDeclarationId': entry['contractDeclarationId'],
            'ff': [add(identity)], 'fm': modifiers,
            'fi': [add(x) for x in sorted(reached - {identity} - set(modifier_ids))],
            'fv': [add(x) for x in sorted(states)], 'stateDeclarations': sorted(states),
            'modifierOrder': modifier_ids, 'internalClosureComplete': not gaps,
            'protectionClosureComplete': False, 'relatedEntries': related,
            'gaps': sorted(set(gaps)), 'callbackBoundary': '外部实现及回调前提另行核验'})
    return {'schemaVersion': 'focus-context-1', 'capability': 'COMPILED_STRUCTURE',
        'parserIdentity': 'bound-solc-ast', 'sourceHash': bundle['sourceHash'],
        'receiptDigest': bundle['receiptDigest'], 'environmentHash': bundle['environmentHash'],
        'complete': False, 'inputMode': 'FULL_UNCHANGED', 'consumedByModel': False,
        'blocks': list(blocks.values()), 'entries': records,
        'permissionFacts': build_permission_index(bundle, all_entries, facts, entry_gaps),
        'sourceUnits': [{'sourceUnit': name, 'sha256': unit['sha256']} for name, unit in sorted(units.items())],
        'gaps': sorted(set(entry_gaps + [gap for record in records for gap in record['gaps']]))}


def build_syntax_context(source, source_unit='contracts/C.sol'):
    """词法回退只提供声明原文；缺导入时仍展示可解析部分，D2不得消费为编译证据。"""
    result = {'schemaVersion': 'focus-context-1', 'capability': 'SYNTAX_ONLY',
        'parserIdentity': 'program-facts-tokenizer-1', 'sourceHash': hashlib.sha256(source.encode()).hexdigest(),
        'complete': False, 'inputMode': 'FULL_UNCHANGED', 'consumedByModel': False,
        'blocks': [], 'entries': [], 'gaps': ['仅词法索引；声明引用、继承及调用闭包未核验']}
    try:
        tokens, pairs = _tokens(source)
        values = [x[0] for x in tokens]
        if 'import' in values: result['gaps'].append('导入依赖尚未编译绑定')
        for i, token in enumerate(tokens):
            if token[0] not in {'function', 'modifier', 'constructor', 'fallback', 'receive'}: continue
            end = i
            while end < len(tokens) and values[end] not in {'{', ';'}: end += 1
            if end == len(tokens): raise ValueError('声明未闭合')
            finish = pairs[end] if values[end] == '{' else end
            start_byte = len(source[:token[1]].encode())
            end_byte = len(source[:tokens[finish][1] + len(values[finish])].encode())
            span = {'sourceUnit': source_unit, 'start': start_byte, 'length': end_byte - start_byte,
                    'line': token[2], 'endLine': tokens[finish][2]}
            block = _block(source, span)
            block['kind'] = token[0]
            result['blocks'].append(block)
    except (ValueError, KeyError, IndexError) as error:
        result.update(capability='UNAVAILABLE', blocks=[], gaps=[str(error)])
    return result
