"""显式运行一次已授权的三条件开发集探索；缺省只做零付费预检。"""
import argparse
import copy
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from verirag.audit.audit_run import model_runner
from verirag.experiments.benchmark_batch import make_plan, prepare_batch, replay_batch, run_batch, save_summary
from verirag.experiments.benchmark_runtime import BenchmarkRuntime, _validate_input
from verirag.infrastructure.ollama_embed import OllamaEncoder, MODEL, DIMENSION, QUERY_PREFIX, DOCUMENT_PREFIX
from verirag.experiments.phase5_cli import _batch, compare_dataset, read_pointer, validate_run, verify_sources, write_output
from verirag.retrieval.phase5_retrieval import rank_pool
from verirag.infrastructure.storage import atomic_json, decode, exclusive_lock, fingerprint, read_artifact
from verirag.evaluation.tool_replay import _code_identity


CONDITIONS = ['P5_FROZEN', 'P5_RELEVANCE', 'P5_MARGIN']
PROVIDER = {'endpoint': 'https://ark.cn-beijing.volces.com/api/coding/v3', 'model': 'deepseek-v4-flash'}


class EncoderIdentityChanged(Exception):
    """身份漂移终止整轮，不得被单操作的可恢复评分失败吞掉。"""


def strict_nomic_encoder(expected_digest, transport=None):
    """每份完整文本单独编码；服务端禁止截断，实际 token 缺失即拒绝。"""
    client = OllamaEncoder(expected_digest=expected_digest, transport=transport)
    limit = client.context_length
    if type(limit) is not int or limit < 1:
        raise ValueError('本机编码器缺少可核对的上下文上限')
    identity = {'model': 'ollama/' + MODEL, 'revision': client.digest,
                'dimension': DIMENSION, 'weightsHash': client.digest}
    config = {'identity': identity, 'queryPrefix': QUERY_PREFIX, 'documentPrefix': DOCUMENT_PREFIX,
              'maxInputTokens': limit, 'encodingProtocol': 'ollama-embed-no-truncation-1'}
    cache = {}

    def check():
        try:
            current = OllamaEncoder(expected_digest=expected_digest, transport=client.transport)
        except ValueError as error:
            raise EncoderIdentityChanged('本机编码器身份无法保持') from error
        if current.context_length != limit:
            raise EncoderIdentityChanged('本机编码上限发生变化')

    def encoder(texts):
        check()
        vectors, counts = [], []
        for text in texts:
            if text not in cache:
                response = client.transport('/api/embed', {'model': MODEL, 'input': text,
                    'truncate': False, 'options': {'num_ctx': limit}})
                count, values = response.get('prompt_eval_count'), response.get('embeddings')
                if (response.get('model') != MODEL or type(count) is not int or not 1 <= count <= limit
                        or not isinstance(values, list) or len(values) != 1
                        or len(values[0]) != DIMENSION):
                    raise ValueError('本机编码缺少实际 token、完整向量或模型身份')
                cache[text] = (values[0], count)
            vector, count = cache[text]
            vectors.append(vector); counts.append(count)
        check()
        return {'identity': identity, 'vectors': vectors, 'tokenCounts': counts,
                'truncated': [False] * len(texts)}
    return encoder, config


def aggregate_target(run, target):
    """每个材料跨全部结构有效操作等权平均，再使用共同过滤和预算。"""
    queries = [q for q in target.get('queries', {}).get('queries', []) if q['structureStatus'] == 'VALID']
    keys = [q['operationKey'] for q in queries]
    blocked = {'status': 'BLOCKED', 'operationKeys': keys, 'reason': '没有完整可评分对照，三条件共同阻断'}
    rows = {row['operationKey']: row['scores'] for row in run['comparisons'] if row['targetKey'] == target['targetKey']}
    resources = {q.get('resourceKey') for q in queries}
    if (not keys or target['status'] != 'READY' or len(resources) != 1
            or any(rows.get(k, {}).get('status') != 'SCORED' for k in keys)):
        return blocked
    pair_ids = [e['pairId'] for e in target['pool']['evidence']]
    by_operation = [{r['pairId']: r for r in rows[k]['scores']} for k in keys]
    if any(set(items) != set(pair_ids) for items in by_operation):
        raise ValueError('目标聚合的操作未覆盖同一完整候选池')
    scores = [{'pairId': pair, **{name: sum(items[pair][name] for items in by_operation) / len(keys)
                                for name in ('originalScore', 'margin')}} for pair in pair_ids]
    result = {'status': 'SCORED', 'operationKeys': keys, 'operationKey': fingerprint(keys),
        'aggregation': 'MEAN_ALL_STRUCTURALLY_VALID_OPERATIONS', 'scores': scores,
        'mechanism': queries[0]['mechanism'], 'resourceKey': next(iter(resources)),
        'evidenceHash': fingerprint(target['pool']['evidence'])}
    result['rankings'] = {s: rank_pool(target['pool'], result, s, run['dataset']['budget']) for s in CONDITIONS[1:]}
    return result


