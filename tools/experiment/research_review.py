"""只读准备双批次候选身份、来源盘点与独立审核表；不执行模型或核验器。"""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from storage import artifact_exists, decode, durable_write, fingerprint, read_artifact


DEFAULT_BATCHES = ('119b4862f8a14818b62848ce709c3ee6', '6cae40677b104152bd92efedc5bbc479')
REGISTRY = 'data/audit/r2/research-review/source-registry.json'
LEDGER = 'data/audit/r1/formal-expansion/formal-v2-ledger.json'
ARTIFACTS = ('plan.json', 'events.jsonl', 'samples.jsonl', 'summary.json')
VERDICTS = ('SUPPORTED', 'REFUTED', 'UNKNOWN')
REVIEW_FIELDS = ('reviewer1', 'reviewer2', 'sampleTruth', 'candidateLocationCorrect',
                 'candidateOperationCorrect', 'candidateTruth', 'repairSemanticsCorrect',
                 'evidenceRefs', 'disagreement', 'arbitrator', 'arbitration', 'reviewedAt')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _empty_review():
    # 来源标签和历史准入记录不能代填本项目独立候选审核。
    return dict.fromkeys(REVIEW_FIELDS)


def _batch_directory(root, batch_id):
    if not isinstance(batch_id, str) or re.fullmatch('[0-9a-f]{32}', batch_id) is None:
        raise ValueError('批次编号无效')
    return Path(root) / 'research-artifacts/runs/benchmarks' / batch_id


def _triage(hypothesis, assessment, verdict, failed):
    if failed:
        return 'PIPELINE_FAILURE'
    if assessment is None:
        return 'MISSING_ASSESSMENT'
    if verdict != 'UNKNOWN':
        return 'SAVED_' + verdict
    proof = assessment.get('candidateProof') or {}
    gaps = (proof.get('proofScope') or {}).get('gaps') or []
    joined = '\n'.join(gaps)
    if '终止内置证明范围' in joined:
        return 'AC_CALL_OUTSIDE_SCOPE'
    if any('风险' in gap and '未唯一绑定' in gap for gap in gaps):
        return 'RISK_BINDING_OR_OPERATION'
    if proof.get('proofKind') == 'ACCESS_CONTROL_AUTHORITY_WRITE_CANDIDATE':
        return 'AUTHORITY_WRITE_COMMIT_WITNESS'
    if hypothesis.get('vulnerabilityType') == 'ACCESS_CONTROL':
        return 'AC_RESOURCE_AUTHORITY_CLOSURE'
    if '未绑定同主体 msg.sender 映射余额与编译 uint 转账数值' in joined:
        return 'RE_BALANCE_ALIAS_OR_VALUE'
    if '辅助外部调用的正常返回或无回调条件尚未核验' in joined:
        return 'RE_EXTERNAL_RETURN_OR_CALLBACK'
    if '未证明余额与资金的可调用建态历史' in joined:
        return 'RE_INITIALIZATION_OR_FUNDS'
    return 'PATH_OR_ENTRY_CLOSURE'


