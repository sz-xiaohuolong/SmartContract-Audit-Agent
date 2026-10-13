"""只读诊断登记案例的编译闭包与有限证明缺口；不调用模型或执行最终裁决。"""
import argparse
import copy
import json
import subprocess
from pathlib import Path

from candidate_proofs import prove_candidate
from compiler_facts import load_bound_compilation
from reentrancy_proofs import prove_reentrancy
from storage import fingerprint, read_artifact


def check_case(root, manifest, candidate):
    """保持原候选，实际重编译；成功只说明收据与局部证明可读取。"""
    original = copy.deepcopy(candidate)
    candidate_hash = fingerprint(original)
    report = {'schemaVersion': 'real-case-check-1', 'status': 'PARTIAL',
              'candidateHash': candidate_hash, 'candidateUnchanged': True,
              'newModelRequests': 0, 'researchEligible': False, 'verdict': 'UNKNOWN',
              'limitations': ['此入口只诊断编译与局部证明，不执行工具双收据或最终 D2 裁决',
                              '未执行部署、代理初始化或外部依赖前提的 EVM 见证',
                              '知识侧真实案例不得作为独立泛化测试']}
    mechanism = original.get('vulnerabilityType') if isinstance(original, dict) else None
    if mechanism not in ('ACCESS_CONTROL', 'REENTRANCY'):
        report.update(status='FAILED', errorCategory='UNSUPPORTED_MECHANISM', error='候选机制不在诊断范围内')
        return report
    try:
        bundle = load_bound_compilation(manifest, root)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        report.update(status='FAILED', errorCategory='COMPILATION_BINDING_FAILED', error=str(error))
        return report
    report['compilation'] = {key: bundle[key] for key in (
        'manifestDigest', 'receiptDigest', 'environmentHash', 'sourceHash',
        'targetSourceUnit', 'targetContract', 'compilerVersion', 'entryGaps')}
    report['compilation']['status'] = bundle['verificationStatus']
    report['sourceClosure'] = [{'sourceUnit': unit['sourceUnit'], 'path': unit['path'], 'sha256': unit['sha256']}
                              for _, unit in sorted(bundle['units'].items())]
    report['constructors'] = copy.deepcopy(bundle['constructors'])
    report['entries'] = copy.deepcopy(bundle['entries'])
    try:
        solver = prove_candidate if mechanism == 'ACCESS_CONTROL' else prove_reentrancy
        proof = solver(bundle, original)
        if fingerprint(original) != candidate_hash:
            raise ValueError('诊断期间候选发生修改，证明不接纳')
        if not isinstance(proof, dict) or proof.get('status') not in ('FAILED', 'UNKNOWN', 'PROVED', 'COUNTEREXAMPLE'):
            raise ValueError('有限证明结果结构无效')
        report['candidateProof'] = proof
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
        report.update(status='FAILED', errorCategory='CANDIDATE_PROOF_FAILED', error=str(error))
    report['candidateUnchanged'] = fingerprint(original) == candidate_hash and fingerprint(candidate) == candidate_hash
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='项目根目录')
    parser.add_argument('--manifest', required=True, help='登记编译清单')
    parser.add_argument('--candidate', required=True, help='固定候选 JSON，支持 gzip 原件')
    parser.add_argument('--output', required=True, help='不存在的新诊断 JSON 文件；禁止覆盖')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    candidate_path = Path(args.candidate)
    candidate_path = candidate_path if candidate_path.is_absolute() else root / candidate_path
    candidate = json.loads(read_artifact(candidate_path))
    report = check_case(root, args.manifest, candidate)
    output = Path(args.output)
    output = output if output.is_absolute() else root / output
    with output.open('x', encoding='utf-8') as saved:
        json.dump(report, saved, ensure_ascii=False, indent=2)
        saved.write('\n')
    print(json.dumps({'status': report['status'], 'verdict': report['verdict'],
                      'output': str(output), 'newModelRequests': 0}, ensure_ascii=False))
    return 1 if report['status'] == 'FAILED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