def build_views(run, historical_rows):
    """原方案照原字节消费，新方案只替换选中材料和顺序。"""
    validate_run(run)
    views, aggregates = {}, {}
    for target in run['dataset']['targets']:
        sample = target['sampleId']; aggregate = aggregate_target(run, target)
        aggregates[sample] = aggregate
        if aggregate['status'] != 'SCORED':
            continue
        matches = [r for r in historical_rows if r['sampleId'] == sample and r['strategy'] == 'R3_FUSION']
        if len(matches) != 1 or matches[0]['sourceHash'] != target['sourceHash']:
            raise ValueError('原冻结方案缺失、重复或源码身份不一致')
        base = copy.deepcopy(matches[0]['retrieval'])
        views[sample] = {'P5_FROZEN': base}
        candidates = {c['chunkId']: c for c in base['pool']['candidates']}
        for condition in CONDITIONS[1:]:
            ranking = aggregate['rankings'][condition]
            view = copy.deepcopy(base); view.pop('r3Receipt', None)
            view['phase5Receipt'] = {'runHash': run['runHash'], 'aggregation': aggregate['aggregation'],
                'operationKeys': aggregate['operationKeys'], 'ranking': ranking}
            view['d1'] = {'status': 'COMPLETED', 'context': ranking['context'],
                'selected': [{'candidate': candidates[key], 'use': 'SUPPORT'} for key in ranking['selectedEvidenceIds']],
                'gaps': [], 'evaluations': {}, 'budgetKind': 'UTF8_BYTES'}
            views[sample][condition] = view
    return views, aggregates


class FrozenRuntime(BenchmarkRuntime):
    """复用原模型与 D2 流程，但只读已保存的候选池，不重新召回。"""
    def __init__(self, root, snapshot, views):
        self.root, self.snapshot, self.frozen_views = Path(root), snapshot, views
        self.model_runner = model_runner

    def preview(self, target):
        _validate_input(target)
        view = copy.deepcopy(self.frozen_views[target['sampleId']][target['_phase5Condition']])
        if view['sourceHash'] != target['sourceHash']:
            raise ValueError('冻结视图与当前消费源码不一致')
        return view


class PaidGuard:
    """实际消费必须等于零付费预检；失败后没有自动重试或续采。"""
    def __init__(self, receipts, max_requests, identity_check, runner=model_runner):
        self.receipts, self.max_requests, self.identity_check, self.runner = receipts, max_requests, identity_check, runner
        self.attempted, self.stopped = 0, None

    def __call__(self, root, target, view, mode):
        if mode != 'real' or self.stopped or not self.identity_check() or self.attempted >= self.max_requests:
            self.stopped = self.stopped or '运行身份变化或请求预算耗尽'
            raise ValueError(self.stopped)
        expected = self.receipts[target['sampleId']][target['_phase5Condition']]
        check = self.runner(root, target, view, 'preflight')
        actual = check.get('requestConsumptionReceipt', {})
        if check.get('status') != 'COMPLETED' or actual.get('requestSha256') != expected.get('requestSha256'):
            self.stopped = '实际请求与冻结预检不一致'
            raise ValueError(self.stopped)
        if not self.identity_check():
            self.stopped = '预检期间身份变化，停止后续请求'
            raise ValueError(self.stopped)
        self.attempted += 1
        try:
            result = self.runner(root, target, view, mode)
        except Exception:
            self.stopped = '模型执行异常，停止后续请求'
            raise
        if (not self.identity_check() or result.get('status') != 'COMPLETED'
                or result.get('requestConsumptionReceipt', {}).get('requestSha256') != expected.get('requestSha256')):
            self.stopped = '模型失败或消费回执不一致'
            if result.get('status') == 'COMPLETED':
                result = {**result, 'providerStatus': result['status'], 'status': 'FAILED',
                          'conclusion': 'UNRESOLVED', 'errorCategory': 'REQUEST_IDENTITY_MISMATCH'}
        return result


