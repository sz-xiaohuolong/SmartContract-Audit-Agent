"""为待审 D1 知识候选生成可复核的本地语义向量，不激活正式快照。"""
import argparse
import json
from pathlib import Path

from d1_kb import _excerpt
from s3 import audit_lineage
from snapshots import vector32
from storage import atomic_json, decode, fingerprint


MODEL = 'BAAI/bge-small-en-v1.5'
REVISION = '5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'
DIMENSION = 384


def load_encoder(factory, cache):
    try:
        model = factory(MODEL, revision=REVISION, cache_folder=str(cache), trust_remote_code=False)
    except Exception as error:
        raise ValueError('固定模型权重无法读取，请检查网络或本机缓存') from error
    return lambda texts: model.encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                                      show_progress_bar=False)


def candidate_vectors(ledger, root, pairs, encode, revision, dimension):
    audit = audit_lineage(ledger, root)
    if not audit['ok']:
        raise ValueError('知识候选存在跨划分泄漏')
    knowledge = {row['id']: row for row in ledger['samples'] if row['split'] == 'knowledge'}
    if (not knowledge or not isinstance(pairs, list) or any(not isinstance(item, dict) for item in pairs)
            or len(pairs) != len(knowledge) or {item.get('sampleId') for item in pairs} != set(knowledge)):
        raise ValueError('知识候选配对未完整覆盖')
    sources = {row['id']: row for row in ledger['sources']}
    names, texts = [], []
    for spec in sorted(pairs, key=lambda item: item['sampleId']):
        row = knowledge[spec['sampleId']]
        source = sources[row['sourceId']]
        if any(source[kind + 'Status'] != 'VERIFIED' for kind in ('source', 'report', 'patch')):
            raise ValueError('知识候选源码、原始报告或补丁未固定')
        artifacts = {item['kind']: item for item in row['artifacts']}
        if len(artifacts) != len(row['artifacts']) or not {'SOURCE', 'REPORT', 'PATCH'} <= artifacts.keys():
            raise ValueError('知识候选原件不完整或重复')
        if artifacts['SOURCE']['path'] != row['path'] or artifacts['SOURCE']['sha256'] != row['sourceHash']:
            raise ValueError('知识候选源码与谱系不一致')
        for suffix, kind, key in (('original', 'SOURCE', 'sourceLines'), ('patch', 'PATCH', 'patchLines')):
            names.append(row['id'] + '-' + suffix)
            texts.append(_excerpt(root, artifacts[kind], spec.get(key), spec['function']))
    encoded = encode(texts)
    if len(encoded) != len(names):
        raise ValueError('语义向量数量不完整')
    vectors = {name: vector32(list(vector), dimension) for name, vector in zip(names, encoded)}
    return {'candidateOnly': True, 'lineageHash': audit['ledgerHash'],
            'textsHash': fingerprint(dict(zip(names, texts))),
            'embedding': {'model': MODEL, 'dimension': dimension, 'revision': revision},
            'vectors': vectors}


def main():
    parser = argparse.ArgumentParser(description='使用本地固定模型计算待审 D1 候选向量')
    for name in ('ledger', 'pairs', 'root', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--model-cache', default='.local/d1-embedding-model')
    args = parser.parse_args()
    try:
        ledger = decode(Path(args.ledger).read_bytes())
        pairs = decode(Path(args.pairs).read_bytes())
        from sentence_transformers import SentenceTransformer
        encode = load_encoder(SentenceTransformer, args.model_cache)
        result = candidate_vectors(ledger, Path(args.root), pairs, encode, REVISION, DIMENSION)
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        atomic_json(output / 'candidate-vectors.json', result)
        atomic_json(output / 'vectors.json', result['vectors'])
        atomic_json(output / 'embedding.json', result['embedding'])
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        parser.exit(2, '候选向量生成失败：' + str(error) + '\n')
    print(json.dumps({'candidateOnly': True, 'documents': len(result['vectors']),
                      'model': MODEL, 'revision': REVISION, 'lineageHash': result['lineageHash']},
                     ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
