"""D2 核验漏洞假设；保护义务与漏洞结论使用相反的三态语义。"""
import re
from pathlib import PurePosixPath

from program_facts import _tokens, extract_facts

OBLIGATIONS = ('actor', 'resource', 'pre_risk_guard', 'entry_coverage', 'state_version', 'bypass')


ISSUE_TYPES = {
    'reentrancy-eth': ('REENTRANCY', 'CALL'),
    'reentrancy-no-eth': ('REENTRANCY', 'CALL'),
    'reentrancy-benign': ('REENTRANCY', 'CALL'),
    'reentrancy-events': ('REENTRANCY', 'CALL'),
    'protected-vars': ('ACCESS_CONTROL', 'WRITE'),
    'arbitrary-send-eth': ('ACCESS_CONTROL', 'CALL'),
    'arbitrary-send-erc20': ('ACCESS_CONTROL', 'CALL'),
    'unprotected-upgrade': ('ACCESS_CONTROL', 'CALL'),
    'suicidal': ('ACCESS_CONTROL', 'CALL'),
}


def _references(facts):
    result = []
    for fact in facts:
        ref = {'factId': fact['id'], 'line': fact['line'], 'scope': fact['scope']}
        if ref not in result:
            result.append(ref)
    return result


def _set(result, name, status, facts, reason):
    item = next(item for item in result['obligations'] if item['name'] == name)
    item.update(status=status, references=_references(facts), reason=reason)


def _path(result, status, facts, reason):
    result['pathEvidence'] = {'status': status, 'references': _references(facts), 'reason': reason}


def _source_metadata(source, facts):
    """补读可见性、声明类型和赋值表达式，不扩大事实提取器的完整性承诺。"""
    tokens, pairs = _tokens(source)
    values = [token[0] for token in tokens]
    metadata, types = {}, {}
    for ci, value in enumerate(values):
        if value != 'contract':
            continue
        contract = values[ci + 1]
        opening = values.index('{', ci + 2)
        closing = pairs[opening]
        cursor = opening + 1
        while cursor < closing:
            start = cursor
            kind = values[cursor]
            if kind in ('function', 'modifier', 'constructor', 'fallback', 'receive'):
                name = values[cursor + 1] if kind in ('function', 'modifier') and values[cursor + 1] != '(' else kind
                paren = values.index('(', cursor)
                after = pairs[paren] + 1
                cursor = after
                while values[cursor] not in ('{', ';'):
                    cursor += 1
                if values[cursor] == ';':
                    cursor += 1
                    continue
                end = pairs[cursor]
                if kind != 'modifier':
                    prefix = f'{contract}.{name}@{tokens[start][2]}:'
                    candidates = [s for s in facts['scopes'] if s['id'].startswith(prefix) and s['id'] not in metadata]
                    if candidates:
                        header = values[after:cursor]
                        flags = header[:header.index('returns')] if 'returns' in header else header
                        visibility = [v for v in flags if v in ('public', 'external', 'internal', 'private')]
                        metadata[candidates[0]['id']] = {
                            'visibility': visibility[0] if len(visibility) == 1 else None,
                            'payable': 'payable' in flags, 'body': tokens[cursor + 1:end],
                        }
                cursor = end + 1
            else:
                while cursor < closing and values[cursor] not in (';', '{'):
                    if values[cursor] in ('(', '['):
                        cursor = pairs[cursor]
                    cursor += 1
                if cursor >= closing:
                    break
                if values[cursor] == '{':
                    cursor = pairs[cursor] + 1
                    continue
                declaration = values[start:cursor]
                for variable in facts['stateVariables']:
                    if variable['contract'] == contract and variable['name'] in declaration:
                        at = declaration.index(variable['name'])
                        types[(contract, variable['name'])] = ''.join(
                            v for v in declaration[:at] if v not in ('public', 'private', 'internal', 'constant', 'immutable', 'payable'))
                cursor += 1
    return metadata, types


