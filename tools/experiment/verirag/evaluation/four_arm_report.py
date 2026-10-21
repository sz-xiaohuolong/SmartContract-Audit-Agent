"""冻结候选的四臂离线报告；弱基线只是过滤决策，不冒充属性证明。"""
import re
from collections import Counter
from time import perf_counter

from verirag.analysis.program_facts import _tokens
from verirag.infrastructure.storage import fingerprint

ARMS = ('RAW_ACCEPTANCE', 'GUARD_NAME_EXISTS', 'LINE_CHECK', 'FULL_D2')
RULES = {
    'RAW_ACCEPTANCE': '无验证，直接接受全部保存候选；不表示有证明',
    'GUARD_NAME_EXISTS': '同合约唯一同名函数声明含only*或nonReentrant修饰符名称则拒绝，否则接受；不解析主体或语义',
    'LINE_CHECK': '同合约唯一同名函数内存在行号不晚于候选的require/assert则拒绝，否则接受；不检查支配与主体',
    'FULL_D2': '实际证明SUPPORTED接受、REFUTED拒绝，缺失、失败及UNKNOWN保持未知'}


def _weak_features(source, hypothesis):
    tokens, pairs = _tokens(source)
    values = [item[0] for item in tokens]
    candidates = []
    name = hypothesis.get('functionSignature', hypothesis.get('function', '')).split('(', 1)[0]
    for index, value in enumerate(values[:-1]):
        if value not in {'contract', 'library', 'interface'} or values[index + 1] != hypothesis.get('contract'):
            continue
        opening = next((i for i in range(index + 2, len(tokens)) if values[i] in {'{', ';'}), None)
        if opening is None or values[opening] != '{':
            continue
        end = pairs[opening]
        for at in range(opening + 1, end):
            if values[at] not in {'function', 'fallback', 'receive', 'constructor'}:
                continue
            found = ('fallback' if values[at + 1] == '(' else values[at + 1]) if values[at] == 'function' else values[at]
            if found != name:
                continue
            args = next((i for i in range(at + 1, end) if values[i] == '('), None)
            if args is None:
                continue
            body = next((i for i in range(pairs[args] + 1, end) if values[i] in {'{', ';'}), None)
            if body is None or values[body] != '{':
                continue
            close = pairs[body]
            if not tokens[at][2] <= hypothesis.get('riskLine', 0) <= tokens[close][2]:
                continue
            header = values[pairs[args] + 1:body]
            guard_name = any(re.fullmatch(r'only[A-Za-z0-9_]*|nonReentrant', value) for value in header)
            lines = [token[2] for i, token in enumerate(tokens[body + 1:close], body + 1)
                     if token[0] in {'require', 'assert'} and values[i + 1] == '(']
            candidates.append((guard_name, any(line <= hypothesis['riskLine'] for line in lines)))
    return candidates[0] if len(candidates) == 1 else (None, None)


def _index(rows):
    result = {(row['sampleId'], row['strategy']): row for row in rows}
    if len(result) != len(rows):
        raise ValueError('四臂输入存在重复单元')
    return result


def _assessments(row):
    result = {}
    count = len(row['model'].get('hypotheses', []))
    for index, item in enumerate(row.get('d2', {}).get('assessments', [])):
        key = item.get('hypothesisIndex', index)
        if type(key) is not int or not 0 <= key < count or key in result:
            raise ValueError('候选核验索引重复或超出冻结候选范围')
        result[key] = item
    return result


def verification_summary(changes):
    """按全部冻结候选统计程序证据；正确性必须另有独立真值。"""
    count = len(changes)
    counts = Counter(row['verificationStatus'] for row in changes)
    return {'denominator': count, 'counts': {key: counts[key] for key in
            ('SUPPORTED', 'REFUTED', 'UNKNOWN', 'FAILED')},
        'decisiveCoverage': (counts['SUPPORTED'] + counts['REFUTED']) / count if count else None,
        'falseSupports': None, 'falseRefutations': None, 'independentAccuracy': None,
        'truthStatus': 'INDEPENDENT_REVIEW_PENDING'}


