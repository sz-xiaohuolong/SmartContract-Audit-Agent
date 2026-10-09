"""从独立批量报告计算嵌入对照，额外输出所有策略共同有效的分母。"""
import argparse
import csv
import io
import json
from pathlib import Path

from benchmark_batch import replay_batch
from storage import atomic_json


def _metrics(rows, labels):
    tp = sum(labels[row['sampleId']]['hasVulnerability'] and row['prediction'] == 'REPORT' for row in rows)
    fp = sum(not labels[row['sampleId']]['hasVulnerability'] and row['prediction'] == 'REPORT' for row in rows)
    fn = sum(labels[row['sampleId']]['hasVulnerability'] and row['prediction'] == 'NO_REPORT' for row in rows)
    tn = sum(not labels[row['sampleId']]['hasVulnerability'] and row['prediction'] == 'NO_REPORT' for row in rows)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = None if precision is None or recall is None else 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    return {'samples': len(rows), 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': precision, 'recall': recall, 'f1': f1}


def compare_reports(bge, nomic):
    for field in ('sampleIds', 'sourceHashes', 'labels', 'strategies', 'provider', 'mode'):
        if bge['plan'][field] != nomic['plan'][field]:
            raise ValueError('两组实验的目标、标签、策略或模型配置不一致')
    if bge['status'] != 'COMPLETED' or nomic['status'] != 'COMPLETED' or bge['plan']['mode'] != 'real':
        raise ValueError('嵌入对照要求两组已完成真实实验')
    reports = {'bge': bge, 'nomic': nomic}
    indexed = {profile: {(row['sampleId'], row['strategy']): row for row in report['samples']}
               for profile, report in reports.items()}
    strategies = bge['plan']['strategies']
    common = [sample for sample in bge['plan']['sampleIds'] if all(
        indexed[profile].get((sample, strategy), {}).get('status') == 'COMPLETED'
        and indexed[profile][sample, strategy].get('prediction') in ('REPORT', 'NO_REPORT')
        for profile in reports for strategy in strategies)]
    common_metrics = {profile: {strategy: _metrics([rows[sample, strategy] for sample in common],
        bge['plan']['labels']) for strategy in strategies} for profile, rows in indexed.items()}
    changes = {strategy: sum(indexed['bge'][sample, strategy].get('selectedIds') !=
        indexed['nomic'][sample, strategy].get('selectedIds') for sample in bge['plan']['sampleIds'])
        for strategy in strategies}
    query_receipts = {row['sampleId']: row['queryEmbeddingReceipt'] for row in nomic['samples']
                      if isinstance(row.get('queryEmbeddingReceipt'), dict)}
    return {'schemaVersion': 'embedding-compare-1', 'batchIds': {key: value['batchId'] for key, value in reports.items()},
            'metrics': {key: value['metrics'] for key, value in reports.items()},
            'denominators': {key: value['denominators'] for key, value in reports.items()},
            'commonSampleIds': common, 'commonMetrics': common_metrics, 'selectionChanges': changes,
            'nomicQueryTruncation': {'observed': len(query_receipts),
                'truncated': sum(row['truncated'] for row in query_receipts.values())},
            'tokenTotals': {profile: {field: sum(row[field] for row in report['samples']
                if type(row.get(field)) is int) for field in ('inputTokens', 'outputTokens')}
                for profile, report in reports.items()},
            'limitations': ['自动标注改动对不代表已证实修复；仅一次重复',
                '本机 Nomic 有效窗口为 2048，不能标为 8192 实验',
                'Nomic 使用升级后的解析及一次网络重试，旧 BGE 使用旧版；横向结果存在版本混杂',
                '仅限制检索上下文字节，完整提示 token 未等额固定',
                '类别命中属于机制代理标签，不能替代人工相关性召回指标'],
            'researchEligible': False}


def main():
    parser = argparse.ArgumentParser(description='重放两组嵌入实验并导出对比表')
    parser.add_argument('--bge-batch', required=True)
    parser.add_argument('--nomic-batch', required=True)
    parser.add_argument('--store', default='.local/auto-benchmark-runs')
    parser.add_argument('--output-dir', default='.local/embedding-comparison')
    args = parser.parse_args()
    result = compare_reports(replay_batch(args.store, args.bge_batch), replay_batch(args.store, args.nomic_batch))
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / 'comparison.json', result)
    output = io.StringIO()
    writer = csv.writer(output)
    fields = ['planned', 'completed', 'failed', 'unknown', 'tp', 'fp', 'fn', 'tn', 'precision', 'recall', 'f1',
              'retrievalHitAtK', 'avgInputTokens', 'avgOutputTokens', 'avgDurationMs', 'usageObserved',
              'requestAttemptsObserved', 'requestAttemptsMissing']
    writer.writerow(['embedding', 'strategy', *fields])
    for profile, metrics in result['metrics'].items():
        for strategy, row in metrics.items():
            writer.writerow([profile, strategy, *[row.get(key) for key in fields]])
    (directory / 'comparison.csv').write_text(output.getvalue(), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
