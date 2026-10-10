"""待审语料的只读三策略探索；逐样本保存，不生成审计准确率。"""
import argparse
import hashlib
import math
import os
from pathlib import Path

from d1_embed import DIMENSION, MODEL_MANIFEST, load_local_encoder
from exploratory_corpus import candidate_metadata, load_corpus, verify_remote
from exploratory_targets import load_targets
from evaluation_input import clean_evaluation_source
from formal_recall import CONTEXT_BYTES, java_retrieval, select_strategy
from milvus_rest import MilvusRestIndex
from program_facts import extract_facts
from snapshots import vector32
from storage import atomic_json, decode, encode, exclusive_lock, fingerprint


def _cosine(left, right):
    a = math.sqrt(sum(x * x for x in left))
    b = math.sqrt(sum(x * x for x in right))
    if not a or not b:
        raise ValueError('零向量不能参与余弦检索')
    return sum(x * y for x, y in zip(left, right)) / (a * b)


def build_pool(corpus, target, query_vector, index, limit=80):
    """验证真实召回距离，再补全被召回的暂定配对。"""
    dimension = corpus['receipt']['embedding']['dimension']
    query = vector32([float(value) for value in query_vector], dimension)
    if not 1 <= limit <= len(corpus['rows']):
        raise ValueError('候选池上限无效')
    hits = index.search(corpus['receipt']['collection'], query, limit)
    if not isinstance(hits, list) or len(hits) > limit:
        raise ValueError('Milvus 召回结果无效')
    chosen, scores = [], {}
    for hit in hits:
        key = hit.get('id') if isinstance(hit, dict) else None
        score = hit.get('distance') if isinstance(hit, dict) else None
        if key not in corpus['rows'] or key in scores or isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError('Milvus 召回 ID 或分数无效')
        expected = _cosine(query, corpus['vectors'][key])
        if not math.isfinite(score) or abs(score - expected) > 1e-4:
            raise ValueError('Milvus 召回分数与固定向量不符')
        scores[key] = float(score)
        if corpus['rows'][key]['categoryHint'] == target['mechanism']:
            chosen.append(key)
    for key in tuple(chosen):
        row = corpus['rows'][key]
        if row['source'] != 'AutoMESC':
            continue
        meta = candidate_metadata(corpus, row)
        if meta['role'] == 'REFERENCE':
            continue
        partner = row['pairId'] + ('_after' if row['side'] == 'before' else '_before')
        if partner not in scores:
            scores[partner] = _cosine(query, corpus['vectors'][partner])
        if partner not in chosen:
            chosen.append(partner)
    candidates = []
    for key in chosen:
        row = corpus['rows'][key]
        metadata = candidate_metadata(corpus, row)
        candidates.append({**metadata, 'text': row['text'][:700], 'denseScore': scores[key],
                           'lexicalScore': 0.0})
    return {'schemaVersion': 'exploratory-1', 'snapshotId': corpus['receipt']['identity'],
            'sourceHash': target['sourceHash'], 'candidates': candidates}


def _govern_target(target):
    """探索入口保持原件证据；默认发现不传评分位置给消费链。"""
    if hashlib.sha256(target['source'].encode()).hexdigest() != target['sourceHash']:
        raise ValueError('探索目标源码摘要不符')
    governed = clean_evaluation_source(target.get('originalSource', target['source']))
    if 'originalSource' in target and (target.get('originalSourceHash') != governed['originalSourceHash']
            or target['source'] != governed['source']):
        raise ValueError('探索目标原件与清理文本不一致')
    kind = target.get('taskKind', 'DISCOVERY')
    if kind not in ('DISCOVERY', 'CLAIM_VALIDATION'):
        raise ValueError('探索任务类型无效')
    governed['inputGovernanceReceipt'].update(taskKind=kind, scope='FULL')
    return {**{key: value for key, value in target.items() if key != 'vulnerableLines'},
            **governed, 'taskKind': kind}


def _risk_fact(facts, target):
    kinds = {'CALL'} if target['mechanism'] == 'REENTRANCY' else {'WRITE', 'CALL'}
    risk_line = target.get('riskLine') if target['taskKind'] == 'CLAIM_VALIDATION' else None
    if target['taskKind'] == 'CLAIM_VALIDATION' and (type(risk_line) is not int or risk_line < 1):
        return None
    exact = [fact for fact in facts['facts'] if fact['kind'] in kinds
             and (risk_line is None or fact['line'] == risk_line)]
    if len(exact) == 1:
        return exact[0]
    return None


