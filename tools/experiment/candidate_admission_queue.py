"""为待审向量生成逐项证据缺口清单，不执行自动转正。"""
import argparse
import hashlib
from pathlib import Path

from storage import atomic_json, decode, fingerprint


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build_queue(automesc, forge):
    if not isinstance(automesc, list) or not isinstance(forge, list):
        raise ValueError('候选清单格式无效')
    entries = []
    seen = set()
    for row in sorted(automesc + forge, key=lambda item: item['id']):
        identifier = row['id']
        if identifier in seen or row.get('reviewStatus') != 'PENDING':
            raise ValueError('候选 ID 重复或审核状态被改动')
        seen.add(identifier)
        common = {'candidateId': identifier, 'source': row['source'],
                  'sourceRevision': row['sourceRevision'], 'projectHint': row['project'],
                  'categoryHint': row['categoryHint'], 'decision': 'PENDING',
                  'lineageGroupId': None, 'reviewer': None}
        if row['source'] == 'AutoMESC' and row.get('patchStatus') == 'UNVERIFIED':
            entry = {**common, 'sourceLocator': row['commitUrl'], 'commit': row['commit'],
                     'file': row['file'], 'beforeSnippetHash': _hash(row['before']),
                     'afterSnippetHash': _hash(row['after']), 'vectorCount': 2,
                     'missingEvidence': ['INDEPENDENT_REPORT', 'FULL_SOURCE_BEFORE',
                                         'FULL_SOURCE_AFTER', 'SECURITY_PATCH_REVIEW',
                                         'LINEAGE_GROUP', 'CONDITION_WITNESS']}
        elif row['source'] == 'FORGE-Curated' and row.get('patchStatus') == 'MISSING':
            entry = {**common, 'sourceLocator': row['reportFile'],
                     'rawHash': row['rawHash'], 'candidateTextHash': _hash(row['text']),
                     'findingCount': row['findingCount'], 'vectorCount': 1,
                     'missingEvidence': ['ORIGINAL_REPORT', 'FULL_SOURCE_VERSION', 'PATCH',
                                         'SECURITY_PATCH_REVIEW', 'LINEAGE_GROUP',
                                         'CONDITION_WITNESS']}
        else:
            raise ValueError('候选来源或补丁状态无效')
        entries.append(entry)
    report = {'schemaVersion': '1', 'candidateOnly': True,
              'sourceHash': fingerprint({'automesc': automesc, 'forge': forge}),
              'summary': {'candidateGroups': len(entries), 'admittedGroups': 0,
                          'pendingGroups': len(entries),
                          'candidateVectors': sum(row['vectorCount'] for row in entries),
                          'admittedVectors': 0}, 'entries': entries}
    return {**report, 'queueHash': fingerprint(report)}


def main():
    parser = argparse.ArgumentParser(description='生成待审向量逐项证据缺口清单')
    parser.add_argument('--candidate-dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.candidate_dir)
    automesc = decode((root / 'automesc-selected.json').read_bytes())
    forge = decode((root / 'forge-selected.json').read_bytes())
    report = build_queue(automesc, forge)
    receipt = decode((root / 'receipt.json').read_bytes())
    if (receipt.get('candidateOnly') is not True or receipt.get('formalD1Enabled') is not False
            or receipt.get('vectorCount') != report['summary']['candidateVectors']
            or receipt.get('automescPairs') != len(automesc)
            or receipt.get('forgeVfp') != len(forge)):
        raise ValueError('待审集合收据与逐项清单不一致')
    atomic_json(Path(args.output), report)
    print(f"待审 {report['summary']['candidateGroups']} 组 / "
          f"{report['summary']['candidateVectors']} 条向量；自动转正 0 组")


if __name__ == '__main__':
    main()
