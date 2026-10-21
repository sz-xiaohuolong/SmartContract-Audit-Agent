"""phase 5 离线准备、同池比较与审核评估；没有真实模型请求入口。"""
import argparse
import hashlib
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

from compiler_facts import load_bound_compilation
from phase5_retrieval import (CONDITIONS, QUERY_CONFIG, VERSION, build_queries, freeze_pool,
                              rank_pool, score_pool)
from snapshots import verify_snapshot
from storage import atomic_json, decode, durable_write, fingerprint, read_artifact, sync_directory


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _path(root, relative):
    root, relative = Path(root).resolve(), Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('原件路径越界')
    path = root / relative
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents] if p != root):
        raise ValueError('原件路径越界或使用符号链接')
    if path.with_name(path.name + '.gz').is_symlink():
        raise ValueError('压缩原件不接受符号链接')
    return path


def read_pointer(root, pointer):
    """按逻辑路径回读唯一原件，gzip 的摘要仍按原始字节计算。"""
    data = read_artifact(_path(root, pointer['path']))
    if sha(data) != pointer['sha256']:
        raise ValueError('来源原件摘要变化')
    return data


def _batch(root, batch_id):
    if not re.fullmatch(r'[0-9a-f]{32}', batch_id):
        raise ValueError('历史批次编号无效')
    path = _path(root, 'research-artifacts/runs/benchmarks/' + batch_id)
    plan_bytes, raw = (read_artifact(_path(root, str((path / name).relative_to(root))))
                       for name in ('plan.json', 'samples.jsonl'))
    plan = decode(plan_bytes)
    if plan.get('planHash') != fingerprint({k: v for k, v in plan.items() if k != 'planHash'}):
        raise ValueError('历史计划摘要不符')
    rows = [decode(line) for line in raw.splitlines() if line.strip()]
    identities = [(row['sampleId'], row['strategy']) for row in rows]
    if len(identities) != len(set(identities)) or any(
            sample not in plan['sampleIds'] or strategy not in plan['strategies'] for sample, strategy in identities):
        raise ValueError('历史结果重复或不属于计划')
    origin = {'batchId': batch_id, 'planHash': plan['planHash'],
        'plan': {'path': str((path / 'plan.json').relative_to(root)), 'sha256': sha(plan_bytes)},
        'samples': {'path': str((path / 'samples.jsonl').relative_to(root)), 'sha256': sha(raw)}}
    return plan, rows, origin


