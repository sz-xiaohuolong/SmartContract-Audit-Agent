"""从独立审核的真实补丁对生成 D1 正式知识快照，不自动激活。"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from isolation import validate_documents
from s3 import audit_lineage
from snapshots import build_snapshot
from storage import atomic_json, decode


MECHANISMS = {'ACCESS_CONTROL': ('CHECK_BEFORE', 'WRITE'),
              'REENTRANCY': ('STATE_WRITE_BEFORE', 'CALL')}


def _excerpt(root, artifact, bounds, function):
    if (not isinstance(bounds, list) or len(bounds) != 2
            or any(type(value) is not int for value in bounds)
            or bounds[0] < 1 or bounds[1] < bounds[0]):
        raise ValueError('知识片段行号无效')
    relative = Path(artifact['path'])
    path = (Path(root) / relative).resolve()
    if (relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(Path(root).resolve())
            or not path.is_file()):
        raise ValueError('知识原件路径越界或缺失')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact['sha256']:
        raise ValueError('知识原件摘要不符')
    lines = raw.decode('utf-8').splitlines()
    if bounds[1] > len(lines):
        raise ValueError('知识片段超出原件')
    text = '\n'.join(lines[bounds[0] - 1:bounds[1]])
    if not re.search(r'\bfunction\s+' + re.escape(function) + r'\s*\(', text):
        raise ValueError('知识片段未包含指定函数')
    return text


def stage_snapshot(ledger, root, pairs, vectors, embedding, snapshot_root):
    """仅在全部谱系与成对标签通过审核时构建快照和元数据。"""
    audit = audit_lineage(ledger, root)
    if not audit['ok'] or audit['pendingSamples']:
        raise ValueError('谱系冲突或真实标签待审，禁止建立正式知识快照')
    knowledge = {row['id']: row for row in ledger['samples'] if row['split'] == 'knowledge'}
    if (not knowledge or not isinstance(pairs, list)
            or any(not isinstance(item, dict) for item in pairs)
            or {item.get('sampleId') for item in pairs} != set(knowledge)
            or len(pairs) != len(knowledge)):
        raise ValueError('知识补丁对必须精确覆盖已审核知识样本')
    documents, cases = [], {}
    for spec in sorted(pairs, key=lambda item: item['sampleId']):
        row = knowledge[spec['sampleId']]
        mechanism = spec.get('mechanism')
        expected = MECHANISMS.get(mechanism)
        if (spec.get('reviewed') is not True or spec.get('reviewerType') != 'INDEPENDENT'
                or not isinstance(spec.get('reviewer'), str) or not spec['reviewer'].strip()
                or mechanism != row['vulnerabilityType'] or expected is None
                or (spec.get('predicate'), spec.get('riskKind')) != expected
                or spec.get('subject') != '$actor'
                or spec.get('resource') != ('$authority' if mechanism == 'ACCESS_CONTROL' else '$resource')
                or not isinstance(spec.get('function'), str) or not spec['function'].strip()):
            raise ValueError('知识条件或独立配对审核待审')
        artifacts = {item['kind']: item for item in row['artifacts']}
        if len(artifacts) != len(row['artifacts']):
            raise ValueError('知识原件类型重复，不能任意选择补丁')
        if not {'SOURCE', 'REPORT', 'PATCH'} <= artifacts.keys() or not isinstance(spec.get('evidence'), list):
            raise ValueError('知识配对缺少原始报告或补丁证据')
        if not all(artifacts[kind]['id'] in spec['evidence'] for kind in ('REPORT', 'PATCH')):
            raise ValueError('知识配对证据引用不匹配')
        if artifacts['SOURCE']['sha256'] != row['sourceHash'] or artifacts['SOURCE']['path'] != row['path']:
            raise ValueError('知识源码与谱系不一致')
        for suffix, kind, key, role, condition in (
                ('original', 'SOURCE', 'sourceLines', 'VULNERABLE', False),
                ('patch', 'PATCH', 'patchLines', 'DEFENSE', True)):
            doc_id = row['id'] + '-' + suffix
            text = _excerpt(root, artifacts[kind], spec.get(key), spec['function'])
            documents.append({'id': doc_id, 'sample_id': row['id'], 'text': text})
            cases[doc_id] = {'caseId': doc_id, 'pairId': row['patchPairId'], 'role': role,
                             'mechanism': mechanism, 'riskKind': spec['riskKind'],
                             'conditions': [{'predicate': spec['predicate'], 'subject': spec['subject'],
                                             'resource': spec['resource'], 'expected': condition}],
                             'reviewed': True}
    sources = {item['id']: item for item in ledger['sources']}
    manifest = {'schema_version': '1', 'categories': sorted(MECHANISMS),
                'samples': [{'id': row['id'], 'path': row['path'], 'source_hash': row['sourceHash'],
                             'exact_group': row['sourceHash'], 'project_group': row['projectId'],
                             'clone_groups': row['cloneGroups'],
                             'origin': sources[row['sourceId']]['url'] + '@' + sources[row['sourceId']]['revision'],
                             'split': {'knowledge': 'knowledge', 'development': 'train',
                                       'validation': 'validation'}[row['split']],
                             'types': [row['vulnerabilityType']], 'review_status': 'REVIEWED'}
                            for row in sorted(ledger['samples'], key=lambda item: item['id'])]}
    validate_documents(manifest, documents)
    identifier = build_snapshot(snapshot_root, manifest, documents, embedding,
                                {'version': 'reviewed-function-pair-v1'}, vectors)
    catalog = {'snapshotId': identifier, 'cases': cases}
    catalog_path = Path(snapshot_root) / 'catalogs' / (identifier + '.json')
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(catalog_path, catalog)
    return {'snapshotId': identifier, 'catalog': catalog, 'catalogPath': str(catalog_path),
            'documentCount': len(documents), 'lineageHash': audit['ledgerHash']}


def main():
    parser = argparse.ArgumentParser(description='从完整审核材料构建 D1 知识快照；不会自动激活')
    for name in ('ledger', 'pairs', 'vectors', 'embedding', 'root', 'snapshot-root'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = stage_snapshot(decode(Path(args.ledger).read_bytes()), Path(args.root),
                                decode(Path(args.pairs).read_bytes()), decode(Path(args.vectors).read_bytes()),
                                decode(Path(args.embedding).read_bytes()), Path(args.snapshot_root))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, '正式知识快照构建拒绝：' + str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