def compare_target(root, corpus, target, index, encoder, java_runner=None, limit=80):
    target = _govern_target(target)
    provenance = {key: target.get(key) for key in
        ('taskKind', 'claimOrigin', 'originalSourceHash', 'inputGovernanceReceipt')}
    encoded = encoder([target['source']])
    if len(encoded) != 1:
        raise ValueError('查询模型未返回唯一向量')
    pool = build_pool(corpus, target, encoded[0], index, limit)
    facts = extract_facts(target['source'])
    risk = _risk_fact(facts, target) if facts['status'] != 'FAILED' else None
    if risk is None:
        return {**provenance, 'sampleId': target['sampleId'], 'status': 'UNKNOWN', 'reason': 'NO_UNIQUE_RISK_FACT',
                'poolHash': fingerprint(pool), 'poolSize': len(pool['candidates']), 'riskStatus': 'UNKNOWN',
                'selected': {'DENSE': [], 'FIELD_FILTER': [], 'D1': []}}
    resource = risk['resource'] if risk['kind'] == 'WRITE' else 'owner'
    request = {'target': {'mechanism': target['mechanism'], 'riskFactId': risk['id'],
                          'bindings': {'actor': 'msg.sender', 'resource': resource, 'authority': resource}},
               'pool': pool, 'budget': {'maxBytes': CONTEXT_BYTES, 'maxCases': 4}}
    answer = (java_runner or (lambda source, value: java_retrieval(root, source, value)))(target['source'], request)
    results = answer.get('results') if isinstance(answer, dict) else None
    if not isinstance(results, list) or len(results) != 1 or results[0].get('strategy') != 'D1':
        raise ValueError('D1 返回结构无效')
    d1 = results[0]
    if d1.get('sourceHash') != target['sourceHash'] or d1.get('snapshotId') != corpus['receipt']['identity']:
        raise ValueError('D1 返回的源码或知识身份不一致')
    view = {'pool': pool, 'd1': d1, 'snapshotId': corpus['receipt']['identity']}
    selected = {}
    for strategy in ('DENSE', 'FIELD_FILTER', 'D1'):
        choice = select_strategy(view, strategy)['d1']
        selected[strategy] = [item['candidate']['chunkId'] for item in choice['selected']]
    return {**provenance, 'sampleId': target['sampleId'], 'status': 'COMPLETED', 'poolHash': fingerprint(pool),
            'poolSize': len(pool['candidates']), 'riskStatus': facts['status'],
            'selected': selected, 'd1Gaps': d1.get('gaps', []),
            'candidateRoles': {item['chunkId']: item['role'] for item in pool['candidates']}}


def _paths(store, batch_id):
    if not isinstance(batch_id, str) or len(batch_id) != 32 or any(c not in '0123456789abcdef' for c in batch_id):
        raise ValueError('批次 ID 无效')
    folder = Path(store) / batch_id
    return folder, folder / 'plan.json', folder / 'results.jsonl'


def run_probe(store, targets, receipt, runner, batch_id=None, parameters=None):
    if not targets or len({row['sampleId'] for row in targets}) != len(targets):
        raise ValueError('探索目标缺失或重复')
    if receipt.get('candidateOnly') is not True or receipt.get('formalD1Enabled') is not False:
        raise ValueError('只允许待审候选库')
    targets = [_govern_target(row) if 'source' in row else dict(row) for row in targets]
    parameters = parameters or {'candidateLimit': 80, 'textExcerptCharacters': 700}
    batch_id = batch_id or fingerprint({'targets': targets, 'receipt': receipt['identity'],
                                        'parameters': parameters})[:32]
    folder, plan_path, result_path = _paths(store, batch_id)
    folder.mkdir(parents=True, exist_ok=True)
    plan = {'batchId': batch_id, 'candidateIdentity': receipt['identity'],
            'targetIds': [row['sampleId'] for row in targets],
            'targetHashes': {row['sampleId']: row['sourceHash'] for row in targets},
            'targetMetadata': {row['sampleId']: {key: row.get(key) for key in
                ('documentHash', 'projectHint', 'mechanism', 'split', 'taskKind', 'riskLine',
                 'claimOrigin', 'originalSourceHash', 'inputGovernanceReceipt',
                 'labelStatus', 'maxCandidateCloneSimilarity')} for row in targets},
            'mode': 'EXPLORATORY_RETRIEVAL_ONLY', 'modelCalls': 0,
            'researchEligible': False, 'parameters': parameters,
            'contextBudget': {'kind': 'UTF8_BYTES', 'limit': CONTEXT_BYTES}}
    with exclusive_lock(folder / '.lock'):
        if plan_path.exists():
            if decode(plan_path.read_bytes()) != plan:
                raise ValueError('续跑计划身份已变化')
        else:
            atomic_json(plan_path, plan)
        completed = {}
        if result_path.exists():
            for line in result_path.read_bytes().splitlines():
                record = decode(line)
                key = record.get('sampleId')
                if key in completed or key not in plan['targetHashes'] or record.get('sourceHash') != plan['targetHashes'][key]:
                    raise ValueError('逐样本结果重复或与计划不一致')
                completed[key] = record
        with result_path.open('ab') as output:
            for target in targets:
                key = target['sampleId']
                if key in completed:
                    continue
                try:
                    value = runner(target)
                    if not isinstance(value, dict) or value.get('sampleId') != key or value.get('status') not in ('COMPLETED', 'UNKNOWN'):
                        raise ValueError('探索结果契约无效')
                    record = {**value, 'sourceHash': target['sourceHash']}
                except Exception as error:
                    record = {'sampleId': key, 'sourceHash': target['sourceHash'],
                              'status': 'FAILED', 'reason': type(error).__name__, 'decision': 'UNKNOWN'}
                output.write(encode(record) + b'\n')
                output.flush()
                os.fsync(output.fileno())
    return batch_id


