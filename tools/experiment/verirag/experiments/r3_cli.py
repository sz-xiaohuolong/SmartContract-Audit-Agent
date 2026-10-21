"""沿用批量平台运行五条件或权限事实四条件探索；默认只做无付费预检。"""
import argparse
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from verirag.audit.audit_run import model_runner
from verirag.experiments.benchmark_batch import make_plan, prepare_batch, replay_batch, run_batch, save_summary
from verirag.experiments.benchmark_cli import prepare_runtime
from verirag.experiments.mvp_runtime import _config_values, _properties_text
from verirag.experiments.r3_protocol import CONDITIONS, P4_CONDITIONS, freeze_plan, freeze_phase4_plan, condition_target, condition_view
from verirag.retrieval.r3_retrieval import R3Retrieval
from verirag.analysis.risk_catalog import prepare_model_context
from verirag.knowledge.snapshots import verify_snapshot
from verirag.infrastructure.storage import atomic_json, decode, durable_write, encode, exclusive_lock, fingerprint
from verirag.infrastructure.tool_environment import _configuration
from verirag.evaluation.tool_replay import _code_identity


DEFAULT_TARGETS = [
    'access_control__dataset_access_control_incorrect_constructor_name1__539cfe0360',
    'access_control__dataset_access_control_phishable__32d30f14ab',
    'reentrancy__dataset_reentrancy_simple_dao__1dca773a63',
    'reentrancy__dataset_reentrancy_reentrancy_cross_function__4070c6f3df',
    'safe_23_Ownable', 'safe_24_Ownable2Step', 'safe_25_AccessControl', 'safe_30_Pausable']


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _emit(kind, **values):
    print(json.dumps({'kind': kind, 'at': datetime.now(timezone.utc).isoformat(), **values}, ensure_ascii=False), flush=True)


def _validate_provider(provider, phase4):
    endpoint = ('https://ark.cn-beijing.volces.com/api/coding/v3' if phase4 else
                'https://ark.cn-beijing.volces.com/api/plan/v3')
    if provider != {'endpoint': endpoint, 'model': 'deepseek-v4-flash'}:
        raise ValueError('本次批量的模型或计费端点与已明确选择的配置不同')


def _view(runtime, target, strategy):
    base = runtime.preview(target)
    return condition_view(base, strategy) if strategy == 'VANILLA' or strategy in P4_CONDITIONS else runtime.r3.select(
        base, strategy, allow_unreviewed=True)


def preflight(root, runtime, targets, max_prompt_bytes, conditions=CONDITIONS):
    """经同一个 Java 提示构造器检查全部实际文本，不连接付费端点。"""
    receipts = {}
    for target in targets:
        target['_maxPromptBytes'] = max_prompt_bytes
        receipts[target['sampleId']] = {}
        for strategy in conditions:
            current, _ = condition_target(target, strategy)
            try:
                view = _view(runtime, current, strategy)
                prepare_model_context(root, current, view, 'real')
                result = model_runner(root, current, view, 'preflight')
                receipt = result.get('requestConsumptionReceipt')
                if result.get('status') != 'COMPLETED' or not receipt or receipt.get('requestAttempts') != 0:
                    raise ValueError(f"无付费预检未通过：{result.get('errorCategory')}")
                receipts[target['sampleId']][strategy] = {
                    **receipt, 'contextHash': view.get('r3Receipt', {}).get('contextHash'),
                    'selectedPairs': view.get('r3Receipt', {}).get('selectedPairs', []),
                    'poolHash': view['poolHash'], 'riskCatalogStatus': view.get('riskCatalogDiagnostic', {}).get('status')}
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                if conditions != P4_CONDITIONS:
                    raise
                receipts[target['sampleId']][strategy] = {'status': 'FAILED', 'reason': str(error), 'requestAttempts': 0}
        _emit('目标预检完成', sample=target['sampleId'], conditions=len(conditions),
              blocked=any(row.get('status') == 'FAILED' for row in receipts[target['sampleId']].values()))
    return receipts


