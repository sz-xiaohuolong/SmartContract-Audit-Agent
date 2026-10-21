"""D1 零请求准入：核验保存的配对、条件与消费身份，并生成待审实验协议。"""
import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from verirag.retrieval.d1_consumption import candidate_context
from verirag.evaluation.d1_offline_check import run_check
from verirag.knowledge.snapshots import verify_snapshot
from verirag.infrastructure.storage import atomic_json, decode, fingerprint, read_artifact


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def inspect_consumption(row):
    """展示文本与最终请求分别验收；仅摘要回执不重新证明供应商执行。"""
    view, issues = row['retrieval'], []
    choice = view['d1']
    selected = choice.get('selected', [])
    expected = ''.join(candidate_context(item['candidate']) for item in selected)
    context = choice.get('context')
    ids = [item['candidate']['chunkId'] for item in selected]
    if context != expected:
        issues.append('CONTEXT_SELECTION_MISMATCH')
    if row.get('selectedIds') != ids or len(set(ids)) != len(ids):
        issues.append('CONTEXT_EVIDENCE_IDS_MISMATCH')
    used = len(expected.encode('utf-8'))
    if 'usedBytes' in choice and choice['usedBytes'] != used:
        issues.append('CONTEXT_BYTE_COUNT_MISMATCH')
    model = row.get('model', {})
    receipt = model.get('requestConsumptionReceipt')
    request_issues = []
    if receipt is None:
        request_status = 'UNVERIFIED'
    elif not isinstance(receipt, dict):
        request_status = 'FAILED'
        request_issues.append('REQUEST_RECEIPT_INVALID')
    else:
        expected_fields = {'schemaVersion': 'request-consumption-1', 'sourceHash': row['sourceHash'],
                           'modelSourceHash': view['modelSourceHash'], 'contextSha256': _sha(expected),
                           'evidenceIds': ids, 'messageOrder': ['system', 'user']}
        request_issues += ['REQUEST_' + key.upper() + '_MISMATCH' for key, value in expected_fields.items()
                           if receipt.get(key) != value]
        if (not all(_hash(receipt.get(key)) for key in ('systemPromptSha256', 'userPromptSha256'))
                or not all(type(receipt.get(key)) is int and receipt[key] >= 0
                           for key in ('systemPromptBytes', 'userPromptBytes'))
                or not isinstance(receipt.get('promptTemplateVersion'), str)
                or not receipt['promptTemplateVersion'].strip()):
            request_issues.append('FINAL_MESSAGE_IDENTITY_MISSING')
        for key in ('inputTokens', 'outputTokens'):
            value = receipt.get(key)
            if value is not None and (type(value) is not int or value < 0):
                request_issues.append('INVALID_USAGE_' + key)
            if key in model and value != model[key]:
                request_issues.append('USAGE_RECEIPT_MISMATCH_' + key)
        request_status = 'FAILED' if request_issues else 'VERIFIED'
    return {'sampleId': row['sampleId'], 'strategy': row['strategy'],
            'contextStatus': 'FAILED' if issues else 'VERIFIED', 'requestStatus': request_status,
            'actualRequestVerified': not issues and request_status == 'VERIFIED',
            'contextSha256': _sha(expected), 'contextBytes': used,
            'issues': issues + request_issues,
            'meaning': '回执核对最终消息身份与入选片段；不以本地字节计数替代供应商token或推断模型注意力'}