def _write_expression(meta, fact):
    statements, current = [], []
    for token in meta['body']:
        if token[0] == ';':
            if current:
                statements.append(current)
            current = []
        else:
            current.append(token)
    candidates = []
    for statement in statements:
        text = ''.join(token[0] for token in statement)
        prefix = fact['resource'] + '='
        if statement[0][2] == fact['line'] and text.startswith(prefix):
            candidates.append(text[len(prefix):])
    return candidates[0] if len(candidates) == 1 else None


def _call_resource(meta, risk, source):
    """仅关联直接发送给 msg.sender 的无 gas 限制、空数据低级调用。"""
    tokens = meta['body']
    values = [token[0] for token in tokens]
    candidates = []
    for i in range(len(values) - 9):
        if values[i:i + 5] != ['msg', '.', 'sender', '.', 'call'] or tokens[i + 4][2] != risk['line']:
            continue
        if values[i + 5:i + 8] != ['{', 'value', ':']:
            continue
        end = values.index('}', i + 8) if '}' in values[i + 8:] else len(values)
        if values[end + 1:end + 4] != ['(', '<literal>', ')']:
            continue
        literal = source[tokens[end + 2][1]:tokens[end + 3][1]].strip()
        if literal not in ('""', "''"):
            continue
        resource = ''.join(values[i + 8:end])
        if re.fullmatch(r'[A-Za-z_$][\w$]*\[msg\.sender\]', resource):
            candidates.append(resource)
    return candidates[0] if len(candidates) == 1 else None


def _authority(check, types, contract):
    if check['kind'] != 'CHECK':
        return None
    left, right = check['subject'], check['resource']
    authority = right if left == 'msg.sender' else left if right == 'msg.sender' else None
    return authority if types.get((contract, authority)) == 'address' else None


def _entry_ready(facts, scope, metadata):
    related = [s for s in facts['scopes'] if s['contract'] == scope['contract']]
    return (facts['status'] == 'COMPLETE' and metadata[scope['id']]['visibility'] in ('public', 'external')
            and all(s['id'] in metadata and metadata[s['id']]['visibility'] is not None for s in related))


