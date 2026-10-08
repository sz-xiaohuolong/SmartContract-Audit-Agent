"""整理公开语料的待审候选，并存入与正式快照隔离的 Milvus 集合。"""
import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

from d1_embed import DIMENSION, MODEL, MODEL_MANIFEST, REVISION, load_local_encoder
from milvus_rest import MilvusRestIndex
from snapshots import vector32
from storage import atomic_json, decode, encode, fingerprint


SOURCE_REVISION = 'a143612ca5bfa52109367750a034ae4c9b66803d'
SOURCE_HASHES = {
    'commits_exported_data_.csv': '3d0f9a670e03c450740a7d71a56593d42a51e27ceb51fe6d51be524b3dfcc6f5',
    'file_change_exported_data_.csv': '5acd8576b84d79df3f39718681e960712359d33d24d2e0253c135f6a1430cf83',
    'fixes_exported_data_.csv': '92a2b5bfb6d421acd2fff98f64d30de2581a5c7f76a9f7213987e8546cbe4377',
    'repository_exported_data_.csv': '7b1b86b12933921fa88cbbb7f62b7e3e3cc834335e4d2a194fbfa4124f2bc00b',
}
FORGE_REVISION = 'bace532526e5a978a5b175964d1ce769c577362c'
FORBIDDEN_PROJECTS = ('maia', 'atomicloans', 'pooltogether', 'rabbithole', 'infinity', 'jpegd')
ACCESS = re.compile(r'(?i)access[ -]?control|permission|unauthori[sz]|onlyowner|only owner|authenti|privilege|\brole\b|modifier|\bowner\b|\badmin\b|msg\.sender')
REENTRY = re.compile(r'(?i)re.?entr|nonreentrant|checks.effects|external call|\.call\{|\.call\(|\.transfer\(|\.send\(')
ACCESS_CHANGE = re.compile(r'(?i)onlyowner|hasrole|accesscontrol|msg\.sender|_owner|onlyadmin|onlyauthorized|require\s*\(')
REENTRY_CHANGE = re.compile(r'(?i)nonreentrant|reentrancyguard|reentrant|\.call\{|\.call\(|\.transfer\(|\.send\(')
ACCESS_REPORT = re.compile(r'(?i)access|authoriz|permission|privilege|\brole\b|\bowner\b|CWE-862|CWE-863|CWE-284')
REENTRY_REPORT = re.compile(r'(?i)re.?entr|CWE-841')


def _csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_automesc(root, limit_per_category=150):
    root = Path(root)
    for name, expected in SOURCE_HASHES.items():
        if _sha(root / name) != expected:
            raise ValueError('AutoMESC 原始文件摘要不符：' + name)
    commits = {row['hash']: row for row in _csv(root / 'commits_exported_data_.csv')}
    repos = {row['repo_id']: row for row in _csv(root / 'repository_exported_data_.csv')}
    fixed = {row['hash'] for row in _csv(root / 'fixes_exported_data_.csv') if row['checked'] == 'True'}
    ranked = {'ACCESS_CONTROL': [], 'REENTRANCY': []}
    for row in _csv(root / 'file_change_exported_data_.csv'):
        commit = commits.get(row['hash'])
        if commit is None or row['hash'] not in fixed:
            continue
        repo = repos.get(commit['repo_id'])
        if repo is None or not repo['repo_url'].startswith('https://github.com/'):
            continue
        if any(word in repo['repo_url'].lower() for word in FORBIDDEN_PROJECTS):
            continue
        if (not row['filename'].endswith('.sol') or re.search(r'(?i)test|mock|interface|spec', row['filename'])
                or row['change_type'] != 'modified'):
            continue
        before, after = row['cod_befor'].strip(), row['code_after'].strip()
        if not (80 <= len(before) <= 8000 and 80 <= len(after) <= 8000) or before == after:
            continue
        message = commit['msg']
        changed = '\n'.join(line for line in (before + '\n' + after).splitlines()
                            if line.startswith(('+', '-')))
        for category, pattern, change_pattern in (
                ('ACCESS_CONTROL', ACCESS, ACCESS_CHANGE),
                ('REENTRANCY', REENTRY, REENTRY_CHANGE)):
            if not change_pattern.search(changed):
                continue
            score = 4 * bool(pattern.search(message)) + 2 * bool(pattern.search(after)) + bool(pattern.search(before))
            ranked[category].append((-score, repo['repo_url'], row['hash'], row['file_change_id'], row, commit, repo))
    selected, used_projects = [], set()
    for category in ('REENTRANCY', 'ACCESS_CONTROL'):
        count = 0
        for _, project, _, _, row, commit, repo in sorted(ranked[category]):
            if project in used_projects:
                continue
            used_projects.add(project)
            selected.append({'id': 'am_' + row['file_change_id'], 'source': 'AutoMESC',
                             'sourceRevision': SOURCE_REVISION, 'project': project,
                             'commit': row['hash'], 'commitUrl': project + '/commit/' + row['hash'],
                             'file': row['filename'], 'categoryHint': category,
                             'selectionRule': 'changed-line-keyword-v1',
                             'reviewStatus': 'PENDING', 'patchStatus': 'UNVERIFIED',
                             'before': row['cod_befor'].strip(), 'after': row['code_after'].strip()})
            count += 1
            if count == limit_per_category:
                break
        if count < limit_per_category:
            raise ValueError('AutoMESC 候选不足，不能凑数')
    return sorted(selected, key=lambda row: row['id'])


