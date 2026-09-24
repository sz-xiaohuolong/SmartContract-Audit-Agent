"""受限 Solidity 结构事实；不编译、不推断完整控制流、不证明安全。"""
import argparse
import hashlib
import json
import re
from pathlib import Path

TOKEN = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|==|!=|=>|\+=|-=|\+\+|--|&&|\|\||[^\s]')
IDENTIFIER = re.compile(r'[A-Za-z_$][\w$]*\Z')


def _tokens(source):
    tokens = []
    for match in TOKEN.finditer(source):
        text = match.group()
        if text.startswith('//') or text.startswith('/*'): continue
        if text in ('"', "'") or text == '/' and source[match.start():].startswith('/*'):
            raise ValueError("注释或字符串未闭合")
        if text.startswith(('"', "'")): text = '<literal>'
        tokens.append((text, match.start(), source.count('\n', 0, match.start()) + 1))
    pairs, stack = {}, []
    for i, token in enumerate(tokens):
        text = token[0]
        if text in ('(', '[', '{'): stack.append(i)
        elif text in (')', ']', '}'):
            if not stack or tokens[stack[-1]][0] != {')': '(', ']': '[', '}': '{'}[text]:
                raise ValueError("括号不匹配")
            start = stack.pop()
            pairs[start] = i
    if stack: raise ValueError("括号未闭合")
    return tokens, pairs


def _text(tokens): return ''.join(t[0] for t in tokens)


def _body_facts(tokens, state_names):
    values = [t[0] for t in tokens]
    complete = not any(v in {'if', 'else', 'for', 'while', 'do', 'try', 'catch', 'assembly', 'return', 'revert', 'throw', '?', 'delete', 'storage', 'memory', 'calldata', '&&', '||'} for v in values)
    if any(values[i:i + 2] == [')', '='] for i in range(len(values) - 1)):
        complete = False
    facts = []
    recognized_writes = set()
    index_names = set()
    index_depth = 0
    for value in values:
        if value == '[': index_depth += 1
        elif value == ']': index_depth -= 1
        elif index_depth and IDENTIFIER.fullmatch(value): index_names.add(value)
    for i, token in enumerate(tokens):
        value, _, line = token
        if value in ('require', 'assert') and i + 1 < len(tokens) and values[i + 1] == '(':
            depth, end = 1, i + 2
            while end < len(tokens) and depth:
                depth += (values[end] == '(') - (values[end] == ')')
                if depth: end += 1
            expression = values[i + 2:end]
            if ',' in expression: expression = expression[:expression.index(',')]
            if expression.count('==') == 1 and not any(v in expression for v in ('&&', '||', '(', ')')):
                split = expression.index('==')
                facts.append({'kind': 'CHECK', 'subject': ''.join(expression[:split]),
                              'resource': ''.join(expression[split + 1:]), 'line': line, 'position': i})
            else: complete = False
        if value in state_names:
            if i > 0 and (values[i - 1] == '.' or IDENTIFIER.fullmatch(values[i - 1])):
                complete = False
            if i > 0 and values[i - 1] in ('++', '--'):
                complete = False
            end = i + 1
            if end < len(tokens) and values[end] == '[':
                depth = 1
                end += 1
                while end < len(tokens) and depth:
                    depth += (values[end] == '[') - (values[end] == ']')
                    end += 1
            # 多维索引尚未建模，不能把漏提取的写入当作保护不存在。
            if end < len(tokens) and values[end] == '[':
                complete = False
            if end + 1 < len(tokens) and values[end] in ('*', '/', '%', '&', '|', '^', '<', '>') and '=' in values[end:end + 3]:
                complete = False
            if end < len(tokens) and values[end] in ('=', '+=', '-=', '++', '--'):
                recognized_writes.add(end)
                if value in index_names: complete = False
                finish = values.index(';', end) if ';' in values[end:] else len(values)
                if any(v in ('call', 'send', 'transfer', 'delegatecall', 'staticcall') for v in values[end:finish]):
                    complete = False
                facts.append({'kind': 'WRITE', 'subject': 'msg.sender', 'resource': _text(tokens[i:end]),
                              'line': line, 'position': i})
        if value in ('call', 'delegatecall', 'staticcall', 'send', 'transfer') and i > 0 and values[i - 1] == '.':
            start = i - 2
            while start > 0 and (IDENTIFIER.fullmatch(values[start - 1]) or values[start - 1] == '.'):
                start -= 1
            subject = _text(tokens[start:i - 1])
            if not re.fullmatch(r'[\w$]+(?:\.[\w$]+)*', subject): complete = False
            facts.append({'kind': 'CALL', 'subject': subject, 'resource': '', 'line': line, 'position': i})
            if value in ('delegatecall', 'staticcall'): complete = False
        if IDENTIFIER.fullmatch(value) and i + 1 < len(tokens) and values[i + 1] == '(':
            if value not in ('require', 'assert', 'call', 'send', 'transfer'):
                complete = False
        if value in state_names and i > 0 and re.fullmatch(r'(?:u?int\d*|address|bool|string|bytes\d*)', values[i - 1]):
            complete = False
    # 未追踪局部变量的数据流；下标重绑定和嵌套赋值不能沿用文本相等性。
    writes_in_statement = 0
    for i, value in enumerate(values):
        if value == ';': writes_in_statement = 0
        if value in ('=', '+=', '-=', '++', '--'):
            writes_in_statement += 1
            if i not in recognized_writes or writes_in_statement > 1: complete = False
    return sorted(facts, key=lambda f: f['position']), complete


