"""固定验证目标的三策略批量运行、断点保护和保守指标汇总。"""
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from storage import atomic_json, decode, durable_write, encode, exclusive_lock, fingerprint, sync_directory

STRATEGIES = frozenset({'DENSE', 'FIELD_FILTER', 'D1'})
ID = re.compile(r'[0-9a-f]{32}')


def make_plan(sample_ids, strategies, mode, targets, state):
    if (not isinstance(sample_ids, list) or not sample_ids
            or len(set(sample_ids)) != len(sample_ids) or
            not isinstance(strategies, list) or not strategies or len(strategies) > 3
            or len(set(strategies)) != len(strategies) or not set(strategies) <= STRATEGIES
            or mode not in ('offline', 'real')):
        raise ValueError('批量选择无效')
    allowed = {row['sampleId'] for row in targets if row.get('split') == 'validation' and row.get('runnable')}
    if not set(sample_ids) <= allowed or not state.get('ready') or not state.get('snapshotId'):
        raise ValueError('目标或正式知识快照不可用')
    if mode == 'real' and not state.get('realReady'):
        raise ValueError('真实模型未配置')
    count = len(sample_ids) * len(strategies)
    bounds = {'samples': len(sample_ids), 'strategies': len(strategies), 'repeats': 1,
              'modelStages': 1, 'attemptsPerUnit': 2 if mode == 'real' else 0,
              'maxRequests': 2 * count if mode == 'real' else 0,
              'maxOutputTokens': 2 * count * 2048 if mode == 'real' else 0,
              'maxInputBytes': 2 * count * 10000 if mode == 'real' else 0,
              'maxInputTokens': None if mode == 'real' else 0,
              'maxCost': None if mode == 'real' else 0}
    target_index = {row['sampleId']: row for row in targets if row.get('sampleId') in sample_ids}
    plan = {'schemaVersion': '1', 'sampleIds': sample_ids, 'strategies': strategies,
            'sourceHashes': {sample: target_index[sample].get('fullSourceHash') for sample in sample_ids},
            'mode': mode, 'snapshotId': state['snapshotId'], 'collection': state.get('collection'),
            'provider': {'endpoint': state.get('endpoint'), 'model': state.get('model')} if mode == 'real' else None,
            'requestBounds': bounds, 'researchEligible': False}
    return {**plan, 'planHash': fingerprint(plan)}


def _append(path, value):
    with path.open('ab') as output:
        output.write(encode(value) + b'\n')
        output.flush()
        os.fsync(output.fileno())
    sync_directory(path.parent)


def _lines(path):
    if not path.is_file():
        return []
    data = path.read_bytes()
    return [decode(line) for line in data.split(b'\n')[:-1]]


def _repair_tail(path):
    if not path.is_file():
        return
    with path.open('r+b') as output:
        data = output.read()
        if data and not data.endswith(b'\n'):
            output.truncate(data.rfind(b'\n') + 1)
            output.flush()
            os.fsync(output.fileno())


def _units(plan):
    return [(sample, strategy) for sample in plan['sampleIds'] for strategy in plan['strategies']]


def _summarize(directory, plan):
    events = _lines(directory / 'events.jsonl')
    samples = _lines(directory / 'samples.jsonl')
    if not events or events[0] != {'kind': 'PLAN', 'planHash': plan['planHash']}:
        raise ValueError('批量计划事件损坏')
    units = _units(plan)
    if any(row.get('kind') != 'STARTED' for row in events[1:]):
        raise ValueError('批量事件类型无效')
    start_list = [(row.get('sampleId'), row.get('strategy')) for row in events[1:]]
    if len(start_list) != len(set(start_list)) or not set(start_list) <= set(units):
        raise ValueError('批量启动事件重复或不属于计划')
    started = set(start_list)
    indexed = {}
    for row in samples:
        key = (row['sampleId'], row['strategy'])
        if key not in units or key in indexed or key not in started:
            raise ValueError('逐样本记录重复或不属于计划')
        indexed[key] = row
    metrics = {}
    pool_conflicts = []
    for sample in plan['sampleIds']:
        hashes = {indexed[(sample, strategy)].get('poolHash') for strategy in plan['strategies']
                  if (sample, strategy) in indexed and indexed[(sample, strategy)].get('poolHash')}
        if len(hashes) > 1:
            pool_conflicts.append(sample)
    for strategy in plan['strategies']:
        rows = [indexed.get((sample, strategy)) for sample in plan['sampleIds']]
        finished = [row for row in rows if row is not None]
        token_fields = ('inputTokens', 'outputTokens')
        usage = {field: sum(row[field] for row in finished) if len(finished) == len(rows)
                 and all(type(row.get(field)) is int for row in finished) else None
                 for field in token_fields}
        metrics[strategy] = {'planned': len(rows), 'completed': sum(row['status'] == 'COMPLETED' for row in finished),
                             'failed': sum(row['status'] != 'COMPLETED' for row in finished),
                             'unknown': sum(row['verdict'] == 'UNKNOWN' for row in finished),
                             'reported': sum(row['status'] == 'COMPLETED' and row.get('conclusion') == 'VULNERABILITY_REPORTED'
                                             for row in finished),
                             'unresolved': sum(row.get('conclusion') == 'UNRESOLVED' for row in finished),
                             'selectedEvidence': sum(row.get('selectedEvidence', 0) for row in finished),
                             'detectionRecall': None, 'precision': None, 'f1': None,
                             'retrievalRecallAtK': None, 'ndcgAtK': None,
                             'wrongSelectedRate': None, 'complementCoverage': None,
                             **usage}
    return {'batchId': directory.name, 'plan': plan, 'status': 'COMPLETED' if len(indexed) == len(units) else 'RUNNING',
            'denominators': {'planned': len(units), 'completed': sum(row['status'] == 'COMPLETED' for row in indexed.values()),
                             'failed': sum(row['status'] != 'COMPLETED' for row in indexed.values()),
                             'unknown': sum(row['verdict'] == 'UNKNOWN' for row in indexed.values()),
                             'pending': len(units) - len(indexed)},
            'metrics': metrics, 'poolConflicts': pool_conflicts, 'requestBounds': plan['requestBounds'],
            'metricBlockers': ['缺少独立审核的目标—案例标签', '缺少真实 tokenizer 与完整聊天模板的同 token 预算',
                               '缺少可验证的安全负例；离线模式为固定空假设'] if plan['mode'] == 'offline' else
                              ['缺少独立审核的目标—案例标签', '缺少真实 tokenizer 与完整聊天模板的同 token 预算',
                               '缺少可验证的安全负例'],
            'researchEligible': False, 'samples': [indexed[key] for key in units if key in indexed]}