def select_forge(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('FORGE-Curated 文件夹缺失')
    result = []
    for path in sorted(root.glob('vfp_*.json')):
        data = decode(path.read_bytes())
        if not isinstance(data, dict) or data.get('vfp_id') != path.stem:
            raise ValueError('FORGE-Curated 条目 ID 不匹配')
        findings = []
        for finding in data.get('findings', []):
            signal = ' '.join((str(finding.get('title', '')), str(finding.get('description', '')),
                               json.dumps(finding.get('category', {}), sort_keys=True)))
            if ACCESS_REPORT.search(signal) or REENTRY_REPORT.search(signal):
                findings.append(finding)
        if not findings:
            continue
        files = data.get('affected_files')
        if not isinstance(files, dict) or not files:
            continue
        chunks = []
        for name, code in sorted(files.items()):
            if isinstance(code, str) and name.endswith('.sol'):
                chunks.append(name + '\n' + code[:10000])
        if not chunks:
            continue
        report = '\n'.join(str(finding.get('title', '')) + '\n' + str(finding.get('description', ''))[:3000]
                           for finding in findings)
        text = (report + '\n' + '\n'.join(chunks))[:24000]
        result.append({'id': 'forge_' + path.stem, 'source': 'FORGE-Curated',
                       'sourceRevision': FORGE_REVISION, 'project': str(data.get('project_name', '')),
                       'reportFile': path.name, 'categoryHint': 'REENTRANCY' if any(
                           REENTRY_REPORT.search(str(item.get('title', '')) + ' ' + str(item.get('description', '')))
                           for item in findings) else 'ACCESS_CONTROL',
                       'reviewStatus': 'PENDING', 'patchStatus': 'MISSING', 'text': text,
                       'findingCount': len(findings), 'fileCount': len(chunks),
                       'rawHash': _sha(path)})
    return result


def documents(automesc, forge):
    rows = []
    for pair in automesc:
        for suffix in ('before', 'after'):
            rows.append({'id': pair['id'] + '_' + suffix, 'pairId': pair['id'],
                         'source': pair['source'], 'project': pair['project'],
                         'categoryHint': pair['categoryHint'], 'reviewStatus': 'PENDING',
                         'patchStatus': 'UNVERIFIED', 'side': suffix,
                         'text': pair[suffix]})
    for item in forge:
        rows.append({'id': item['id'], 'pairId': None, 'source': item['source'],
                     'project': item['project'], 'categoryHint': item['categoryHint'],
                     'reviewStatus': 'PENDING', 'patchStatus': 'MISSING', 'side': 'audit_source',
                     'text': item['text']})
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('候选文档 ID 重复')
    return rows


def upload_candidates(index, collection, rows, vectors):
    if not re.fullmatch(r'r1pending_[0-9a-f]{32}', collection):
        raise ValueError('待审集合名称无效')
    exists = index.request('collections/has', {'collectionName': collection})['has']
    schema = {'autoID': False, 'enableDynamicField': False, 'fields': [
        {'fieldName': 'id', 'dataType': 'VarChar', 'isPrimary': True,
         'elementTypeParams': {'max_length': '64'}},
        {'fieldName': 'vector', 'dataType': 'FloatVector',
         'elementTypeParams': {'dim': str(DIMENSION)}},
        {'fieldName': 'payload', 'dataType': 'VarChar',
         'elementTypeParams': {'max_length': '65535'}}]}
    if not exists:
        index.request('collections/create', {'collectionName': collection, 'schema': schema,
            'indexParams': [{'fieldName': 'vector', 'indexName': 'vector_idx',
                             'indexType': 'AUTOINDEX', 'metricType': 'COSINE'}],
            'params': {'consistencyLevel': 'Strong'}})
    index.request('collections/load', {'collectionName': collection})

    def read_all():
        observed = {}
        for offset in range(0, len(rows) + 256, 256):
            batch = index.request('entities/query', {'collectionName': collection, 'filter': '',
                'outputFields': ['id', 'vector', 'payload'], 'limit': 256, 'offset': offset,
                'consistencyLevel': 'Strong'})
            for item in batch:
                if item['id'] in observed:
                    raise ValueError('待审集合读回出现重复 ID')
                observed[item['id']] = (decode(item['payload']), vector32(item['vector'], DIMENSION))
            if len(batch) < 256:
                break
        return observed

    expected = {row['id']: (row, vectors[row['id']]) for row in rows}
    observed = read_all() if exists else {}
    if any(identifier not in expected or expected[identifier] != content
           for identifier, content in observed.items()):
        raise ValueError('既有待审集合与原始数据不一致，拒绝续写')
    missing = [row for row in rows if row['id'] not in observed]
    for offset in range(0, len(missing), 64):
        batch = [{'id': row['id'], 'vector': vectors[row['id']],
                  'payload': encode(row).decode('utf-8')} for row in missing[offset:offset + 64]]
        answer = index.request('entities/insert', {'collectionName': collection, 'data': batch})
        if answer.get('insertCount') != len(batch):
            raise ValueError('待审向量插入数量不完整')
    index.request('collections/load', {'collectionName': collection})
    if read_all() != expected:
        raise ValueError('待审集合读回与原始数据不一致')


def main():
    parser = argparse.ArgumentParser(description='构建待审语料并写入独立 Milvus 集合；不激活正式 D1 快照')
    parser.add_argument('--automesc-dir', required=True)
    parser.add_argument('--forge-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--model-dir', default='.local/d1-embedding-model')
    parser.add_argument('--milvus-url', default='http://127.0.0.1:29531')
    args = parser.parse_args()
    checkout = Path(args.forge_dir).resolve().parents[1]
    revision = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
    if revision != FORGE_REVISION:
        raise ValueError('FORGE-Curated 本地版本与固定修订不符')
    changes = subprocess.run(['git', '-C', str(checkout), 'status', '--porcelain', '--untracked-files=no'],
                             capture_output=True, text=True, check=True).stdout.strip()
    if changes:
        raise ValueError('FORGE-Curated 原始文件存在未提交改动')
    automesc = select_automesc(args.automesc_dir)
    forge = select_forge(args.forge_dir)
    rows = documents(automesc, forge)
    from sentence_transformers import SentenceTransformer
    encoder = load_local_encoder(SentenceTransformer, args.model_dir,
                                 decode(MODEL_MANIFEST.read_bytes()))
    encoded = encoder([row['text'] for row in rows])
    if len(encoded) != len(rows):
        raise ValueError('候选向量数量不完整')
    vectors = {row['id']: vector32([float(value) for value in vector], DIMENSION)
               for row, vector in zip(rows, encoded)}
    identity = fingerprint({'rows': rows, 'embedding': {'model': MODEL, 'revision': REVISION},
                            'vectors': vectors})
    collection = 'r1pending_' + identity[:32]
    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(root / 'automesc-selected.json', automesc)
    atomic_json(root / 'forge-selected.json', forge)
    atomic_json(root / 'vectors.json', vectors)
    receipt = {'collection': collection, 'candidateOnly': True, 'formalD1Enabled': False,
               'automescPairs': len(automesc), 'forgeVfp': len(forge), 'vectorCount': len(rows),
               'uniqueAutoMescProjects': len({row['project'] for row in automesc}),
               'embedding': {'model': MODEL, 'revision': REVISION, 'dimension': DIMENSION},
               'identity': identity}
    upload_candidates(MilvusRestIndex(args.milvus_url), collection, rows, vectors)
    atomic_json(root / 'receipt.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