def _access(result, facts, scope, risk, metadata, types):
    local = [f for f in facts['facts'] if f['scope'] == scope['id']]
    checks = [f for f in local if _authority(f, types, scope['contract'])]
    guards = [f for f in checks if f['order'] < risk['order']]
    guard = guards[0] if guards else checks[0] if checks else None
    authority = _authority(guard, types, scope['contract']) if guard else None
    _set(result, 'actor', 'SUPPORTED' if guard else 'REFUTED', [risk] + checks,
         '检查绑定实际调用者与声明的地址权限状态' if guard else '完整作用域没有实际调用者的地址权限检查；这本身不证明漏洞')
    resource_root = risk['resource'].split('[')[0]
    known = (risk['kind'] == 'WRITE' and (scope['contract'], resource_root) in types
             or risk['kind'] == 'CALL' and risk['subject'] == 'msg.sender')
    _set(result, 'resource', 'SUPPORTED' if known else 'UNKNOWN', [risk],
         '风险操作唯一绑定该作用域的状态资源或直接调用目标' if known else '不能关联风险操作的确切资源')
    _set(result, 'pre_risk_guard', 'SUPPORTED' if guards else 'REFUTED', [risk] + checks,
         '按展开后的执行 order，权限检查先于风险操作' if guards else '权限检查缺失或位于风险之后；晚检查可能回滚，不能直接证明攻击成功')
    changed = [f for f in local if f['kind'] == 'WRITE' and f['resource'] == authority and f['order'] < risk['order']]
    prior_calls = [f for f in local if f['kind'] == 'CALL' and f['order'] < risk['order']]
    stable = bool(guards) and not changed and not prior_calls
    _set(result, 'state_version', 'REFUTED' if changed else 'SUPPORTED' if stable else 'UNKNOWN',
         [risk] + checks + changed + prior_calls,
         '权限状态在风险前被重写' if changed else '权限状态未重写，且风险前无外部调用' if stable else '缺少权限状态稳定性或调用影响证据')
    entry = 'UNKNOWN'
    entry_refs = [risk] + checks
    if _entry_ready(facts, scope, metadata):
        entry = 'SUPPORTED'
        for other in facts['scopes']:
            if other['contract'] != scope['contract'] or metadata[other['id']]['visibility'] not in ('public', 'external'):
                continue
            observed = [f for f in facts['facts'] if f['scope'] == other['id']]
            sensitive = [f for f in observed if f['kind'] == 'CALL' or f['kind'] == 'WRITE'
                         and f['resource'].split('[')[0] in (resource_root, authority)]
            for operation in sensitive:
                coverage = [f for f in observed if _authority(f, types, scope['contract']) == authority
                            and authority is not None and f['order'] < operation['order']]
                entry_refs.extend([operation] + coverage)
                if not coverage:
                    entry = 'REFUTED'
    _set(result, 'entry_coverage', entry, entry_refs,
         '全部可见的相关公开入口均先执行相同权限检查' if entry == 'SUPPORTED' else
         '存在未覆盖的相关公开入口' if entry == 'REFUTED' else '公开入口可见性或全量作用域完整性未知')
    if known and guards and stable and entry == 'SUPPORTED':
        _set(result, 'bypass', 'SUPPORTED', entry_refs, '未授权调用者在绑定风险前被检查阻断，直线作用域无替代路径')
        _path(result, 'BLOCKED', entry_refs, 'msg.sender 与权限状态不同则检查失败；风险操作不可达')
        return
    # 仅确认可接管且被真实权限检查使用的地址状态，不把任意无 guard 写入当漏洞。
    policies = [f for f in facts['facts'] if f['scope'].startswith(scope['contract'] + '.')
                and _authority(f, types, scope['contract']) == risk['resource']]
    takeover = (risk['kind'] == 'WRITE' and types.get((scope['contract'], risk['resource'])) == 'address'
                and _write_expression(metadata[scope['id']], risk) == 'msg.sender' and policies
                and not any(f['kind'] in ('CHECK', 'CALL') for f in local)
                and _entry_ready(facts, scope, metadata))
    if takeover:
        overwritten = [f for f in local if f['kind'] == 'WRITE' and f['resource'] == risk['resource']
                       and f['order'] > risk['order']]
        if overwritten:
            refs = [risk] + overwritten
            _set(result, 'bypass', 'UNKNOWN', refs, '权限状态在接管后再次写入，不能证明攻击者在入口返回后保有权限')
            _path(result, 'UNKNOWN', refs, '按展开后的执行顺序存在后续同资源写入，临时接管不足以证明后续权限入口可达')
            return
        consumers = []
        for other in facts['scopes']:
            if (other['contract'] != scope['contract'] or other['id'] == scope['id']
                    or not other['complete'] or not _entry_ready(facts, other, metadata)):
                continue
            observed = [f for f in facts['facts'] if f['scope'] == other['id']]
            # 仅证明两步直线路径，附加检查、权限覆盖和额外调用均留给 UNKNOWN。
            if len(observed) != 2:
                continue
            check, operation = observed
            sensitive = (operation['kind'] == 'CALL' or operation['kind'] == 'WRITE'
                         and operation['resource'].split('[')[0] != risk['resource']
                         and (scope['contract'], operation['resource'].split('[')[0]) in types)
            if (_authority(check, types, scope['contract']) == risk['resource']
                    and check['order'] < operation['order'] and sensitive):
                consumers.extend(observed)
        if not consumers:
            refs = [risk] + policies
            _set(result, 'bypass', 'UNKNOWN', refs, '未证明完整公开消费入口中只有同权限检查及后续敏感操作')
            _path(result, 'UNKNOWN', refs, '消费入口可见性、额外检查、权限覆盖或调用影响存在缺口，跨函数接管路径未获证明')
            return
        _set(result, 'bypass', 'REFUTED', [risk] + consumers, '公开直线入口接管权限后，可通过同权限检查执行绑定的敏感操作')
        _path(result, 'REACHABLE', [risk] + consumers, '接管赋值保持有效，完整公开消费入口只有同权限检查及后续敏感操作，无额外关门路径')