def inspect_bindings(view):
    """检查自动路径弃权及正式路径绑定引用；运行时安全性不在本检查结论中。"""
    pool, choice = view['pool'], view['d1']
    auto = pool['schemaVersion'] == 'auto-1'
    path = ('AUTO_JAVA_SOFT' if 'target' in choice else 'AUTO_PYTHON_SOFT') if auto else 'FORMAL_CONDITION_BINDER'
    issues, states = [], Counter()
    facts = {row['id']: row for row in view.get('facts', {}).get('facts', [])}
    scopes = {row['id']: row for row in view.get('facts', {}).get('scopes', [])}
    risk = facts.get(choice.get('target', {}).get('riskFactId'))
    evaluations = choice.get('evaluations', {})
    for candidate in pool['candidates']:
        key = candidate['chunkId']
        binding = evaluations.get(key)
        if not isinstance(binding, dict):
            issues.append({'chunkId': key, 'kind': 'BINDING_MISSING'})
            continue
        state = binding.get('applicability')
        states[state or 'MISSING'] += 1
        conditions = binding.get('conditions', [])
        if auto:
            if state != 'UNKNOWN' or conditions:
                issues.append({'chunkId': key, 'kind': 'AUTO_BINDING_NOT_UNKNOWN'})
            continue
        if state not in ('SUPPORTED', 'CONTRADICTED', 'UNKNOWN'):
            issues.append({'chunkId': key, 'kind': 'BINDING_STATE_INVALID'})
        # 类别／风险操作不匹配允许直接反对，不伪装成某个具体条件的证据。
        if not conditions:
            if state == 'SUPPORTED':
                issues.append({'chunkId': key, 'kind': 'EMPTY_CONDITIONS_CANNOT_SUPPORT'})
            continue
        if [value.get('condition') for value in conditions] != candidate.get('conditions'):
            issues.append({'chunkId': key, 'kind': 'CONDITION_CATALOG_MISMATCH'})
        condition_states = [value.get('state') for value in conditions]
        aggregate = ('CONTRADICTED' if 'CONTRADICTED' in condition_states else
                     'UNKNOWN' if 'UNKNOWN' in condition_states else 'SUPPORTED')
        if aggregate != state or any(value not in ('SUPPORTED', 'CONTRADICTED', 'UNKNOWN') for value in condition_states):
            issues.append({'chunkId': key, 'kind': 'CONDITION_AGGREGATE_MISMATCH'})
        for condition in conditions:
            predicate = condition.get('condition', {}).get('predicate')
            definitive = condition.get('state') != 'UNKNOWN'
            if definitive and (not condition.get('subject') or not condition.get('resource')):
                issues.append({'chunkId': key, 'kind': 'UNBOUND_CONDITION_CANNOT_DECIDE'})
            if predicate in ('CHECK_BEFORE', 'STATE_WRITE_BEFORE') and definitive:
                scope = scopes.get(risk.get('scope')) if risk else None
                if not scope or not scope.get('complete'):
                    issues.append({'chunkId': key, 'kind': 'INCOMPLETE_SCOPE_CANNOT_DECIDE'})
                observed = (condition['condition'].get('expected') is True) == (condition['state'] == 'SUPPORTED')
                if observed and not condition.get('evidence'):
                    issues.append({'chunkId': key, 'kind': 'OBSERVED_CONDITION_WITHOUT_EVIDENCE'})
            for evidence_id in condition.get('evidence', []):
                evidence = facts.get(evidence_id)
                if (not risk or not evidence or evidence['scope'] != risk['scope']
                        or evidence['order'] >= risk['order']):
                    issues.append({'chunkId': key, 'kind': 'CONDITION_EVIDENCE_OUTSIDE_PRECONDITION'})
                elif predicate in ('CHECK_BEFORE', 'STATE_WRITE_BEFORE'):
                    kind = 'CHECK' if predicate == 'CHECK_BEFORE' else 'WRITE'
                    direct = evidence.get('subject') == condition.get('subject') and evidence.get('resource') == condition.get('resource')
                    symmetric = (kind == 'CHECK' and evidence.get('subject') == condition.get('resource')
                                 and evidence.get('resource') == condition.get('subject'))
                    if evidence.get('kind') != kind or not (direct or symmetric):
                        issues.append({'chunkId': key, 'kind': 'CONDITION_EVIDENCE_BINDING_MISMATCH'})
    for item in choice.get('selected', []):
        key, binding = item['candidate']['chunkId'], item.get('binding')
        if binding != evaluations.get(key):
            issues.append({'chunkId': key, 'kind': 'SELECTED_BINDING_MISMATCH'})
        if auto and (not isinstance(binding, dict) or binding.get('applicability') != 'UNKNOWN'):
            issues.append({'chunkId': key, 'kind': 'AUTO_BINDING_NOT_UNKNOWN'})
    return {'passed': not issues, 'path': path, 'states': dict(sorted(states.items())), 'issues': issues,
            'semanticVerification': 'UNKNOWN_BY_DESIGN' if auto else 'REFERENCES_CHECKED_NOT_RUNTIME_PROOF',
            'meaning': '正式名称/前置条件绑定只说明受限程序事实；不证明修饰器完整实现、修复正确或目标安全'}


