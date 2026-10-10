"""对保存候选追加本机工具和 D2 证据；不调用模型、不重写原批次。"""
import argparse
import hashlib
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from audit_workbench import assess, final_conclusion
from program_facts import extract_facts
from storage import atomic_json, decode, encode, fingerprint


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _code_identity(root):
    command = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True)
    paths = list((root / 'tools/experiment').glob('*.py'))
    paths.extend((root / 'audit-mvp/src/main/java').rglob('*.java'))
    jar = root / 'audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar'
    return {'commit': command.stdout.strip() if command.returncode == 0 else None,
            'sourceFiles': {str(path.relative_to(root)): _sha(path.read_bytes())
                            for path in paths if path.is_file()},
            'artifactHash': _sha(jar.read_bytes()) if jar.is_file() else None}


def _load_original(original):
    raw = (original / 'samples.jsonl').read_bytes()
    rows = [decode(line) for line in raw.splitlines() if line.strip()]
    if not rows:
        raise ValueError('原批次没有保存的单元')
    seen, sources = set(), {}
    for row in rows:
        source = row.get('source')
        if (not isinstance(source, str) or not source.strip() or len(source.encode()) > 1_048_576
                or row.get('sourceHash') != _sha(source.encode())):
            raise ValueError('原批次源码摘要无效或不一致')
        if (not isinstance(row.get('sampleId'), str) or not isinstance(row.get('strategy'), str)
                or not isinstance(row.get('model'), dict)):
            raise ValueError('原批次单元结构无效')
        key = (row['sampleId'], row['strategy'])
        if key in seen or row['sampleId'] in sources and sources[row['sampleId']] != row['sourceHash']:
            raise ValueError('原批次单元重复或同一目标源码发生变化')
        seen.add(key); sources[row['sampleId']] = row['sourceHash']
    plan = decode((original / 'plan.json').read_bytes()) if (original / 'plan.json').exists() else {}
    target_path = original / 'target-manifest.json'
    targets = decode(target_path.read_bytes()).get('targets', []) if target_path.exists() else []
    return rows, plan, {target['sampleId']: target for target in targets}, _sha(raw)


def _original_hashes(original):
    return {str(path.relative_to(original)): _sha(path.read_bytes())
            for path in sorted(original.rglob('*')) if path.is_file()}


def _target(row, metadata):
    source = row['source']
    start, end = metadata.get('lineStart', 1), metadata.get('lineEnd', len(source.splitlines()))
    scope = metadata.get('scope', 'FULL')
    if (scope not in ('FULL', 'FUNCTION') or type(start) is not int or type(end) is not int
            or not 1 <= start <= end <= len(source.splitlines())):
        raise ValueError('原目标审计范围无效')
    model_source = source if scope == 'FULL' else '\n'.join(source.splitlines()[start - 1:end])
    mechanism = metadata.get('mechanism') or row.get('retrieval', {}).get('targetMechanism')
    if mechanism is None and row['model'].get('hypotheses'):
        mechanism = row['model']['hypotheses'][0].get('vulnerabilityType')
    return {'sampleId': row['sampleId'], 'fullSource': source, 'source': source,
            'sourceHash': row['sourceHash'], 'fullSourceHash': row['sourceHash'],
            'modelSource': model_source, 'modelSourceHash': _sha(model_source.encode()),
            'scope': scope, 'lineStart': start, 'lineEnd': end,
            'mechanism': mechanism, 'function': metadata.get('function', ''),
            'taskKind': 'CLAIM_VALIDATION', 'researchEligible': False}