def _reentrancy(result, facts, scope, risk, metadata, types, source):
    local = [f for f in facts['facts'] if f['scope'] == scope['id']]
    resource = _call_resource(metadata[scope['id']], risk, source)
    if not resource or not re.fullmatch(r'mapping\(address=>uint\d*\)', types.get((scope['contract'], resource.split('[')[0]), '')):
        _set(result, 'resource', 'UNKNOWN', [risk], 'CALL 金额不能唯一关联调用者索引的整数状态；任意状态写入不构成 CEI')
        return
    writes = [f for f in local if f['kind'] == 'WRITE' and f['resource'] == resource]
    checks = [f for f in local if f['kind'] == 'CHECK' and
              (f['subject'] == resource and f['resource'] == '1' or f['resource'] == resource and f['subject'] == '1')]
    refs = [risk] + writes + checks
    _set(result, 'actor', 'SUPPORTED', refs, 'CALL 接收方与金额状态的下标均为实际 msg.sender')
    _set(result, 'resource', 'SUPPORTED', refs, 'CALL 金额精确读取同一调用者的状态资源：' + resource)
    guards = [f for f in checks if f['order'] < risk['order']]
    _set(result, 'pre_risk_guard', 'SUPPORTED' if guards else 'REFUTED', refs,
         '同资源的非零等值检查先于 CALL' if guards else '缺少已支持的同资源非零检查，不能靠任意 guard 证明保护')
    # 支持明确的清零，不把 +=、赋原值、其他资源或多个更新当作经济效果证明。
    write = writes[0] if len(writes) == 1 else None
    clears = write is not None and _write_expression(metadata[scope['id']], write) == '0'
    before = clears and write['order'] < risk['order']
    after = clears and write['order'] > risk['order']
    _set(result, 'state_version', 'SUPPORTED' if before else 'REFUTED' if after else 'UNKNOWN', refs,
         '同资源清零先于外部调用' if before else '同资源直到外部调用之后才清零' if after else '缺少唯一且语义明确的同资源清零证据')
    other_entries, setups = [], []
    for other in facts['scopes']:
        if other['id'] == scope['id'] or other['contract'] != scope['contract']:
            continue
        observed = [f for f in facts['facts'] if f['scope'] == other['id']]
        relevant = [f for f in observed if f['kind'] == 'CALL' or f['kind'] == 'WRITE'
                    and f['resource'].split('[')[0] == resource.split('[')[0]]
        other_entries.extend(relevant)
        meta = metadata.get(other['id'], {})
        if (other['complete'] and meta.get('visibility') in ('public', 'external') and meta.get('payable')
                and len(observed) == 1 and observed[0]['kind'] == 'WRITE'
                and observed[0]['resource'] == resource and _write_expression(meta, observed[0]) == '1'):
            setups.extend(observed)
    entry = 'SUPPORTED' if _entry_ready(facts, scope, metadata) and not other_entries else 'UNKNOWN'
    _set(result, 'entry_coverage', entry, refs + other_entries,
         '全量完整作用域中无其他写入同资源或调用外部目标的入口' if entry == 'SUPPORTED' else
         '入口完整性未知，或存在其他资源入口；未证明跨入口经济语义')
    exact = (len(local) == 3 and len(guards) == 1 and len(writes) == 1
             and guards[0]['order'] < write['order'] and not scope['modifiers'])
    if exact and before:
        _set(result, 'bypass', 'SUPPORTED', refs, '直接重复进入该函数时，清零后的同资源无法通过非零检查；跨入口覆盖另行核验')
        _path(result, 'BLOCKED', refs, '清零发生在唯一 CALL 前；该函数重复调用的入口条件为假')
    elif exact and after and setups and _entry_ready(facts, scope, metadata):
        _set(result, 'bypass', 'REFUTED', refs + setups, '可付款公开入口建立非零状态，CALL 回调时同资源未清零，重复进入仍可通过检查')
        _path(result, 'REACHABLE', refs + setups,
              '攻击者可先用可付款入口设置余额并提供至少两次付款的资金，空数据 CALL 允许回调，重复读取未更新余额')