def inspect_pair_sources(snapshot, catalog, rows):
    """来源限于冻结文档全文；AutoMESC 的全文是保存的diff片段，不冒充仓库全合约。"""
    documents = {row['id']: row for row in snapshot['documents']}
    sources = {row['id']: row for row in snapshot['manifest']['samples']}
    pairs, selected, complete, windows, issues = defaultdict(list), Counter(), Counter(), {}, []
    for key, value in catalog['cases'].items():
        pairs[value['pairId']].append((key, value))
    for row in rows:
        unit_roles = defaultdict(list)
        for item in row['retrieval']['d1'].get('selected', []):
            selected[item['candidate']['pairId']] += 1
            unit_roles[item['candidate']['pairId']].append(item['candidate']['role'])
        for pair, roles in unit_roles.items():
            complete[pair] += sorted(roles) == ['DEFENSE', 'VULNERABLE']
        for candidate in row['retrieval']['pool']['candidates']:
            key = candidate['chunkId']
            document = documents.get(key)
            origin = sources.get(document['sample_id']) if document else None
            if not origin or candidate.get('provenance') != origin['origin'] + '@' + origin['source_hash']:
                issues.append({'sampleId': row['sampleId'], 'strategy': row['strategy'],
                               'chunkId': key, 'kind': 'PAIR_PROVENANCE_MISMATCH'})
            windows.setdefault(key, set()).add(_sha(candidate['text']))
    ledger = []
    for key, members in sorted(pairs.items()):
        identifiers = [identifier for identifier, _ in members]
        origins = {documents[identifier]['sample_id'] for identifier in identifiers if identifier in documents}
        valid = (len(members) == 2 and len(origins) == 1 and
                 sorted(value['role'] for _, value in members) == ['DEFENSE', 'VULNERABLE'])
        if not valid:
            issues.append({'pairId': key, 'kind': 'PAIR_SOURCE_RELATION_INVALID'})
            continue
        origin = sources[next(iter(origins))]
        before = next(identifier for identifier, value in members if value['role'] == 'VULNERABLE')
        # 自动清单源身份固定在before侧；人工知识的source_hash可能绑定完整源文件。
        automatic = origin.get('review_status') == 'AUTO_LABELED'
        if automatic and _sha(documents[before]['text']) != origin['source_hash']:
            issues.append({'pairId': key, 'kind': 'PAIR_SOURCE_HASH_MISMATCH'})
        ledger.append({'pairId': key, 'origin': origin['origin'], 'projectGroup': origin['project_group'],
            'sourceHash': origin['source_hash'], 'selectedDocumentOccurrences': selected[key],
            'selectedCompletePairOccurrences': complete[key],
            'sourceScope': 'FROZEN_DIFF_DOCUMENTS' if automatic else 'FROZEN_KNOWLEDGE_DOCUMENTS',
            'members': [{'chunkId': identifier, 'role': value['role'],
                         'documentSha256': _sha(documents[identifier]['text']),
                         'documentLines': len(documents[identifier]['text'].splitlines()),
                         'observedWindowHashes': sorted(windows.get(identifier, []))}
                        for identifier, value in members],
            'humanReview': {'status': 'PENDING', 'reviewer': None, 'repairCorrect': None,
                           'targetApplicability': None, 'evidence': [],
                           'reason': '冻结元数据不替代独立的修复语义和目标适用性审核'}})
    return {'passed': not issues, 'pairCount': len(pairs), 'selectedPairs': len(selected),
            'pairs': ledger, 'issues': issues, 'humanTruthCreated': False}


