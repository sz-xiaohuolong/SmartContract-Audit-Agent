"""在本机自动标注知识快照上运行可重放的三策略数据集审计。"""
import argparse
import json
from pathlib import Path

from audit_run import model_runner
from benchmark_batch import export_csv, make_plan, replay_batch, run_batch
from benchmark_runtime import BenchmarkRuntime
from benchmark_targets import load_benchmark_targets
from d1_embed import MODEL_MANIFEST, load_local_encoder
from exploratory_corpus import load_corpus
from milvus_rest import MilvusRestIndex
from storage import atomic_json, decode


def prepare_runtime(root, index=None, encoder=None, model=None):
    root = Path(root).resolve()
    corpus = load_corpus(root / '.local/dataset-candidates/r1-pending')
    targets = load_benchmark_targets(root, list(corpus['rows'].values()))
    index = index or MilvusRestIndex('http://127.0.0.1:29531')
    if encoder is None:
        from sentence_transformers import SentenceTransformer
        encoder = load_local_encoder(SentenceTransformer, root / '.local/d1-embedding-model',
                                     decode(MODEL_MANIFEST.read_bytes()))
    runtime = BenchmarkRuntime(root, index, encoder, model or model_runner)
    return targets, runtime


def main():
    parser = argparse.ArgumentParser(description='数据集标签下的自动知识三策略批量审计')
    parser.add_argument('--mode', choices=('offline', 'real'), default='offline')
    parser.add_argument('--sample-ids', nargs='*')
    parser.add_argument('--strategies', nargs='+', default=['DENSE', 'FIELD_FILTER', 'D1'])
    parser.add_argument('--report-dir', default='.local/auto-benchmark-runs')
    parser.add_argument('--batch-id')
    args = parser.parse_args()
    root = Path.cwd()
    targets, runtime = prepare_runtime(root)
    selected = args.sample_ids or [row['sampleId'] for row in targets if row['runnable']]
    provider = None
    if args.mode == 'real':
        from mvp_runtime import _config_values
        config = _config_values(root / 'config/providers.local.properties')
        provider = {'endpoint': config['providers.ark.base-url'], 'model': config['providers.ark.model']}
    plan = make_plan(selected, args.strategies, args.mode, targets,
                     runtime.pointer['snapshot_id'], provider)
    indexed = {row['sampleId']: row for row in targets}
    batch_id = run_batch(root / args.report_dir, plan,
        lambda sample, strategy, mode: runtime.run(indexed[sample], strategy, mode), args.batch_id)
    report = replay_batch(root / args.report_dir, batch_id)
    folder = root / args.report_dir / batch_id
    atomic_json(folder / 'summary.json', report)
    (folder / 'samples.csv').write_text(export_csv(report), encoding='utf-8')
    print(json.dumps({'batchId': batch_id, 'denominators': report['denominators'],
                      'metrics': report['metrics'], 'reportDir': str(folder)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