def review_batch(root, batch_id):
    """每个计划单元均保留；只导出候选位置、摘要和原件指针，不复制响应或源码。"""
    root = Path(root)
    directory = _batch_directory(root, batch_id)
    raw = {name: read_artifact(directory / name) for name in ARTIFACTS}
    before = {name: sha(data) for name, data in raw.items()}
    plan = decode(raw['plan.json'])
    if plan.get('planHash') != fingerprint({k: v for k, v in plan.items() if k != 'planHash'}):
        raise ValueError('批量计划摘要不一致')
    sample_ids, strategies = plan['sampleIds'], plan['strategies']
    if len(set(sample_ids)) != len(sample_ids) or len(set(strategies)) != len(strategies):
        raise ValueError('计划单元重复')
    expected = {(sample, strategy) for sample in sample_ids for strategy in strategies}
    events = [decode(line) for line in raw['events.jsonl'].splitlines() if line.strip()]
    if not events or events[0] != {'kind': 'PLAN', 'planHash': plan['planHash']}:
        raise ValueError('计划事件与原计划不一致')
    started = set()
    for event in events[1:]:
        key = event.get('sampleId'), event.get('strategy')
        if event.get('kind') != 'STARTED' or key not in expected or key in started:
            raise ValueError('启动事件重复或越界')
        started.add(key)
    indexed = {}
    for number, line in enumerate(raw['samples.jsonl'].splitlines(), 1):
        if not line.strip():
            continue
        row = decode(line)
        key = row.get('sampleId'), row.get('strategy')
        if key in indexed or key not in expected or key not in started:
            raise ValueError('保存单元重复或越界')
        if row.get('sourceHash') != plan['sourceHashes'][key[0]] or row.get('snapshotId') != plan['snapshotId']:
            raise ValueError('保存单元输入身份与计划不一致')
        if row.get('source') is not None and sha(row['source'].encode()) != row['sourceHash']:
            raise ValueError('保存单元素材源码摘要不一致')
        indexed[key] = number, row
    candidates, units, samples = [], [], []
    counts = Counter(plannedUnits=len(expected), savedUnits=len(indexed), missingUnits=len(expected) - len(indexed))
    for sample_id in sample_ids:
        samples.append({'sampleId': sample_id, 'sourceHash': plan['sourceHashes'][sample_id],
                        'sourceLabel': plan['labels'][sample_id], 'labelPointer': '/labels/' + sample_id,
                        'split': None, 'projectGroup': None, 'cloneGroups': None,
                        'lineageStatus': 'PENDING_REVIEW', 'independentReview': _empty_review(),
                        'researchEligible': False})
        for strategy in strategies:
            key = sample_id, strategy
            if key not in indexed:
                units.append({'sampleId': sample_id, 'strategy': strategy, 'status': 'MISSING',
                              'pipelineStatus': 'MISSING', 'candidateCount': 0,
                              'sourceHash': plan['sourceHashes'][sample_id], 'sampleLine': None})
                continue
            number, row = indexed[key]
            hypotheses = (row.get('model') or {}).get('hypotheses', [])
            if not isinstance(hypotheses, list) or any(not isinstance(h, dict) for h in hypotheses):
                raise ValueError('保存候选结构无效')
            assessments = {}
            for assessment in (row.get('d2') or {}).get('assessments', []):
                index = assessment.get('hypothesisIndex')
                if type(index) is not int or index < 0 or index >= len(hypotheses) or index in assessments:
                    raise ValueError('候选核验索引重复或越界')
                assessments[index] = assessment
            unit = {field: row.get(field) for field in ('sampleId', 'strategy', 'sourceHash', 'status',
                    'pipelineStatus', 'prediction', 'errorCategory', 'compilationError', 'diagnosticPath')}
            unit.update(sampleLine=number, candidateCount=len(hypotheses), sourcePresent=isinstance(row.get('source'), str))
            units.append(unit)
            counts['modelCompleted' if row.get('status') == 'COMPLETED' else 'modelFailed'] += 1
            counts['pipelineCompleted' if row.get('pipelineStatus') == 'COMPLETED' else 'pipelineFailed'] += 1
            for index, hypothesis in enumerate(hypotheses):
                assessment = assessments.get(index)
                saved = (assessment or {}).get('verdict')
                failed = (row.get('status') != 'COMPLETED' or row.get('pipelineStatus') != 'COMPLETED'
                          or bool((assessment or {}).get('errorCategory')))
                verdict = saved if saved in VERDICTS and not failed else 'UNKNOWN'
                candidate_hash = fingerprint(hypothesis)
                identity = [batch_id, plan['planHash'], sample_id, strategy, index, candidate_hash]
                proof = (assessment or {}).get('candidateProof') or {}
                candidate = {'candidateId': 'candidate-' + fingerprint(identity), 'candidateHash': candidate_hash,
                    'hashEncoding': 'storage.encode:UTF-8/sort_keys/compact/allow_nan=false',
                    'batchId': batch_id, 'planHash': plan['planHash'], 'sampleId': sample_id, 'strategy': strategy,
                    'hypothesisIndex': index, 'sourceHash': row['sourceHash'],
                    'original': {'path': (directory / 'samples.jsonl').relative_to(root).as_posix(),
                                 'sha256': before['samples.jsonl'], 'line': number,
                                 'jsonPointer': '/model/hypotheses/' + str(index)},
                    'position': {field: hypothesis.get(field) for field in
                                 ('contract', 'function', 'riskLine', 'riskOperation', 'vulnerabilityType')},
                    'savedVerdict': saved, 'verdict': verdict, 'assessmentPresent': assessment is not None,
                    'triageCode': _triage(hypothesis, assessment, verdict, failed),
                    'proofKind': proof.get('proofKind'), 'candidateBound': proof.get('candidateBound'),
                    'proofGaps': (proof.get('proofScope') or {}).get('gaps', []),
                    'independentReview': _empty_review(), 'researchEligible': False}
                candidates.append(candidate)
                counts[verdict] += 1
                counts['missingAssessments'] += assessment is None
    usage = {}
    for field in ('inputTokens', 'outputTokens', 'requestAttempts'):
        values = [r.get(field) for _, r in indexed.values()]
        known = [v for v in values if type(v) is int and v >= 0]
        usage[field] = {'total': sum(known) if len(known) == len(expected) else None,
                        'observedSubtotal': sum(known), 'missingUnits': len(expected) - len(known)}
    usage['cost'] = None
    after = {name: sha(read_artifact(directory / name)) for name in ARTIFACTS}
    if before != after:
        raise ValueError('读取期间原件发生变化，拒绝生成稳定身份报告')
    for name in (*VERDICTS, 'modelCompleted', 'modelFailed', 'pipelineCompleted', 'pipelineFailed', 'missingAssessments'):
        counts.setdefault(name, 0)
    counts['candidates'] = len(candidates)
    saved_counts = {verdict: sum((c['savedVerdict'] if c['savedVerdict'] in VERDICTS else 'UNKNOWN') == verdict
                                 for c in candidates) for verdict in VERDICTS}
    review_counts = {verdict: counts.pop(verdict) for verdict in VERDICTS}
    return {'schemaVersion': 'research-review-1', 'batchId': batch_id, 'planHash': plan['planHash'],
            'snapshotId': plan['snapshotId'], 'counts': dict(counts), 'usage': usage,
            'savedCandidateVerdicts': saved_counts, 'reviewCandidateVerdicts': review_counts,
            'verdictConflicts': [{'candidateId': c['candidateId'], 'savedVerdict': c['savedVerdict'],
                                 'reviewVerdict': c['verdict'], 'triageCode': c['triageCode']}
                                for c in candidates if c['savedVerdict'] in VERDICTS and c['savedVerdict'] != c['verdict']],
            'originalHashesBefore': before, 'originalHashesAfter': after,
            'samples': samples, 'units': units, 'candidates': candidates,
            'unknownTriage': dict(Counter(c['triageCode'] for c in candidates if c['verdict'] == 'UNKNOWN')),
            'researchEligible': False, 'modelRequests': 0,
            'limitations': ['裁决仅为保存结果，不是重跑证明。分流不是唯一因果根因。',
                            '来源标签不等于候选位置、操作、性质的独立真值。',
                            '项目及克隆谱系待审核，未由字节去重推导无泄漏。',
                            '原保存计数与保守审核计数分列；单元失败中的保存裁决不直接成为已核结论。']}


