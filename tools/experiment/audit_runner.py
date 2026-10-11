"""保存候选的离线静态审计入口；与工作台共用编译、工具和 D2 接缝。"""
import argparse
import hashlib
import subprocess
from pathlib import Path

from audit_workbench import assess
from compilation_runtime import prepare_compilation
from compiler_facts import extract_compiler_facts, load_bound_compilation
from d2_verify import _unknown_result
from program_facts import extract_facts
from storage import decode, encode


def analyze_saved(root, target, hypotheses):
    """模型假设只读复用；失败返回未知六义务并保留独立失败状态。"""
    root = Path(root).resolve()
    source = target.get('fullSource', target.get('source'))
    if not isinstance(source, str) or not isinstance(hypotheses, list) or any(
            not isinstance(hypothesis, dict) for hypothesis in hypotheses):
        raise ValueError('保存候选或源码结构无效')
    source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if any(target.get(key, source_hash) != source_hash for key in ('sourceHash', 'fullSourceHash')):
        raise ValueError('保存候选目标的源码摘要不一致')
    facts = extract_facts(source)
    result = {'facts': facts, 'tools': [], 'compiledFacts': None,
              'newModelRequests': 0, 'researchEligible': False, 'sourceHash': source_hash}
    model = {'schemaVersion': '2', 'status': 'COMPLETED', 'hypotheses': hypotheses,
             'fixture': True, 'inputTokens': None, 'outputTokens': None}
    bound = {**target, 'fullSource': source, 'sourceHash': source_hash,
             'candidateContracts': sorted({hypothesis.get('contract') for hypothesis in hypotheses
                                          if isinstance(hypothesis.get('contract'), str)})}
    try:
        manifest = prepare_compilation(root, bound)
        bundle = load_bound_compilation(manifest, root)
        from bound_slither import analyze_bound
        tools = [analyze_bound(manifest, root=root)]
        result.update(compilerManifest=manifest, compiledFacts=extract_compiler_facts(bundle), tools=tools)
        result['d2'] = assess(model, facts, tools, source, target=target if 'scope' in target else None,
                              compilation_manifest=manifest, root=root)
        result['status'] = ('FAILED' if result['d2']['status'] == 'FAILED'
                            or any(tool['status'] != 'OK' for tool in tools) else 'COMPLETED')
    except (ValueError, OSError, TypeError, KeyError, subprocess.TimeoutExpired) as error:
        result.update(status='FAILED', errorCategory='STATIC_ANALYSIS_FAILED', reason=str(error),
            d2={'schemaVersion': '2', 'status': 'FAILED', 'verdict': 'UNKNOWN',
                'assessments': [{**_unknown_result('静态证据缺失或绑定失败：' + str(error)),
                    'status': 'FAILED', 'hypothesisIndex': index} for index, _ in enumerate(hypotheses)]})
    return result


def main():
    parser = argparse.ArgumentParser(description='零模型请求核验保存候选的防御静态属性')
    parser.add_argument('--source', required=True)
    parser.add_argument('--hypotheses', required=True)
    parser.add_argument('--manifest', help='可选的完整依赖编译清单')
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    source = Path(args.source).read_text(encoding='utf-8')
    hypotheses = decode(Path(args.hypotheses).read_bytes())
    target = {'fullSource': source}
    if args.manifest:
        target['compilerManifest'] = args.manifest
    result = analyze_saved(args.root, target, hypotheses)
    print(encode(result).decode())
    return int(result['status'] == 'FAILED')


if __name__ == '__main__':
    raise SystemExit(main())