def replay(root, original_run, output_run, *, tool_runner=None, environment_resolver=None,
           code_identity=None):
    """生成不可覆盖的派生批次；缓存身份包含源码、环境和当前实现。"""
    root, original, output = Path(root).resolve(), Path(original_run).resolve(), Path(output_run).resolve()
    if output == original or original in output.parents or output in original.parents:
        raise ValueError('派生输出不能覆盖原批次或写入其内部')
    rows, plan, targets, original_hash = _load_original(original)
    original_hashes = _original_hashes(original)
    if output.exists():
        raise FileExistsError('派生目录已存在，禁止覆盖')
    if tool_runner is None:
        from audit_run import tool_runner
    configuration = None
    if environment_resolver is None:
        from tool_environment import _configuration, resolve_environment
        configuration = _configuration(root / 'config/tools.local.properties')
        environment_resolver = lambda source: resolve_environment(source, configuration)
    identity = code_identity if code_identity is not None else _code_identity(root)
    identity_hash = fingerprint(identity)
    provenance = {'originalBatchId': plan.get('batchId', original.name),
                  'originalSamplesSha256': original_hash, 'originalRun': str(original),
                  'originalFileHashes': original_hashes,
                  'codeIdentity': identity, 'codeIdentityHash': identity_hash,
                  'kind': 'SAVED_CANDIDATE_TOOL_REPLAY', 'newModelRequests': 0,
                  'inputScope': '原始模型候选核验，未重新执行清理后的模型发现实验'}
    output.mkdir(parents=True)
    manifest = {'schemaVersion': '1', 'status': 'RUNNING', 'startedAt': datetime.now(timezone.utc).isoformat(),
                'provenance': provenance, 'plannedUnits': len(rows), 'completedUnits': 0}
    atomic_json(output / 'manifest.json', manifest)
    cache, collected, tool_executions = {}, [], 0
    try:
        with (output / 'samples.jsonl').open('xb') as saved:
            for row in rows:
                target = _target(row, targets.get(row['sampleId'], {}))
                environment = environment_resolver(target['fullSource'])
                if not isinstance(environment, dict) or not isinstance(environment.get('configHash'), str):
                    raise ValueError('工具环境缺少可绑定的配置摘要')
                target['_toolEnvironment'] = environment
                if configuration is not None:
                    target['_toolConfiguration'] = configuration
                key = fingerprint({'sourceHash': target['sourceHash'], 'environmentHash': environment['configHash'],
                                   'codeIdentityHash': identity_hash})
                cached = key in cache
                if not cached:
                    try:
                        tools = tool_runner(root, target, 'real')
                        if (not isinstance(tools, list) or not tools
                                or any(not isinstance(tool, dict) for tool in tools)):
                            raise ValueError('工具输出缺失')
                    except (ValueError, OSError, subprocess.TimeoutExpired):
                        tools = [{'engine': 'SLITHER', 'status': 'PROCESS_ERROR', 'issues': [],
                                  'sourceHash': target['sourceHash'], 'errorCategory': 'TOOL_EXECUTION_FAILED'}]
                    cache[key] = tools
                    tool_executions += 1
                    atomic_json(output / ('tool-' + key + '.json'),
                                {'sourceHash': target['sourceHash'], 'environment': environment, 'tools': tools})
                tools = cache[key]
                facts = extract_facts(target['fullSource'])
                try:
                    d2 = assess(row['model'], facts, tools, target['fullSource'], target=target)
                except (ValueError, KeyError, TypeError):
                    d2 = {'schemaVersion': '2', 'verdict': 'UNKNOWN', 'assessments': [],
                          'errorCategory': 'D2_EXECUTION_ERROR'}
                failed = (row['model'].get('status') != 'COMPLETED' or bool(d2.get('errorCategory'))
                          or any(t.get('status') != 'OK' for t in tools))
                derived = {**row, 'tools': tools, 'd2': d2, 'facts': facts,
                           'pipelineVersion': 'r2-derived-v1', 'pipelineStatus': 'FAILED' if failed else 'COMPLETED',
                           'conclusion': final_conclusion(row['model'], d2, failed, 'real'),
                           'environment': environment, 'toolCacheHit': cached, 'newModelRequests': 0,
                           'provenance': {**provenance, 'originalUnitHash': fingerprint(row), 'toolCacheKey': key},
                           'researchEligible': False}
                saved.write(encode(derived) + b'\n'); saved.flush()
                collected.append(derived)
                manifest['completedUnits'] = len(collected)
                atomic_json(output / 'manifest.json', manifest)
        if _original_hashes(original) != original_hashes:
            raise ValueError('重放期间原批次被改变，结果不能封口')
        if code_identity is None and _code_identity(root) != identity:
            raise ValueError('重放期间实现或构建产物变化，结果不能封口')
        summary = {'schemaVersion': '1', 'units': len(collected),
                   'targets': len({row['sampleId'] for row in collected}), 'toolExecutions': tool_executions,
                   'newModelRequests': 0, 'researchEligible': False, 'provenance': provenance,
                   'toolStatuses': dict(Counter(t.get('status', 'UNKNOWN') for row in collected for t in row['tools'])),
                   'd2Verdicts': dict(Counter(row['d2']['verdict'] for row in collected)),
                   'factsStatuses': dict(Counter(row['facts']['status'] for row in
                       {item['sampleId']: item for item in collected}.values())),
                   'pathStates': dict(Counter(a.get('pathEvidence', {}).get('status', 'UNKNOWN')
                       for row in collected for a in row['d2']['assessments'])),
                   'hypotheses': sum(len(row['model'].get('hypotheses', [])) for row in collected)}
        atomic_json(output / 'summary.json', summary)
        report = ('# 保存候选的工具与D2派生重放\n\n'
                  f"原批次：`{provenance['originalBatchId']}`；单元 {summary['units']}，唯一目标 {summary['targets']}。\n\n"
                  f"工具执行 {tool_executions} 次；新增模型请求 0。\n\n"
                  f"工具状态：{summary['toolStatuses']}。D2：{summary['d2Verdicts']}。\n\n"
                  '原模型输出与usage保留，原批次samples摘要封口前再次核对。'
                  '本报告仅评价保存候选的核验，不是清理输入后的模型发现实验；研究资格未验证。\n')
        (output / 'REPORT.md').write_text(report, encoding='utf-8')
        manifest.update(status='COMPLETED', finishedAt=datetime.now(timezone.utc).isoformat(),
                        outputHashes={name: _sha((output / name).read_bytes()) for name in
                                      ('samples.jsonl', 'summary.json', 'REPORT.md')})
        atomic_json(output / 'manifest.json', manifest)
        return summary
    except BaseException:
        manifest.update(status='INTERRUPTED', completedUnits=len(collected))
        atomic_json(output / 'manifest.json', manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description='零模型请求重放已保存的候选，原批次保持只读')
    parser.add_argument('--original-run', required=True)
    parser.add_argument('--output-run', required=True)
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    result = replay(args.root, args.original_run, args.output_run)
    print(encode(result).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