def inventory(root, batch_ids, unit_indexes=None):
    """保留每批自己的分母；历史自动标签只用于诊断登记，不进入查询或评分。"""
    if not batch_ids or len(batch_ids) != len(set(batch_ids)):
        raise ValueError('历史批次为空或重复')
    root = Path(root).resolve()
    records, unit_indexes = [], unit_indexes or {}
    if not set(unit_indexes) <= set(batch_ids):
        raise ValueError('有效单元索引不属于所选批次')
    for batch_id in batch_ids:
        plan, rows, origin = _batch(root, batch_id)
        raw_count = sum(len(r.get('model', {}).get('hypotheses', [])) for r in rows)
        segments = {batch_id: origin}
        index_pointer = None
        if batch_id in unit_indexes:
            index_path = _path(root, unit_indexes[batch_id])
            raw_index = read_artifact(index_path); unit_index = decode(raw_index)
            if unit_index['batchId'] != batch_id or unit_index['planHash'] != plan['planHash']:
                raise ValueError('有效单元索引与计划身份不符')
            index_pointer = {'path': str(index_path.relative_to(root)), 'sha256': sha(raw_index)}
            restored, seen, cache = [], set(), {batch_id: rows}
            for item in unit_index['units']:
                key = item['sampleId'], item['strategy']
                if (key in seen or item['artifact'] != 'samples.jsonl' or type(item['rowIndex']) is not int
                        or item['rowIndex'] < 0):
                    raise ValueError('有效单元索引含重复或非法位置')
                seen.add(key)
                if item['batchId'] not in cache:
                    _, cache[item['batchId']], segments[item['batchId']] = _batch(root, item['batchId'])
                values = cache[item['batchId']]
                if item['rowIndex'] >= len(values):
                    raise ValueError('有效单元索引行越界')
                row = values[item['rowIndex']]
                if ((row['sampleId'], row['strategy']) != key or row['sourceHash'] != plan['sourceHashes'].get(item['sampleId'])):
                    raise ValueError('有效单元索引来源或行身份不符')
                restored.append(row)
            if seen != {(sample, strategy) for sample in plan['sampleIds'] for strategy in plan['strategies']}:
                raise ValueError('有效单元索引没有覆盖完整计划')
            rows = restored
        indexed = {(row['sampleId'], row['strategy']): row for row in rows}
        units = []
        for sample in plan['sampleIds']:
            strategies = {}
            for strategy in plan['strategies']:
                row = indexed.get((sample, strategy))
                candidates = row.get('model', {}).get('hypotheses', []) if row else []
                strategies[strategy] = {'status': row.get('status', 'NOT_RUN') if row else 'NOT_RUN',
                    'candidateCount': len(candidates), 'prediction': row.get('modelPrediction') if row else None,
                    'sourceHash': row.get('sourceHash') if row else plan['sourceHashes'][sample],
                    'rowHash': fingerprint(row) if row else None}
            dense, vanilla = strategies.get('DENSE'), strategies.get('VANILLA')
            expected = 'REPORT' if plan.get('labels', {}).get(sample, {}).get('hasVulnerability') else 'NO_REPORT'
            diagnosis = 'NOT_COMPARABLE'
            if dense and vanilla and dense['prediction'] in ('REPORT', 'NO_REPORT') and vanilla['prediction'] in ('REPORT', 'NO_REPORT'):
                diagnosis = 'DENSE_ONLY_MISMATCH' if dense['prediction'] != expected and vanilla['prediction'] == expected else 'OTHER_OR_NO_REGRESSION'
            units.append({'sampleId': sample, 'strategies': strategies, 'diagnosis': diagnosis,
                'causalAttribution': 'UNKNOWN', 'independentReview': 'UNREVIEWED'})
        records.append({'origin': origin, 'plannedTargets': len(plan['sampleIds']),
            'plannedUnits': len(plan['sampleIds']) * len(plan['strategies']), 'savedUnits': len(rows),
            'effectiveUnits': len(rows) if index_pointer else None, 'unitIndex': index_pointer,
            'segments': list(segments.values()), 'rawSavedCandidateCount': raw_count,
            'candidateCount': sum(len(r.get('model', {}).get('hypotheses', [])) for r in rows), 'targets': units})
    result = {'schemaVersion': 'phase5-history-1', 'batches': records, 'requestAttempts': 0,
        'limitations': ['各批次分别计数；同数量候选不是同一批原件',
                       '历史分段批次只登记保存结果，不能替代有效单元索引的权威合并',
                       'Dense 相对退步不证明材料干扰；原因与独立审核仍未知']}
    return {**result, 'manifestHash': fingerprint(result)}


def seal_dataset(data):
    result = {k: v for k, v in data.items() if k != 'datasetHash'}
    return {**result, 'datasetHash': fingerprint(result)}


def validate_dataset(data):
    if data.get('schemaVersion') != 'phase5-dataset-1' or data != seal_dataset(data):
        raise ValueError('phase 5 冻结输入摘要无效')
    keys = [target['targetKey'] for target in data['targets']]
    if not keys or len(keys) != len(set(keys)):
        raise ValueError('目标为空或重复')
    if (type(data['k']) is not int or not 1 <= data['k'] <= data['budget']['maxPairs']
            or any(type(data['budget'][k]) is not int or data['budget'][k] < 1 for k in ('maxPairs', 'maxBytes'))):
        raise ValueError('k 或完整配对预算无效')
    for target in data['targets']:
        if target['status'] != 'READY':
            continue
        if 'sourceHash' in target['queries'] and target['sourceHash'] != target['queries']['sourceHash']:
            raise ValueError('查询来源不符')
        operations = [q['operationKey'] for q in target['queries']['queries']]
        if len(operations) != len(set(operations)):
            raise ValueError('操作查询身份重复')