def resolve_candidate(root, candidate):
    """审核时从单份原件回读完整候选，同时检查原件、单元和候选身份。"""
    expected_path = _batch_directory(Path(root), candidate['batchId']) / 'samples.jsonl'
    if candidate['original']['path'] != expected_path.relative_to(root).as_posix():
        raise ValueError('候选原件路径与批次不一致')
    raw = read_artifact(expected_path)
    if sha(raw) != candidate['original']['sha256']:
        raise ValueError('候选原件摘要已变化')
    row = decode(raw.splitlines()[candidate['original']['line'] - 1])
    if any(row.get(field) != candidate[field] for field in ('sampleId', 'strategy', 'sourceHash')):
        raise ValueError('候选指针指向其他单元')
    value = row['model']['hypotheses'][candidate['hypothesisIndex']]
    identity = [candidate['batchId'], candidate['planHash'], candidate['sampleId'], candidate['strategy'],
                candidate['hypothesisIndex'], fingerprint(value)]
    if (fingerprint(value) != candidate['candidateHash']
            or 'candidate-' + fingerprint(identity) != candidate['candidateId']):
        raise ValueError('候选内容或身份摘要不一致')
    return value


def split_audit(rows):
    """只检查已经登记的分组；待审分组不会获得无泄漏结论。"""
    groups = defaultdict(list)
    unresolved = []
    for row in rows:
        if not row.get('projectId') or row.get('cloneGroups') is None or row.get('split') not in ('knowledge', 'train', 'validation', 'test'):
            unresolved.append(row['id'])
        keys = [('bytes', row.get('sourceHash')), ('project', row.get('projectId'))]
        keys += [('clone', clone) for clone in (row.get('cloneGroups') or [])]
        for kind, group in keys:
            if group and row.get('split') in ('knowledge', 'train', 'validation', 'test'):
                groups[kind, group].append({'id': row['id'], 'split': row['split']})
    conflicts = [{'kind': kind, 'group': group, 'members': members}
                 for (kind, group), members in sorted(groups.items()) if len({r['split'] for r in members}) > 1]
    duplicates = [{'sha256': group, 'members': members} for (kind, group), members in groups.items()
                  if kind == 'bytes' and len(members) > 1]
    return {'conflicts': conflicts, 'exactDuplicates': duplicates, 'unresolvedIds': sorted(unresolved),
            'scope': '仅登记的项目、字节与克隆组；不代表未知克隆或模型预训练污染已排除',
            'researchEligible': False}