def prepare_batch(store, plan, batch_id):
    if not ID.fullmatch(batch_id):
        raise ValueError('批量编号无效')
    directory = Path(store) / batch_id
    directory.mkdir(parents=True, exist_ok=False)
    durable_write(directory / 'plan.json', encode(plan) + b'\n')
    _append(directory / 'events.jsonl', {'kind': 'PLAN', 'planHash': plan['planHash']})
    sync_directory(directory)
    return directory


def run_batch(store, plan, runner, batch_id=None):
    store = Path(store)
    if not isinstance(plan, dict) or plan.get('planHash') != fingerprint({k: v for k, v in plan.items() if k != 'planHash'}):
        raise ValueError('批量计划摘要无效')
    batch_id = batch_id or uuid.uuid4().hex
    if not ID.fullmatch(batch_id):
        raise ValueError('批量编号无效')
    store.mkdir(parents=True, exist_ok=True)
    directory = store / batch_id
    if not directory.is_dir():
        prepare_batch(store, plan, batch_id)
    with exclusive_lock(directory / '.lock'):
        plan_path = directory / 'plan.json'
        if decode(plan_path.read_bytes()) != plan:
            raise ValueError('续跑计划与原计划不一致')
        _repair_tail(directory / 'events.jsonl')
        _repair_tail(directory / 'samples.jsonl')
        events = _lines(directory / 'events.jsonl')
        samples = _lines(directory / 'samples.jsonl')
        started = {(row['sampleId'], row['strategy']) for row in events if row['kind'] == 'STARTED'}
        finished = {(row['sampleId'], row['strategy']) for row in samples}
        for sample, strategy in _units(plan):
            key = (sample, strategy)
            if key in finished:
                continue
            if key in started:
                # 曾开始的请求可能已经计费；续跑只记未决，绝不自动重发。
                row = {'sampleId': sample, 'strategy': strategy, 'status': 'FAILED',
                       'verdict': 'UNKNOWN', 'errorCategory': 'INTERRUPTED_AFTER_START',
                       'inputTokens': None, 'outputTokens': None, 'selectedEvidence': 0}
            else:
                _append(directory / 'events.jsonl', {'kind': 'STARTED', 'sampleId': sample, 'strategy': strategy,
                                                     'at': datetime.now(timezone.utc).isoformat()})
                try:
                    result = runner(sample, plan['mode'], strategy)
                    if (result.get('researchEligible') is not False or result.get('plan', {}).get('sampleId') != sample
                            or result['plan'].get('strategy') != strategy
                            or result['plan'].get('snapshotId') != plan['snapshotId']
                            or result['plan'].get('mode') != plan['mode']):
                        raise ValueError('单样本结果不属于批量计划')
                    expected_source = plan['sourceHashes'][sample]
                    if expected_source is not None and result['plan'].get('sourceHash') != expected_source:
                        raise ValueError('单样本源码与批量计划不一致')
                    row = {'sampleId': sample, 'strategy': strategy, 'status': result['status'],
                           'verdict': result.get('d2', {}).get('verdict', 'UNKNOWN'),
                           'conclusion': result.get('conclusion', 'UNRESOLVED'),
                           'runId': result['runId'], 'poolHash': result['plan'].get('poolHash'),
                           'selectedEvidence': len(result.get('retrieval', {}).get('d1', {}).get('selected', [])),
                           'inputTokens': result.get('model', {}).get('inputTokens'),
                           'outputTokens': result.get('model', {}).get('outputTokens')}
                except Exception:
                    row = {'sampleId': sample, 'strategy': strategy, 'status': 'FAILED',
                           'verdict': 'UNKNOWN', 'errorCategory': 'UNIT_EXECUTION_ERROR',
                           'inputTokens': None, 'outputTokens': None, 'selectedEvidence': 0}
            _append(directory / 'samples.jsonl', row)
            finished.add(key)
        atomic_json(directory / 'summary.json', _summarize(directory, plan))
    return batch_id


def replay_batch(store, batch_id):
    if not isinstance(batch_id, str) or not ID.fullmatch(batch_id):
        raise ValueError('批量编号无效')
    directory = Path(store) / batch_id
    plan = decode((directory / 'plan.json').read_bytes())
    if plan.get('planHash') != fingerprint({k: v for k, v in plan.items() if k != 'planHash'}):
        raise ValueError('批量计划遭到修改')
    return _summarize(directory, plan)
