"""对保存候选追加本机工具和 D2 证据；不调用模型、不重写原批次。"""
import argparse
import hashlib
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from audit_workbench import assess, final_conclusion
from compiler_facts import CompilationBindingError, extract_compiler_facts, load_bound_compilation
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


def _input_blocked(row, plan):
    """缺源码只接受冻结计划登记的零请求输入阻断，不能放宽普通源码校验。"""
    eligibility = plan.get('inputEligibility', {}).get(row.get('sampleId'), {})
    source_hash = row.get('sourceHash')
    d2 = row.get('d2', {})
    return (isinstance(eligibility, dict) and eligibility.get('runnable') is False
            and 'source' not in row and isinstance(source_hash, str) and len(source_hash) == 64
            and all(character in '0123456789abcdef' for character in source_hash)
            and plan.get('sourceHashes', {}).get(row.get('sampleId')) == source_hash
            and row.get('errorCategory') == 'EVALUATION_INPUT_BLOCKED'
            and row.get('inputReason') == eligibility.get('reason')
            and row.get('status') == 'FAILED' and row.get('pipelineStatus') == 'FAILED'
            and row.get('prediction') == 'UNKNOWN' and row.get('modelPrediction') == 'UNKNOWN'
            and row.get('conclusion') == 'UNRESOLVED'
            and type(row.get('requestAttempts')) is int and row['requestAttempts'] == 0
            and row.get('model') == {} and row.get('inputTokens') is None and row.get('outputTokens') is None
            and row.get('tools') == [] and isinstance(d2, dict) and d2.get('verdict') == 'UNKNOWN'
            and d2.get('assessments') == [] and d2.get('errorCategory') == 'EVALUATION_INPUT_BLOCKED')


def _load_original(original):
    from storage import read_artifact
    raw = read_artifact(original / 'samples.jsonl')
    rows = [decode(line) for line in raw.splitlines() if line.strip()]
    if not rows:
        raise ValueError('原批次没有保存的单元')
    plan = decode((original / 'plan.json').read_bytes()) if (original / 'plan.json').exists() else {}
    if (not isinstance(plan, dict) or not isinstance(plan.get('inputEligibility', {}), dict)
            or not isinstance(plan.get('sourceHashes', {}), dict)):
        raise ValueError('原批次计划结构无效')
    seen, sources = set(), {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('sampleId'), str) or not isinstance(row.get('strategy'), str)
                or not isinstance(row.get('model'), dict)):
            raise ValueError('原批次单元结构无效')
        blocked = _input_blocked(row, plan)
        if row.get('errorCategory') == 'EVALUATION_INPUT_BLOCKED' and not blocked:
            raise ValueError('原批次输入阻断身份无效或与冻结计划不一致')
        source = row.get('source')
        if not blocked and (not isinstance(source, str) or not source.strip() or len(source.encode()) > 1_048_576
                or row.get('sourceHash') != _sha(source.encode())):
            raise ValueError('原批次源码摘要无效或不一致')
        key = (row['sampleId'], row['strategy'])
        if key in seen or row['sampleId'] in sources and sources[row['sampleId']] != row['sourceHash']:
            raise ValueError('原批次单元重复或同一目标源码发生变化')
        seen.add(key); sources[row['sampleId']] = row['sourceHash']
    target_path = original / 'target-manifest.json'
    targets = decode(target_path.read_bytes()).get('targets', []) if target_path.exists() else []
    return rows, plan, {target['sampleId']: target for target in targets}, _sha(raw)