def _artifact_status(root, descriptor):
    result = dict(descriptor)
    path = descriptor.get('path')
    if path is None or not artifact_exists(root / path):
        return {**result, 'status': 'MISSING', 'sha256': None, 'byteCount': None}
    raw = read_artifact(root / path)
    actual, expected = sha(raw), descriptor.get('expectedSha256')
    return {**result, 'status': 'HASH_MISMATCH' if expected and actual != expected else 'AVAILABLE',
            'sha256': actual, 'byteCount': len(raw), 'hashMatches': actual == expected if expected else None}


def benchmark_provenance(root, samples):
    """把稳定历史编号定位到现存原始来源；当前字节绝不替换批次冻结输入。"""
    from exploratory_targets import _sample_id
    from benchmark_targets import SAFE_FUNCTIONS
    root = Path(root)
    metadata_path = root / 'smartbugs-curated/vulnerabilities.json'
    entries, metadata_hash = {}, None
    if artifact_exists(metadata_path):
        raw = read_artifact(metadata_path)
        metadata_hash = sha(raw)
        for item in decode(raw):
            categories = {v['category'] for v in item.get('vulnerabilities', [])}
            if len(categories) == 1:
                category = next(iter(categories))
                entries[_sample_id(category, item['path'])] = item
    mapped = []
    for sample in samples:
        sample_id = sample['sampleId']
        entry = entries.get(sample_id)
        path, origin, project = None, None, None
        if entry:
            path, origin = 'smartbugs-curated/' + entry['path'], entry.get('source')
            parsed = urlsplit(origin or '')
            pieces = parsed.path.strip('/').split('/')
            if parsed.netloc.lower() == 'github.com' and len(pieces) >= 2:
                project = 'https://github.com/' + '/'.join(pieces[:2]).removesuffix('.git')
        elif sample_id + '.sol' in SAFE_FUNCTIONS:
            path = 'data/controls/openzeppelin/' + sample_id + '.sol'
            origin = project = 'https://github.com/OpenZeppelin/openzeppelin-contracts'
        identity = _artifact_status(root, {'path': path, 'expectedSha256': None})
        mapped.append({'sampleId': sample_id, 'currentSource': identity, 'originUrl': origin,
                       'proposedProjectGroup': project, 'lineageStatus': 'PENDING_REVIEW',
                       'currentMetadataPath': 'smartbugs-curated/vulnerabilities.json' if entry else None,
                       'currentMetadataSha256': metadata_hash if entry else None,
                       'currentRawBytesMatchFrozen': identity['sha256'] == sample['sourceHash'] if identity['sha256'] else None,
                       'note': '冻结的模型输入仍只从原批次回读；来源原件经过注释遮罩或历史加工可有字节差异。'})
    return mapped


