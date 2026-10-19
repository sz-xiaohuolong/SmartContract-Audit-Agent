"""R3 在既有批量平台上的显式比较组与完整配对分母。"""
from collections import defaultdict
import hashlib
from storage import fingerprint


CONDITIONS = ['VANILLA', 'R3_CODE', 'R3_CARD', 'R3_DENSE', 'R3_FUSION']
P4_CONDITIONS = ['P4_BASELINE', 'P4_FACTS', 'P4_D1', 'P4_FACTS_D1']


def condition_target(target, strategy):
    """条件开关只写入单元副本，防止同一目标的后续条件继承开关。"""
    result = dict(target)
    if strategy in P4_CONDITIONS:
        result['factGuidanceEnabled'] = strategy in ('P4_FACTS', 'P4_FACTS_D1')
        return result, 'D1' if strategy in ('P4_D1', 'P4_FACTS_D1') else 'VANILLA'
    return result, strategy


def condition_view(base, strategy):
    from formal_recall import select_strategy
    _, underlying = condition_target({}, strategy)
    view = select_strategy(base, underlying)
    if strategy in P4_CONDITIONS:
        view.update(strategy=strategy, baseStrategy=underlying)
    return view


def freeze_phase4_plan(plan, identity, preflight, max_prompt_bytes):
    if (plan['strategies'] != P4_CONDITIONS or type(max_prompt_bytes) is not int or max_prompt_bytes < 1
            or set(preflight) != set(plan['sampleIds'])
            or any(set(row) != set(P4_CONDITIONS) for row in preflight.values())
            or not identity.get('artifactHash')):
        raise ValueError('phase 4 冻结输入、预检或构建身份不完整')
    result = {**plan, 'pipelineVersion': 'phase4-v1', 'codeIdentity': identity, 'preflight': preflight,
        'evaluationPairs': [], 'metricTier': 'DATASET_LABEL_EXPLORATORY', 'researchEligible': False,
        'admission': {'independentLabels': False, 'semanticKnowledgeReview': False,
                      'realFixPairs': False, 'exactTokenFairness': False},
        'comparisonGroups': [['P4_BASELINE', 'P4_FACTS'], ['P4_D1', 'P4_FACTS_D1']],
        'requestBounds': {**plan['requestBounds'], 'maxPromptBytesPerRequest': max_prompt_bytes,
            'maxPromptBytesTotal': max_prompt_bytes * plan['requestBounds']['maxRequests'],
            'maxInputTokens': None, 'messageOverheadTokens': None,
            'budgetKind': 'COMPLETE_SYSTEM_USER_UTF8_BYTES', 'repetitions': 1,
            'paidSummaryRequests': 0, 'paidJudgeRequests': 0}}
    rows = [{'sampleId': sample, 'strategy': strategy, 'poolHash': receipt.get('poolHash'),
             'model': {'requestConsumptionReceipt': receipt}}
            for sample, conditions in preflight.items() for strategy, receipt in conditions.items()]
    if _phase4_audit(rows, result):
        raise ValueError('phase 4 事实、案例、候选池或请求预检不一致')
    result.pop('planHash', None)
    return {**result, 'planHash': fingerprint(result)}


def _phase4_audit(rows, plan):
    indexed = defaultdict(dict)
    for row in rows:
        if row['strategy'] in indexed[row['sampleId']]:
            raise ValueError('比较结果重复')
        indexed[row['sampleId']][row['strategy']] = row
    errors = []
    for sample in plan['sampleIds']:
        if not plan.get('inputEligibility', {}).get(sample, {'runnable': True})['runnable']:
            continue
        conditions = indexed[sample]
        if set(conditions) != set(P4_CONDITIONS):
            errors.append({'sampleId': sample, 'reason': '四条件结果缺失'})
            continue
        receipts = {s: row.get('model', {}).get('requestConsumptionReceipt', {}) for s, row in conditions.items()}
        if any(not r.get('requestSha256') or r.get('requestSha256') != plan['preflight'][sample][s].get('requestSha256')
               for s, r in receipts.items()):
            errors.append({'sampleId': sample, 'reason': '实际请求与冻结预检不一致或回执缺失'})
        if any(r.get('sourceHash') != plan['sourceHashes'][sample]
               or r.get('modelSourceHash') != plan['sourceHashes'][sample] for r in receipts.values()):
            errors.append({'sampleId': sample, 'reason': '全文消费源码身份不同或缺失'})
        if len({conditions[s].get('poolHash') for s in P4_CONDITIONS}) != 1 or not conditions[P4_CONDITIONS[0]].get('poolHash'):
            errors.append({'sampleId': sample, 'reason': '候选池身份不同或缺失'})
        a, b, c, d = (receipts[s] for s in P4_CONDITIONS)
        if (a.get('factGuidance') is not None or c.get('factGuidance') is not None
                or not b.get('factGuidance') or b.get('factGuidance') != d.get('factGuidance')):
            errors.append({'sampleId': sample, 'reason': '事实开关或事实正文不同'})
        if (a.get('contextSha256') != hashlib.sha256(b'').hexdigest() or a.get('contextSha256') != b.get('contextSha256')
                or a.get('evidenceIds') != [] or b.get('evidenceIds') != []
                or not c.get('contextSha256') or c.get('contextSha256') != d.get('contextSha256')
                or c.get('evidenceIds') is None or c.get('evidenceIds') != d.get('evidenceIds')):
            errors.append({'sampleId': sample, 'reason': '历史知识文本、案例或顺序不同'})
    return errors


