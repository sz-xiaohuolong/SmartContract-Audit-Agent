"""确定性证据复核侧报告；不以模型意见或义务卡片替代漏洞三态。"""
from compiler_facts import source_span, extract_compiler_facts
from storage import fingerprint


def review_evidence(hypothesis, result, bundle):
    """核对六类接缝，局部支持与全入口反驳按各自证明范围检查。"""
    checks = []
    def check(name, status, reason):
        checks.append({'name': name, 'status': status, 'reason': reason})
    references = [r for r in result.get('references', []) if isinstance(r, dict) and 'nodeId' in r]
    conflicts = []
    for reference in references:
        node = bundle['nodes'].get(reference['nodeId'])
        if node is None:
            conflicts.append('引用节点不存在'); continue
        span = source_span(node, bundle['units'])
        if any(reference.get('span', {}).get(k) != span[k] for k in ('sourceUnit', 'start', 'length')):
            conflicts.append('引用跨度与编译节点不同')
        if any(reference.get(k, bundle[k]) != bundle[k] for k in ('sourceHash', 'environmentHash')):
            conflicts.append('引用源码或编译环境不同')
    check('引用与原字节', 'CONFLICT' if conflicts else 'PASS' if references else 'UNRESOLVED',
          '；'.join(conflicts) if conflicts else '编译节点与原源码跨度核对一致' if references else '没有可核验的节点引用')
    binding = result.get('binding', {})
    same = all(binding.get(k) == bundle[k] for k in ('sourceHash', 'receiptDigest', 'environmentHash'))
    status = 'CONFLICT' if not same else 'PASS' if result.get('toolBinding', {}).get('status') == 'MATCH' else 'UNRESOLVED'
    check('发现候选工具收据', status, '编译身份核对一致；工具双收据结果单独保留' if same else '候选编译收据与重验 bundle 不一致')
    risk = result.get('riskBinding', {})
    matches = [node for node in result.get('cfg', {}).get('nodes', []) if node.get('nodeId') == risk.get('nodeId')]
    bound_node = bundle['nodes'].get(risk.get('nodeId'))
    signature = hypothesis.get('functionSignature', hypothesis.get('function', ''))
    name = hypothesis.get('function', '')
    entries = [entry for entry in bundle['entries'] if entry['matched'] and entry['kind'] != 'getter'
        and (entry['signature'] == signature or '(' not in signature
             and entry['signature'].split('(', 1)[0] == signature)]
    independent_risk, graph = None, None
    identity_conflict = (hypothesis.get('contract') != bundle['targetContract']
        or hypothesis.get('sourceFile', bundle['targetSourceUnit']) != bundle['targetSourceUnit']
        or hypothesis.get('sourceHash', bundle['sourceHash']) != bundle['sourceHash']
        or hypothesis.get('vulnerabilityType') not in {'ACCESS_CONTROL', 'REENTRANCY'}
        or hypothesis.get('riskOperation') not in {'CALL', 'WRITE'}
        or len(entries) != 1
        or 'functionSignature' in hypothesis and name != signature and name != signature.split('(', 1)[0])
    if not identity_conflict:
        from risk_binding import bind_risks
        if hypothesis['vulnerabilityType'] == 'REENTRANCY':
            from reentrancy_proofs import _ReentrancyGraph
            graph = _ReentrancyGraph(bundle, entries[0])
        elif hypothesis['riskOperation'] == 'CALL':
            from access_call_proofs import _AccessCallGraph
            graph = _AccessCallGraph(bundle, entries[0])
        else:
            from candidate_proofs import _PermissionGraph
            graph = _PermissionGraph(bundle, entries[0])
        risks = bind_risks(graph, hypothesis, bundle, extract_compiler_facts(bundle))
        independent_risk = risks[0] if len(risks) == 1 else None
    if identity_conflict:
        status = 'CONFLICT'
    elif independent_risk is None:
        status = 'CONFLICT' if risk and not graph.gaps else 'UNRESOLVED'
    elif bound_node is None or not matches:
        status = 'UNRESOLVED'
    else:
        span = source_span(bound_node, bundle['units'])
        status = ('PASS' if len(matches) == 1 and independent_risk['nodeId'] == risk['nodeId']
                  and all(risk.get('span', {}).get(k) == span[k]
                  for k in ('sourceUnit', 'start', 'length')) else 'CONFLICT')
    check('合约入口操作唯一性', status, '仅核验当前唯一操作，未绑定或多调用上下文不猜配')
    path = result.get('pathEvidence', {})
    witness_resource = path.get('witness', {}).get('location', {}).get('resource')
    actual_resource = matches[0].get('resource') if len(matches) == 1 else None
    expected_resource = independent_risk.get('resource') if independent_risk else None
    if independent_risk is not None and hypothesis['vulnerabilityType'] == 'REENTRANCY':
        from reentrancy_proofs import _caller_balance
        expected_resource = _caller_balance(independent_risk, graph)
    resource_status = ('UNRESOLVED' if witness_resource is None or actual_resource is None else
                       'PASS' if fingerprint(witness_resource) == fingerprint(actual_resource) else 'CONFLICT')
    if expected_resource is not None and actual_resource is not None:
        if fingerprint(expected_resource) != fingerprint(actual_resource):
            resource_status = 'CONFLICT'
    elif resource_status == 'PASS':
        resource_status = 'UNRESOLVED'
    check('主体资源及状态版本', resource_status, '路径见证与操作资源按声明、key及字段完整身份比较；无见证时保持未决')
    scope = result.get('proofScope', {})
    if result.get('verdict') == 'REFUTED':
        status = 'PASS' if scope.get('complete') is True and not scope.get('gaps') else 'UNRESOLVED'
    elif result.get('verdict') == 'SUPPORTED':
        status = 'PASS' if path.get('status') == 'FEASIBLE' else 'UNRESOLVED'
    else:
        status = 'UNRESOLVED'
    check('必要上下文及闭包', status, '反驳需要完整保护闭包；支持只消费其已证明正常提交的局部反例')
    if result.get('verdict') == 'SUPPORTED':
        status = 'PASS' if path.get('status') == 'FEASIBLE' and path.get('normalExit') is True else (
                 'CONFLICT' if path.get('normalExit') is False else 'UNRESOLVED')
    elif result.get('verdict') == 'REFUTED':
        status = 'PASS' if path.get('status') == 'BLOCKED' and scope.get('complete') is True else 'UNRESOLVED'
    else:
        status = 'UNRESOLVED'
    check('路径及正常提交', status, '回滚或缺路径证据不构成可行反例；静态保护不得伪造执行见证')
    statuses = [row['status'] for row in checks]
    return {'schemaVersion': 'evidence-review-1', 'status': 'CONFLICT' if 'CONFLICT' in statuses else
            'UNRESOLVED' if 'UNRESOLVED' in statuses else 'PASS', 'checks': checks,
            'candidateHash': fingerprint(hypothesis), 'gateApplied': False, 'newModelRequests': 0,
            'independentGroundTruth': None, 'precision': None,
            'reason': '复核单列冲突与弃权，最终漏洞三态仍由现行 D2 证明消费'}