def build_protocol(plan, repetitions=3, retries=0, input_token_cap=None, output_token_cap=16384,
                   tokenizer=None, prices=None):
    """预注册是可审核方案，不是API执行授权或已完成研究准入。"""
    if type(repetitions) is not int or repetitions < 1 or type(retries) is not int or retries < 0:
        raise ValueError('重复数必须为正，重试上限不得为负')
    for value in (input_token_cap, output_token_cap):
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError('token上限必须为正整数或null')
    if tokenizer is not None and (not isinstance(tokenizer, dict)
            or not all(isinstance(tokenizer.get(k), str) and tokenizer[k].strip() for k in ('name', 'revision', 'source'))
            or any(term in str(tokenizer).lower() for term in ('codepoint', 'character', 'utf8', '字节', '字符'))):
        raise ValueError('tokenizer必须有真实模型计数身份，禁止字符/字节估算冒充token')
    if prices is not None and (not isinstance(prices, dict) or not prices.get('currency')
            or not prices.get('source') or not prices.get('verifiedAt')
            or any(type(prices.get(k)) not in (int, float) or prices[k] < 0
                   for k in ('inputPerMillion', 'outputPerMillion'))):
        raise ValueError('价格需包含核实来源、日期、货币与输入/输出单价')
    arms = [
        ('VANILLA', '无检索文本，禁止无关padding', False, False),
        ('DENSE', '同冻结池按dense分数选择', False, False),
        ('D1', '正式条件选择完整漏洞/修复对；自动层仍为软配对并单独报告', True, True),
        ('PAIRED_ONLY', '同池完整配对，按dense排序，不按条件筛选', False, True),
        ('D1_NO_CONDITIONS', '移除条件选择和条件陈述，保留完整配对与同一预算', False, True),
        ('D1_NO_REPAIR', '保留条件选择，仅消费before侧；不得补入其他文本凑等长', True, False)]
    requests = len(plan['sampleIds']) * len(arms) * repetitions * (1 + retries)
    maximum_input = requests * input_token_cap if input_token_cap is not None else None
    maximum_output = requests * output_token_cap if output_token_cap is not None else None
    amount = ((maximum_input * prices['inputPerMillion'] + maximum_output * prices['outputPerMillion']) / 1_000_000
              if prices is not None and maximum_input is not None and maximum_output is not None else None)
    protocol = {'schemaVersion': 'd1-protocol-1', 'status': 'PREREGISTERED_PENDING_ADMISSION',
        'snapshotId': plan['snapshotId'], 'historicalPlanHash': plan.get('planHash'),
        'targetIds': list(plan['sampleIds']), 'provider': plan.get('provider', {}),
        'arms': [{'id': key, 'treatment': text, 'conditionSelection': conditions, 'repairContext': repair}
                 for key, text, conditions, repair in arms],
        'repetitions': repetitions, 'retryLimit': retries, 'newModelRequests': 0,
        'budget': {'components': {'system': {'templateSha256': None, 'tokens': None},
                                 'source': {'policy': 'FULL_GOVERNED_SOURCE', 'tokens': None},
                                 'context': {'sameInputCap': True, 'tokens': None, 'legacyByteCap': 4096},
                                 'messageOverhead': {'tokens': None},
                                 'output': {'maxTokensPerAttempt': output_token_cap, 'actualTokens': None}},
                   'fullPromptInputTokenCap': input_token_cap, 'tokenizer': tokenizer,
                   'maxRequests': requests, 'maxInputTokens': maximum_input, 'maxOutputTokens': maximum_output,
                   'prices': prices, 'estimatedAmount': amount,
                   'fairnessStatus': 'UNVERIFIED', 'countingRule': '最终system+完整源码+context+消息封装；上限与实际usage分开报告'},
        'evaluation': {'samplingUnit': 'PROJECT_OR_CLONE_GROUP', 'splitStatus': 'INDEPENDENT_REVIEW_PENDING',
            'pairing': '同目标×重复编号×模型设置配对；按项目成组重采样',
            'order': '解盲前固定分组与随机顺序，失败保留原分母',
            'retrievalMetrics': ['人工适用性P@K', '完整pair率', '条件绑定正确率', '实际贡献窗口'],
            'discoveryMetrics': ['位置与理由均正确的发现率', 'TP/FP/FN/TN', '失败率', '弃权率'],
            'effectMethod': '按项目配对bootstrap或置换；项目过少仅报探索区间',
            'minimumMeaningfulEffect': None, 'errorTolerance': None,
            'noBenefitPolicy': '无独立增益则保留工程贡献并报告负结果，不改标签、知识划分或分母',
            'mechanismClaimGate': '自动软配对与正式条件路径分别报告；组处理相同时不能宣称条件机制增益'},
        'formalAdmission': {'passed': False, 'gaps': ['独立来源/克隆/标签与适用性审核待完成',
            '完整提示计数工具与模板/消息上限待核实', '条件组与消融处理差异待实际执行验证',
            '最小效应与错误容忍度待在解盲前确定', '正式执行配置与预算需冻结至运行计划']},
        'researchEligible': False}
    protocol['protocolHash'] = fingerprint(protocol)
    return protocol