def main():
    parser = argparse.ArgumentParser(description='R3 五条件预检与单次探索批量；正式研究准入独立判断')
    parser.add_argument('--execute', action='store_true', help='显式执行一次已授权真实批量；缺省不调用真实 API')
    parser.add_argument('--phase4', action='store_true', help='运行全文、权限事实、D1、事实加D1四条件；共同阻断目标保留在分母')
    parser.add_argument('--allow-unreviewed', action='store_true', help='明确接受未独立审核卡片，仅作工程探索')
    parser.add_argument('--batch-id', help='真实批量必须明确指定32位十六进制编号；禁止重复新建同一授权批次')
    parser.add_argument('--sample-ids', nargs='+', default=DEFAULT_TARGETS)
    parser.add_argument('--max-prompt-bytes', type=int, default=32768)
    parser.add_argument('--preflight-output', default='.evidence/R3-20261015/implementation/preflight.json')
    args = parser.parse_args()
    if not args.allow_unreviewed:
        parser.error('当前卡片尚未独立审核；探索运行必须明确 --allow-unreviewed')
    if args.execute and not args.batch_id:
        parser.error('真实批量必须指定 --batch-id 并保存本次授权身份')
    root = Path.cwd()
    all_targets, runtime = prepare_runtime(root, embedding_profile='nomic')
    indexed = {row['sampleId']: row for row in all_targets}
    if len(set(args.sample_ids)) != len(args.sample_ids) or not set(args.sample_ids) <= set(indexed):
        parser.error('目标不存在或重复')
    targets = [indexed[key] for key in args.sample_ids]
    conditions = P4_CONDITIONS if args.phase4 else CONDITIONS
    if args.phase4 and (len(targets) > 8 or not set(args.sample_ids) <= set(DEFAULT_TARGETS)):
        parser.error('本次四条件授权只覆盖已有八个开发目标、最多32次正式请求')
    if not args.phase4:
        runtime.r3 = R3Retrieval(runtime.store, runtime.pointer['snapshot_id'], runtime.catalog)
        runtime.r3_allow_unreviewed = True
    provider_path, tool_path = root / 'config/providers.local.properties', root / 'config/tools.local.properties'
    # 离线提示预检不解析凭证，执行时再核对明确选择的计费入口。
    provider_values = _config_values(provider_path) if args.execute else None
    public_values = {key.strip(): value.strip() for line in provider_path.read_text(encoding='utf-8').splitlines()
                     for key, separator, value in [line.partition('=')]
                     if separator and key.strip() in ('providers.ark.base-url', 'providers.ark.model')}
    provider = {'endpoint': public_values['providers.ark.base-url'], 'model': public_values['providers.ark.model']}
    # 本轮采用现有计费配置，不自动改模型或端点。
    if args.execute:
        _validate_provider(provider, args.phase4)
    tool_values = _configuration(tool_path)
    config_hashes = {str(path.relative_to(root)): _sha(path) for path in (provider_path, tool_path)}
    identity = _code_identity(root)
    for target in targets:
        target['_toolConfiguration'] = tool_values
        target['_toolConfigPath'] = str(tool_path)
    receipts = preflight(root, runtime, targets, args.max_prompt_bytes, conditions)
    if args.phase4:
        for target in targets:
            failures = [f'{s}：{r["reason"]}' for s, r in receipts[target['sampleId']].items() if r.get('status') == 'FAILED']
            if failures:
                target.update(runnable=False, inputReason='四条件共同预检阻断；' + '；'.join(failures))
    if identity != _code_identity(root):
        raise ValueError('预检期间源码或 JAR 已改变')
    if args.phase4:
        registry = runtime.catalog
        registry_path = runtime.store / 'catalogs' / (runtime.pointer['snapshot_id'] + '.json')
    else:
        registry = runtime.r3.registry
        registry_path = root / 'research-artifacts/snapshots/r3' / (registry['registryHash'] + '.json')
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        if registry_path.exists():
            if decode(registry_path.read_bytes()) != registry:
                raise ValueError('已保存卡片身份冲突')
        else:
            durable_write(registry_path, encode(registry) + b'\n')
    registry_sha = _sha(registry_path)
    preflight_path = root / args.preflight_output
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(preflight_path, {'codeIdentity': identity, 'registryPath': str(registry_path.relative_to(root)),
        'registryHash': fingerprint(registry), 'cards': len(registry.get('cards', [])),
        'excludedCards': len(registry.get('excluded', [])), 'provider': provider, 'receipts': receipts,
        'researchEligible': False, 'paidRequests': 0})
    _emit('全部预检完成', targets=len(targets), maxRequests=sum(t['runnable'] for t in targets) * len(conditions),
          blockedTargets=sum(not t['runnable'] for t in targets), paidRequests=0)
    if not args.execute:
        return
    store = root / 'research-artifacts/runs/benchmarks'
    directory = store / args.batch_id
    if directory.exists():
        raise ValueError('该批量已存在；不得重复消费或覆盖授权，需要先检查保存结果')
    plan = make_plan(args.sample_ids, conditions, 'real', targets, runtime.pointer['snapshot_id'], provider, 'nomic',
                     include_blocked=args.phase4)
    plan = (freeze_phase4_plan(plan, identity, receipts, args.max_prompt_bytes) if args.phase4 else
            freeze_plan(plan, registry, identity, receipts, args.max_prompt_bytes))
    plan['configurationHashes'] = config_hashes
    plan['registryPath'] = str(registry_path.relative_to(root))
    plan['authorization'] = (f'用户于2026-10-19要求优化结束后直接用真实API跑一次实验，2026-10-20明确沿用当前coding/v3入口和既定模型；{len(targets)}个既有开发目标四条件，最多32次正式请求'
        if args.phase4 else f'用户于2026-10-16明确要求按计划实施并运行一次真实API批量；本批为{len(targets)}目标五条件工程探索')
    plan['stoppingRule'] = '身份或请求改变、任何模型失败或请求预算耗尽时停止后续付费单元；不重试、不换端点'
    plan['planHash'] = fingerprint({key: value for key, value in plan.items() if key != 'planHash'})
    prepare_batch(store, plan, args.batch_id)
    atomic_json(directory / 'target-manifest.json', {'targets': [{key: value for key, value in target.items()
        if not key.startswith('_') and key not in ('fullSource', 'modelSource', 'originalSource')} for target in targets]})
    stopped, attempted = None, 0
    with exclusive_lock(root / '.local/r3-api.lock'), tempfile.TemporaryDirectory(prefix='r3-provider-') as temp:
        frozen = Path(temp) / 'providers.properties'
        frozen.write_text(_properties_text(provider_values), encoding='utf-8')
        frozen.chmod(0o600)
        for target in targets:
            target['_providerConfigPath'] = str(frozen)

        def guarded_model(root, target, view, mode):
            nonlocal attempted, stopped
            strategy = view['strategy']
            if (identity != _code_identity(root) or any(_sha(root / name) != digest for name, digest in config_hashes.items())
                    or decode((runtime.store / 'active.json').read_bytes()) != runtime.pointer
                    or fingerprint(verify_snapshot(runtime.store, runtime.pointer['snapshot_id'])) != runtime.pointer['snapshot_id']
                    or _sha(registry_path) != registry_sha):
                stopped = '运行身份已改变'
            if stopped or attempted >= plan['requestBounds']['maxRequests']:
                raise ValueError(stopped or '请求预算耗尽')
            check = model_runner(root, target, view, 'preflight')
            expected = receipts[target['sampleId']][strategy]['requestSha256']
            if check.get('status') != 'COMPLETED' or check.get('requestConsumptionReceipt', {}).get('requestSha256') != expected:
                stopped = '实际请求与冻结预检不一致'
                raise ValueError(stopped)
            attempted += 1
            result = model_runner(root, target, view, mode)
            if (result.get('status') != 'COMPLETED'
                    or result.get('requestConsumptionReceipt', {}).get('requestSha256') != expected):
                stopped = '模型失败或实际请求回执不一致'
            return result

        runtime.model_runner = guarded_model

        def runner(sample, strategy, mode):
            nonlocal stopped
            if stopped:
                return {'status': 'FAILED', 'prediction': 'UNKNOWN', 'pipelineStatus': 'FAILED',
                        'errorCategory': 'EXPERIMENT_STOPPED', 'stopReason': stopped,
                        'requestAttempts': 0, 'inputTokens': None, 'outputTokens': None, 'model': {}}
            _emit('开始单元', sample=sample, strategy=strategy)
            try:
                row = runtime.run(indexed[sample], strategy, mode)
            except Exception:
                stopped = '执行单元异常，停止后续付费'
                raise
            _emit('完成单元', sample=sample, strategy=strategy, status=row['status'],
                  prediction=row['prediction'], inputTokens=row['inputTokens'], outputTokens=row['outputTokens'],
                  d2=row['d2']['verdict'])
            return row

        run_batch(store, plan, runner, args.batch_id)
    report = replay_batch(store, args.batch_id)
    save_summary(directory, report)
    atomic_json(directory / 'execution-complete.json', {'status': report['status'], 'stopped': stopped,
        'paidUnitsAttempted': attempted, 'codeIdentityUnchanged': identity == _code_identity(root),
        'configurationUnchanged': all(_sha(root / name) == digest for name, digest in config_hashes.items()),
        'comparisonAudit': report['comparisonAudit'], 'researchEligible': False})
    _emit('批量结束', batchId=args.batch_id, denominators=report['denominators'],
          metrics=report['metrics'], comparisonAudit=report['comparisonAudit'], stopped=stopped)


if __name__ == '__main__':
    main()
