"""只读检查保存的 D1 候选池与结果；派生产物不冒充重新发现实验。"""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluation_input import clean_evaluation_source
from snapshots import verify_snapshot
from storage import decode, encode, fingerprint


STRATEGIES = ('DENSE', 'FIELD_FILTER', 'D1')


def pair_summary(cases):
    groups = defaultdict(list)
    for identifier, row in cases.items():
        groups[row['pairId']].append((identifier, row))
    pairs, counts = {}, Counter(total=len(groups))
    for identifier, members in sorted(groups.items()):
        by_role = {role: [row for _, row in members if row['role'] == role]
                   for role in ('VULNERABLE', 'DEFENSE')}
        complete = (len(members) == 2 and all(len(rows) == 1 for rows in by_role.values())
                    and len({row['mechanism'] for _, row in members}) == 1)
        if not complete:
            kind = 'INCOMPLETE'
        elif all(row.get('conditions') for _, row in members):
            before, after = by_role['VULNERABLE'][0]['conditions'], by_role['DEFENSE'][0]['conditions']
            signatures = lambda conditions: [{key: value for key, value in row.items() if key != 'expected'}
                                             for row in conditions]
            kind = ('EXPLICIT_CONDITION_DIFFERENCE' if signatures(before) == signatures(after)
                    and all(row.get('expected') is False for row in before)
                    and all(row.get('expected') is True for row in after) else 'INCOMPLETE')
        elif all(not row.get('conditions') for _, row in members):
            kind = 'SOFT'
        else:
            kind = 'INCOMPLETE'
        counts[{'EXPLICIT_CONDITION_DIFFERENCE': 'explicitConditionPairs',
                'SOFT': 'softPairs', 'INCOMPLETE': 'incompletePairs'}[kind]] += 1
        pairs[identifier] = {'kind': kind, 'members': sorted(key for key, _ in members),
                            'reviewed': all(row.get('reviewed') is True for _, row in members)}
    return {'counts': {key: counts[key] for key in ('total', 'explicitConditionPairs', 'softPairs', 'incompletePairs')},
            'pairs': pairs,
            'meaning': '明确条件差异仅指保存的自动规则字段，不表示真实修复或人工适用性真值'}


def _model_metrics(plan, rows):
    counts = Counter()
    for row in rows:
        counts['completed' if row['status'] == 'COMPLETED' else 'failed'] += 1
        if row.get('prediction') not in ('REPORT', 'NO_REPORT') or row['status'] != 'COMPLETED':
            counts['unknown'] += 1
            continue
        label = plan['labels'][row['sampleId']].get('hasVulnerability')
        if type(label) is not bool:
            counts['labelUnknown'] += 1
            continue
        counts[('tp' if label else 'fp') if row['prediction'] == 'REPORT' else ('fn' if label else 'tn')] += 1
    precision = counts['tp'] / (counts['tp'] + counts['fp']) if counts['tp'] + counts['fp'] else None
    recall = counts['tp'] / (counts['tp'] + counts['fn']) if counts['tp'] + counts['fn'] else None
    f1 = None if precision is None or recall is None else 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {**{key: counts[key] for key in ('completed', 'failed', 'unknown', 'labelUnknown', 'tp', 'fp', 'fn', 'tn')},
            'precision': precision, 'recall': recall, 'f1': f1, 'tier': 'CONTAMINATED_HISTORICAL_DATASET_LABELS'}


def _usage(rows):
    result = {}
    for field in ('inputTokens', 'outputTokens'):
        known = [row[field] for row in rows if type(row.get(field)) is int and row[field] >= 0]
        result[field] = sum(known) if len(known) == len(rows) and known else None
        result['known' + field[0].upper() + field[1:]] = sum(known) if known else None
        result[field + 'Missing'] = len(rows) - len(known)
    return result


