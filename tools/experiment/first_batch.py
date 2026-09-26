"""固定首批候选源码，执行分组隔离；待审材料不会进入正式快照。"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from s3 import _tokens, audit_lineage
from storage import atomic_json


SPLITS = {'knowledge', 'development', 'validation', 'excluded'}
SOURCE_URL = re.compile(r'https://github\.com/([^/]+)/([^/]+)/blob/([0-9a-f]{40})/(.+)')
IDENTIFIER = re.compile(r'[A-Za-z0-9-]+')


def _entries(intake, assignment):
    if not isinstance(intake, dict) or intake.get('schemaVersion') != '1' or not isinstance(intake.get('cases'), list):
        raise ValueError('候选清单无效')
    if not isinstance(assignment, dict) or assignment.get('schemaVersion') != '1' or not isinstance(assignment.get('assignments'), list):
        raise ValueError('分配清单无效')
    cases = {}
    for case in intake['cases']:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or not IDENTIFIER.fullmatch(case['id']) or case['id'] in cases:
            raise ValueError('候选 ID 无效或重复')
        if not SOURCE_URL.fullmatch(case.get('sourceUrl', '')) or not re.fullmatch('[0-9a-f]{64}', case.get('sourceSha256', '')):
            raise ValueError('候选固定源码无效')
        for field in ('projectId', 'eventId', 'direction'):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError('候选谱系字段缺失')
        cases[case['id']] = case
    assignments = {}
    for row in assignment['assignments']:
        if not isinstance(row, dict) or row.get('id') in assignments or row.get('split') not in SPLITS or not isinstance(row.get('reason'), str) or not row['reason'].strip():
            raise ValueError('分配条目无效或重复')
        assignments[row['id']] = row
    if not cases or set(cases) != set(assignments):
        raise ValueError('分配必须精确覆盖候选清单')
    return cases, assignments


def _source_path(root, source_dir, identifier):
    relative = Path(source_dir) / (identifier + '.sol')
    if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative):
        raise ValueError('源码目录无效')
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('源码目录越界')
    return relative.as_posix(), path


def _evidence(root, identifier, group, kind, item):
    if not isinstance(item, dict) or set(item) != {'url', 'path', 'sha256'} or not item['url'].startswith('https://') or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
        raise ValueError(identifier + ' 原件登记无效')
    relative = Path(item['path'])
    if relative.is_absolute() or '..' in relative.parts or '\\' in item['path']:
        raise ValueError(identifier + ' 原件路径越界')
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError(identifier + ' 原件缺失')
    if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError(identifier + ' 原件摘要不符')
    return {'id': identifier + '-' + kind.lower(), 'kind': kind, 'path': relative.as_posix(),
            'sha256': item['sha256'], 'groupId': group}


def _raw_url(url):
    match = SOURCE_URL.fullmatch(url)
    if not match:
        raise ValueError('仅接受固定 GitHub 提交的源码 URL')
    return 'https://raw.githubusercontent.com/' + '/'.join(match.groups())


def fetch_sources(intake, assignment, root, source_dir):
    cases, _ = _entries(intake, assignment)
    verified = []
    for identifier, case in sorted(cases.items()):
        _, path = _source_path(root, source_dir, identifier)
        if path.exists():
            raw = path.read_bytes()
        else:
            completed = subprocess.run(['curl', '-fLsS', '--retry', '3', '--max-time', '30',
                                        _raw_url(case['sourceUrl'])], capture_output=True, timeout=120)
            if completed.returncode != 0:
                raise RuntimeError(identifier + ' 固定源码下载失败')
            raw = completed.stdout
            if len(raw) > 2_000_000:
                raise ValueError('源码超过单文件上限')
        if hashlib.sha256(raw).hexdigest() != case['sourceSha256']:
            raise ValueError(identifier + ' 源码摘要不符')
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        verified.append({'id': identifier, 'bytes': len(raw), 'sha256': case['sourceSha256']})
    return verified


def prepare(intake, assignment, root, source_dir):
    cases, assignments = _entries(intake, assignment)
    sources, samples, excluded, raw_by_id = [], [], [], {}
    root = Path(root)
    for identifier, case in sorted(cases.items()):
        relative, path = _source_path(root, source_dir, identifier)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != case['sourceSha256']:
            raise ValueError(identifier + ' 源码摘要不符')
        raw_by_id[identifier] = raw
        split = assignments[identifier]['split']
        if split == 'excluded':
            excluded.append(identifier)
            continue
        revision = SOURCE_URL.fullmatch(case['sourceUrl']).group(3)
        artifacts = [{'id': identifier + '-source', 'kind': 'SOURCE', 'path': relative,
                      'sha256': case['sourceSha256'], 'groupId': case['eventId']}]
        evidence_status = {}
        for kind in ('REPORT', 'PATCH'):
            item = assignments[identifier].get(kind.lower() + 'Evidence')
            if item:
                artifacts.append(_evidence(root, identifier, case['eventId'], kind, item))
                evidence_status[kind] = 'VERIFIED'
            else:
                evidence_status[kind] = 'PENDING' if case.get(kind.lower() + 'Url') else 'UNAVAILABLE'
        sources.append({'id': identifier, 'url': case['sourceUrl'], 'revision': revision,
                        'licenseStatus': 'PENDING', 'license': None, 'sourceStatus': 'VERIFIED',
                        'reportStatus': evidence_status['REPORT'], 'patchStatus': evidence_status['PATCH']})
        samples.append({'id': identifier, 'sourceId': identifier, 'path': relative,
                        'sourceHash': case['sourceSha256'], 'split': split,
                        'projectId': case['projectId'], 'eventId': case['eventId'],
                        'patchPairId': case['eventId'], 'cloneGroups': [],
                        'originType': 'REAL_PATCH' if evidence_status['PATCH'] == 'VERIFIED' else 'REAL_UNPAIRED',
                        'labelStatus': 'PENDING', 'artifacts': artifacts})
    if not samples:
        raise ValueError('分配后没有待审研究样本')
    ledger = {'schemaVersion': '1', 'sources': sources, 'samples': samples, 'edges': []}
    result = audit_lineage(ledger, root)
    excluded_overlap = []
    token_sets = {identifier: _tokens(raw) for identifier, raw in raw_by_id.items()}
    for left in excluded:
        for right in sorted(set(raw_by_id) - set(excluded)):
            a, b = token_sets[left], token_sets[right]
            score = len(a & b) / len(a | b) if a | b else 1.0
            if cases[left]['sourceSha256'] == cases[right]['sourceSha256'] or score >= .85:
                excluded_overlap.append({'excluded': left, 'active': right, 'jaccard': round(score, 6)})
    report = dict(result, excluded=excluded, assignments={row['id']: assignments[row['id']]['split'] for row in samples},
                  excludedOverlapCandidates=excluded_overlap,
                  readyForFormalSnapshot=False, note='源码分组已检查；报告、修复和独立标签仍待逐项确认，不得激活正式知识快照')
    return ledger, report


def main():
    parser = argparse.ArgumentParser(description='首批真实候选的固定源码获取与离线分组隔离')
    parser.add_argument('command', choices=('fetch', 'audit'))
    parser.add_argument('--intake', required=True)
    parser.add_argument('--assignment', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--source-dir', default='.local/first-batch/sources')
    parser.add_argument('--output-dir', default='.local/first-batch')
    args = parser.parse_args()
    intake = json.loads(Path(args.intake).read_text(encoding='utf-8'))
    assignment = json.loads(Path(args.assignment).read_text(encoding='utf-8'))
    if args.command == 'fetch':
        result = {'verified': fetch_sources(intake, assignment, args.root, args.source_dir)}
    else:
        ledger, result = prepare(intake, assignment, args.root, args.source_dir)
        output = Path(args.root) / args.output_dir
        output.mkdir(parents=True, exist_ok=True)
        atomic_json(output / 'ledger.json', ledger)
        atomic_json(output / 'leakage-report.json', result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get('ok', True) else 2


if __name__ == '__main__':
    raise SystemExit(main())
