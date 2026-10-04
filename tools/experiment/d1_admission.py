"""用固定原件和外部审计裁决形成首版知识库准入清单。"""
import argparse
import hashlib
import json
from pathlib import Path

from s3 import audit_lineage
from storage import atomic_json, decode, fingerprint


def _verified_file(root, artifact):
    relative = Path(artifact['path'])
    candidate = Path(root) / relative
    target = candidate.resolve()
    if (relative.is_absolute() or '..' in relative.parts or not target.is_relative_to(Path(root).resolve())
            or not target.is_file() or candidate.is_symlink()):
        raise ValueError('审核原件路径无效')
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact['sha256']:
        raise ValueError('审核原件摘要不符')
    return raw


def admit_candidates(candidate, decisions, root):
    if (not isinstance(decisions, dict) or decisions.get('schemaVersion') != '1'
            or decisions.get('candidateLedgerHash') != fingerprint(candidate)):
        raise ValueError('候选清单版本与准入裁决不一致')
    entries = decisions.get('admissions')
    if not isinstance(entries, list) or not entries:
        raise ValueError('准入裁决为空')
    original_audit = audit_lineage(candidate, root)
    if not original_audit['ok']:
        raise ValueError('候选清单存在谱系冲突')
    candidates = {row['id']: row for row in candidate['samples']}
    sources = {row['id']: row for row in candidate['sources']}
    ids = [entry.get('sampleId') for entry in entries if isinstance(entry, dict)]
    if len(ids) != len(entries) or len(set(ids)) != len(ids) or any(value not in candidates for value in ids):
        raise ValueError('准入样本 ID 重复或未知')
    admitted_sources, admitted_samples, pairs = [], [], []
    for entry in entries:
        row = dict(candidates[entry['sampleId']])
        source = dict(sources[row['sourceId']])
        if (entry.get('sourceHash') != row['sourceHash'] or entry.get('split') not in ('knowledge', 'validation')
                or entry.get('vulnerabilityType') not in ('ACCESS_CONTROL', 'REENTRANCY')
                or type(entry.get('vulnerabilityLine')) is not int
                or entry.get('reviewerType') != 'INDEPENDENT'
                or not isinstance(entry.get('reviewer'), str) or not entry['reviewer'].strip()
                or entry.get('reviewVersion') != next(
                    (item['sha256'] for item in row['artifacts'] if item['kind'] == 'REPORT'), None)):
            raise ValueError('固定源码、外部审计或漏洞位置裁决不完整')
        if any(source[kind + 'Status'] != 'VERIFIED' for kind in ('source', 'report', 'patch')):
            raise ValueError('准入样本的源码、报告或补丁待审')
        artifacts = {item['kind']: item for item in row['artifacts']}
        if len(artifacts) != len(row['artifacts']) or not {'SOURCE', 'REPORT', 'PATCH'} <= artifacts.keys():
            raise ValueError('准入原件缺失或重复')
        license_record = entry.get('licenseEvidence')
        if (not isinstance(license_record, dict) or license_record.get('license') != 'MIT'
                or not isinstance(license_record.get('path'), str)
                or not isinstance(license_record.get('sha256'), str)):
            raise ValueError('许可证原件未固定')
        raw_license = _verified_file(root, license_record)
        if b'SPDX-License-Identifier: MIT' not in raw_license and b'MIT License' not in raw_license:
            raise ValueError('许可证原件不支持 MIT 声明')
        source.update(license='MIT', licenseStatus='VERIFIED')
        row.update(split=entry['split'], labelStatus='REVIEWED',
                   vulnerabilityType=entry['vulnerabilityType'], vulnerabilityLine=entry['vulnerabilityLine'],
                   truthReviewerType='INDEPENDENT', truthReviewer=entry['reviewer'],
                   truthReviewVersion=entry['reviewVersion'],
                   truthEvidence=[artifacts['REPORT']['id'], artifacts['PATCH']['id']])
        admitted_sources.append(source)
        admitted_samples.append(row)
        if row['split'] == 'knowledge':
            pair = entry.get('pair')
            if not isinstance(pair, dict) or pair.get('sampleId') != row['id']:
                raise ValueError('知识补丁对裁决缺失')
            pair = dict(pair, reviewed=True, reviewerType='INDEPENDENT', reviewer=entry['reviewer'],
                        evidence=row['truthEvidence'])
            pairs.append(pair)
        elif entry.get('pair') is not None:
            raise ValueError('检测样本不得进入知识配对')
    admitted = {'schemaVersion': '1', 'sources': admitted_sources, 'samples': admitted_samples,
                'edges': [edge for edge in candidate['edges'] if edge['left'] in ids and edge['right'] in ids]}
    audit = audit_lineage(admitted, root)
    if not audit['ok'] or audit['pendingSamples']:
        raise ValueError('首版准入后仍有泄漏或待审样本')
    return admitted, pairs, dict(audit, excludedFromV1=sorted(set(candidates) - set(ids)),
                                 note='仅对外部原始审计证实的漏洞与真实修复对准入；目标—案例适用性仍须独立审核')


def main():
    parser = argparse.ArgumentParser(description='从固定外部审计原件生成首版正式准入清单')
    for name in ('candidate-ledger', 'decisions', 'root', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        ledger, pairs, report = admit_candidates(decode(Path(args.candidate_ledger).read_bytes()),
                                                  decode(Path(args.decisions).read_bytes()), Path(args.root))
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        atomic_json(output / 'ledger.json', ledger)
        atomic_json(output / 'pairs.json', pairs)
        atomic_json(output / 'leakage-report.json', report)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, '正式准入拒绝：' + str(error) + '\n')
    print(json.dumps({'admitted': len(ledger['samples']), 'knowledgePairs': len(pairs),
                      'pending': len(report['pendingSamples']), 'lineageHash': report['ledgerHash']},
                     ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
