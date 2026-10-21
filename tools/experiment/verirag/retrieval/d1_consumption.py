"""冻结改动片段的保守消费规则；语法差异不能证明补丁有效或目标安全。"""
import difflib
import re
from collections import Counter


NO_CHANGE = '【未识别机制保护改动】'
UNPAIRABLE = '【配对关系不唯一，禁止软配对】'
CONSUMPTION_VERSION = 'mechanism-window-unknown-v1'
_TOKEN = re.compile(r'[A-Za-z_$][\w$]*|\d+|==|!=|>=|<=|&&|\|\||\+=|-=|[^\s]')
_IGNORED = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_STABLE = {'require', 'assert', 'if', 'msg', 'sender', 'value', 'tx', 'origin', 'this',
           'true', 'false', 'ecrecover', 'hasRole', 'isOwner', 'isAuthorized', 'delete'}
_GUARD = re.compile(r'\b(?:require|assert|if)\s*\(')
_MODIFIER = re.compile(r'\b(?:nonReentrant|only[A-Z][A-Za-z0-9_]*|onlyOwner|hasRole|onlyRole)\b')
_CALL = re.compile(r'\.\s*(call|send|transfer|transferFrom|safeTransfer|safeTransferFrom)\b')
_WRITE = re.compile(r'\bdelete\s+[A-Za-z_$][\w$]*(?:\s*\[[^;\n]*?\])?'
                    r'|\b[A-Za-z_$][\w$]*(?:\s*\[[^;\n]*?\])+\s*(?:=|\+=|-=|\+\+|--)'
                    r'|\b[A-Za-z_$][\w$]*\s*=\s*(?:true|false)\b')


def _code(text):
    # 快照为不连续 diff 片段，只去除已闭合注释；未闭合区域不能作运行语义证明。
    source = '\n'.join(line[1:] if line.startswith(('+', '-')) else line for line in text.splitlines())
    return _IGNORED.sub(lambda match: ''.join('\n' if c == '\n' else ' ' for c in match.group()), source)


def _normal(fragment):
    identifiers = {}
    parts = []
    for token in _TOKEN.findall(fragment):
        if re.fullmatch(r'[A-Za-z_$][\w$]*', token) and token not in _STABLE:
            token = identifiers.setdefault(token, f'v{len(identifiers)}')
        parts.append(token)
    return ''.join(parts)


def mechanism_events(text, mechanism):
    """仅提取可见权限条件、互斥声明及 CALL／索引写入顺序；不生成适用性。"""
    code = _code(text)
    events = []
    for match in _GUARD.finditer(code):
        depth, end = 1, match.end()
        while end < len(code) and depth:
            depth += (code[end] == '(') - (code[end] == ')')
            end += 1
        if depth:
            continue
        expression = code[match.end():end - 1]
        relevant = (re.search(r'\b(?:msg\s*\.\s*sender|tx\s*\.\s*origin|ecrecover|hasRole|isOwner|isAuthorized)\b', expression)
                    if mechanism == 'ACCESS_CONTROL' else
                    re.search(r'\[|\b(?:lock\w*|_?status|mutex\w*|reentr\w*)\b', expression, re.I))
        if relevant:
            events.append((match.start(), end, 'GUARD:' + _normal(expression)))
    for match in _MODIFIER.finditer(code):
        if (mechanism == 'REENTRANCY') == (match.group() == 'nonReentrant'):
            events.append((match.start(), match.end(), 'MODIFIER:' + match.group()))
    if mechanism == 'REENTRANCY':
        events.extend((m.start(), m.end(), 'CALL:' + m.group(1)) for m in _CALL.finditer(code))
        events.extend((m.start(), m.end(), 'WRITE:' + _normal(m.group())) for m in _WRITE.finditer(code))
    return sorted(events)


def mechanism_changed(before, after, mechanism):
    if before.startswith((NO_CHANGE, UNPAIRABLE)) or after.startswith((NO_CHANGE, UNPAIRABLE)):
        return False
    left = [event[2] for event in mechanism_events(before, mechanism)]
    right = [event[2] for event in mechanism_events(after, mechanism)]
    return bool(left or right) and left != right


def pair_snippets(before, after, mechanism, limit=900):
    """从完整冻结片段定位机制差异窗口，保留省略标识与原片段行号。"""
    if type(limit) is not int or limit <= len(NO_CHANGE) + 1:
        raise ValueError('机制片段预算不足')

    def fallback(text):
        return NO_CHANGE + '\n' + text[:min(700, limit - len(NO_CHANGE) - 1)]

    left, right = mechanism_events(before, mechanism), mechanism_events(after, mechanism)
    if not mechanism_changed(before, after, mechanism):
        return fallback(before), fallback(after)
    left_focus, right_focus = set(), set()
    for kind, a, b, c, d in difflib.SequenceMatcher(a=[e[2] for e in left], b=[e[2] for e in right], autojunk=False).get_opcodes():
        if kind != 'equal':
            left_focus.update(range(max(0, a - 1), min(len(left), b + 1)))
            right_focus.update(range(max(0, c - 1), min(len(right), d + 1)))

    def excerpt(text, events, focus, radius):
        code = _code(text)
        lines = text.splitlines()
        indexes = set()
        for index in sorted(focus):
            start, end, _ = events[index]
            first, last = code.count('\n', 0, start), code.count('\n', 0, end)
            indexes.update(range(max(0, first - radius), min(len(lines), last + radius + 1)))
        if not indexes:
            indexes.update(range(min(4, len(lines))))
        parts, previous = ['【冻结机制改动片段·未审核；省略其他上下文】'], -2
        for index in sorted(indexes):
            prefix = f'// 原片段第{index + 1}行\n' if index != previous + 1 else ''
            line = prefix + lines[index]
            parts.append(line)
            previous = index
        result = '\n'.join(parts)
        return result if len(result) <= limit else None

    for radius in (1, 0):
        first, second = excerpt(before, left, left_focus, radius), excerpt(after, right, right_focus, radius)
        # 必须容纳全部选定差异；预算不足时不交付伪装完整的配对。
        if first is not None and second is not None and mechanism_changed(first, second, mechanism):
            return first, second
    return fallback(before), fallback(after)


