"""编译操作的唯一行绑定；容差改变关联，不改写保存的模型候选。"""
from compiler_facts import source_span

_STATEMENTS = frozenset({'ExpressionStatement', 'VariableDeclarationStatement',
                        'Return', 'EmitStatement', 'RevertStatement'})
_LINE_TOLERANCE = 2


def operation_matches(node, hypothesis, bundle, facts):
    if node.get('kind') != hypothesis.get('riskOperation') or 'span' not in node:
        return False
    if node['kind'] == 'CALL' and node.get('callKind') not in {'CALL', 'STATICCALL'}:
        return False
    source = hypothesis.get('sourceFile', bundle.get('targetSourceUnit'))
    if source is not None and node['span'].get('sourceUnit') != source:
        return False
    requested = hypothesis.get('riskSpan')
    if requested is not None and (not isinstance(requested, dict) or any(
            requested.get(key) != node['span'].get(key) for key in ('start', 'length', 'sourceUnit'))):
        return False
    fact_id = hypothesis.get('riskFactId')
    return fact_id is None or any(f['id'] == fact_id and f['nodeId'] == node.get('nodeId')
                                 for f in facts['facts'])


def _line_span(span, bundle):
    """结束位置为排他 UTF-8 字节偏移；尾部换行不属于下一行的语句。"""
    unit = next((unit for unit in bundle['units'].values()
                 if unit['sourceUnit'] == span['sourceUnit']), None)
    if unit is None:
        return span
    content = unit['content'].encode('utf-8')
    end = span['start'] + max(span['length'] - 1, 0)
    return {**span, 'endLine': content[:end].count(b'\n') + 1}


def _statement_span(node, bundle):
    span = node['span']
    containers = []
    for ast in bundle['nodes'].values():
        if ast.get('nodeType') not in _STATEMENTS:
            continue
        candidate = source_span(ast, bundle['units'])
        if (candidate['sourceUnit'] == span['sourceUnit'] and candidate['start'] <= span['start']
                and span['start'] + span['length'] <= candidate['start'] + candidate['length']):
            containers.append(candidate)
    return _line_span(min(containers, key=lambda item: item['length']) if containers else span, bundle)


def bind_risks(graph, hypothesis, bundle, facts):
    """精确行、操作／同语句跨度、两行窗口依次匹配；任何多义均拒绝。"""
    line = hypothesis.get('riskLine')
    if type(line) is not int or line < 1:
        return []
    candidates = [node for node in graph.nodes if operation_matches(node, hypothesis, bundle, facts)]
    exact = [node for node in candidates if node['line'] == line]
    if exact:
        return exact if len(exact) == 1 else []
    spans = [node for node in candidates if (span := _statement_span(node, bundle))['line']
             <= line <= span.get('endLine', span['line'])]
    if spans:
        return spans if len(spans) == 1 else []
    window = [node for node in candidates if abs(node['line'] - line) <= _LINE_TOLERANCE]
    return window if len(window) == 1 else []


def binding_record(node, hypothesis):
    line = hypothesis['riskLine']
    return {'originalLine': line, 'boundLine': node['line'],
            'mode': 'EXACT' if line == node['line'] else 'UNIQUE_STATEMENT_OR_WINDOW',
            'toleranceLines': _LINE_TOLERANCE, 'nodeId': node['nodeId'], 'span': dict(node['span'])}
