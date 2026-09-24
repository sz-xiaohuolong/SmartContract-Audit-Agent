"""从经校验的知识快照生成共享候选池；目标真值不进入检索接口。"""
import argparse
import math
import re
from pathlib import Path
from snapshots import verify_snapshot, vector32, active_snapshot
from storage import decode, encode, fingerprint


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x*x for x in a) * sum(y*y for y in b))


def recall_pool(root, snapshot_id, catalog, query_vector, query_text, limit, search=None, target_source_hash=None):
    snapshot = verify_snapshot(root, snapshot_id)
    targets = [s for s in snapshot['manifest']['samples'] if s['source_hash'] == target_source_hash]
    if not targets or any(s['split'] == 'knowledge' for s in targets):
        raise ValueError('目标源码必须来自快照全量审核清单的非知识划分')
    query = vector32(query_vector, snapshot['embedding']['dimension'])
    if type(limit) is not int or not 1 <= limit <= 1000 or not isinstance(query_text, str):
        raise ValueError('召回预算或查询文本无效')
    if (not isinstance(catalog, dict) or set(catalog) != {'snapshotId', 'cases'} or catalog['snapshotId'] != snapshot_id
            or not isinstance(catalog['cases'], dict) or set(catalog['cases']) != {d['id'] for d in snapshot['documents']}):
        raise ValueError('案例审核元数据必须精确覆盖当前快照')
    for metadata in catalog['cases'].values():
        if not isinstance(metadata, dict) or set(metadata) != {'caseId', 'pairId', 'role', 'mechanism', 'riskKind', 'conditions', 'reviewed'} or metadata['reviewed'] is not True:
            raise ValueError('案例条件与配对尚未审核或字段无效')
    rows = {r['id']: r for r in snapshot['rows']}
    scores = {key: cosine(query, row['vector']) for key, row in rows.items()}
    if search is None:
        hits = [{'id': key, 'distance': score} for key, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]]
    else:
        hits = search(query, limit)
        if not isinstance(hits, list) or len(hits) != min(limit, len(rows)): raise ValueError('远端召回条数不完整')
    seen, selected = set(), []
    origins = {s['id']: s for s in snapshot['manifest']['samples']}
    query_terms = set(re.findall(r'\w+', query_text.lower()))
    for hit in hits:
        key = hit.get('id') if isinstance(hit, dict) else None
        score = hit.get('distance') if isinstance(hit, dict) else None
        if (key not in rows or key in seen or type(score) not in (int, float) or not math.isfinite(score)
                or not math.isclose(score, scores[key], abs_tol=1e-5)):
            raise ValueError('远端召回包含未知、重复或向量分数不符的条目')
        seen.add(key)
        document = rows[key]['document']
        metadata = catalog['cases'][document['id']]
        origin = origins[document['sample_id']]
        words = set(re.findall(r'\w+', document['text'].lower()))
        union = query_terms | words
        lexical = len(query_terms & words) / len(union) if union else 0.0
        selected.append(dict(metadata, chunkId=document['id'], text=document['text'],
                             provenance=origin['origin'] + '@' + origin['source_hash'],
                             denseScore=scores[key], lexicalScore=lexical))
    selected.sort(key=lambda c: (-c['denseScore'], c['caseId'], c['chunkId']))
    return {'pool': {'schemaVersion': '1', 'snapshotId': snapshot_id, 'sourceHash': target_source_hash, 'candidates': selected},
            'recall': {'version': 'cosine-jaccard-v1', 'queryHash': fingerprint({'vector': query, 'text': query_text}),
                       'catalogHash': fingerprint(catalog), 'embedding': snapshot['embedding'], 'limit': limit,
                       'backend': 'local' if search is None else 'milvus'}}


def main():
    parser = argparse.ArgumentParser(description='从已冻结快照导出 D1 与对照共享的候选池')
    for option in ('root', 'snapshot', 'catalog', 'query', 'output'):
        parser.add_argument('--' + option, required=True)
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--milvus-url', help='显式使用本地 Milvus 已激活的新集合')
    args = parser.parse_args()
    try:
        query = decode(Path(args.query).read_bytes())
        search = None
        if args.milvus_url:
            from milvus_rest import MilvusRestIndex
            index = MilvusRestIndex(args.milvus_url)
            pointer = active_snapshot(args.root, index)
            if pointer['snapshot_id'] != args.snapshot or pointer['backend'] != 'milvus': raise ValueError('激活快照不匹配')
            search = lambda vector, limit: index.search(pointer['collection'], vector, limit)
        result = recall_pool(args.root, args.snapshot, decode(Path(args.catalog).read_bytes()), query['vector'], query['text'], args.limit, search, query['sourceHash'])
        with Path(args.output).open('xb') as output: output.write(encode(result) + b'\n')
    except (ValueError, OSError, KeyError, TypeError):
        parser.exit(2, '召回失败：检查快照、审核元数据、查询向量和输出路径；不会回退或调用模型。\n')


if __name__ == '__main__': main()
