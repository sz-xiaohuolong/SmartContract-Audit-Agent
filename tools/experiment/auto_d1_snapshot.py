"""将固定 AutoMESC 前后候选构建为显式标注等级的 S1b 自动知识快照。"""
import argparse
import hashlib
from pathlib import Path

from exploratory_corpus import candidate_metadata, load_corpus, verify_remote
from milvus_rest import MilvusRestIndex
from snapshots import activate_snapshot, build_snapshot, verify_snapshot
from storage import atomic_json, decode, fingerprint


def stage_auto_snapshot(corpus, snapshot_root, vectors_override=None, embedding_override=None):
    pairs = corpus['pairs']
    if not pairs or len(corpus['rows']) < 2 * len(pairs):
        raise ValueError('自动知识的前后片段不完整')
    samples, documents, cases, vectors = [], [], {}, {}
    for identifier, pair in sorted(pairs.items()):
        if (pair.get('reviewStatus') != 'PENDING' or pair.get('patchStatus') != 'UNVERIFIED'
                or pair.get('source') != 'AutoMESC' or pair.get('categoryHint') not in
                ('ACCESS_CONTROL', 'REENTRANCY')):
            raise ValueError('自动知识来源或标签状态异常')
        before_id, after_id = identifier + '_before', identifier + '_after'
        before, after = corpus['rows'].get(before_id), corpus['rows'].get(after_id)
        if (before is None or after is None or before['text'] != pair['before']
                or after['text'] != pair['after'] or not pair['before'].strip()
                or not pair['after'].strip() or pair['before'] == pair['after']):
            raise ValueError('自动知识配对内容不一致')
        samples.append({'id': identifier, 'path': 'AutoMESC/' + identifier + '.sol',
                        'source_hash': hashlib.sha256(pair['before'].encode()).hexdigest(),
                        'exact_group': hashlib.sha256(pair['before'].encode()).hexdigest(),
                        'project_group': pair['project'], 'clone_groups': [],
                        'origin': pair['commitUrl'] + '@' + pair['sourceRevision'],
                        'split': 'knowledge', 'types': [pair['categoryHint']],
                        'review_status': 'AUTO_LABELED', 'evidence_tier': 'HEURISTIC',
                        'label_rule': 'automesc-before-after-diff-v1'})
        for key in (before_id, after_id):
            row = corpus['rows'][key]
            documents.append({'id': key, 'sample_id': identifier, 'text': row['text']})
            metadata = candidate_metadata(corpus, row)
            cases[key] = {field: metadata[field] for field in
                          ('caseId', 'pairId', 'role', 'mechanism', 'riskKind', 'conditions', 'reviewed')}
            # 即使未识别出保护机制，前后侧仍是自动标注的暂定配对，不伪装成人工安全真值。
            if cases[key]['role'] == 'REFERENCE':
                cases[key]['role'] = 'VULNERABLE' if row['side'] == 'before' else 'DEFENSE'
                cases[key]['pairId'] = identifier
            vectors[key] = (vectors_override if vectors_override is not None else corpus['vectors'])[key]
    manifest = {'schema_version': '1', 'categories': ['ACCESS_CONTROL', 'REENTRANCY'], 'samples': samples}
    embedding = embedding_override if embedding_override is not None else corpus['receipt']['embedding']
    snapshot_root = Path(snapshot_root)
    identifier = build_snapshot(snapshot_root, manifest, documents, embedding,
        {'version': 'automesc-auto-v1:' + fingerprint({'corpus': corpus['receipt']['identity'], 'cases': cases})}, vectors)
    catalog = {'snapshotId': identifier, 'cases': cases}
    folder = snapshot_root / 'catalogs'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (identifier + '.json')
    if path.exists():
        if decode(path.read_bytes()) != catalog:
            raise ValueError('既有自动知识元数据与快照冲突')
    else:
        atomic_json(path, catalog)
    return {'snapshotId': identifier, 'catalog': catalog, 'pairCount': len(pairs),
            'documentCount': len(documents), 'candidateIdentity': corpus['receipt']['identity']}


def main():
    parser = argparse.ArgumentParser(description='构建并可显式激活 AutoMESC 自动标注 S1b 知识快照')
    parser.add_argument('--corpus-dir', default='.local/dataset-candidates/r1-pending')
    parser.add_argument('--snapshot-root', default='.local/d1-kb-snapshots')
    parser.add_argument('--milvus-url', default='http://127.0.0.1:29531')
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    corpus = load_corpus(args.corpus_dir)
    index = MilvusRestIndex(args.milvus_url)
    verify_remote(corpus, index)
    result = stage_auto_snapshot(corpus, args.snapshot_root)
    if not 100 <= result['pairCount'] <= 300 or result['documentCount'] != 2 * result['pairCount']:
        raise ValueError('自动知识数量不在本轮批准范围')
    verify_snapshot(args.snapshot_root, result['snapshotId'])
    if args.activate:
        result['active'] = activate_snapshot(args.snapshot_root, result['snapshotId'], index)
    print(__import__('json').dumps({k: v for k, v in result.items() if k != 'catalog'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
