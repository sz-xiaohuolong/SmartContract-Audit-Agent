"""数据集标签下的三策略逐项审计、断点续跑与可重放指标。"""
import csv
import io
import json
import uuid
from pathlib import Path

from batch_compare import _append, _lines, _repair_tail
from storage import decode, durable_write, exclusive_lock, fingerprint


STRATEGIES = frozenset({'DENSE', 'FIELD_FILTER', 'D1'})


def make_plan(sample_ids, strategies, mode, targets, snapshot_id, provider=None, embedding_profile='bge'):
    indexed = {row['sampleId']: row for row in targets if row.get('runnable')}
    if (not sample_ids or len(set(sample_ids)) != len(sample_ids) or not set(sample_ids) <= set(indexed)
            or not strategies or len(set(strategies)) != len(strategies)
            or not set(strategies) <= STRATEGIES or mode not in ('offline', 'real')
            or not isinstance(snapshot_id, str) or len(snapshot_id) != 64
            or embedding_profile not in ('bge', 'nomic')):
        raise ValueError('自动标注批量计划无效')
    labels = {key: indexed[key]['groundTruth'] for key in sample_ids}
    plan = {'schemaVersion': 'auto-benchmark-1', 'sampleIds': sample_ids,
            'sourceHashes': {key: indexed[key]['sourceHash'] for key in sample_ids},
            'labels': labels, 'strategies': strategies, 'mode': mode,
            'snapshotId': snapshot_id, 'embeddingProfile': embedding_profile,
            'provider': provider if mode == 'real' else None,
            'requestBounds': {'maxRequests': 2 * len(sample_ids) * len(strategies) if mode == 'real' else 0,
                              'maxOutputTokens': 2 * len(sample_ids) * len(strategies) * 2048 if mode == 'real' else 0},
            'researchEligible': False, 'metricTier': 'DATASET_LABEL_EXPLORATORY'}
    return {**plan, 'planHash': fingerprint(plan)}


def _id(value):
    if not isinstance(value, str) or len(value) != 32 or any(char not in '0123456789abcdef' for char in value):
        raise ValueError('批量编号无效')
    return value


def prepare_batch(store, plan, batch_id):
    directory = Path(store) / _id(batch_id)
    directory.mkdir(parents=True, exist_ok=False)
    durable_write(directory / 'plan.json', __import__('storage').encode(plan) + b'\n')
    _append(directory / 'events.jsonl', {'kind': 'PLAN', 'planHash': plan['planHash']})
    return directory


def run_batch(store, plan, runner, batch_id=None):
    if plan.get('planHash') != fingerprint({key: value for key, value in plan.items() if key != 'planHash'}):
        raise ValueError('批量计划摘要无效')
    batch_id = _id(batch_id or uuid.uuid4().hex)
    directory = Path(store) / batch_id
    directory.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(directory / '.lock'):
        plan_path = directory / 'plan.json'
        if plan_path.exists():
            if decode(plan_path.read_bytes()) != plan:
                raise ValueError('续跑计划与原计划不一致')
        else:
            durable_write(plan_path, __import__('storage').encode(plan) + b'\n')
            _append(directory / 'events.jsonl', {'kind': 'PLAN', 'planHash': plan['planHash']})
        _repair_tail(directory / 'events.jsonl')
        _repair_tail(directory / 'samples.jsonl')
        events = _lines(directory / 'events.jsonl')
        samples = _lines(directory / 'samples.jsonl')
        started = {(row['sampleId'], row['strategy']) for row in events if row['kind'] == 'STARTED'}
        finished = {(row['sampleId'], row['strategy']) for row in samples}
        for sample in plan['sampleIds']:
            for strategy in plan['strategies']:
                key = sample, strategy
                if key in finished:
                    continue
                if key in started:
                    value = {'status': 'FAILED', 'prediction': 'UNKNOWN',
                             'errorCategory': 'INTERRUPTED_AFTER_START', 'categoryHit': None,
                             'selectedEvidence': 0, 'inputTokens': None, 'outputTokens': None,
                             'durationMs': None, 'model': {}}
                else:
                    _append(directory / 'events.jsonl', {'kind': 'STARTED',
                            'sampleId': sample, 'strategy': strategy})
                    try:
                        value = runner(sample, strategy, plan['mode'])
                        if (not isinstance(value, dict) or value.get('status') not in ('COMPLETED', 'FAILED')
                                or value.get('prediction') not in ('REPORT', 'NO_REPORT', 'UNKNOWN')
                                or value['status'] == 'FAILED' and value['prediction'] != 'UNKNOWN'):
                            raise ValueError('逐样本审计结果无效')
                    except Exception as error:
                        value = {'status': 'FAILED', 'prediction': 'UNKNOWN',
                                 'errorCategory': type(error).__name__, 'categoryHit': None,
                                 'selectedEvidence': 0, 'inputTokens': None, 'outputTokens': None,
                                 'durationMs': None, 'model': {}}
                row = {**value, 'sampleId': sample, 'strategy': strategy,
                       'sourceHash': plan['sourceHashes'][sample],
                       'snapshotId': plan['snapshotId']}
                _append(directory / 'samples.jsonl', row)
                finished.add(key)
    return batch_id


