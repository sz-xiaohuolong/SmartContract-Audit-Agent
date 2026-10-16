"""沿用批量平台运行 R3 五条件探索；默认只做无付费预检。"""
import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from audit_run import model_runner
from benchmark_batch import make_plan, prepare_batch, replay_batch, run_batch, save_summary
from benchmark_cli import prepare_runtime
from formal_recall import select_strategy
from mvp_runtime import _config_values, _properties_text
from r3_protocol import CONDITIONS, freeze_plan
from r3_retrieval import R3Retrieval
from risk_catalog import prepare_model_context
from snapshots import verify_snapshot
from storage import atomic_json, decode, durable_write, encode, exclusive_lock, fingerprint
from tool_environment import _configuration
from tool_replay import _code_identity


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


def _view(runtime, target, strategy):
    base = runtime.preview(target)
    return select_strategy(base, strategy) if strategy == 'VANILLA' else runtime.r3.select(
        base, strategy, allow_unreviewed=True)


def preflight(root, runtime, targets, max_prompt_bytes):
    """经同一个 Java 提示构造器检查全部实际文本，不连接付费端点。"""
    receipts = {}
    for target in targets:
        target['_maxPromptBytes'] = max_prompt_bytes
        receipts[target['sampleId']] = {}
        for strategy in CONDITIONS:
            view = _view(runtime, target, strategy)
            prepare_model_context(root, target, view, 'real')
            result = model_runner(root, target, view, 'preflight')
            receipt = result.get('requestConsumptionReceipt')
            if result.get('status') != 'COMPLETED' or not receipt or receipt.get('requestAttempts') != 0:
                raise ValueError(f"无付费预检未通过：{target['sampleId']} / {strategy} / {result.get('errorCategory')}")
            receipts[target['sampleId']][strategy] = {
                **receipt, 'contextHash': view.get('r3Receipt', {}).get('contextHash'),
                'selectedPairs': view.get('r3Receipt', {}).get('selectedPairs', []),
                'poolHash': view['poolHash'], 'riskCatalogStatus': view.get('riskCatalogDiagnostic', {}).get('status')}
        _emit('目标预检完成', sample=target['sampleId'], conditions=len(CONDITIONS))
    return receipts


def main():
    parser = argparse.ArgumentParser(description='R3 五条件预检与单次探索批量；正式研究准入独立判断')
    parser.add_argument('--execute', action='store_true', help='显式执行一次已授权真实批量；缺省不调用真实 API')
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
    runtime.r3 = R3Retrieval(runtime.store, runtime.pointer['snapshot_id'], runtime.catalog)
    runtime.r3_allow_unreviewed = True
    provider_path, tool_path = root / 'config/providers.local.properties', root / 'config/tools.local.properties'
    provider_values = _config_values(provider_path)
    provider = {'endpoint': provider_values['providers.ark.base-url'], 'model': provider_values['providers.ark.model']}
    # 本轮采用现有计费配置，不自动改模型或端点。
    if provider != {'endpoint': 'https://ark.cn-beijing.volces.com/api/plan/v3', 'model': 'deepseek-v4-flash'}:
        raise ValueError('本次批量的模型或计费端点与已核对配置不同')
    tool_values = _configuration(tool_path)
    config_hashes = {str(path.relative_to(root)): _sha(path) for path in (provider_path, tool_path)}
    identity = _code_identity(root)
    for target in targets:
        target['_toolConfiguration'] = tool_values
        target['_toolConfigPath'] = str(tool_path)
    receipts = preflight(root, runtime, targets, args.max_prompt_bytes)
    if identity != _code_identity(root):
        raise ValueError('预检期间源码或 JAR 已改变')
    registry = runtime.r3.registry
    registry_path = root / 'research-artifacts/snapshots/r3' / (registry['registryHash'] + '.json')
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if registry_path.exists():
        if decode(registry_path.read_bytes()) != registry:
            raise ValueError('已保存卡片身份冲突')
    else:
        durable_write(registry_path, encode(registry) + b'\n')
    preflight_path = root / args.preflight_output
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(preflight_path, {'codeIdentity': identity, 'registryPath': str(registry_path.relative_to(root)),
        'registryHash': registry['registryHash'], 'cards': len(registry['cards']),
        'excludedCards': len(registry['excluded']), 'provider': provider, 'receipts': receipts,
        'researchEligible': False, 'paidRequests': 0})
    _emit('全部预检通过', targets=len(targets), maxRequests=len(targets) * len(CONDITIONS),
          cards=len(registry['cards']), paidRequests=0)
    if not args.execute:
        return
    store = root / 'research-artifacts/runs/benchmarks'
    directory = store / args.batch_id
    if directory.exists():
        raise ValueError('该批量已存在；不得重复消费或覆盖授权，需要先检查保存结果')
    plan = make_plan(args.sample_ids, CONDITIONS, 'real', targets, runtime.pointer['snapshot_id'], provider, 'nomic')
    plan = freeze_plan(plan, registry, identity, receipts, args.max_prompt_bytes)
    plan['configurationHashes'] = config_hashes
    plan['registryPath'] = str(registry_path.relative_to(root))
    plan['authorization'] = f'用户于2026-10-16明确要求按计划实施并运行一次真实API批量；本批为{len(targets)}目标五条件工程探索'
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
                    or _sha(registry_path) != hashlib.sha256(encode(registry) + b'\n').hexdigest()):
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
            if stopped:
                return {'status': 'FAILED', 'prediction': 'UNKNOWN', 'pipelineStatus': 'FAILED',
                        'errorCategory': 'EXPERIMENT_STOPPED', 'stopReason': stopped,
                        'requestAttempts': 0, 'inputTokens': None, 'outputTokens': None, 'model': {}}
            _emit('开始单元', sample=sample, strategy=strategy)
            row = runtime.run(indexed[sample], strategy, mode)
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