def check_lineage(records):
    """检查已登记的字节、项目、事件与补丁；缺失谱系仍需人工补齐。"""
    seen, groups, missing = set(), {}, []
    for record in records:
        if record['id'] in seen or record['split'] not in ('knowledge', 'development', 'evaluation'):
            raise ValueError('来源登记重复或划分无效')
        seen.add(record['id'])
        if not re.fullmatch(r'[0-9a-f]{64}', record['sourceHash']):
            raise ValueError('来源字节摘要无效')
        for field in ('sourceHash', 'project', 'event', 'patch'):
            value = record.get(field)
            if value is None:
                missing.append({'id': record['id'], 'field': field}); continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError('来源谱系字段为空')
            key = field, value
            if key in groups and groups[key] != record['split']:
                raise ValueError('同源项目、事件、补丁或字节跨划分：' + field)
            groups[key] = record['split']
    return {'status': 'REVIEW_REQUIRED' if missing else 'IDENTITY_CHECKED', 'records': len(records),
            'missing': missing, 'ledgerHash': fingerprint(records), 'independentReview': 'UNREVIEWED'}


def prepare_batch(root, batch_id, *, query_config=None, budget=None, k=2):
    """读取历史多路并集，不连接索引；缺编译或不支持的目标均保留。"""
    root = Path(root).resolve()
    plan, rows, origin = _batch(root, batch_id)
    store = _path(root, 'research-artifacts/snapshots/' + plan['embeddingProfile'])
    snapshot = verify_snapshot(store, plan['snapshotId'])
    catalog_bytes = read_artifact(_path(root, str((store / 'catalogs' / (plan['snapshotId'] + '.json')).relative_to(root))))
    catalog = decode(catalog_bytes)
    query_config, budget = query_config or dict(QUERY_CONFIG), budget or {'maxPairs': 2, 'maxBytes': 4096}
    targets = []
    for sample in plan['sampleIds']:
        target = {'targetKey': batch_id + '/' + sample, 'sampleId': sample, 'sourceHash': plan['sourceHashes'][sample],
            'snapshotId': plan['snapshotId'], 'status': 'INPUT_MISSING', 'reason': '没有保存的多路候选池',
            'origin': origin, 'splitReview': 'UNREVIEWED', 'researchEligible': False}
        candidates = [r for r in rows if r['sampleId'] == sample and r['strategy'] == 'R3_FUSION']
        if not candidates:
            targets.append(target); continue
        row = candidates[0]; view = row.get('retrieval', {})
        try:
            if (sha(row['source'].encode()) != target['sourceHash'] or row['sourceHash'] != target['sourceHash']
                    or view['sourceHash'] != target['sourceHash'] or view['pool']['schemaVersion'] != 'r3-union-1'):
                raise ValueError('源代码、计划或多路候选池身份不符')
            pool = freeze_pool(view, snapshot, catalog)
            source_hashes = {target['sourceHash'], view.get('originalSourceHash'),
                             view.get('inputGovernanceReceipt', {}).get('originalSourceHash')}
            if any(s['split'] == 'knowledge' and s['source_hash'] in source_hashes for s in snapshot['manifest']['samples']):
                raise ValueError('目标源码跨入知识划分')
            # 所有历史文本必须与模型实际消费的上下文摘要一致。
            receipt = row.get('model', {}).get('requestConsumptionReceipt')
            if (not receipt or receipt.get('contextSha256') != sha(view['d1']['context'].encode())
                    or receipt.get('sourceHash') != target['sourceHash']):
                raise ValueError('缺少匹配的实际消费回执')
            target.update(pool=pool, sourceText=row['source'], originRowHash=fingerprint(row))
            manifest = view.get('discoveryCompilation')
            if not manifest:
                raise ValueError('没有绑定编译收据，不能用词法事实代替')
            for key in ('bindingPath', 'inputPath', 'outputPath'):
                _path(root, manifest[key])
            bundle = load_bound_compilation(manifest, root)
            if bundle['sourceHash'] != target['sourceHash']:
                raise ValueError('编译来源与当前源码不符')
            queries = build_queries(bundle, {'sourceHash': bundle['sourceHash'], 'receiptDigest': bundle['receiptDigest'],
                'mechanism': view['targetMechanism']}, query_config)
            target.update(status='READY', reason=None, queries=queries,
                compilationManifest=manifest, receiptDigest=bundle['receiptDigest'],
                sourceClosureSha256=bundle['binding']['sourceClosureSha256'])
        except (ValueError, OSError, KeyError, TypeError) as error:
            target.update(status='INPUT_FAILED', reason=str(error))
        targets.append(target)
    lineage = [{'id': 'knowledge/' + s['id'], 'split': 'knowledge', 'sourceHash': s['source_hash'],
                'project': s['project_group'], 'event': None, 'patch': None} for s in snapshot['manifest']['samples']]
    lineage += [{'id': t['targetKey'], 'split': 'development', 'sourceHash': t['sourceHash'],
                 'project': None, 'event': None, 'patch': None} for t in targets]
    lineage_check = check_lineage(lineage)
    result = seal_dataset({'schemaVersion': 'phase5-dataset-1', 'targets': targets, 'budget': budget,
        'k': k, 'queryConfig': query_config, 'sources': [origin], 'requestAttempts': 0, 'researchEligible': False,
        'catalogHash': sha(catalog_bytes), 'splitReview': 'UNREVIEWED', 'lineageRecords': lineage,
        'lineageCheck': lineage_check,
        'limitations': ['当前程序事实由原编译器重验；未解析操作与入口缺口保留',
                       '字节重合已检查；项目、事件及补丁谱系仍须独立审核']})
    validate_dataset(result)
    return result


