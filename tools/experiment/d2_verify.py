"""D2 初版仅根据可定位证据评估保护覆盖，信息不足保持未知。"""

OBLIGATIONS = ('actor', 'resource', 'pre_risk_guard', 'entry_coverage', 'state_version', 'bypass')


def _issue_lines(issue):
    lines = []
    for element in issue.get('elements', []) if isinstance(issue.get('elements'), list) else []:
        mapping = element.get('source_mapping', {}) if isinstance(element, dict) else {}
        if isinstance(mapping, dict) and isinstance(mapping.get('lines'), list):
            lines.extend(line for line in mapping['lines'] if type(line) is int)
    return lines


def evaluate(hypothesis, facts, tools):
    """只认可与风险行匹配的显式反例；空告警与工具故障均不证明保护充分。"""
    if not isinstance(hypothesis, dict) or not isinstance(facts, dict) or not isinstance(tools, list):
        raise ValueError('D2 输入结构无效')
    line = hypothesis.get('riskLine')
    if type(line) is not int or line < 1:
        raise ValueError('风险行无效')
    obligations = [{'name': name, 'status': 'UNKNOWN', 'references': []} for name in OBLIGATIONS]
    references = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get('status') != 'OK':
            continue
        issues = tool.get('issues')
        if not isinstance(issues, list):
            continue
        for index, issue in enumerate(issues):
            if not isinstance(issue, dict) or line not in _issue_lines(issue):
                continue
            check = str(issue.get('check', '')).lower()
            if check.startswith('reentrancy') or check.startswith('arbitrary-send'):
                reference = {'engine': tool.get('engine'), 'issueIndex': index, 'line': line}
                obligations[-1] = {'name': 'bypass', 'status': 'REFUTED', 'references': [reference]}
                references.append(reference)
    return {'schemaVersion': '1', 'verdict': 'REFUTED' if references else 'UNKNOWN',
            'obligations': obligations, 'references': references,
            'note': '六项保护义务未获完整证明时不得推断安全'}