def reserve_batch(store, plan, batch_id):
    """本次单次授权独立于批次编号登记；换编号也不能重复消费。"""
    store = Path(store)
    register = store / 'phase5-20261021/real-authorization.json'
    register.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(register.with_suffix('.lock')):
        if register.exists():
            raise ValueError('本次单次真实请求授权已登记，须核对原批次，禁止换编号再次消费')
        directory = prepare_batch(store, plan, batch_id)
        atomic_json(register, {'schemaVersion': 'phase5-single-authorization-1', 'batchId': batch_id,
            'planHash': plan['planHash'], 'maxRequests': plan['requestBounds']['maxRequests'],
            'reservedAt': datetime.now(timezone.utc).isoformat(), 'researchEligible': False})
    return directory


def comparison_audit(rows, plan):
    """回放核对实际请求、全文、材料与证据顺序；阻断项不冒充成功。"""
    if plan['strategies'] != CONDITIONS:
        raise ValueError('phase 5 三条件不能省略或替换')
    errors = []
    for row in rows:
        sample, strategy = row['sampleId'], row['strategy']
        if not plan['inputEligibility'][sample]['runnable']:
            if row.get('requestAttempts') != 0 or row.get('prediction') != 'UNKNOWN':
                errors.append({'sampleId': sample, 'strategy': strategy, 'reason': '阻断目标出现请求或分类'})
            continue
        expected = plan['preflight'][sample][strategy]
        actual = row.get('model', {}).get('requestConsumptionReceipt', {})
        fields = ('requestSha256', 'contextSha256', 'sourceHash', 'modelSourceHash', 'evidenceIds', 'factGuidance')
        if row.get('status') == 'COMPLETED' and (not actual.get('requestSha256') or any(
                actual.get(k) != expected.get(k) for k in fields)
                or actual.get('sourceHash') != plan['sourceHashes'][sample]
                or actual.get('modelSourceHash') != plan['sourceHashes'][sample]
                or actual.get('factGuidance') is not None):
            errors.append({'sampleId': sample, 'strategy': strategy, 'reason': '全文、材料或请求与预检不一致'})
    return errors


def candidate_summary(rows):
    """每个模型候选只统计一次；核验失败与未知各有独立分母。"""
    from verirag.evaluation.four_arm_report import _assessments, verification_summary
    result = {}
    for strategy in CONDITIONS:
        states, missing = [], 0
        for row in rows:
            if row['strategy'] != strategy:
                continue
            assessments = _assessments(row)
            for index, _ in enumerate(row.get('model', {}).get('hypotheses', [])):
                item = assessments.get(index)
                missing += item is None
                failed = (item is None or item.get('status') == 'FAILED' or item.get('errorCategory')
                    or row.get('model', {}).get('status') == 'FAILED'
                    or row.get('d2', {}).get('status') == 'FAILED' or row.get('d2', {}).get('errorCategory'))
                state = 'FAILED' if failed else item.get('verdict', 'UNKNOWN')
                if state not in ('SUPPORTED', 'REFUTED', 'UNKNOWN', 'FAILED'):
                    raise ValueError('候选核验四态无效')
                states.append({'verificationStatus': state})
        result[strategy] = {**verification_summary(states), 'assessmentMissing': missing}
    return result


def _sha(path):
    return hashlib.sha256(read_artifact(Path(path))).hexdigest()