def verify_sources(root, data):
    """比较前重新核对原件与编译事实，重新封摘要不能替换真实来源。"""
    validate_dataset(data)
    for origin in data['sources']:
        for kind in ('plan', 'samples'):
            read_pointer(root, origin[kind])
    if len(data['sources']) != 1:
        raise ValueError('同池工程比较只接受一个冻结来源批次')
    restored = prepare_batch(root, data['sources'][0]['batchId'], query_config=data['queryConfig'],
                             budget=data['budget'], k=data['k'])
    if restored != data:
        raise ValueError('派生输入与原件、编译事实或候选池不符')


def review_template(data):
    """只导出中性来源、查询及完整配对，隐藏方法名称、分数和排名。"""
    validate_dataset(data)
    targets = []
    empty = {'status': 'UNREVIEWED', 'reviewer': None, 'reviewerType': None, 'rationale': None}
    for target in data['targets']:
        if target['status'] != 'READY':
            continue
        pool = target['pool']
        targets.append({'targetKey': target['targetKey'], 'sourceHash': target['sourceHash'],
            'poolHash': pool['poolHash'], 'sourceText': target.get('sourceText'),
            'queries': [{'operationKey': q['operationKey'], 'queryHash': fingerprint(q), **empty,
                'original': q['original'], 'contrasts': q['contrasts'], 'references': q.get('references', []),
                'structureStatus': q['structureStatus'], 'pairGrades': {e['pairId']: None for e in pool['evidence']},
                'relevance': dict(empty)} for q in target['queries']['queries']],
            'materials': [{'pairId': e['pairId'], 'beforeId': e['beforeId'], 'afterId': e['afterId'],
                'text': e['text'], 'sources': e.get('sources'), 'lineage': e.get('lineage')} for e in sorted(pool['evidence'], key=lambda e: e['pairId'])],
            'poolIds': sorted(e['pairId'] for e in pool['evidence'])})
    return {'schemaVersion': 'phase5-review-1', 'datasetHash': data['datasetHash'], 'targets': targets,
            'scope': 'CASE_PAIR_CANDIDATE_POOL', 'instructions': '查询接受／拒绝与材料等级分别审核；程序不能代填独立人工审核。'}


def compare_dataset(data, encoder, config):
    validate_dataset(data)
    comparisons = []
    for target in data['targets']:
        if target['status'] != 'READY':
            continue
        for q in target['queries']['queries']:
            scores = score_pool(q, target['pool']['evidence'], encoder, config)
            rankings = {condition: rank_pool(target['pool'], scores, condition, data['budget']) for condition in CONDITIONS}
            comparisons.append({'targetKey': target['targetKey'], 'operationKey': q['operationKey'],
                                'scores': scores, 'rankings': rankings})
    result = {'schemaVersion': VERSION, 'dataset': data, 'comparisons': comparisons, 'config': config,
              'requestAttempts': 0, 'researchEligible': False}
    return {**result, 'runHash': fingerprint(result)}