def freeze_plan(plan, registry, identity, preflight, max_prompt_bytes):
    if (plan['strategies'] != CONDITIONS or type(max_prompt_bytes) is not int or max_prompt_bytes < 1
            or set(preflight) != set(plan['sampleIds'])
            or any(set(preflight[key]) != set(CONDITIONS) for key in plan['sampleIds'])
            or any(not receipt.get('requestSha256') for row in preflight.values() for receipt in row.values())
            or not registry.get('registryHash') or not identity.get('artifactHash')):
        raise ValueError('R3 冻结输入、预检或构建身份不完整')
    result = {**plan, 'pipelineVersion': 'r3-v1', 'registryHash': registry['registryHash'],
              'codeIdentity': identity, 'preflight': preflight, 'evaluationPairs': [],
              'metricTier': 'DATASET_LABEL_EXPLORATORY', 'researchEligible': False,
              'admission': {'independentLabels': False, 'semanticCardReview': False,
                            'realFixPairs': False, 'exactTokenFairness': False},
              'comparisonGroups': [['R3_CODE', 'R3_CARD'], ['R3_DENSE', 'R3_FUSION']],
              'requestBounds': {**plan['requestBounds'], 'maxPromptBytesPerRequest': max_prompt_bytes,
                  'maxPromptBytesTotal': max_prompt_bytes * plan['requestBounds']['maxRequests'],
                  'maxInputTokens': None, 'messageOverheadTokens': None,
                  'budgetKind': 'COMPLETE_SYSTEM_USER_UTF8_BYTES',
                  'repetitions': 1, 'paidSummaryRequests': 0, 'paidJudgeRequests': 0}}
    result.pop('planHash', None)
    return {**result, 'planHash': fingerprint(result)}


def paired_accuracy(pairs, rows, strategies):
    identities = [p['pairId'] for p in pairs]
    members = [p[side] for p in pairs for side in ('before', 'after')]
    if len(identities) != len(set(identities)) or len(members) != len(set(members)):
        raise ValueError('评价配对身份重复')
    indexed = {}
    for row in rows:
        key = row['sampleId'], row['strategy']
        if key in indexed:
            raise ValueError('评价结果重复')
        indexed[key] = row
    result = {}
    for strategy in strategies:
        correct = complete = 0
        for pair in pairs:
            before, after = (indexed.get((pair[side], strategy), {}) for side in ('before', 'after'))
            valid = all(row.get('status') == 'COMPLETED' and row.get('prediction') in ('REPORT', 'NO_REPORT') for row in (before, after))
            complete += bool(valid)
            correct += bool(valid and before['prediction'] == 'REPORT' and after['prediction'] == 'NO_REPORT')
        result[strategy] = {'plannedPairs': len(pairs), 'correctPairs': correct, 'completePairs': complete,
                            'accuracy': correct / len(pairs) if pairs else None}
    return result


def paired_evidence_coverage(pairs, rows, strategies):
    """登记漏洞支持／修复反驳的程序证据覆盖，不代替独立正确率。"""
    # 沿用配对与结果唯一性校验，所有冻结配对都留在分母。
    paired_accuracy(pairs, rows, strategies)
    indexed = {(row['sampleId'], row['strategy']): row for row in rows}
    result = {}
    for strategy in strategies:
        complete = 0
        for pair in pairs:
            members = [indexed.get((pair[side], strategy), {}) for side in ('before', 'after')]
            valid = all(row and row.get('pipelineStatus') != 'FAILED' and row.get('status') != 'FAILED'
                        and row.get('d2', {}).get('status') != 'FAILED'
                        and not row.get('d2', {}).get('errorCategory') for row in members)
            complete += bool(valid and members[0].get('d2', {}).get('verdict') == 'SUPPORTED'
                             and members[1].get('d2', {}).get('verdict') == 'REFUTED')
        result[strategy] = {'plannedPairs': len(pairs), 'supportedRefutedPairs': complete,
            'evidenceCoverage': complete / len(pairs) if pairs else None, 'independentAccuracy': None}
    return result


def comparison_audit(rows, plan=None):
    if plan is not None and plan.get('pipelineVersion') == 'phase4-v1':
        return _phase4_audit(rows, plan)
    indexed = defaultdict(dict)
    for row in rows:
        if row['strategy'] in indexed[row['sampleId']]:
            raise ValueError('比较结果重复')
        indexed[row['sampleId']][row['strategy']] = row
    errors = []
    for sample, conditions in indexed.items():
        for left, right, same_selection in [('R3_CODE', 'R3_CARD', True), ('R3_DENSE', 'R3_FUSION', False)]:
            if left not in conditions or right not in conditions:
                errors.append({'sampleId': sample, 'comparison': [left, right], 'reason': '结果缺失'})
                continue
            a, b = conditions[left], conditions[right]
            if not a.get('poolHash') or a.get('poolHash') != b.get('poolHash'):
                errors.append({'sampleId': sample, 'comparison': [left, right], 'reason': '候选池身份不同'})
            if same_selection and a.get('retrieval', {}).get('r3Receipt', {}).get('selectedPairs') != b.get('retrieval', {}).get('r3Receipt', {}).get('selectedPairs'):
                errors.append({'sampleId': sample, 'comparison': [left, right], 'reason': '表达对照案例或顺序不同'})
    return errors