def _retrieval_metrics(rows, catalog_pairs):
    counts, gap_reasons, applicability = Counter(), Counter(), Counter()
    for row in rows:
        d1 = row['retrieval']['d1']
        selected = [item['candidate'] for item in d1.get('selected', [])]
        counts['selectedCases'] += len(selected)
        selected_pairs = pair_summary({item['chunkId']: item for item in selected})
        for identifier, pair in selected_pairs['pairs'].items():
            if pair['kind'] == 'INCOMPLETE':
                counts['selectedIncompletePairs'] += 1
            else:
                kind = catalog_pairs['pairs'][identifier]['kind']
                counts['selectedExplicitCompletePairs' if kind == 'EXPLICIT_CONDITION_DIFFERENCE'
                       else 'selectedSoftCompletePairs'] += 1
                texts = [item['text'] for item in selected if item['pairId'] == identifier]
                counts['selectedIdenticalPairTexts'] += len(set(texts)) == 1
        gaps = set(d1.get('gaps', []) + row.get('retrievalGaps', []))
        counts['unitsWithGaps'] += bool(gaps)
        gap_reasons.update(gaps)
        applicability.update(value.get('applicability', 'UNKNOWN') for value in d1.get('evaluations', {}).values())
    return {**{key: counts[key] for key in ('selectedCases', 'selectedExplicitCompletePairs',
            'selectedSoftCompletePairs', 'selectedIncompletePairs', 'selectedIdenticalPairTexts', 'unitsWithGaps')},
            'gapReasons': dict(sorted(gap_reasons.items())), 'applicability': dict(sorted(applicability.items())),
            'meaning': '配对计数按保存上下文逐单元累计；适用状态是历史自动事实输出，不是独立人工标签'}


def _source_probe(rows, plan):
    from benchmark_runtime import _risk_fact
    from program_facts import extract_facts
    by_sample, comments, ungoverned, failures = {}, 0, 0, []
    for row in rows:
        sample = row['sampleId']
        if sample in by_sample:
            continue
        source = row.get('source')
        if not isinstance(source, str) or hashlib.sha256(source.encode()).hexdigest() != plan['sourceHashes'][sample]:
            raise ValueError('保存源码与批次摘要不一致：' + sample)
        cleaned = clean_evaluation_source(source)
        receipt = cleaned['inputGovernanceReceipt']
        comments += len(receipt['removedComments'])
        historical_receipt = row['retrieval'].get('inputGovernanceReceipt')
        ungoverned += not isinstance(historical_receipt, dict)
        full = cleaned['fullSource']
        facts = extract_facts(full)
        target = {'taskKind': 'DISCOVERY', 'scope': 'FULL', 'function': '',
                  'mechanism': row['retrieval']['targetMechanism'], 'lineStart': 1, 'lineEnd': len(full.splitlines()),
                  'groundTruth': {'hasVulnerability': True}, 'vulnerableLines': [1]}
        before = _risk_fact(facts, target)
        changed = {**target, 'groundTruth': {'hasVulnerability': False}, 'vulnerableLines': [len(full.splitlines())]}
        after = _risk_fact(facts, changed)
        invariant = before == after
        if not invariant:
            failures.append(sample)
        by_sample[sample] = {'originalSourceHash': cleaned['originalSourceHash'],
            'potentialDiscoveryInputHash': cleaned['fullSourceHash'],
            'commentCount': len(receipt['removedComments']), 'factsStatus': facts['status'],
            'riskSelectionInvariant': invariant, 'riskFactId': before['id'] if before else None,
            'withinDefault6000ByteBudget': len(full.encode()) <= 6000,
            'historicalModelSourceHash': row['retrieval'].get('modelSourceHash')}
    return {'status': 'HISTORICAL_INPUT_UNCONTROLLED' if ungoverned else 'RECEIPTS_PRESENT_REVIEW_REQUIRED',
            'targets': len(by_sample), 'targetsWithoutGovernanceReceipt': ungoverned,
            'commentsMaskedInProbe': comments, 'discoveryMutationProbePassed': not failures,
            'mutationFailures': failures, 'perTarget': by_sample,
            'meaning': '清理与真值变异仅检查当前输入规则；没有重算向量、候选池或模型发现，不能修复历史污染'}