def candidate_context(candidate, soft=False):
    label = candidate['role']
    if soft or candidate.get('reviewed') is False:
        label = {'VULNERABLE': '改动前·未审核', 'DEFENSE': '改动后·未审核'}.get(label, '参考片段·未审核')
    return f"[{candidate['caseId']}/{candidate['chunkId']}|{label}]\n{candidate['text']}\n"


def soft_pairs(pool, mechanism, max_bytes=4096, max_cases=4):
    pairs = []
    pair_counts = Counter(row['pairId'] for row in pool['candidates'])
    for before in pool['candidates']:
        if before['role'] != 'VULNERABLE' or before['mechanism'] != mechanism or pair_counts[before['pairId']] != 2:
            continue
        for after in pool['candidates']:
            if (after['role'] != 'DEFENSE' or after['pairId'] != before['pairId'] or after['mechanism'] != mechanism
                    or before.get('riskKind') != after.get('riskKind') or before['chunkId'] == after['chunkId']
                    or before['caseId'] == after['caseId'] or not mechanism_changed(before['text'], after['text'], mechanism)):
                continue
            score = min(before['denseScore'], after['denseScore']) + .25 * abs(before['denseScore'] - after['denseScore'])
            pairs.append((score, before['chunkId'], after['chunkId'], before, after))
    pairs.sort(key=lambda pair: (-pair[0], pair[1], pair[2]))
    selected, parts, used, seen_pairs, seen_texts = [], [], 0, set(), set()
    for _, _, _, before, after in pairs:
        snippet = candidate_context(before, True) + candidate_context(after, True)
        length = len(snippet.encode('utf-8'))
        if (len(selected) + 2 > max_cases or used + length > max_bytes or before['pairId'] in seen_pairs
                or before['text'] in seen_texts or after['text'] in seen_texts):
            continue
        selected.extend({'candidate': row, 'use': use, 'binding': {'applicability': 'UNKNOWN', 'conditions': []}}
                        for row, use in ((before, 'SOFT_SUPPORT'), (after, 'SOFT_CONTRAST')))
        parts.append(snippet)
        used += length
        seen_pairs.add(before['pairId'])
        seen_texts.update((before['text'], after['text']))
    return {'status': 'COMPLETED', 'strategy': 'D1', 'selected': selected, 'context': ''.join(parts),
            'usedBytes': used, 'budget': {'maxBytes': max_bytes, 'maxCases': max_cases},
            'budgetVersion': 'utf8-context-bytes-v1',
            'consumptionVersion': CONSUMPTION_VERSION,
            'gaps': ['无唯一风险事实；使用机制改动软配对，不宣称防护适用性'] +
                    ([] if selected else ['没有满足机制改动、完整配对与上下文预算的候选']),
            'evaluations': {row['chunkId']: {'applicability': 'UNKNOWN', 'conditions': []} for row in pool['candidates']}}


def risk_bindings(facts, risk):
    """资源只来自同作用域事实和已登记状态槽，无法唯一关联时不填猜测值。"""
    bindings = {'actor': 'msg.sender'}
    scope = next(row for row in facts['scopes'] if row['id'] == risk['scope'])
    names = {row['name'] for row in facts['stateVariables'] if row['contract'] == scope['contract']}
    def known(resource):
        return resource.split('[', 1)[0] in names
    if risk['kind'] == 'WRITE':
        bindings['resource'] = risk['resource']
    else:
        resources = {row['resource'] for row in facts['facts'] if row['scope'] == risk['scope']
                     and row['kind'] == 'WRITE' and known(row['resource'])
                     and '[msg.sender]' in row['resource'] and risk['subject'] == 'msg.sender'}
        if len(resources) == 1:
            bindings['resource'] = next(iter(resources))
    authorities = set()
    for row in facts['facts']:
        if row['scope'] == risk['scope'] and row['kind'] == 'CHECK' and row['order'] < risk['order']:
            resource = row['resource'] if row['subject'] == 'msg.sender' else row['subject'] if row['resource'] == 'msg.sender' else ''
            if known(resource):
                authorities.add(resource)
    if len(authorities) == 1:
        bindings['authority'] = next(iter(authorities))
    return bindings