def inventory_sources(root, registry, ledger):
    """按既有账本继承准入与划分；描述表不能替代正式标签账本。"""
    root = Path(root)
    formal = {item['id']: item for item in ledger['samples']}
    events = []
    for descriptor in registry['events']:
        row = dict(descriptor)
        inherited = formal.get(row['id'])
        if inherited:
            row.update({key: inherited.get(key) for key in
                        ('projectId', 'eventId', 'split', 'cloneGroups', 'sourceHash', 'labelStatus', 'originType')})
            row['inheritedTruthReview'] = {key: inherited.get(key) for key in
                                          ('truthReviewer', 'truthReviewerType', 'truthReviewVersion')}
            registered = {artifact['kind']: artifact for artifact in inherited['artifacts']}
            artifacts = []
            for item in row['artifacts']:
                registered_item = registered.get(item['kind'])
                if registered_item:
                    item = {**item, 'path': registered_item['path'], 'expectedSha256': registered_item['sha256']}
                artifacts.append(item)
        else:
            row.update(split=None, cloneGroups=None, labelStatus='PENDING', originType=None)
            artifacts = row['artifacts']
        row['artifacts'] = [_artifact_status(root, item) for item in artifacts]
        row['independentReview'] = _empty_review()
        row['researchEligible'] = False
        row['formalAdmissionPresent'] = inherited is not None
        events.append(row)
    controls = []
    for descriptor in registry['controls']:
        controls.append({**descriptor, 'artifact': _artifact_status(root, descriptor['artifact']),
                         'independentReview': _empty_review(), 'researchEligible': False})
    # 再次读取本轮已用原件，避免把读取期间变化的材料封成固定审核输入。
    original_hashes = {}
    for artifact in [a for event in events for a in event['artifacts']] + [c['artifact'] for c in controls]:
        if artifact['status'] != 'MISSING':
            path = artifact['path']
            if sha(read_artifact(root / path)) != artifact['sha256']:
                raise ValueError('来源原件在盘点期间变化')
            original_hashes[path] = artifact['sha256']
    return {'schemaVersion': 'research-source-review-1', 'events': events, 'controls': controls,
            'counts': {'eventProjects': len({r['projectId'] for r in events}), 'events': len(events),
                       'formalEvents': sum(r['formalAdmissionPresent'] for r in events),
                       'pendingEvents': sum(not r['formalAdmissionPresent'] for r in events),
                       'controls': len(controls), 'controlUpstreams': len({r['projectId'] for r in controls})},
            'splitAudit': split_audit(events), 'originalHashesBefore': original_hashes,
            'originalHashesAfter': dict(original_hashes), 'researchEligible': False,
            'limitations': ['已有漏洞裁决不自动构成本项目候选及修复覆盖的独立审核。',
                            '四个 OpenZeppelin 文件共享同一上游，来源阴性标签不是安全证明。']}


