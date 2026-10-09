"""以本机 Ollama 构建可续跑的 768 维 AutoMESC 独立知识快照。"""
import argparse
import hashlib
import json
from pathlib import Path

from auto_d1_snapshot import stage_auto_snapshot
from batch_compare import _append, _lines, _repair_tail
from exploratory_corpus import load_corpus, verify_remote
from milvus_rest import MilvusRestIndex
from ollama_embed import DIMENSION, MODEL, OllamaEncoder
from snapshots import activate_snapshot, active_snapshot, verify_snapshot, vector32
from storage import atomic_json, decode, exclusive_lock


def _documents(corpus):
    rows = corpus['rows']
    identifiers = [identifier + '_' + side for identifier in sorted(corpus['pairs'])
                   for side in ('before', 'after')]
    if len(identifiers) != 2 * len(corpus['pairs']) or any(
            key not in rows or rows[key]['source'] != 'AutoMESC' for key in identifiers):
        raise ValueError('AutoMESC 前后文档未完整覆盖')
    return [(key, rows[key]['text']) for key in identifiers]


def embed_corpus(corpus, directory, encoder):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    identity = {'corpusIdentity': corpus['receipt']['identity'], 'model': MODEL,
                'digest': encoder.digest, 'dimension': DIMENSION,
                'documentPrefix': 'search_document: ', 'queryPrefix': 'search_query: ',
                'requestedContext': 8192, 'reportedContext': encoder.context_length}
    with exclusive_lock(directory / '.lock'):
        manifest_path = directory / 'manifest.json'
        if manifest_path.is_file():
            if decode(manifest_path.read_bytes()) != identity:
                raise ValueError('本机嵌入模型或来源变更，不能混写已有向量')
        else:
            atomic_json(manifest_path, identity)
        log = directory / 'vectors.jsonl'
        _repair_tail(log)
        completed = {}
        for row in _lines(log):
            key = row.get('id')
            if key in completed or row.get('modelDigest') != encoder.digest:
                raise ValueError('Nomic 向量断点存在重复或不同模型')
            completed[key] = row
        vectors, receipts = {}, {}
        for key, text in _documents(corpus):
            digest = hashlib.sha256(text.encode()).hexdigest()
            if key in completed:
                row = completed[key]
                if row.get('textHash') != digest:
                    raise ValueError('Nomic 向量断点与源文本不一致')
                vector = vector32(row['vector'], DIMENSION)
                receipt = row['receipt']
            else:
                vector, receipt = encoder.encode_document(text)
                _append(log, {'id': key, 'textHash': digest, 'modelDigest': encoder.digest,
                              'receipt': receipt, 'vector': vector})
            vectors[key], receipts[key] = vector, receipt
        if set(completed) - set(vectors):
            raise ValueError('Nomic 向量断点包含额外文档')
    return {'vectors': vectors, 'receipts': receipts, 'identity': identity}


def build_nomic_snapshot(corpus, directory, snapshot_root, encoder, index=None, activate=False):
    embedded = embed_corpus(corpus, directory, encoder)
    embedding = {'model': 'ollama/' + MODEL, 'dimension': DIMENSION, 'revision': encoder.digest}
    staged = stage_auto_snapshot(corpus, snapshot_root, embedded['vectors'], embedding)
    verify_snapshot(snapshot_root, staged['snapshotId'])
    result = {'snapshotId': staged['snapshotId'], 'pairCount': staged['pairCount'],
              'documentCount': staged['documentCount'], 'embedding': embedding,
              'reportedContext': encoder.context_length, 'requestedContext': 8192,
              'truncatedDocuments': sum(row['truncated'] for row in embedded['receipts'].values()),
              'embeddingDirectory': str(directory)}
    if activate:
        if index is None:
            raise ValueError('激活 Nomic 快照必须提供 Milvus')
        pointer_path = Path(snapshot_root) / 'active.json'
        if pointer_path.is_file():
            current = active_snapshot(snapshot_root, index)
            if current['snapshot_id'] != staged['snapshotId']:
                raise ValueError('独立 Nomic 快照目录已激活另一版本')
            result['active'] = current
        else:
            result['active'] = activate_snapshot(snapshot_root, staged['snapshotId'], index,
                                                  collection_prefix='s1b_nomic_')
    return result


def main():
    parser = argparse.ArgumentParser(description='构建并激活独立 Nomic 768 维知识快照')
    parser.add_argument('--corpus-dir', default='.local/dataset-candidates/r1-pending')
    parser.add_argument('--embedding-dir', default='.local/d1-nomic-embeddings')
    parser.add_argument('--snapshot-root', default='.local/d1-nomic-snapshots')
    parser.add_argument('--milvus-url', default='http://127.0.0.1:29531')
    parser.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    corpus = load_corpus(args.corpus_dir)
    if len(corpus['pairs']) != 300:
        raise ValueError('本轮 Nomic 对照要求固定 300 组成对知识')
    index = MilvusRestIndex(args.milvus_url)
    verify_remote(corpus, index)
    encoder = OllamaEncoder(args.ollama_url)
    result = build_nomic_snapshot(corpus, args.embedding_dir, args.snapshot_root,
                                  encoder, index, args.activate)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