def replay_probe(store, batch_id):
    _, plan_path, result_path = _paths(store, batch_id)
    plan = decode(plan_path.read_bytes())
    records = [decode(line) for line in result_path.read_bytes().splitlines()] if result_path.exists() else []
    planned = set(plan['targetIds'])
    if len(records) != len({row['sampleId'] for row in records}) or any(
            row['sampleId'] not in planned or row['sourceHash'] != plan['targetHashes'][row['sampleId']]
            for row in records):
        raise ValueError('回放结果与计划不一致')
    completed = sum(row['status'] == 'COMPLETED' for row in records)
    failed = sum(row['status'] == 'FAILED' for row in records)
    unknown = sum(row['status'] in ('FAILED', 'UNKNOWN') for row in records)
    return {'plan': plan, 'denominators': {'planned': len(planned), 'completed': completed,
            'failed': failed, 'unknown': unknown},
            'metrics': {'detectionRecall': None, 'precision': None, 'd1Improvement': None},
            'results': records}


class PendingIndex:
    def __init__(self, rest):
        self.rest = rest

    def search(self, collection, vector, limit):
        if not collection.startswith('r1pending_'):
            raise ValueError('仅允许待审候选集合')
        return self.rest.request('entities/search', {'collectionName': collection, 'data': [vector],
            'annsField': 'vector', 'limit': limit, 'outputFields': ['id'],
            'consistencyLevel': 'Strong', 'searchParams': {'metricType': 'COSINE', 'params': {}}})


def main():
    parser = argparse.ArgumentParser(description='待审 742 条知识候选的离线 D1 探索；无模型付费调用')
    parser.add_argument('--root', default='.')
    parser.add_argument('--corpus-dir', default='.local/dataset-candidates/r1-pending')
    parser.add_argument('--target-dir', default='src/main/resources/document/smartbugs_kb')
    parser.add_argument('--model-dir', default='.local/d1-embedding-model')
    parser.add_argument('--milvus-url', default='http://127.0.0.1:29531')
    parser.add_argument('--report-dir', default='.local/d1-exploratory-runs')
    parser.add_argument('--limit', type=int, default=80)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    corpus = load_corpus(root / args.corpus_dir)
    rest = MilvusRestIndex(args.milvus_url)
    verify_remote(corpus, rest)
    targets = load_targets(root / args.target_dir, list(corpus['rows'].values()))
    from sentence_transformers import SentenceTransformer
    encoder = load_local_encoder(SentenceTransformer, root / args.model_dir,
                                 decode(MODEL_MANIFEST.read_bytes()))
    index = PendingIndex(rest)
    batch_id = run_probe(root / args.report_dir, targets, corpus['receipt'],
        lambda target: compare_target(root, corpus, target, index, encoder, limit=args.limit),
        parameters={'candidateLimit': args.limit, 'textExcerptCharacters': 700})
    report = replay_probe(root / args.report_dir, batch_id)
    atomic_json(root / args.report_dir / batch_id / 'report.json', report)
    print(encode({'batchId': batch_id, 'denominators': report['denominators'],
                  'report': str(root / args.report_dir / batch_id / 'report.json')}).decode())


if __name__ == '__main__':
    main()
