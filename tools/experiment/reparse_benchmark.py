"""离线重放批量解析失败原文，另存派生报告并保留原始调用费用。"""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from benchmark_batch import export_csv, replay_batch, run_batch
from benchmark_runtime import interpret_model
from benchmark_targets import load_benchmark_targets
from exploratory_corpus import load_corpus
from storage import atomic_json, decode, encode, fingerprint


def reparse_rows(report, targets, root, parser, parser_hash):
    root = Path(root).resolve()
    rows = []
    for original in report['samples']:
        row = dict(original)
        if row.get('errorCategory') == 'MODEL_OUTPUT_INVALID' and row.get('diagnosticPath'):
            target = targets[row['sampleId']]
            if row['sourceHash'] != target['sourceHash']:
                raise ValueError('重放目标源码与原始实验不一致')
            raw = (root / row['diagnosticPath']).resolve()
            if not raw.is_relative_to(root / '.local/auto-benchmark-diagnostics') or not raw.is_file():
                raise ValueError('重放原文路径超出本机诊断目录')
            result = parser(target, row, raw)
            if not isinstance(result, dict) or result.get('status') not in ('COMPLETED', 'FAILED'):
                raise ValueError('重放解析结果无效')
            # 原始模型用量和调用时长属于已发生的实验，不能被零请求重放抹去。
            model = {**row['model'], **result, **{key: row.get(key)
                     for key in ('inputTokens', 'outputTokens', 'requestAttempts')},
                     'durationMs': row['model'].get('durationMs')}
            row.update(model=model, status=model['status'], prediction=interpret_model(model, 'real'),
                errorCategory=model.get('errorCategory'), parseReplay={
                    'originalBatchId': report['batchId'], 'originalStatus': original['status'],
                    'originalValidationIssue': original['model'].get('validationIssue'),
                    'rawHash': hashlib.sha256(raw.read_bytes()).hexdigest(),
                    'parserJarHash': parser_hash, 'additionalModelRequests': 0})
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description='不调用模型地重放结构化输出失败')
    parser.add_argument('--batch-id', required=True)
    parser.add_argument('--store', default='.local/auto-benchmark-runs')
    parser.add_argument('--output-id')
    args = parser.parse_args()
    root = Path.cwd()
    report = replay_batch(args.store, args.batch_id)
    if report['status'] != 'COMPLETED':
        raise ValueError('原批量尚未完成，不能发布派生评估')
    corpus = load_corpus(root / '.local/dataset-candidates/r1-pending')
    targets = {row['sampleId']: row for row in load_benchmark_targets(root, list(corpus['rows'].values()))}
    jar = root / 'audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar'
    jar_hash = hashlib.sha256(jar.read_bytes()).hexdigest()
    def parse(target, row, raw):
        with tempfile.TemporaryDirectory(prefix='audit-reparse-') as directory:
            directory = Path(directory)
            source = directory / 'source.sol'
            source.write_text(target['fullSource'], encoding='utf-8')
            request = directory / 'request.json'
            request.write_bytes(encode({'schemaVersion': '1', 'sourceHash': target['sourceHash'],
                **{key: target[key] for key in ('modelSource', 'scope', 'lineStart', 'lineEnd', 'mechanism', 'function')},
                'context': '', 'evidenceIds': row['selectedIds']}))
            completed = subprocess.run(['java', '-jar', str(jar), '--hypotheses', '--source', str(source),
                '--request', str(request), '--replay-response', str(raw)], capture_output=True, timeout=30)
            if completed.returncode not in (0, 1):
                raise ValueError('本机原文重放 CLI 失败')
            return decode(completed.stdout)
    rows = reparse_rows(report, targets, root, parse, jar_hash)
    indexed = {(row['sampleId'], row['strategy']): row for row in rows}
    plan = {key: value for key, value in report['plan'].items() if key != 'planHash'}
    plan['parseReplay'] = {'originalBatchId': args.batch_id, 'parserJarHash': jar_hash, 'additionalModelRequests': 0}
    plan['planHash'] = fingerprint(plan)
    batch_id = run_batch(args.store, plan, lambda sample, strategy, mode: indexed[sample, strategy], args.output_id)
    replayed = replay_batch(args.store, batch_id)
    folder = Path(args.store) / batch_id
    atomic_json(folder / 'summary.json', replayed)
    (folder / 'samples.csv').write_text(export_csv(replayed), encoding='utf-8')
    print(json.dumps({'batchId': batch_id, 'originalBatchId': args.batch_id,
        'reparsed': sum('parseReplay' in row for row in rows), 'denominators': replayed['denominators'],
        'additionalModelRequests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
