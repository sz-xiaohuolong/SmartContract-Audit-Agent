"""绑定本机审计输入与受限 Solidity 语法树，不替代编译器和控制流证明。"""
import hashlib

from program_facts import _tokens, extract_facts
from storage import fingerprint

MAX_SOURCE_BYTES = 131072
MAX_MODEL_BYTES = 16 * 1024
MECHANISMS = frozenset({'ACCESS_CONTROL', 'REENTRANCY'})


def syntax_tree(source, facts=None):
    facts = facts or extract_facts(source)
    tokens, pairs = _tokens(source)
    values = [item[0] for item in tokens]
    contracts = []
    for index, value in enumerate(values[:-1]):
        if value not in ('contract', 'library', 'interface'):
            continue
        opening = next((at for at in range(index + 2, len(tokens)) if values[at] in ('{', ';')), None)
        if opening is None or values[opening] != '{':
            continue
        closing = pairs[opening]
        functions = []
        for at in range(opening + 1, closing):
            if values[at] not in ('function', 'constructor', 'fallback', 'receive'):
                continue
            name = (values[at + 1] if values[at + 1] != '(' else 'fallback') if values[at] == 'function' else values[at]
            body = next((offset for offset in range(at + 2, closing) if values[offset] in ('{', ';')), None)
            if body is not None and values[body] == '{':
                start, end = tokens[at][2], tokens[pairs[body]][2]
                scopes = [row for row in facts['scopes'] if row['contract'] == values[index + 1]
                          and row['name'] == name and row['id'].split('@')[-1].split(':')[0] == str(start)]
                scope = scopes[0] if len(scopes) == 1 else None
                operations = [row for row in facts['facts'] if scope and row['scope'] == scope['id']]
                calls = [row for row in operations if row['kind'] == 'CALL']
                writes = [row for row in operations if row['kind'] == 'WRITE']
                cei = 'UNKNOWN'
                if scope and scope['complete'] and calls and writes:
                    cei = 'WRITES_BEFORE_CALLS' if max(row['order'] for row in writes) < min(row['order'] for row in calls) else 'WRITE_AFTER_CALL'
                functions.append({'name': name, 'lineStart': start, 'lineEnd': end,
                                  'scopeId': scope['id'] if scope else None,
                                  'complete': bool(scope and scope['complete']),
                                  'externalCalls': calls, 'stateWrites': writes, 'cei': cei})
        contracts.append({'name': values[index + 1], 'lineStart': tokens[index][2],
                          'lineEnd': tokens[closing][2], 'functions': functions})
    return {'kind': 'SolidityStructure', 'sourceHash': facts['sourceHash'], 'contracts': contracts,
            'status': facts['status'], 'limitations': ['受限结构语法树，未进行 Solidity 编译、类型解析或完整路径证明'] + facts['limitations']}


