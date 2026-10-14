"""只读焦点索引：完整源码继续消费，结构闭包与防御证明分别记录。"""
import hashlib

from compiler_facts import _walk, _entry_indices, source_span, extract_compiler_facts
from program_facts import _tokens
from storage import fingerprint


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
