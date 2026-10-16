"""R3 在既有批量平台上的显式比较组与完整配对分母。"""
from collections import defaultdict
from storage import fingerprint


CONDITIONS = ['VANILLA', 'R3_CODE', 'R3_CARD', 'R3_DENSE', 'R3_FUSION']


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


def comparison_audit(rows):
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