def _mean(rows, field):
    values = [row[field] for row in rows if type(row.get(field)) is int]
    return sum(values) / len(values) if values else None


def replay_batch(store, batch_id):
    directory = Path(store) / _id(batch_id)
    plan = decode((directory / 'plan.json').read_bytes())
    if plan.get('planHash') != fingerprint({key: value for key, value in plan.items() if key != 'planHash'}):
        raise ValueError('批量计划遭到修改')
    events = _lines(directory / 'events.jsonl')
    if not events or events[0] != {'kind': 'PLAN', 'planHash': plan['planHash']}:
        raise ValueError('批量计划事件损坏')
    units = {(sample, strategy) for sample in plan['sampleIds'] for strategy in plan['strategies']}
    started = {(row['sampleId'], row['strategy']) for row in events[1:] if row.get('kind') == 'STARTED'}
    if len(started) != len(events) - 1 or not started <= units:
        raise ValueError('批量启动事件重复或越界')
    indexed = {}
    for row in _lines(directory / 'samples.jsonl'):
        key = row.get('sampleId'), row.get('strategy')
        if (key not in started or key in indexed or row.get('sourceHash') != plan['sourceHashes'][key[0]]
                or row.get('snapshotId') != plan['snapshotId']):
            raise ValueError('逐样本结果重复或与计划不一致')
        indexed[key] = row
    metrics = {}
    for strategy in plan['strategies']:
        rows = [indexed[key] for key in units if key[1] == strategy and key in indexed]
        classified = [row for row in rows if row['status'] == 'COMPLETED'
                      and row['prediction'] in ('REPORT', 'NO_REPORT')]
        tp = sum(plan['labels'][row['sampleId']]['hasVulnerability'] is True and row['prediction'] == 'REPORT' for row in classified)
        fp = sum(plan['labels'][row['sampleId']]['hasVulnerability'] is False and row['prediction'] == 'REPORT' for row in classified)
        fn = sum(plan['labels'][row['sampleId']]['hasVulnerability'] is True and row['prediction'] == 'NO_REPORT' for row in classified)
        tn = sum(plan['labels'][row['sampleId']]['hasVulnerability'] is False and row['prediction'] == 'NO_REPORT' for row in classified)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = None if precision is None or recall is None else (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0)
        retrieval = [row for row in rows if plan['labels'][row['sampleId']]['hasVulnerability'] is True
                     and row.get('categoryHit') in (True, False)]
        hit = sum(row['categoryHit'] for row in retrieval) / len(retrieval) if retrieval else None
        metrics[strategy] = {'planned': len(plan['sampleIds']), 'completed': sum(row['status'] == 'COMPLETED' for row in rows),
                             'failed': sum(row['status'] == 'FAILED' for row in rows),
                             'unknown': sum(row['prediction'] == 'UNKNOWN' for row in rows),
                             'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
                             'precision': precision, 'recall': recall, 'f1': f1,
                             'retrievalHitAtK': hit, 'retrievalRecallAtK': hit,
                             'retrievalLabelTier': 'MECHANISM_PROXY',
                             'selectedEvidence': sum(row.get('selectedEvidence', 0) for row in rows),
                             'avgInputTokens': _mean(rows, 'inputTokens'),
                             'avgOutputTokens': _mean(rows, 'outputTokens'),
                             'avgDurationMs': _mean(rows, 'durationMs'),
                             'requestAttemptsObserved': sum(row.get('requestAttempts') or 0 for row in rows),
                             'requestAttemptsMissing': sum(row.get('requestAttempts') is None for row in rows),
                             'usageObserved': sum(type(row.get('inputTokens')) is int and type(row.get('outputTokens')) is int for row in rows)}
    samples = [indexed[(sample, strategy)] for sample in plan['sampleIds']
               for strategy in plan['strategies'] if (sample, strategy) in indexed]
    paired_ids = [sample for sample in plan['sampleIds'] if all(
        (sample, strategy) in indexed and indexed[(sample, strategy)]['status'] == 'COMPLETED'
        and indexed[(sample, strategy)]['prediction'] in ('REPORT', 'NO_REPORT')
        for strategy in plan['strategies'])]
    paired_metrics = {}
    for strategy in plan['strategies']:
        rows = [indexed[(sample, strategy)] for sample in paired_ids]
        tp = sum(plan['labels'][row['sampleId']]['hasVulnerability'] and row['prediction'] == 'REPORT' for row in rows)
        fp = sum(not plan['labels'][row['sampleId']]['hasVulnerability'] and row['prediction'] == 'REPORT' for row in rows)
        fn = sum(plan['labels'][row['sampleId']]['hasVulnerability'] and row['prediction'] == 'NO_REPORT' for row in rows)
        tn = sum(not plan['labels'][row['sampleId']]['hasVulnerability'] and row['prediction'] == 'NO_REPORT' for row in rows)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = None if precision is None or recall is None else (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0)
        paired_metrics[strategy] = {'samples': len(paired_ids), 'tp': tp, 'fp': fp, 'fn': fn,
                                    'tn': tn, 'precision': precision, 'recall': recall, 'f1': f1}
    conflicts = [sample for sample in plan['sampleIds'] if len({indexed[(sample, strategy)].get('poolHash')
                 for strategy in plan['strategies'] if (sample, strategy) in indexed
                 and indexed[(sample, strategy)].get('poolHash')}) > 1]
    return {'batchId': batch_id, 'status': 'COMPLETED' if len(samples) == len(units) else 'RUNNING',
            'plan': plan, 'denominators': {'planned': len(units),
                'completed': sum(row['status'] == 'COMPLETED' for row in samples),
                'failed': sum(row['status'] == 'FAILED' for row in samples),
                'unknown': sum(row['prediction'] == 'UNKNOWN' for row in samples),
                'pending': len(units) - len(samples)}, 'metrics': metrics,
            'poolConflicts': conflicts, 'pairedSamples': paired_ids,
            'pairedMetrics': paired_metrics, 'samples': samples, 'researchEligible': False}