def extract_facts(source):
    source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    result = {'schemaVersion': '1', 'sourceHash': source_hash, 'status': 'FAILED',
              'stateVariables': [], 'scopes': [], 'facts': [], 'limitations': []}
    try:
        tokens, pairs = _tokens(source)
        values = [t[0] for t in tokens]
        contracts = [i for i, v in enumerate(values) if v == 'contract']
        if not contracts: raise ValueError("没有可识别的合约")
        for ci in contracts:
            contract = values[ci + 1]
            opening = values.index('{', ci + 2)
            closing = pairs[opening]
            inherited = 'is' in values[ci + 2:opening]
            members, variables, cursor = [], [], opening + 1
            while cursor < closing:
                start = cursor
                if values[cursor] in ('function', 'modifier', 'constructor', 'fallback', 'receive'):
                    kind = values[cursor]
                    name = values[cursor + 1] if kind in ('function', 'modifier') and values[cursor + 1] != '(' else kind
                    paren = values.index('(', cursor)
                    after = pairs[paren] + 1
                    cursor = after
                    while cursor < closing and values[cursor] not in ('{', ';'): cursor += 1
                    if values[cursor] == ';':
                        inherited = True
                        cursor += 1
                        continue
                    end = pairs[cursor]
                    members.append((kind, name, tokens[after:cursor], tokens[cursor + 1:end], tokens[start][2], tokens[paren + 1:pairs[paren]]))
                    cursor = end + 1
                else:
                    while cursor < closing and values[cursor] not in (';', '{'):
                        if values[cursor] in ('(', '['): cursor = pairs[cursor]
                        cursor += 1
                    if cursor >= closing: raise ValueError("成员声明不完整")
                    if values[cursor] == '{':
                        inherited = True
                        cursor = pairs[cursor] + 1
                        continue
                    declaration = values[start:cursor]
                    if ',' in declaration: inherited = True
                    if declaration and declaration[0] not in ('event', 'error', 'using'):
                        before = declaration[:declaration.index('=')] if '=' in declaration else declaration
                        names = [v for v in before if IDENTIFIER.fullmatch(v)]
                        if len(names) >= 2:
                            variables.append(names[-1])
                            result['stateVariables'].append({'contract': contract, 'name': names[-1], 'line': tokens[start][2]})
                        else: inherited = True
                    cursor += 1
            modifiers = {m[1]: m for m in members if m[0] == 'modifier'}
            for member_index, (kind, name, header, body, line, parameters) in enumerate(members):
                if kind == 'modifier': continue
                scope = f'{contract}.{name}@{line}:{member_index}'
                flags = [t[0] for t in header]
                applied = []
                supported = not inherited and kind == 'function'
                h = 0
                while h < len(header):
                    value = header[h][0]
                    if value == 'returns': break
                    if value in ('public', 'external', 'internal', 'private', 'view', 'pure', 'payable', 'virtual'):
                        h += 1
                        continue
                    if IDENTIFIER.fullmatch(value): applied.append(value)
                    else: supported = False
                    h += 1
                expanded = list(body)
                for modifier in reversed(applied):
                    definition = modifiers.get(modifier)
                    if definition is None:
                        supported = False
                        continue
                    _, _, _, contents, _, params = definition
                    places = [i for i, t in enumerate(contents) if t[0] == '_']
                    if params or len(places) != 1:
                        supported = False
                        continue
                    at = places[0]
                    expanded = contents[:at] + expanded + contents[at + 1:]
                if any(t[0] in variables for t in parameters): supported = False
                observed, straight = _body_facts(expanded, set(variables))
                complete = supported and straight
                result['scopes'].append({'id': scope, 'contract': contract, 'name': name,
                                         'modifiers': applied, 'complete': complete})
                for order, fact in enumerate(observed):
                    fact.pop('position')
                    fact.update(scope=scope, order=order, id=hashlib.sha256(f'{source_hash}:{scope}:{order}'.encode()).hexdigest())
                    result['facts'].append(fact)
        result['status'] = 'COMPLETE' if result['scopes'] and all(s['complete'] for s in result['scopes']) else 'PARTIAL'
        if result['status'] == 'PARTIAL':
            result['limitations'].append('存在未支持的控制流、继承、修饰器或调用；这些作用域的条件适用性为 UNKNOWN')
    except (ValueError, IndexError, KeyError):
        result.update(status='FAILED', stateVariables=[], scopes=[], facts=[], limitations=['源码结构解析失败，不能推断保护不存在'])
    return result


def main():
    parser = argparse.ArgumentParser(description='提取受限程序事实，不调用编译器或模型')
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    with Path(args.source).open('rb') as source: data = source.read(1_048_577)
    if len(data) > 1_048_576: parser.exit(2, '源码超出上限\n')
    result = extract_facts(data.decode('utf-8'))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__': raise SystemExit(main())