def _original_hashes(original):
    from storage import read_artifact
    result = {}
    for path in sorted(original.rglob('*')):
        if not path.is_file():
            continue
        logical = path.with_suffix('') if path.suffix == '.gz' and path.with_suffix('').suffix in ('.jsonl', '.json', '.csv') else path
        result[str(logical.relative_to(original))] = _sha(read_artifact(logical))
    return result


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
    target = {'sampleId': row['sampleId'], 'fullSource': source, 'source': source,
            'sourceHash': row['sourceHash'], 'fullSourceHash': row['sourceHash'],
            'modelSource': model_source, 'modelSourceHash': _sha(model_source.encode()),
            'scope': scope, 'lineStart': start, 'lineEnd': end,
            'mechanism': mechanism, 'function': metadata.get('function', ''),
            'taskKind': 'CLAIM_VALIDATION', 'researchEligible': False}
    discovery = row.get('retrieval', {}).get('discoveryCompilation')
    if discovery is not None:
        target['discoveryCompilation'] = discovery
    return target


def replay(root, original_run, output_run, *, tool_runner=None, environment_resolver=None,
           compilation_resolver=None, code_identity=None):
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
        configuration = (_configuration(root / 'config/tools.local.properties')
                         if any(not _input_blocked(row, plan) for row in rows) else {})
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
    candidate_contracts = {}
    for row in rows:
        candidate_contracts.setdefault(row['sampleId'], set()).update(
            hypothesis.get('contract') for hypothesis in row['model'].get('hypotheses', [])
            if isinstance(hypothesis.get('contract'), str))
    try:
        with (output / 'samples.jsonl').open('xb') as saved:
            for row in rows:
                unit_started = perf_counter()
                if _input_blocked(row, plan):
                    # 没有消费源码时不能编译或追加证据；原阻断、模型和用量原样保留。
                    derived = {**row, 'facts': {'status': 'SKIPPED', 'sourceHash': row['sourceHash'],
                        'facts': [], 'scopes': [], 'limitations': ['原输入已阻断，未提供可消费源码']},
                        'compiledFacts': None, 'compilerBinding': None, 'environment': None,
                        'pipelineVersion': 'r2-derived-v2', 'toolCacheHit': False, 'newModelRequests': 0,
                        'provenance': {**provenance, 'originalUnitHash': fingerprint(row), 'toolCacheKey': None},
                        'researchEligible': False, 'replayTiming': {'durationMs': (perf_counter() - unit_started) * 1000}}
                    saved.write(encode(derived) + b'\n'); saved.flush()
                    collected.append(derived)
                    manifest['completedUnits'] = len(collected)
                    atomic_json(output / 'manifest.json', manifest)
                    continue
                target = _target(row, targets.get(row['sampleId'], {}))
                target['candidateContracts'] = sorted(candidate_contracts[row['sampleId']])
                environment = environment_resolver(target['fullSource'])
                if not isinstance(environment, dict) or not isinstance(environment.get('configHash'), str):
                    raise ValueError('工具环境缺少可绑定的配置摘要')
                target['_toolEnvironment'] = environment
                if configuration is not None:
                    target['_toolConfiguration'] = configuration
                compilation_manifest, compiled_facts, binding, binding_error = None, None, None, None
                binding_diagnostic = None
                if compilation_resolver is not None:
                    try:
                        compilation_manifest = compilation_resolver(target)
                        if compilation_manifest is not None:
                            target['compilerManifest'] = compilation_manifest
                            manifests = (compilation_manifest['manifests'] if isinstance(compilation_manifest, dict)
                                and compilation_manifest.get('provider') == 'contract-map' else {'target': compilation_manifest})
                            bindings, fact_sets = {}, {}
                            for contract, manifest_value in manifests.items():
                                bundle = load_bound_compilation(manifest_value, root)
                                if bundle['sourceHash'] != target['sourceHash']:
                                    raise CompilationBindingError('编译源码与原批次不一致')
                                fact_sets[contract] = extract_compiler_facts(bundle)
                                bindings[contract] = {name: bundle[name] for name in
                                           ('sourceHash', 'environmentHash', 'manifestDigest', 'receiptDigest')}
                            compiled_facts = fact_sets.get('target', fact_sets)
                            binding = bindings.get('target', bindings)
                    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                        binding_error = 'COMPILATION_BINDING_FAILED'
                        binding_diagnostic = str(error)
                key = fingerprint({'sourceHash': target['sourceHash'], 'environmentHash': environment['configHash'],
                                   'codeIdentityHash': identity_hash, 'compilerBinding': binding,
                                   'compilationError': binding_error})
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
                    if binding_error:
                        d2 = {'schemaVersion': '2', 'status': 'FAILED', 'verdict': 'UNKNOWN',
                              'assessments': [], 'errorCategory': binding_error}
                    else:
                        d2 = assess(row['model'], facts, tools, target['fullSource'], target=target,
                                    compilation_manifest=compilation_manifest, root=root)
                except (ValueError, KeyError, TypeError):
                    d2 = {'schemaVersion': '2', 'verdict': 'UNKNOWN', 'assessments': [],
                          'errorCategory': 'D2_EXECUTION_ERROR'}
                failed = (row['model'].get('status') != 'COMPLETED' or d2.get('status') == 'FAILED'
                          or bool(d2.get('errorCategory'))
                          or any(t.get('status') != 'OK' for t in tools))
                derived = {**row, 'tools': tools, 'd2': d2, 'facts': facts,
                           'compiledFacts': compiled_facts, 'compilerBinding': binding,
                           'compilationManifest': compilation_manifest, 'compilationError': binding_error,
                           'compilationDiagnostic': binding_diagnostic,
                           'pipelineVersion': 'r2-derived-v2', 'pipelineStatus': 'FAILED' if failed else 'COMPLETED',
                           'conclusion': final_conclusion(row['model'], d2, failed, 'real'),
                           'environment': environment, 'toolCacheHit': cached, 'newModelRequests': 0,
                           'provenance': {**provenance, 'originalUnitHash': fingerprint(row), 'toolCacheKey': key,
                                          'originalCompilationError': row.get('compilationError')},
                           'researchEligible': False, 'replayTiming': {'durationMs': (perf_counter() - unit_started) * 1000}}
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
                   'inputBlockedUnits': sum(_input_blocked(row, plan) for row in rows),
                   'newModelRequests': 0, 'researchEligible': False, 'provenance': provenance,
                   'toolStatuses': dict(Counter(t.get('status', 'UNKNOWN') for row in collected for t in row['tools'])),
                   'd2Verdicts': dict(Counter(row['d2']['verdict'] for row in collected)),
                   'assessmentVerdicts': dict(Counter(a['verdict'] for row in collected for a in row['d2']['assessments'])),
                   'pipelineStatuses': dict(Counter(row['pipelineStatus'] for row in collected)),
                   'factsStatuses': dict(Counter(row['facts']['status'] for row in
                       {item['sampleId']: item for item in collected}.values())),
                   'pathStates': dict(Counter(a.get('pathEvidence', {}).get('status', 'UNKNOWN')
                       for row in collected for a in row['d2']['assessments'])),
                   'hypotheses': sum(len(row['model'].get('hypotheses', [])) for row in collected)}
        comparisons = []
        for original_row, derived in zip(rows, collected):
            original_assessments = {a.get('hypothesisIndex', i): a for i, a in
                                    enumerate(original_row.get('d2', {}).get('assessments', []))}
            new_assessments = {a.get('hypothesisIndex', i): a for i, a in
                               enumerate(derived['d2'].get('assessments', []))}
            for index, hypothesis in enumerate(original_row['model'].get('hypotheses', [])):
                old, new = original_assessments.get(index, {}), new_assessments.get(index, {})
                comparisons.append({'sampleId': derived['sampleId'], 'strategy': derived['strategy'],
                    'hypothesisIndex': index, 'hypothesis': hypothesis, 'before': old.get('verdict', 'UNKNOWN'),
                    'after': new.get('verdict', 'UNKNOWN'), 'status': new.get('status', derived['pipelineStatus']),
                    'reason': new.get('note', derived['d2'].get('errorCategory', '证据不足')),
                    'gaps': new.get('candidateProof', {}).get('proofScope', new.get('proofScope', {})).get('gaps', []),
                    'toolBinding': new.get('toolBinding'), 'pathEvidence': new.get('pathEvidence'),
                    'references': new.get('references', [])})
        denominator = len(comparisons)
        before_unknown = sum(row['before'] == 'UNKNOWN' for row in comparisons)
        after_unknown = sum(row['after'] == 'UNKNOWN' for row in comparisons)
        summary['unknownComparison'] = {'denominator': denominator, 'beforeUnknown': before_unknown,
            'afterUnknown': after_unknown, 'beforeRate': before_unknown / denominator if denominator else None,
            'afterRate': after_unknown / denominator if denominator else None,
            'reductionPercentagePoints': (before_unknown - after_unknown) * 100 / denominator if denominator else None}
        summary['transitions'] = dict(Counter(row['before'] + '→' + row['after'] for row in comparisons))
        summary['unknownReasons'] = dict(Counter(row['reason'] for row in comparisons if row['after'] == 'UNKNOWN'))
        from four_arm_report import compare_arms
        four_arm, arm_rows = compare_arms(rows, collected, {**plan, 'batchId': provenance['originalBatchId']})
        atomic_json(output / 'four-arm-summary.json', four_arm)
        with (output / 'four-arm-results.jsonl').open('xb') as arm_file:
            for arm_row in arm_rows:
                arm_file.write(encode(arm_row) + b'\n')
        summary['fourArmReport'] = 'four-arm-summary.json'
        with (output / 'assessments.jsonl').open('xb') as assessment_file:
            for comparison in comparisons:
                assessment_file.write(encode(comparison) + b'\n')
        atomic_json(output / 'summary.json', summary)
        report = ('# 保存候选的工具与D2派生重放\n\n'
                  f"原批次：`{provenance['originalBatchId']}`；单元 {summary['units']}，唯一目标 {summary['targets']}。\n\n"
                  f"输入阻断 {summary['inputBlockedUnits']} 项保留在单元分母中，未编译、未执行工具；原未知与失败状态保留。\n\n"
                  f"工具执行 {tool_executions} 次；新增模型请求 0。\n\n"
                  f"工具状态：{summary['toolStatuses']}。D2：{summary['d2Verdicts']}。\n\n"
                  f"保存假设分母 {denominator}；UNKNOWN 从 {before_unknown} 降至 {after_unknown}。"
                  f"下降百分点：{summary['unknownComparison']['reductionPercentagePoints']}。\n\n"
                  f"逐假设迁移：{summary['transitions']}。完整对照与剩余未知原因见 `assessments.jsonl`。\n\n"
                  '四臂完整决策见 `four-arm-results.jsonl`，统计、逐候选稳定ID／变化与计时见 `four-arm-summary.json`。'
                  '候选独立真值尚未审核，混淆矩阵保持null；弱基线的接受／拒绝不代表形式证明。\n\n'
                  '原模型输出与usage保留，原批次samples摘要封口前再次核对。'
                  '本报告仅评价保存候选的核验，不是清理输入后的模型发现实验；研究资格未验证。\n')
        (output / 'REPORT.md').write_text(report, encoding='utf-8')
        manifest.update(status='COMPLETED', finishedAt=datetime.now(timezone.utc).isoformat(),
                        outputHashes={name: _sha((output / name).read_bytes()) for name in
                                      ('samples.jsonl', 'assessments.jsonl', 'summary.json', 'REPORT.md',
                                       'four-arm-summary.json', 'four-arm-results.jsonl')})
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
    parser.add_argument('--compiled', action='store_true', help='生成固定编译双收据并使用新的 D2 引擎')
    args = parser.parse_args()
    resolver = None
    if args.compiled:
        from compilation_runtime import prepare_candidate_compilations
        resolver = lambda target: prepare_candidate_compilations(args.root, target)
    result = replay(args.root, args.original_run, args.output_run, compilation_resolver=resolver)
    print(encode(result).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