def _emit(kind, **values):
    print(json.dumps({'kind': kind, 'at': datetime.now(timezone.utc).isoformat(), **values}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description='phase 5 三条件开发集探索；默认零付费预检，禁止自动追加批次')
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--comparison', type=Path, help='复用已有 Nomic 评分回执；仍重新核对来源及向量')
    parser.add_argument('--output', type=Path, required=True, help='不存在的本轮派生目录')
    parser.add_argument('--allow-unreviewed', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--batch-id', help='本次单次授权唯一32位十六进制批量编号')
    args = parser.parse_args()
    if not args.allow_unreviewed or args.execute and not args.batch_id:
        parser.error('探索须显式接受未独立审核材料，真实执行还须指定唯一批量编号')
    root = Path.cwd()
    args.output = args.output.resolve()
    from verirag.knowledge.snapshots import verify_snapshot
    from verirag.knowledge.exploratory_corpus import load_corpus
    from verirag.experiments.benchmark_targets import load_benchmark_targets
    from verirag.experiments.mvp_runtime import _config_values, _properties_text
    from verirag.analysis.risk_catalog import prepare_model_context
    from verirag.retrieval.formal_recall import select_strategy

    data = decode(read_artifact(args.dataset))
    verify_sources(root, data)
    historical_plan, historical_rows, origin = _batch(root, data['sources'][0]['batchId'])
    if not 1 <= len(data['targets']) <= 8 or len(data['sources']) != 1:
        raise ValueError('本次授权最多八个已有开发目标、一个冻结来源批次')
    snapshot_store = root / 'research-artifacts/snapshots/nomic'
    snapshot = verify_snapshot(snapshot_store, historical_plan['snapshotId'])
    if args.comparison:
        run = decode(read_artifact(args.comparison)); validate_run(run)
        if (run['dataset'] != data or run['config']['identity']['revision'] != snapshot['embedding']['revision']
                or run['config'].get('encodingProtocol') != 'ollama-embed-no-truncation-1'):
            raise ValueError('保存评分的输入或完整编码身份不符')
    else:
        encoder, config = strict_nomic_encoder(snapshot['embedding']['revision'])
        run = compare_dataset(data, encoder, config)
        validate_run(run)
    views, aggregates = build_views(run, historical_rows)
    targets = load_benchmark_targets(root, list(load_corpus(root / 'data/external/candidates/r1-pending')['rows'].values()))
    indexed = {t['sampleId']: t for t in targets}
    selected = [copy.deepcopy(indexed[t['sampleId']]) for t in data['targets']]
    if any(t['sourceHash'] != historical_plan['sourceHashes'][t['sampleId']] for t in selected):
        raise ValueError('当前源码不能沿用历史输入身份')
    runtime = FrozenRuntime(root, snapshot, views)
    provider_path, tool_path = root / 'config/providers.local.properties', root / 'config/tools.local.properties'
    values = _config_values(provider_path) if args.execute else None
    public = {k.strip(): v.strip() for line in provider_path.read_text().splitlines()
              for k, sep, v in [line.partition('=')] if sep and k.strip() in ('providers.ark.base-url', 'providers.ark.model')}
    provider = {'endpoint': public.get('providers.ark.base-url'), 'model': public.get('providers.ark.model')}
    if provider != PROVIDER:
        raise ValueError('本次模型与计费端点必须保持已明确选择的配置')
    identity = _code_identity(root)
    hashes = {str(p.relative_to(root)): _sha(p) for p in (provider_path, tool_path)}
    receipts = {}
    for target in selected:
        sample = target['sampleId']; receipts[sample] = {}
        target.update(factGuidanceEnabled=False, _maxPromptBytes=32768)
        reasons = []
        if sample not in views:
            reasons.append(aggregates[sample]['reason'])
        else:
            for condition in CONDITIONS:
                current = {**target, '_phase5Condition': condition}
                try:
                    view = select_strategy(runtime.preview(current), 'D1')
                    prepare_model_context(root, current, view, 'real')
                    result = model_runner(root, current, view, 'preflight')
                    receipt = result.get('requestConsumptionReceipt')
                    if result.get('status') != 'COMPLETED' or not receipt or receipt.get('requestAttempts') != 0:
                        raise ValueError('Java 完整提示预检失败：' + str(result.get('errorCategory')))
                    receipts[sample][condition] = receipt
                except (ValueError, OSError) as error:
                    reasons.append(condition + '：' + str(error))
        target.update(runnable=not reasons, inputReason='；'.join(reasons) or None)
        _emit('三条件预检', sample=sample, runnable=target['runnable'], reason=target['inputReason'])
    if identity != _code_identity(root):
        raise ValueError('预检期间源码或构建产物变化')
    plan = make_plan([t['sampleId'] for t in selected], CONDITIONS, 'real', selected,
                     historical_plan['snapshotId'], provider, 'nomic', include_blocked=True)
    plan.update(pipelineVersion='phase5-exploration-1', codeIdentity=identity, preflight=receipts,
        configurationHashes=hashes, origin=origin, datasetHash=data['datasetHash'], rerankHash=run['runHash'],
        aggregation='MEAN_ALL_STRUCTURALLY_VALID_OPERATIONS',
        authorization='用户2026-10-21要求真实模型请求并与优化前比较；本次继续执行一次最多24计划单元的开发集探索',
        stoppingRule='任一模型失败、身份或消费变化即停止后续付费；零重试，不换端点',
        admission={'independentQueryReview': False, 'independentRelevance': False, 'lineageReview': False,
                   'exactTokenFairness': False},
        comparisonGroups=[['P5_RELEVANCE', 'P5_MARGIN']], evaluationPairs=[])
    plan['requestBounds'].update(maxPromptBytesPerRequest=32768, maxOutputTokensPerRequest=16384,
        budgetKind='COMPLETE_SYSTEM_USER_UTF8_BYTES', paidSummaryRequests=0, paidJudgeRequests=0)
    plan['planHash'] = fingerprint({k: v for k, v in plan.items() if k != 'planHash'})
    files = {'aggregates.json': aggregates, 'preflight.json': plan}
    if args.comparison:
        comparison_path = args.comparison.resolve()
        files['comparison-ref.json'] = {'path': str(comparison_path.relative_to(root)), 'sha256': _sha(comparison_path)}
    else:
        files['comparison.json'] = run
        comparison_path = args.output / 'comparison.json'
    write_output(args.output, files)
    _emit('预检结束', maxRequests=plan['requestBounds']['maxRequests'], plannedUnits=3 * len(selected), paidRequests=0)
    if not args.execute:
        return
    store = root / 'research-artifacts/runs/benchmarks'
    # 一次授权只有一个固定批次；原件存在时不自动续采、重试或覆盖。
    directory = reserve_batch(store, plan, args.batch_id)
    frozen_inputs = {p: _sha(p) for p in (comparison_path, args.output / 'preflight.json')}
    def unchanged():
        encoder_identity = OllamaEncoder(expected_digest=run['config']['identity']['revision'])
        return (encoder_identity.context_length == run['config']['maxInputTokens']
                and identity == _code_identity(root) and all(_sha(root / p) == h for p, h in hashes.items())
                and all(_sha(p) == h for p, h in frozen_inputs.items())
                and all(hashlib.sha256(read_pointer(root, origin[k])).hexdigest() == origin[k]['sha256']
                        for k in ('plan', 'samples')))
    guard = PaidGuard(receipts, plan['requestBounds']['maxRequests'], unchanged)
    runtime.model_runner = guard
    selected_map = {t['sampleId']: t for t in selected}
    with exclusive_lock(root / '.local/r3-api.lock'), tempfile.TemporaryDirectory(prefix='phase5-provider-') as temp:
        frozen_config = Path(temp) / 'providers.properties'
        frozen_config.write_text(_properties_text(values), encoding='utf-8'); frozen_config.chmod(0o600)
        def runner(sample, condition, mode):
            if guard.stopped:
                return {'status': 'FAILED', 'pipelineStatus': 'FAILED', 'prediction': 'UNKNOWN',
                    'errorCategory': 'EXPERIMENT_STOPPED', 'stopReason': guard.stopped, 'requestAttempts': 0,
                    'inputTokens': None, 'outputTokens': None, 'model': {}}
            current = {**selected_map[sample], '_phase5Condition': condition, '_providerConfigPath': str(frozen_config)}
            _emit('开始单元', sample=sample, condition=condition)
            try:
                row = runtime.run(current, 'D1', mode)
            except Exception:
                guard.stopped = guard.stopped or '单元执行异常，停止后续请求'
                raise
            row['phase5Condition'] = condition
            _emit('完成单元', sample=sample, condition=condition, status=row['status'],
                  prediction=row['prediction'], inputTokens=row['inputTokens'], outputTokens=row['outputTokens'])
            return row
        run_batch(store, plan, runner, args.batch_id)
    report = replay_batch(store, args.batch_id); save_summary(directory, report)
    atomic_json(directory / 'execution-complete.json', {'status': report['status'], 'stopped': guard.stopped,
        'paidUnitsAttempted': guard.attempted, 'identityUnchanged': unchanged(),
        'comparisonAudit': report['comparisonAudit'], 'derivedPath': str(args.output.relative_to(root)),
        'researchEligible': False})
    _emit('批量结束', batchId=args.batch_id, denominators=report['denominators'],
          pairedMetrics=report['pairedMetrics'], comparisonAudit=report['comparisonAudit'], stopped=guard.stopped)


if __name__ == '__main__':
    main()