def inspect_batch(plan, rows, catalog):
    if plan.get('planHash') != fingerprint({key: value for key, value in plan.items() if key != 'planHash'}):
        raise ValueError('保存计划摘要不一致')
    if catalog.get('snapshotId') != plan['snapshotId']:
        raise ValueError('候选登记与批次快照不一致')
    catalog_pairs = pair_summary(catalog['cases'])
    by_sample, issues = defaultdict(list), []
    seen = set()
    for row in rows:
        key = row.get('sampleId'), row.get('strategy')
        if key in seen or key[0] not in plan['sampleIds'] or key[1] not in plan['strategies']:
            raise ValueError('保存单元重复或不属于计划')
        seen.add(key)
        pool = row['retrieval']['pool']
        if (row.get('snapshotId') != plan['snapshotId'] or pool.get('snapshotId') != plan['snapshotId']
                or row.get('sourceHash') != plan['sourceHashes'][key[0]]
                or pool.get('sourceHash') != plan['sourceHashes'][key[0]]):
            raise ValueError('保存单元、候选池与源码快照不一致')
        if (not isinstance(row.get('source'), str)
                or hashlib.sha256(row['source'].encode()).hexdigest() != plan['sourceHashes'][key[0]]):
            raise ValueError('保存源码与批次摘要不一致：' + key[0])
        digest = fingerprint(pool)
        if row.get('poolHash') != digest:
            issues.append({'sampleId': key[0], 'strategy': key[1], 'kind': 'RECORDED_POOL_HASH_MISMATCH'})
        by_sample[key[0]].append((key[1], digest))
        candidates = {candidate['chunkId']: candidate for candidate in pool['candidates']}
        if len(candidates) != len(pool['candidates']):
            issues.append({'sampleId': key[0], 'strategy': key[1], 'kind': 'DUPLICATE_POOL_CANDIDATE'})
        pool_pairs = pair_summary(candidates)
        if pool_pairs['counts']['incompletePairs']:
            issues.append({'sampleId': key[0], 'strategy': key[1], 'kind': 'INCOMPLETE_POOL_PAIR'})
        for identifier, candidate in candidates.items():
            metadata = catalog['cases'].get(identifier)
            if metadata is None or any(candidate.get(field) != value for field, value in metadata.items()):
                issues.append({'sampleId': key[0], 'strategy': key[1], 'kind': 'CATALOG_METADATA_MISMATCH',
                               'chunkId': identifier})
        selected_ids = [item['candidate']['chunkId'] for item in row['retrieval']['d1'].get('selected', [])]
        if row.get('selectedIds') != selected_ids or row.get('selectedEvidence') != len(selected_ids):
            issues.append({'sampleId': key[0], 'strategy': key[1], 'kind': 'SELECTED_IDS_MISMATCH'})
        for selected in row['retrieval']['d1'].get('selected', []):
            candidate = selected['candidate']
            if candidates.get(candidate['chunkId']) != candidate:
                issues.append({'sampleId': key[0], 'strategy': key[1], 'kind': 'SELECTION_OUTSIDE_FROZEN_POOL'})
    comparisons = []
    for sample in plan['sampleIds']:
        saved = by_sample[sample]
        passed = len(saved) == len(STRATEGIES) and {strategy for strategy, _ in saved} == set(STRATEGIES) and len({digest for _, digest in saved}) == 1
        comparisons.append({'sampleId': sample, 'passed': passed, 'savedStrategies': [strategy for strategy, _ in saved],
                            'poolHashes': sorted({digest for _, digest in saved})})
    metrics = {}
    for strategy in STRATEGIES:
        selected_rows = [row for row in rows if row['strategy'] == strategy]
        metrics[strategy] = {'model': _model_metrics(plan, selected_rows),
            'retrieval': _retrieval_metrics(selected_rows, catalog_pairs), 'usage': _usage(selected_rows),
            'd2SavedVerdicts': dict(sorted(Counter(row.get('d2', {}).get('verdict', 'NOT_RUN') for row in selected_rows).items()))}
    return {'schemaVersion': '1', 'batchId': None, 'snapshotId': plan['snapshotId'],
            'newModelRequests': 0, 'newEmbeddingRequests': 0, 'researchEligible': False,
            'researchStatus': 'UNVERIFIED', 'samePool': {'passed': all(row['passed'] for row in comparisons) and not issues,
                'targetsChecked': len(comparisons), 'comparisons': comparisons, 'issues': issues},
            'catalogPairs': catalog_pairs, 'metrics': metrics, 'historicalInput': _source_probe(rows, plan),
            'formalAdmission': {'passed': False, 'tokenizer': None, 'fullPromptTokenCap': None,
                'reason': '真实 tokenizer、完整消息模板、独立适用性标签与费用授权尚未冻结；字节预算不证明 token 公平'}}