def pasted_target(source, mechanism, function=None, risk_line=None):
    if (not isinstance(source, str) or not source.strip() or '\x00' in source
            or len(source.encode('utf-8')) > MAX_SOURCE_BYTES or mechanism not in MECHANISMS):
        raise ValueError('源码为空、超过 128 KiB，或审计方向无效')
    facts = extract_facts(source)
    tree = syntax_tree(source, facts)
    functions = [(contract['name'], row) for contract in tree['contracts'] for row in contract['functions']]
    if not functions:
        raise ValueError('未找到可定位的合约函数，请提供完整 Solidity 合约')
    if len(source.encode('utf-8')) > MAX_MODEL_BYTES and function is None and risk_line is None:
        raise ValueError('源码超过模型片段上限，请明确指定函数或风险行，不能自动缩小审计范围')
    if function is not None and (not isinstance(function, str) or not function.strip()):
        raise ValueError('函数名称无效')
    matches = [(contract, row) for contract, row in functions
               if function is None or function in (row['name'], contract + '.' + row['name'])]
    if risk_line is not None:
        if type(risk_line) is not int or risk_line < 1 or risk_line > len(source.splitlines()):
            raise ValueError('风险行必须是源码范围内的整数')
        matches = [(contract, row) for contract, row in matches if row['lineStart'] <= risk_line <= row['lineEnd']]
    if not matches or (function is not None or risk_line is not None) and len(matches) != 1:
        raise ValueError('目标函数或风险行不唯一；重载或同名函数请指定风险行和合约名')
    contract, selected = matches[0]
    full = len(source.encode('utf-8')) <= MAX_MODEL_BYTES and function is None and risk_line is None
    start, end = (1, len(source.splitlines())) if full else (selected['lineStart'], selected['lineEnd'])
    model_source = source if full else '\n'.join(source.splitlines()[start - 1:end])
    if len(model_source.encode('utf-8')) > MAX_MODEL_BYTES:
        raise ValueError('模型源码超过 16 KiB，请选择更小的目标函数')
    source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    identity = fingerprint({'sourceHash': source_hash, 'mechanism': mechanism,
                            'function': selected['name'], 'contract': contract,
                            'lineStart': start, 'lineEnd': end, 'riskLine': risk_line})
    return {'sampleId': 'pasted-' + identity[:20], 'source': source, 'fullSource': source,
            'modelSource': model_source, 'fullSourceHash': source_hash, 'sourceHash': source_hash,
            'modelSourceHash': hashlib.sha256(model_source.encode('utf-8')).hexdigest(),
            'scope': 'FULL' if full else 'FUNCTION', 'lineStart': start, 'lineEnd': end,
            'mechanism': mechanism, 'function': selected['name'], 'contract': contract,
            'vulnerableLines': [risk_line] if risk_line is not None else [], 'runnable': True,
            'inputKind': 'PASTED', 'researchEligible': False, 'syntax': tree}


def hypothesis_matches_target(hypothesis, target, source):
    """FULL 核验全文声明，FUNCTION 严格绑定所选声明；整行保存不扩大函数审计范围。"""
    if not isinstance(source, str) or source != target.get('fullSource'):
        return False
    if hashlib.sha256(source.encode('utf-8')).hexdigest() != target.get('fullSourceHash'):
        return False
    start, end, line = target.get('lineStart'), target.get('lineEnd'), hypothesis.get('riskLine')
    if (any(type(value) is not int for value in (start, end, line))
            or not 1 <= start <= line <= end <= len(source.splitlines())
            or hypothesis.get('vulnerabilityType', hypothesis.get('mechanism')) != target.get('mechanism')):
        return False
    scope = target.get('scope')
    if scope not in ('FULL', 'FUNCTION'):
        return False
    expected = source if scope == 'FULL' else '\n'.join(source.splitlines()[start - 1:end])
    if (target.get('modelSource') != expected
            or target.get('modelSourceHash') != hashlib.sha256(expected.encode('utf-8')).hexdigest()):
        return False
    functions = [(contract['name'], row) for contract in syntax_tree(source)['contracts']
                 for row in contract['functions']]
    if scope == 'FULL':
        return any(contract == hypothesis.get('contract') and row['name'] == hypothesis.get('function')
                   and row['lineStart'] <= line <= row['lineEnd'] for contract, row in functions)
    selected = [(contract, row) for contract, row in functions
                if row['name'] == target.get('function')
                and (not target.get('contract') or contract == target['contract'])
                and start <= row['lineStart'] <= row['lineEnd'] <= end]
    contracts = {contract for contract, _ in selected}
    if len(contracts) != 1 or len(selected) != 1:
        return False
    return (hypothesis.get('contract') in contracts
            and any(contract == hypothesis['contract'] and row['name'] == hypothesis.get('function')
                    and row['lineStart'] <= line <= row['lineEnd'] for contract, row in selected))


def normalize_target(target):
    row = dict(target)
    source = row['fullSource']
    if len(source.encode('utf-8')) > MAX_SOURCE_BYTES:
        raise ValueError('预置目标源码超过工作台上限')
    actual = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if actual != row['fullSourceHash']:
        raise ValueError('预置源码摘要不一致')
    row.update(source=source, sourceHash=actual, syntax=syntax_tree(source), researchEligible=False)
    row.setdefault('vulnerableLines', [])
    row.setdefault('inputKind', 'PRESET')
    if not row.get('runnable'):
        raise ValueError('预置目标不满足单次输入范围')
    return row