def export_csv(report):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['sampleId', 'strategy', 'label', 'labelSource', 'status', 'prediction',
                     'categoryHit', 'selectedEvidence', 'selectedIds', 'poolHash', 'snapshotId',
                     'inputTokens', 'outputTokens', 'durationMs', 'errorCategory', 'retrievalGaps', 'model',
                     'requestAttempts', 'diagnosticPath', 'queryEmbeddingReceipt', 'parseReplay'])
    labels = report['plan']['labels']
    for row in report['samples']:
        label = labels[row['sampleId']]
        writer.writerow([row['sampleId'], row['strategy'], label['hasVulnerability'], label['labelSource'],
                         row['status'], row['prediction'], row.get('categoryHit'),
                         row.get('selectedEvidence'), json.dumps(row.get('selectedIds'), ensure_ascii=False),
                         row.get('poolHash'), row.get('snapshotId'), row.get('inputTokens'),
                         row.get('outputTokens'), row.get('durationMs'), row.get('errorCategory'),
                         json.dumps(row.get('retrievalGaps'), ensure_ascii=False),
                         json.dumps(row.get('model'), ensure_ascii=False), row.get('requestAttempts'), row.get('diagnosticPath'),
                         json.dumps(row.get('queryEmbeddingReceipt'), ensure_ascii=False),
                         json.dumps(row.get('parseReplay'), ensure_ascii=False)])
    return output.getvalue()
