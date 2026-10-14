"""真实修复双版本最终裁决验收；零模型，原候选和标签只读。"""
import argparse
import json
from pathlib import Path

from audit_runner import analyze_saved
from compiler_facts import load_bound_compilation
from storage import atomic_json, fingerprint, read_artifact


def validate_fix_pair(root, before_manifest, before_candidate, after_manifest, after_candidate):
    """比较显式登记的同一属性；局部 PROVED 或义务 REFUTED 不构成最终通过。"""
    before_hash, after_hash = fingerprint(before_candidate), fingerprint(after_candidate)
    keys = ['contract', 'function', 'vulnerabilityType', 'riskOperation']
    if any(before_candidate.get(key) != after_candidate.get(key) for key in keys):
        raise ValueError('跨版本候选的合约、入口或属性关系不一致')
    results = {}
    for name, manifest, candidate in [('before', before_manifest, before_candidate),
                                      ('after', after_manifest, after_candidate)]:
        bundle = load_bound_compilation(manifest, root)
        source = bundle['input']['sources'][bundle['targetSourceUnit']]['content']
        run = analyze_saved(root, {'fullSource': source, 'sourceHash': bundle['sourceHash'],
                                   'compilerManifest': manifest}, [candidate])
        assessment = run['d2']['assessments'][0]
        results[name] = {'sourceHash': bundle['sourceHash'], 'candidateHash': fingerprint(candidate),
            'receiptDigest': bundle['receiptDigest'], 'status': run['status'],
            'verdict': assessment['verdict'], 'localProofStatus': assessment.get('candidateProof', {}).get('status'),
            'proofGaps': assessment.get('candidateProof', {}).get('proofScope', {}).get('gaps', []),
            'assessment': assessment, 'toolStatuses': [tool['status'] for tool in run['tools']]}
    unchanged = before_hash == fingerprint(before_candidate) and after_hash == fingerprint(after_candidate)
    passed = (unchanged and results['before']['sourceHash'] != results['after']['sourceHash']
              and results['before']['status'] == results['after']['status'] == 'COMPLETED'
              and results['before']['verdict'] == 'SUPPORTED' and results['after']['verdict'] == 'REFUTED')
    return {'schemaVersion': 'real-fix-pair-1', 'status': 'VERIFIED' if passed else 'PARTIAL',
        'acceptancePassed': passed, 'candidatesUnchanged': unchanged, **results,
        'property': {key: before_candidate.get(key) for key in keys}, 'newModelRequests': 0,
        'researchEligible': False, 'independentReviewer': None,
        'limitations': ['来源和候选独立审核另行验收', '不得把局部保护义务当作漏洞候选反驳']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    for name in ['before-manifest', 'before-candidate', 'after-manifest', 'after-candidate', 'output']:
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = root / args.output
    if output.exists(): raise FileExistsError('不能覆盖已有修复验收原件')
    before = json.loads(read_artifact(root / args.before_candidate))
    after = json.loads(read_artifact(root / args.after_candidate))
    result = validate_fix_pair(root, args.before_manifest, before, args.after_manifest, after)
    atomic_json(output, result)
    print(json.dumps({'status': result['status'], 'acceptancePassed': result['acceptancePassed'],
                      'before': result['before']['verdict'], 'after': result['after']['verdict'],
                      'newModelRequests': 0}, ensure_ascii=False))
    return 0 if result['acceptancePassed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