def _tool_references(hypothesis, facts, tools):
    result = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get('status') != 'OK' or tool.get('sourceHash') != facts['sourceHash']:
            continue
        issues = tool.get('issues')
        filename = tool.get('sourceFile') or hypothesis.get('sourceFile') or facts.get('sourceFile')
        if not isinstance(issues, list) or not isinstance(filename, str):
            continue
        for index, issue in enumerate(issues):
            if not isinstance(issue, dict) or not isinstance(issue.get('check'), str) or ISSUE_TYPES.get(issue['check']) != (
                    hypothesis.get('vulnerabilityType', hypothesis.get('mechanism')), hypothesis['riskOperation']):
                continue
            if 'sourceHash' in issue and issue['sourceHash'] != facts['sourceHash']:
                continue
            if any(key in issue and issue[key] != hypothesis[key] for key in ('contract', 'function', 'riskOperation')):
                continue
            elements = issue.get('elements')
            for element in elements if isinstance(elements, list) else []:
                if not isinstance(element, dict) or element.get('type') != 'function' or element.get('name') != hypothesis['function']:
                    continue
                specific = element.get('type_specific_fields')
                parent = specific.get('parent') if isinstance(specific, dict) else None
                mapping = element.get('source_mapping')
                if not isinstance(parent, dict) or parent.get('name') != hypothesis['contract'] or not isinstance(mapping, dict):
                    continue
                lines = mapping.get('lines')
                if not isinstance(lines, list) or hypothesis['riskLine'] not in [line for line in lines if type(line) is int]:
                    continue
                paths = [mapping[key] for key in ('filename_relative', 'filename_absolute', 'filename_short') if mapping.get(key)]
                if not paths or not all(isinstance(path, str) for path in paths):
                    continue
                if tool.get('sourceFile'):
                    # Java 工具把输入写为临时目录中的 Contract.sol；其他文件仍必须排除。
                    same_file = all(PurePosixPath(path).name == PurePosixPath(filename).name for path in paths)
                else:
                    same_file = mapping.get('filename_relative', mapping.get('filename_absolute', mapping.get('filename_short'))) == filename
                if same_file:
                    reference = {'engine': tool.get('engine'), 'issueIndex': index, 'line': hypothesis['riskLine'],
                                 'sourceHash': facts['sourceHash'], 'sourceFile': filename,
                                 'scope': hypothesis['contract'] + '.' + hypothesis['function']}
                    if reference not in result:
                        result.append(reference)
    return result