def validate_run(run):
    """重算向量差值和消费文本，不把重新封摘要当作验证。"""
    if run.get('schemaVersion') != VERSION or run.get('runHash') != fingerprint({k: v for k, v in run.items() if k != 'runHash'}):
        raise ValueError('重排回执摘要或版本无效')
    data = run['dataset']; validate_dataset(data)
    expected = {(t['targetKey'], q['operationKey']): (t, q) for t in data['targets'] if t['status'] == 'READY'
                for q in t['queries']['queries']}
    seen = set()
    for item in run['comparisons']:
        key = item['targetKey'], item['operationKey']
        if key not in expected or key in seen:
            raise ValueError('比较单元重复或身份不符')
        seen.add(key); target, q = expected[key]; scores = item['scores']
        if (scores['queryHash'] != fingerprint(q) or scores['evidenceHash'] != fingerprint(target['pool']['evidence'])
                or scores['config'] != run['config'] or scores['configHash'] != fingerprint(run['config'])
                or scores['operationKey'] != q['operationKey'] or scores['mechanism'] != q['mechanism']
                or scores['resourceKey'] != q.get('resourceKey')):
            raise ValueError('查询、材料或评分配置身份不符')
        can_score = q['structureStatus'] == 'VALID' and bool(q['contrasts']) and bool(target['pool']['evidence'])
        if (scores['status'] not in ('SCORED', 'FAILED', 'NOT_SCORABLE')
                or (scores['status'] == 'NOT_SCORABLE') == can_score
                or scores['status'] != 'SCORED' and (scores['scores'] or not scores['errors'])
                or scores['status'] == 'SCORED' and scores['errors']):
            raise ValueError('评分状态与冻结输入或错误记录不符')
        if scores['status'] == 'SCORED':
            def restored(texts):
                return {'identity': run['config']['identity'], 'vectors': scores['vectors'],
                        'tokenCounts': scores['tokenCounts'], 'truncated': [False] * len(texts)}
            recalculated = score_pool(q, target['pool']['evidence'], restored, run['config'])
            if recalculated['status'] != 'SCORED' or scores['inputHashes'] != recalculated['inputHashes'] or len(scores['scores']) != len(recalculated['scores']):
                raise ValueError('向量与输入摘要无法复算')
            for left, right in zip(scores['scores'], recalculated['scores']):
                if left['pairId'] != right['pairId'] or any(not math.isclose(left[k], right[k], abs_tol=1e-12)
                        for k in ('originalScore', 'margin')) or len(left['contrastScores']) != len(right['contrastScores']) or any(
                        not math.isclose(a, b, abs_tol=1e-12) for a, b in zip(left['contrastScores'], right['contrastScores'])):
                    raise ValueError('保存分数与向量复算不符')
        if set(item['rankings']) != set(CONDITIONS) or any(
                rank_pool(target['pool'], scores, condition, data['budget']) != item['rankings'][condition] for condition in CONDITIONS):
            raise ValueError('排序或消费文本无法复算')
    if seen != set(expected):
        raise ValueError('比较单元未完整覆盖冻结操作')