def _report(check):
    pairs = check['catalogPairs']['counts']
    lines = ['# D1 保存候选池离线检查', '',
        f"来源批次：`{check['batchId']}`；冻结快照：`{check['snapshotId']}`。",
        f"检查 {check['samePool']['targetsChecked']} 个目标；三策略同池及池内选择检查：{'通过' if check['samePool']['passed'] else '失败'}。新增模型与嵌入请求均为 0。", '',
        f"知识登记 {pairs['total']} 对，明确自动条件差异 {pairs['explicitConditionPairs']} 对、软对 {pairs['softPairs']} 对、不完整 {pairs['incompletePairs']} 对。明确差异不是独立审核的真实修复真值。", '',
        '## 从保存结果重算的工程指标', '',
        '| 策略 | TP | FP | FN | TN | 历史标签 F1 | 完整明确差异对 | 完整软对 | 有缺口单元 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for strategy, data in check['metrics'].items():
        model, retrieval = data['model'], data['retrieval']
        f1 = '未知' if model['f1'] is None else f"{model['f1']:.4f}"
        lines.append(f"| {strategy} | {model['tp']} | {model['fp']} | {model['fn']} | {model['tn']} | {f1} | {retrieval['selectedExplicitCompletePairs']} | {retrieval['selectedSoftCompletePairs']} | {retrieval['unitsWithGaps']} |")
    history = check['historicalInput']
    isolation = check['sourceIsolation']
    cleaning = isolation['knowledgeCommentCleaning']
    lines += ['', '## 输入与研究限制', '',
        f"{history['targetsWithoutGovernanceReceipt']} 个目标缺少历史输入治理回执；当前离线探针遮蔽 {history['commentsMaskedInProbe']} 条注释。真值变异不改变当前发现风险选择：{'通过' if history['discoveryMutationProbePassed'] else '失败'}。",
        '探针只生成清理文本摘要并检查当前规则，没有重新生成查询向量、候选池或模型结果。历史实现还曾用真值选函数与风险，不能把保存发现结果解释为清理后未知位置发现，也不能据此证明 D1 方法提升。',
        '表中分类指标仅按保存的数据集标签重算，安全函数对照不代表整份合约安全；UNKNOWN、失败、标签未知单独统计，usage 缺失保持 null。候选配对与适用状态属于自动规则或历史事实输出，没有独立人工适用性标签。',
        f"候选登记精确覆盖 {check['snapshotBinding']['documentCount']} 份固定文档，池文本按历史截取规则核对。目标原件/潜在清理输入与已取得知识摘要的精确重合为 {len(isolation['exactOverlaps'])}；知识片段清理成功 {cleaning['cleanedDocuments']}/{cleaning['totalDocuments']}，其余缺口逐项保留。项目与近克隆隔离仍为 UNVERIFIED。",
        '本检查不计算有人工相关性真值要求的 Recall@K、nDCG@K 或 D2 准确率。历史 4096 字节上下文上限不证明完整提示 token 公平；正式实验准入未完成，研究效果 UNVERIFIED。', '',
        '## 复核', '', '输入文件前后 SHA-256、脚本 SHA-256、逐策略计数与逐目标比较见 `check.json`；平面指标见 `metrics.csv`。原批次与正式快照保持只读。']
    return '\n'.join(lines) + '\n'


def run_check(batch_dir, snapshot_root, output):
    batch_dir, snapshot_root, output = (Path(value).resolve() for value in (batch_dir, snapshot_root, output))
    if output == batch_dir or output.is_relative_to(batch_dir) or output == snapshot_root or output.is_relative_to(snapshot_root):
        raise ValueError('派生输出必须位于历史批次与正式快照目录之外')
    plan_path, samples_path, events_path = batch_dir / 'plan.json', batch_dir / 'samples.jsonl', batch_dir / 'events.jsonl'
    plan = decode(plan_path.read_bytes())
    snapshot = verify_snapshot(snapshot_root, plan['snapshotId'])
    catalog_path = snapshot_root / 'catalogs' / (plan['snapshotId'] + '.json')
    paths = [plan_path, samples_path, events_path, catalog_path, snapshot_root / plan['snapshotId'] / 'snapshot.json']
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    rows = [decode(line) for line in samples_path.read_bytes().splitlines() if line.strip()]
    catalog = decode(catalog_path.read_bytes())
    documents = {row['id']: row for row in snapshot['documents']}
    if set(catalog['cases']) != set(documents):
        raise ValueError('候选登记必须精确覆盖冻结知识文档')
    events = [decode(line) for line in events_path.read_bytes().splitlines() if line.strip()]
    expected_plan = {'kind': 'PLAN', 'planHash': plan.get('planHash')}
    started = [(row.get('sampleId'), row.get('strategy')) for row in events[1:] if row.get('kind') == 'STARTED']
    if (not events or events[0] != expected_plan or len(started) != len(set(started))
            or any((row.get('sampleId'), row.get('strategy')) not in started for row in rows)):
        raise ValueError('保存结果缺少唯一对应的启动事件或计划事件')
    check = inspect_batch(plan, rows, catalog)
    auto = any(row['review_status'] == 'AUTO_LABELED' for row in snapshot['manifest']['samples'])
    text_issues = []
    for row in rows:
        for candidate in row['retrieval']['pool']['candidates']:
            document = documents.get(candidate['chunkId'])
            expected = document['text'][:700] if document and auto else document['text'] if document else None
            if candidate.get('text') != expected:
                text_issues.append({'sampleId': row['sampleId'], 'strategy': row['strategy'],
                    'kind': 'SNAPSHOT_TEXT_MISMATCH', 'chunkId': candidate['chunkId']})
    check['samePool']['issues'].extend(text_issues)
    check['samePool']['passed'] = check['samePool']['passed'] and not text_issues
    check['snapshotBinding'] = {'catalogExactlyCoversDocuments': True, 'documentCount': len(documents),
        'candidateTextsMatch': not text_issues, 'historicalExcerptCharacters': 700 if auto else None}
    check.update(batchId=batch_dir.name, snapshotEmbedding=snapshot['embedding'])
    knowledge_samples = [row for row in snapshot['manifest']['samples'] if row['split'] == 'knowledge']
    knowledge_hashes = {row['source_hash'] for row in knowledge_samples}
    knowledge_ids = {row['id'] for row in knowledge_samples}
    cleaning_failures, cleaned_documents, knowledge_documents = [], 0, 0
    for document in snapshot['documents']:
        if document['sample_id'] in knowledge_ids:
            knowledge_documents += 1
            knowledge_hashes.add(hashlib.sha256(document['text'].encode()).hexdigest())
            try:
                knowledge_hashes.add(clean_evaluation_source(document['text'])['fullSourceHash'])
                cleaned_documents += 1
            except ValueError as error:
                cleaning_failures.append({'documentId': document['id'], 'reason': str(error)})
    overlaps = [sample for sample, row in check['historicalInput']['perTarget'].items()
                if row['originalSourceHash'] in knowledge_hashes or row['potentialDiscoveryInputHash'] in knowledge_hashes]
    check['sourceIsolation'] = {'exactSourceDisjoint': not overlaps, 'exactOverlaps': overlaps,
        'comparison': '原件/潜在清理输入与知识登记原件、两侧文档及成功清理文档的精确摘要比较；未清理片段保留缺口',
        'knowledgeCommentCleaning': {'complete': not cleaning_failures, 'totalDocuments': knowledge_documents,
            'cleanedDocuments': cleaned_documents, 'failures': cleaning_failures},
        'projectAndCloneIsolation': 'UNVERIFIED',
        'reason': '保存批次缺少完整目标来源/项目/近克隆登记，不能仅从向量池证明全部谱系隔离'}
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    if before != after:
        raise ValueError('检查期间历史原件或冻结知识发生变化')
    check['provenance'] = {'inputs': [{'path': path, 'sha256Before': digest, 'sha256After': after[path]} for path, digest in before.items()],
        'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'originalsUnchanged': True}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'check.json').write_bytes(encode(check) + b'\n')
    (output / 'REPORT.md').write_text(_report(check), encoding='utf-8')
    csv_output = io.StringIO()
    writer = csv.writer(csv_output)
    writer.writerow(['策略', 'TP', 'FP', 'FN', 'TN', '历史标签F1', '完整明确差异对', '完整软对', '有缺口单元', '输入token', '输出token'])
    for strategy, row in check['metrics'].items():
        model, retrieval, usage = row['model'], row['retrieval'], row['usage']
        writer.writerow([strategy, model['tp'], model['fp'], model['fn'], model['tn'], model['f1'],
            retrieval['selectedExplicitCompletePairs'], retrieval['selectedSoftCompletePairs'],
            retrieval['unitsWithGaps'], usage['inputTokens'], usage['outputTokens']])
    (output / 'metrics.csv').write_text(csv_output.getvalue(), encoding='utf-8')
    return check


def main():
    parser = argparse.ArgumentParser(description='只读检查保存 D1 候选池，生成零新增请求的派生报告')
    parser.add_argument('--batch-dir', required=True)
    parser.add_argument('--snapshot-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        check = run_check(args.batch_dir, args.snapshot_root, args.output)
        print(json.dumps({'output': str(Path(args.output).resolve()), 'samePoolPassed': check['samePool']['passed'],
                          'newModelRequests': 0, 'researchEligible': False}, ensure_ascii=False))
        return 0 if check['samePool']['passed'] else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, '离线检查失败：' + str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