def compare_arms(original, derived, plan):
    """消费同一批原件和当前派生证明；候选真值留给独立审核，不从标签推导。"""
    left, right = _index(original), _index(derived)
    if set(left) != set(right):
        raise ValueError('原始与派生单元分母不一致')
    rows, changes = [], []
    for key, old in left.items():
        new = right[key]
        if (old.get('sourceHash') != new.get('sourceHash') or fingerprint(old['model']) != fingerprint(new['model'])
                or any(old.get(field) != new.get(field) for field in ('inputTokens', 'outputTokens', 'requestAttempts'))):
            raise ValueError('原始与派生的源码、候选或历史usage发生变化')
        provenance = new.get('provenance', {})
        if provenance.get('originalBatchId', plan['batchId']) != plan['batchId']:
            raise ValueError('派生结果来自不同批次')
        assessments, prior = _assessments(new), _assessments(old)
        for index, hypothesis in enumerate(old['model'].get('hypotheses', [])):
            identity = [plan['batchId'], plan.get('planHash'), *key, index, fingerprint(hypothesis)]
            common = {'candidateId': 'candidate-' + fingerprint(identity), 'candidateHash': fingerprint(hypothesis),
                'batchId': plan['batchId'], 'sampleId': key[0], 'strategy': key[1], 'hypothesisIndex': index,
                'candidateTruth': None, 'truthStatus': 'INDEPENDENT_REVIEW_PENDING', 'sourceHash': old.get('sourceHash')}
            started = perf_counter()
            try:
                guard, line = _weak_features(old['source'], hypothesis)
            except (ValueError, KeyError, TypeError, IndexError):
                guard, line = None, None
            weak_ms = (perf_counter() - started) * 1000
            assessment = assessments.get(index, {})
            failed = (assessment.get('status') == 'FAILED' or assessment.get('errorCategory')
                      or new.get('d2', {}).get('errorCategory') or new.get('d2', {}).get('status') == 'FAILED')
            verdict = assessment.get('verdict', 'UNKNOWN') if not failed else 'UNKNOWN'
            if verdict not in {'SUPPORTED', 'REFUTED', 'UNKNOWN'}:
                raise ValueError('D2裁决状态无效')
            predictions = ['ACCEPTED', 'UNKNOWN' if guard is None else 'REJECTED' if guard else 'ACCEPTED',
                           'UNKNOWN' if line is None else 'REJECTED' if line else 'ACCEPTED',
                           {'SUPPORTED': 'ACCEPTED', 'REFUTED': 'REJECTED', 'UNKNOWN': 'UNKNOWN'}[verdict]]
            for arm, prediction in zip(ARMS, predictions):
                rows.append({**common, 'arm': arm, 'prediction': prediction,
                    'proofVerdict': verdict if arm == 'FULL_D2' else None,
                    'rule': RULES[arm], 'sharedWeakFeatureDurationMs': weak_ms if arm in ARMS[1:3] else None,
                    'sharedUnitDurationMs': new.get('replayTiming', {}).get('durationMs') if arm == 'FULL_D2' else None})
            proof = assessment.get('candidateProof', {})
            execution = proof.get('executionBinding', {})
            changes.append({**common, 'before': prior.get(index, {}).get('verdict', 'UNKNOWN'), 'after': verdict,
                'verificationStatus': 'FAILED' if failed else verdict,
                'gaps': assessment.get('candidateProof', {}).get('proofScope', assessment.get('proofScope', {})).get('gaps', []),
                'execution': execution.get('status'), 'executionFailureKind': execution.get('failureKind'),
                'proofKind': proof.get('proofKind'), 'proofProperty': proof.get('proofScope', {}).get('property'),
                'riskBinding': assessment.get('riskBinding'), 'toolBinding': assessment.get('toolBinding'),
                'references': assessment.get('references', []),
                'reason': assessment.get('note', new.get('d2', {}).get('errorCategory', '缺少核验记录'))})
    count = len(changes)
    arms = {}
    for arm in ARMS:
        counts = Counter(row['prediction'] for row in rows if row['arm'] == arm)
        arms[arm] = {'rule': RULES[arm], 'counts': {k: counts[k] for k in ('ACCEPTED', 'REJECTED', 'UNKNOWN')},
            'coverage': (count - counts['UNKNOWN']) / count if count else None,
            'unknownRate': counts['UNKNOWN'] / count if count else None,
            'confusionMatrix': None, 'confusionMatrixReason': '没有独立候选真值，不能用样本来源标签代填TP/FP/FN/TN',
            'reviewedCandidates': 0, 'unreviewedCandidates': count}
    unknown = arms['FULL_D2']['counts']['UNKNOWN']
    usage = {}
    for field in ('inputTokens', 'outputTokens', 'requestAttempts'):
        known = [row[field] for row in original if type(row.get(field)) is int and row[field] >= 0]
        usage[field] = {'total': sum(known) if len(known) == len(original) else None,
                        'observedSubtotal': sum(known), 'missingUnits': len(original) - len(known)}
    times = [row.get('replayTiming', {}).get('durationMs') for row in derived]
    summary = {'schemaVersion': 'four-arm-1', 'batchId': plan['batchId'], 'planHash': plan.get('planHash'),
        'unitCount': len(original), 'candidateCount': count, 'arms': arms, 'newModelRequests': 0,
        'historicalUsage': usage, 'cost': None, 'researchEligible': False,
        'verification': verification_summary(changes),
        'discovery': {'frozen': True, 'newModelRequests': 0,
                      'scope': '模型发现原样冻结，只比较同一批候选的核验证据'},
        'fullD2DurationMs': sum(times) if all(type(value) in (int, float) for value in times) else None,
        'timingScope': 'D2按单元计时并包含共享编译与工具；候选不得重复累加该耗时。弱臂共享词法扫描，非等计算量对比。',
        'frozenAcceptance': {'applies': plan['batchId'] == '119b4862f8a14818b62848ce709c3ee6',
            'expectedUnits': 159, 'expectedCandidates': 133, 'maximumUnknown': 13, 'observedUnknown': unknown,
            'numericPassed': count == 133 and len(original) == 159 and unknown <= 13,
            'strictlyBelow13': unknown < 13, 'independentCorrectnessVerified': False},
        'transitions': dict(Counter(row['before'] + '→' + row['after'] for row in changes)), 'changes': changes}
    return summary, rows