def write_output(path, files):
    """目录整体发布，失败时只移除本次临时目录，已有结果不会被覆盖。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError('输出目录已存在，禁止覆盖冻结派生结果')
    temporary = Path(tempfile.mkdtemp(prefix='.phase5-', dir=path.parent))
    try:
        for name, value in files.items():
            if Path(name).name != name:
                raise ValueError('输出文件名称无效')
            if isinstance(value, str): durable_write(temporary / name, value.encode())
            else: atomic_json(temporary / name, value)
        sync_directory(temporary)
        os.rename(temporary, path)
        sync_directory(path.parent)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)


def local_encoder(model_dir, factory=None):
    """仅加载已登记本机 BGE；在编码前检查完整 token 数，禁止静默截断。"""
    from d1_embed import MODEL_MANIFEST, MODEL, REVISION, DIMENSION, verify_model_dir
    manifest = decode(MODEL_MANIFEST.read_bytes())
    if (manifest.get('modelId'), manifest.get('revision'), manifest.get('dimension')) != (MODEL, REVISION, DIMENSION):
        raise ValueError('本机编码器登记身份不符')
    verify_model_dir(model_dir, manifest['files'])
    if factory is None:
        from sentence_transformers import SentenceTransformer
        factory = SentenceTransformer
    model = factory(str(Path(model_dir).resolve()), local_files_only=True, trust_remote_code=False)
    identity = {'model': MODEL, 'revision': REVISION, 'dimension': DIMENSION,
                'weightsHash': fingerprint(manifest['files'])}
    config = {'identity': identity, 'queryPrefix': '', 'documentPrefix': '',
              'maxInputTokens': min(512, model.max_seq_length)}
    def encoder(texts):
        verify_model_dir(model_dir, manifest['files'])
        counts = [len(ids) for ids in model.tokenizer(texts, truncation=False, padding=False)['input_ids']]
        if any(count > config['maxInputTokens'] for count in counts):
            raise ValueError('完整配对或查询超出固定编码器 token 上限，禁止截断')
        vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).tolist()
        verify_model_dir(model_dir, manifest['files'])
        return {'identity': identity, 'vectors': vectors, 'tokenCounts': counts, 'truncated': [False] * len(texts)}
    return encoder, config


def main():
    parser = argparse.ArgumentParser(description='phase 5 纯离线对照查询与同池重排；真实模型请求始终为零')
    sub = parser.add_subparsers(dest='command', required=True)
    history = sub.add_parser('inventory', help='分别登记历史批次、候选数量与未核实原因')
    history.add_argument('--batch-id', action='append', required=True)
    history.add_argument('--root', type=Path, default=Path.cwd())
    history.add_argument('--unit-index', type=Path, action='append', default=[], help='根目录内的权威有效单元索引，可重复指定')
    prepare = sub.add_parser('prepare', help='只读历史多路池，重验编译事实并导出盲审材料')
    prepare.add_argument('--batch-id', required=True)
    prepare.add_argument('--root', type=Path, default=Path.cwd())
    prepare.add_argument('--max-operations', type=int, default=32)
    prepare.add_argument('--max-pairs', type=int, default=2)
    prepare.add_argument('--max-bytes', type=int, default=4096)
    prepare.add_argument('--k', type=int, default=2)
    compare = sub.add_parser('compare', help='显式加载本机固定编码器；不连接外部嵌入服务')
    compare.add_argument('--dataset', type=Path, required=True)
    compare.add_argument('--model-dir', type=Path, required=True)
    compare.add_argument('--allow-unreviewed', action='store_true')
    compare.add_argument('--root', type=Path, default=Path.cwd())
    evaluate = sub.add_parser('evaluate', help='独立审核缺失时保留空成绩和全部分母')
    evaluate.add_argument('--run', type=Path, required=True)
    evaluate.add_argument('--reviews', type=Path)
    replay = sub.add_parser('replay', help='从保存向量重算分数、排序和完整消费文本')
    replay.add_argument('--run', type=Path, required=True)
    lineage = sub.add_parser('lineage', help='检查来源表中已登记的项目、事件及补丁隔离')
    lineage.add_argument('--ledger', type=Path, required=True)
    for command in (history, prepare, compare, evaluate, lineage): command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'inventory':
            indexes = {}
            for path in args.unit_index:
                relative = path.resolve().relative_to(args.root.resolve())
                index = decode(read_artifact(_path(args.root, relative)))
                if index['batchId'] in indexes: raise ValueError('有效单元索引重复')
                indexes[index['batchId']] = str(relative)
            write_output(args.output, {'manifest.json': inventory(args.root, args.batch_id, indexes)})
        elif args.command == 'prepare':
            data = prepare_batch(args.root, args.batch_id, query_config={**QUERY_CONFIG, 'maxOperations': args.max_operations},
                budget={'maxPairs': args.max_pairs, 'maxBytes': args.max_bytes}, k=args.k)
            write_output(args.output, {'dataset.json': data, 'reviews.template.json': review_template(data),
                                      'lineage.template.json': data['lineageRecords']})
        elif args.command == 'compare':
            if not args.allow_unreviewed:
                raise ValueError('当前仅支持工程演练，请显式 --allow-unreviewed；独立审核另行登记')
            data = decode(read_artifact(args.dataset)); verify_sources(args.root, data)
            encoder, config = local_encoder(args.model_dir)
            run = compare_dataset(data, encoder, config); validate_run(run)
            write_output(args.output, {'run.json': run})
        elif args.command == 'evaluate':
            from eval_ragas import evaluate_phase5
            run = decode(read_artifact(args.run))
            report = evaluate_phase5(run, decode(read_artifact(args.reviews)) if args.reviews else None)
            write_output(args.output, {'report.json': report})
        elif args.command == 'replay':
            validate_run(decode(read_artifact(args.run)))
        elif args.command == 'lineage':
            write_output(args.output, {'lineage-report.json': check_lineage(decode(read_artifact(args.ledger)))})
        print('离线操作完成；真实模型请求 0 次。')
        return 0
    except (ValueError, KeyError, TypeError, OSError, ImportError) as error:
        parser.exit(2, '离线操作失败：' + str(error) + '\n')


if __name__ == '__main__':
    main()
