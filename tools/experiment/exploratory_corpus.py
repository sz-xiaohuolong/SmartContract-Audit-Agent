"""只读核对待审候选库，并导出明确标记的句法对照元数据。"""
import hashlib
import re
from pathlib import Path

from r1_candidate_corpus import documents
from snapshots import vector32
from storage import decode, fingerprint


def load_corpus(directory):
    directory = Path(directory)
    automesc = decode((directory / 'automesc-selected.json').read_bytes())
    forge = decode((directory / 'forge-selected.json').read_bytes())
    vectors = decode((directory / 'vectors.json').read_bytes())
    receipt = decode((directory / 'receipt.json').read_bytes())
    rows = documents(automesc, forge)
    embedding = receipt.get('embedding', {})
    identity = fingerprint({'rows': rows, 'embedding': {'model': embedding.get('model'),
                                                        'revision': embedding.get('revision')},
                            'vectors': vectors})
    if (not isinstance(receipt, dict) or receipt.get('candidateOnly') is not True
            or receipt.get('formalD1Enabled') is not False or receipt.get('identity') != identity
            or receipt.get('collection') != 'r1pending_' + identity[:32]
            or receipt.get('automescPairs') != len(automesc) or receipt.get('forgeVfp') != len(forge)
            or receipt.get('vectorCount') != len(rows) or set(vectors) != {row['id'] for row in rows}
            or len({row['id'] for row in rows}) != len(rows)):
        raise ValueError('待审候选收据、正文或向量身份不一致')
    dimension = embedding.get('dimension')
    for key, value in vectors.items():
        if vector32(value, dimension) != value:
            raise ValueError('待审候选向量无效：' + key)
    return {'receipt': receipt, 'rows': {row['id']: row for row in rows}, 'vectors': vectors,
            'pairs': {row['id']: row for row in automesc}}


def verify_remote(corpus, index):
    receipt = corpus['receipt']
    collection = receipt['collection']
    if index.request('collections/has', {'collectionName': collection}).get('has') is not True:
        raise ValueError('待审向量集合不存在')
    expected = corpus['rows']
    seen = set()
    for offset in range(0, len(expected), 256):
        batch = index.request('entities/query', {'collectionName': collection, 'filter': '',
            'outputFields': ['id', 'payload', 'vector'], 'limit': 256, 'offset': offset,
            'consistencyLevel': 'Strong'})
        if not isinstance(batch, list):
            raise ValueError('待审向量读回失败')
        for item in batch:
            key = item.get('id') if isinstance(item, dict) else None
            if (key not in expected or key in seen or decode(item['payload']) != expected[key]
                    or vector32(item['vector'], receipt['embedding']['dimension']) != corpus['vectors'][key]):
                raise ValueError('待审向量正文、元数据或数值不一致')
            seen.add(key)
    extra = index.request('entities/query', {'collectionName': collection, 'filter': '',
        'outputFields': ['id'], 'limit': 1, 'offset': len(expected), 'consistencyLevel': 'Strong'})
    if seen != set(expected) or extra:
        raise ValueError('待审向量集合数量不完整或存在额外数据')
    return len(seen)


def _pair_predicate(pair):
    before, after = pair['before'], pair['after']
    if not (re.search(r'\bfunction\s+\w+\s*\(', before)
            and re.search(r'\bfunction\s+\w+\s*\(', after)):
        return None
    if pair['categoryHint'] == 'REENTRANCY':
        return 'NON_REENTRANT' if not re.search(r'\bnonReentrant\b', before) and re.search(r'\bnonReentrant\b', after) else None
    if pair['categoryHint'] == 'ACCESS_CONTROL':
        pattern = r'\b(?:require|if)\s*\(\s*msg\.sender\s*(?:==|!=)'
        return 'CHECK_BEFORE' if not re.search(pattern, before) and re.search(pattern, after) else None
    return None


def candidate_metadata(corpus, row):
    pair = corpus['pairs'].get(row.get('pairId'))
    predicate = _pair_predicate(pair) if pair is not None else None
    paired = predicate is not None
    mechanism = row['categoryHint']
    conditions = [] if not paired else [{'predicate': predicate, 'subject': '$actor',
        'resource': '$authority' if mechanism == 'ACCESS_CONTROL' else '$resource',
        'expected': row['side'] == 'after'}]
    return {'caseId': row['id'], 'chunkId': row['id'],
            'pairId': row['pairId'] if paired else row['id'],
            'role': ('VULNERABLE' if row['side'] == 'before' else 'DEFENSE') if paired else 'REFERENCE',
            'mechanism': mechanism, 'riskKind': 'CALL' if mechanism == 'REENTRANCY' else 'WRITE',
            'text': row['text'], 'conditions': conditions, 'reviewed': False,
            'provenance': row['source'] + ':' + row['project'] + '@' + hashlib.sha256(row['text'].encode()).hexdigest()}