def run_research_check(batch_dir, snapshot_root, output):
    batch_dir, snapshot_root, output = map(lambda value: Path(value).resolve(), (batch_dir, snapshot_root, output))
    # 先复用身份、归档读取、启动事件及窗口核对，避免绕过原件完整性检查。
    base = run_check(batch_dir, snapshot_root, output / 'saved-batch')
    plan = decode(read_artifact(batch_dir / 'plan.json'))
    rows = [decode(line) for line in read_artifact(batch_dir / 'samples.jsonl').splitlines() if line.strip()]
    snapshot = verify_snapshot(snapshot_root, plan['snapshotId'])
    catalog = decode(read_artifact(snapshot_root / 'catalogs' / (plan['snapshotId'] + '.json')))
    consumption = [inspect_consumption(row) for row in rows]
    bindings = [{'sampleId': row['sampleId'], **inspect_bindings(row['retrieval'])}
                for row in rows if row['strategy'] == 'D1']
    pairs = inspect_pair_sources(snapshot, catalog, rows)
    passed = (base['samePool']['passed'] and pairs['passed'] and all(row['passed'] for row in bindings)
              and all(row['contextStatus'] != 'FAILED' and row['requestStatus'] != 'FAILED' for row in consumption))
    protocol = build_protocol(plan)
    check = {'schemaVersion': 'd1-research-check-1', 'batchId': batch_dir.name,
        'snapshotId': plan['snapshotId'], 'planHash': plan['planHash'], 'engineeringChecksPassed': passed,
        'sourceAndWindow': {'passed': pairs['passed'] and base['snapshotBinding']['candidateTextsMatch'],
            'pairs': pairs['pairCount'], 'selectedPairs': pairs['selectedPairs'],
            'scope': '冻结知识文档及消费窗口；不代表上游全合约/真实修复已审核'},
        'bindingPaths': dict(Counter(row['path'] for row in bindings)), 'bindings': bindings,
        'consumption': consumption, 'consumptionCounts': {
            'contextsVerified': sum(row['contextStatus'] == 'VERIFIED' for row in consumption),
            'actualRequestsVerified': sum(row['actualRequestVerified'] for row in consumption),
            'missingFinalRequestReceipts': sum(row['requestStatus'] == 'UNVERIFIED' for row in consumption)},
        'protocolHash': protocol['protocolHash'], 'formalAdmission': protocol['formalAdmission'],
        'researchEligible': False, 'newModelRequests': 0, 'newEmbeddingRequests': 0,
        'provenance': base['provenance']}
    # 后续读取也必须仍是同一原件，而不是只信前半段检查结果。
    for row in base['provenance']['inputs']:
        if hashlib.sha256(read_artifact(row['path'])).hexdigest() != row['sha256Before']:
            raise ValueError('准入检查期间原件发生变化')
    atomic_json(output / 'check.json', check)
    atomic_json(output / 'pair-review.json', pairs)
    atomic_json(output / 'protocol.json', protocol)
    return check


def main():
    parser = argparse.ArgumentParser(description='D1零请求配对与实际上下文消费准入')
    for option in ('batch-dir', 'snapshot-root', 'output'):
        parser.add_argument('--' + option, required=True)
    parser.add_argument('--require-formal', action='store_true', help='研究准入未完成时返回1，工程检查默认单独报告')
    args = parser.parse_args()
    try:
        result = run_research_check(args.batch_dir, args.snapshot_root, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, 'D1准入检查失败：' + str(error) + '\n')
    print(json.dumps({key: result[key] for key in ('batchId', 'engineeringChecksPassed', 'bindingPaths',
        'consumptionCounts', 'formalAdmission', 'researchEligible', 'newModelRequests')}, ensure_ascii=False))
    return 0 if result['engineeringChecksPassed'] and (not args.require_formal or result['formalAdmission']['passed']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