def evaluate(hypothesis, facts, tools, *, source=None):
    """核验保护义务与程序路径；失败计数属于运行层，不在此推断。

    SUPPORTED 需要具体可行反例及同文件同类别工具佐证；REFUTED 需要
    六项保护与路径阻断证据。缺失、失败或未绑定的工具仍保留程序义务结果，
    最终 UNKNOWN。受限直线语法不等于完整控制流或经济语义证明。
    """
    if not isinstance(hypothesis, dict) or not isinstance(facts, dict) or not isinstance(tools, list):
        raise ValueError('D2 输入结构无效')
    line = hypothesis.get('riskLine')
    if type(line) is not int or line < 1:
        raise ValueError('风险行无效')
    obligations = [{'name': name, 'status': 'UNKNOWN', 'references': [],
                    'reason': '尚无与源码唯一绑定的程序证据'} for name in OBLIGATIONS]
    result = {'schemaVersion': '2', 'verdict': 'UNKNOWN', 'protectionVerdict': 'UNKNOWN',
            'obligations': obligations, 'references': [],
            'pathEvidence': {'status': 'UNKNOWN', 'references': [], 'reason': '尚无路径证明'},
            'note': '六项保护义务未获完整证明时不得推断安全'}
    if not isinstance(source, str):
        result['note'] = '未提供绑定源码，无法核验文件、入口或路径'
        return result
    observed = extract_facts(source)
    if (facts.get('sourceHash') != observed['sourceHash']
            or hypothesis.get('sourceHash', observed['sourceHash']) != observed['sourceHash']
            or any(facts.get(key) != observed[key] for key in ('status', 'stateVariables', 'scopes', 'facts'))):
        result['note'] = '源码摘要或事实与重新提取的程序证据不一致'
        return result
    mechanism = hypothesis.get('vulnerabilityType', hypothesis.get('mechanism'))
    kind = hypothesis.get('riskOperation')
    if (mechanism not in ('ACCESS_CONTROL', 'REENTRANCY') or kind not in ('WRITE', 'CALL')
            or mechanism == 'REENTRANCY' and kind != 'CALL'
            or hypothesis.get('mechanism', mechanism) != mechanism):
        result['note'] = '机制或风险操作未明确绑定已支持的类别'
        return result
    scopes = [s for s in facts['scopes'] if s['contract'] == hypothesis.get('contract') and s['name'] == hypothesis.get('function')]
    candidates = [(s, f) for s in scopes for f in facts['facts']
                  if f['scope'] == s['id'] and f['line'] == line and f['kind'] == kind]
    if len(candidates) != 1:
        result['note'] = '合约、函数、风险行与操作无法唯一绑定事实'
        return result
    scope, risk = candidates[0]
    if (hypothesis.get('riskFactId', risk['id']) != risk['id']
            or hypothesis.get('resource', risk['resource']) != risk['resource']
            or hypothesis.get('riskKind', kind) != kind):
        result['note'] = '显式风险事实、资源或操作与绑定事实不一致'
        return result
    if not scope['complete'] or facts['status'] == 'FAILED':
        for item in result['obligations']:
            item.update(references=_references([risk]), reason='作用域含未支持的继承、别名、调用或复杂流，不能证明保护存在或缺失')
        result['references'] = _references([risk])
        return result
    metadata, types = _source_metadata(source, facts)
    if scope['id'] not in metadata:
        return result
    if mechanism == 'ACCESS_CONTROL':
        _access(result, facts, scope, risk, metadata, types)
    else:
        _reentrancy(result, facts, scope, risk, metadata, types, source)
    corroboration = _tool_references(hypothesis, facts, tools)
    if corroboration:
        result['obligations'][-1]['references'].extend(corroboration)
    for item in result['obligations'] + [result['pathEvidence']]:
        for reference in item['references']:
            if reference not in result['references']:
                result['references'].append(reference)
    tool_complete = bool(tools) and all(isinstance(tool, dict) and tool.get('status') == 'OK'
                                        and isinstance(tool.get('issues'), list)
                                        and all(isinstance(issue, dict) and isinstance(issue.get('check'), str)
                                                for issue in tool['issues'])
                                        and tool.get('sourceHash') == facts['sourceHash'] for tool in tools)
    if facts['status'] == 'COMPLETE' and tool_complete:
        if result['pathEvidence']['status'] == 'REACHABLE' and corroboration:
            result.update(verdict='SUPPORTED', protectionVerdict='REFUTED')
        elif (result['pathEvidence']['status'] == 'BLOCKED'
              and all(item['status'] == 'SUPPORTED' for item in result['obligations'])):
            result.update(verdict='REFUTED', protectionVerdict='SUPPORTED')
    result['note'] = ('结论仅针对绑定的漏洞假设，不是合约整体安全或经济语义证明' if result['verdict'] != 'UNKNOWN' else
                      '程序证据保留；路径、六项覆盖或绑定工具证据不足，最终未知')
    return result