def _csv_bytes(rows, fields):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        # 表格软件不应把来自候选和来源的文字解释成公式。
        writer.writerow({key: ("'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@')) else value)
                         for key, value in row.items() if key in fields})
    return output.getvalue().encode('utf-8')


def write_review(output, batches, inventory, csv_export=False):
    """输出到新目录，避免再次运行覆盖人工审核；CSV仅在显式请求时生成。"""
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('输出目录非空，拒绝覆盖可能已经填写的独立审核')
    output.mkdir(parents=True, exist_ok=True)
    summary = {'schemaVersion': 'research-review-package-1', 'researchEligible': False, 'modelRequests': 0,
               'batches': [{'batchId': b['batchId'], 'path': b['batchId'] + '.json', 'counts': b['counts'],
                            'savedCandidateVerdicts': b['savedCandidateVerdicts'],
                            'reviewCandidateVerdicts': b['reviewCandidateVerdicts']} for b in batches],
               'sources': 'source-inventory.json', 'csvRequested': csv_export}
    for name, value in [('summary.json', summary), ('source-inventory.json', inventory)] + [
            (batch['batchId'] + '.json', batch) for batch in batches]:
        durable_write(output / name, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n')
    if csv_export:
        rows = [{**{key: row.get(key) for key in ('candidateId', 'batchId', 'sampleId', 'strategy', 'hypothesisIndex', 'candidateHash')},
                 **row['position'], **row['independentReview']}
                for batch in batches for row in batch['candidates']]
        fields = ['candidateId', 'batchId', 'sampleId', 'strategy', 'hypothesisIndex', 'candidateHash',
                  'contract', 'function', 'riskLine', 'riskOperation', 'vulnerabilityType', *REVIEW_FIELDS]
        durable_write(output / 'candidate-review.csv', _csv_bytes(rows, fields))
        samples = [{'batchId': batch['batchId'], 'sampleId': row['sampleId'], 'sourceHash': row['sourceHash'],
                    **row['independentReview']} for batch in batches for row in batch['samples']]
        durable_write(output / 'sample-review.csv', _csv_bytes(samples, ['batchId', 'sampleId', 'sourceHash', *REVIEW_FIELDS]))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2], help='项目根目录')
    parser.add_argument('--batch', action='append', help='要读取的批次编号，可重复；默认旧133与新151双批次')
    parser.add_argument('--output', type=Path, required=True, help='新的派生输出目录，拒绝覆盖非空目录')
    parser.add_argument('--csv', action='store_true', help='额外生成空白独立审核CSV')
    args = parser.parse_args(argv)
    batches = args.batch or DEFAULT_BATCHES
    if len(set(batches)) != len(batches):
        parser.error('批次编号重复')
    root = args.root.resolve()
    output = args.output.resolve()
    if output.is_relative_to(root / 'research-artifacts'):
        parser.error('审核导出不能写入历史研究原件目录')
    metadata = {name: read_artifact(root / name) for name in (REGISTRY, LEDGER)}
    registry = decode(metadata[REGISTRY])
    ledger = decode(metadata[LEDGER])
    reports = [review_batch(root, batch_id) for batch_id in batches]
    for report in reports:
        report['currentSourceProvenance'] = benchmark_provenance(root, report['samples'])
    inventory = inventory_sources(root, registry, ledger)
    inventory['metadataHashes'] = {name: sha(raw) for name, raw in metadata.items()}
    if any(read_artifact(root / name) != raw for name, raw in metadata.items()):
        raise ValueError('来源登记在读取期间发生变化')
    summary = write_review(args.output, reports, inventory, args.csv)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
