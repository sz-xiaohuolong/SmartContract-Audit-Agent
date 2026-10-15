"""从冻结批次评估检索排序；可选 Ragas 评分不参与漏洞裁决。"""
import argparse
import hashlib
import math
import re
from collections import Counter
from pathlib import Path

from storage import artifact_exists, decode, durable_write, encode, exclusive_lock, fingerprint, read_artifact


RANK_METRICS = ('precisionAtK', 'poolRecallAtK', 'mrrAtK', 'ndcgAtK')
HEADER = re.compile(r'^\[([^/\n]+)/([^|\n]+)\|[^\]\n]+\]\n', re.MULTILINE)


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def seal(value):
    return {**value, 'datasetHash': fingerprint(value)}


def validate_dataset(data):
    if (data.get('schemaVersion') != 'rag-evaluation-1'
            or data.get('datasetHash') != fingerprint({k: v for k, v in data.items() if k != 'datasetHash'})):
        raise ValueError('评估输入版本或摘要无效')
    keys = [(r['sampleId'], r['strategy']) for r in data['rows']]
    if len(keys) != len(set(keys)):
        raise ValueError('评估输入存在重复单元')


def normalize_row(raw):
    """只读取当时消费的字节；缺收据或函数范围无法恢复时明确弃权。"""
    row = {key: raw.get(key) for key in ('sampleId', 'strategy', 'sourceHash', 'snapshotId', 'poolHash')}
    row.update(inputStatus='MISSING_INPUT', reason='缺少源码、检索或模型输入收据',
               retrieved_contexts=[], retrieved_context_ids=[], poolIds=[], response=None,
               user_input=None, originRowHash=fingerprint(raw))
    if any(raw.get(key) is not None and not isinstance(raw[key], dict) for key in ('retrieval', 'model')):
        row.update(inputStatus='INVALID_INPUT', reason='模型或检索记录不是对象')
        return row
    view, model = raw.get('retrieval') or {}, raw.get('model') or {}
    receipt = model.get('requestConsumptionReceipt')
    if not isinstance(raw.get('source'), str) or not view or not isinstance(receipt, dict):
        return row
    try:
        if receipt.get('schemaVersion') != 'request-consumption-1':
            raise ValueError('模型输入收据版本未登记')
        source, choice = raw['source'], view['d1']
        context, selected = choice['context'], choice['selected']
        for container in (view, view['pool'], choice):
            for key in ('sourceHash', 'snapshotId'):
                if key in container and container[key] != row[key]:
                    raise ValueError('内外层源码或快照身份冲突')
        pool_ids = [c['chunkId'] for c in view['pool']['candidates']]
        ids = [s['candidate']['chunkId'] for s in selected]
        if (sha(source) != row['sourceHash'] or receipt.get('sourceHash') != row['sourceHash']
                or fingerprint(view['pool']) != row['poolHash']
                or len(pool_ids) != len(set(pool_ids)) or len(ids) != len(set(ids))
                or not set(ids) <= set(pool_ids)
                or receipt.get('contextSha256') != sha(context)
                or receipt.get('evidenceIds') != ids):
            raise ValueError('源码、候选池、上下文或证据 ID 与原收据不一致')
        # 当前批次保存清理全文；旧函数范围没有冻结文本时不能猜测起止行。
        if view.get('modelSourceHash') != sha(source) or receipt.get('modelSourceHash') != sha(source):
            row['reason'] = '无法从保存全文恢复当时模型范围，需提供原始消费文本'
            return row
        matches = list(HEADER.finditer(context))
        if (len(matches) != len(ids) or (context and (not matches or matches[0].start() != 0))
                or [m.group(2) for m in matches] != ids
                or [m.group(1) for m in matches] != [s['candidate']['caseId'] for s in selected]
                or row['strategy'] == 'VANILLA' and (context or ids)):
            raise ValueError('实际上下文边界或顺序不能与入选证据一一对应')
        contexts = [context[m.start():matches[i + 1].start() if i + 1 < len(matches) else len(context)]
                    for i, m in enumerate(matches)]
        pool = {c['chunkId']: c for c in view['pool']['candidates']}
        for i, selection in enumerate(selected):
            candidate = pool[ids[i]]
            body = contexts[i][matches[i].end() - matches[i].start():]
            if selection['candidate'] != candidate or body != candidate['text'] + '\n':
                raise ValueError('实际消费片段与人工标注所依据的冻结候选池正文不一致')
        mechanism = view['targetMechanism']
        if mechanism not in ('REENTRANCY', 'ACCESS_CONTROL'):
            raise ValueError('目标机制缺失或未登记')
        response = None
        if raw.get('status') == 'COMPLETED' and model.get('status') == 'COMPLETED' and not model.get('fixture'):
            hypotheses = model.get('hypotheses')
            if isinstance(hypotheses, list) and hypotheses:
                response = '\n'.join(encode(h).decode('utf-8') for h in hypotheses)
            elif hypotheses == [] and model.get('conclusion') == 'NO_CONFIRMED_FINDINGS':
                response = '未报告确认的漏洞；这不代表合约已被证明安全。'
        row.update(inputStatus='READY', reason=None, user_input=f'请审计以下待审源码的 {mechanism} 风险。\n{source}',
                   response=response, retrieved_contexts=contexts, retrieved_context_ids=ids, poolIds=pool_ids,
                   contextSha256=sha(context), modelSourceHash=sha(source),
                   contextBytes=len(context.encode('utf-8')), modelStatus=model.get('status'),
                   hypothesesCount=len(model.get('hypotheses') or []))
    except (KeyError, TypeError, ValueError) as error:
        row.update(inputStatus='INVALID_INPUT', reason=str(error))
    return row


def prepare_dataset(batch, sample_ids=None):
    from benchmark_batch import replay_batch
    batch = Path(batch).resolve()
    with exclusive_lock(batch / '.lock'):
        report = replay_batch(batch.parent, batch.name)
        samples_hash = (hashlib.sha256(read_artifact(batch / 'samples.jsonl')).hexdigest()
                        if artifact_exists(batch / 'samples.jsonl') else None)
    by_key = {(r['sampleId'], r['strategy']): r for r in report['samples']}
    chosen = sample_ids if sample_ids is not None else report['plan']['sampleIds']
    if not chosen or len(set(chosen)) != len(chosen) or not set(chosen) <= set(report['plan']['sampleIds']):
        raise ValueError('所选样本为空、重复或不在原计划中')
    rows = []
    for sample in chosen:
        for strategy in report['plan']['strategies']:
            raw = by_key.get((sample, strategy), {'sampleId': sample, 'strategy': strategy})
            rows.append(normalize_row(raw))
    return seal({'schemaVersion': 'rag-evaluation-1', 'rows': rows,
                 'origin': {'batchId': batch.name, 'batchPath': str(batch), 'mode': report['plan']['mode'],
                            'planHash': report['plan']['planHash'], 'selectedSampleIds': chosen,
                            'samplesSha256': samples_hash},
                 'researchEligible': False})


def qrels_template(data):
    """生成待人工核对的相关性表；不以机制相同或自动标签填真值。"""
    validate_dataset(data)
    queries = {}
    for row in data['rows']:
        if row['inputStatus'] != 'READY':
            continue
        key = (row['sampleId'], row['sourceHash'], row['snapshotId'], row['poolHash'])
        queries[key] = {k: row[k] for k in ('sampleId', 'sourceHash', 'snapshotId', 'poolHash')}
        queries[key].update(reviewStatus='UNREVIEWED', reviewer=None, rationale=None,
                            grades={i: None for i in row['poolIds']}, reference=None)
    return {'schemaVersion': 'rag-qrels-1', 'scope': 'CANDIDATE_POOL', 'queries': list(queries.values())}


def reviewed_queries(data, qrels):
    if qrels is None:
        return {}
    if qrels.get('schemaVersion') != 'rag-qrels-1' or qrels.get('scope') != 'CANDIDATE_POOL':
        raise ValueError('相关性标注必须声明固定候选池范围')
    indexed = {}
    for q in qrels['queries']:
        key = (q['sampleId'], q['sourceHash'], q['snapshotId'], q['poolHash'])
        if key in indexed:
            raise ValueError('相关性标注身份重复')
        rows = [r for r in data['rows'] if r['inputStatus'] == 'READY'
                and tuple(r[k] for k in ('sampleId', 'sourceHash', 'snapshotId', 'poolHash')) == key]
        if not rows:
            raise ValueError('相关性标注与冻结输入身份不一致')
        if q.get('reviewStatus') == 'REVIEWED':
            if (not isinstance(q.get('reviewer'), str) or not q['reviewer'].strip()
                    or not isinstance(q.get('rationale'), str) or not q['rationale'].strip()
                    or set(q['grades']) != set(rows[0]['poolIds'])
                    or any(type(v) is not int or v not in (0, 1, 2) for v in q['grades'].values())
                    or q.get('reference') is not None and (not isinstance(q['reference'], str) or not q['reference'].strip())):
                raise ValueError('人工审核需要完整候选池等级、审核人、依据与有效参考答案')
        elif q.get('reviewStatus') != 'UNREVIEWED':
            raise ValueError('审核状态无效')
        indexed[key] = q
    return indexed


def query_for(row, indexed):
    return indexed.get(tuple(row[k] for k in ('sampleId', 'sourceHash', 'snapshotId', 'poolHash')))


def rank_metrics(ids, grades, k):
    if type(k) is not int or k < 1 or len(ids) != len(set(ids)) or not set(ids) <= set(grades):
        raise ValueError('排序指标要求正整数 k、唯一 ID 及完整标注')
    if any(type(v) is not int or v not in (0, 1, 2) for v in grades.values()):
        raise ValueError('相关等级必须是 0、1 或 2')
    values = [grades[i] for i in ids[:k]]
    hits = sum(v > 0 for v in values)
    relevant = sum(v > 0 for v in grades.values())
    dcg = sum((2 ** v - 1) / math.log2(i + 2) for i, v in enumerate(values))
    ideal = sum((2 ** v - 1) / math.log2(i + 2) for i, v in enumerate(sorted(grades.values(), reverse=True)[:k]))
    return {'precisionAtK': hits / k, 'poolRecallAtK': hits / relevant if relevant else None,
            'mrrAtK': next((1 / (i + 1) for i, v in enumerate(values) if v > 0), 0.0) if relevant else None,
            'ndcgAtK': dcg / ideal if ideal else None}


def summarize(rows, metrics):
    result = {}
    for strategy in sorted({r['strategy'] for r in rows}):
        selected = [r for r in rows if r['strategy'] == strategy]
        result[strategy] = {'planned': len(selected), 'statuses': dict(Counter(r['status'] for r in selected))}
        for metric in metrics:
            values = [r['scores'][metric] for r in selected if r['scores'].get(metric) is not None]
            result[strategy][metric] = {'mean': sum(values) / len(values) if values else None, 'count': len(values)}
    return result


def evaluate_offline(data, qrels=None, k=4):
    validate_dataset(data)
    if type(k) is not int or k < 1:
        raise ValueError('k 必须是正整数')
    indexed = reviewed_queries(data, qrels)
    rows = []
    for row in data['rows']:
        scores = dict.fromkeys(RANK_METRICS)
        status = row['inputStatus']
        if status == 'READY':
            q = query_for(row, indexed)
            if row['strategy'] == 'VANILLA':
                status = 'NOT_APPLICABLE'
            elif not q or q['reviewStatus'] != 'REVIEWED':
                status = 'UNREVIEWED'
            else:
                scores = rank_metrics(row['retrieved_context_ids'], q['grades'], k)
                status = 'SCORED'
        rows.append({'sampleId': row['sampleId'], 'strategy': row['strategy'], 'status': status, 'scores': scores,
                     'reason': row.get('reason'), 'retrievedCount': len(row['retrieved_context_ids']),
                     'poolHash': row['poolHash'], 'sourceHash': row['sourceHash'], 'snapshotId': row['snapshotId']})
    strategies = sorted({r['strategy'] for r in rows if r['strategy'] != 'VANILLA'})
    common = set.intersection(*[{r['sampleId'] for r in rows if r['strategy'] == s and r['status'] == 'SCORED'}
                               for s in strategies]) if len(strategies) >= 2 else set()
    common = {sample for sample in common if len({(r['poolHash'], r['sourceHash'], r['snapshotId'])
              for r in rows if r['sampleId'] == sample and r['strategy'] in strategies}) == 1}
    paired_rows = [r for r in rows if r['sampleId'] in common and r['strategy'] in strategies]
    return {'schemaVersion': 'rag-rank-report-1', 'datasetHash': data['datasetHash'], 'qrelsHash': fingerprint(qrels),
            'k': k, 'scope': 'CANDIDATE_POOL', 'rows': rows, 'strategies': summarize(rows, RANK_METRICS),
            'paired': {'sampleIds': sorted(common), 'strategies': strategies, 'metrics': summarize(paired_rows, RANK_METRICS)},
            'requestAttempts': 0, 'researchEligible': False}


def render_report(report):
    lines = ['# 检索评估报告', '', '本报告使用冻结输入和独立相关性标注；缺失或未审核时保留空分数。', '',
             f"评估输入摘要：`{report['datasetHash']}`。k={report['k']}，评估单位为检索片段。", '',
             '| 策略 | 计划单元 | 已评分 | P@k | 候选池 Recall@k | MRR@k | nDCG@k |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for strategy, stats in report['strategies'].items():
        values = ['未定义' if stats[m]['mean'] is None else f"{stats[m]['mean']:.4f}（n={stats[m]['count']}）" for m in RANK_METRICS]
        lines.append('| ' + ' | '.join([strategy, str(stats['planned']), str(stats['statuses'].get('SCORED', 0)), *values]) + ' |')
    lines += ['', f"共同可比目标：{len(report['paired']['sampleIds'])} 个；比较策略：{'、'.join(report['paired']['strategies'])}。",
              '上表是各策略全部有效单元；共同目标指标单独保存在 JSON 的 paired.metrics 中，不能混用分母。', '',
              'P@k 的分母固定为 k；少返回片段不会提高分数。召回率仅覆盖人工完整审核的候选池，不是整个知识库的召回率。',
              '无检索策略不参加检索评分。所有相关性等级为零时，召回率、MRR 和 nDCG 未定义。',
              'Ragas 语义分数、漏洞发现 F1、定位准确率和 D2 裁决分别报告；本文件不证明 D1 有增益或合约安全。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='冻结批次的检索评估与可选 Ragas 语义评估')
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare', help='零请求导出实际消费文本和待审核相关性表')
    prepare.add_argument('--batch', required=True, type=Path)
    prepare.add_argument('--sample-id', action='append', help='只导出指定样本及原计划中的所有策略；可重复指定')
    prepare.add_argument('--output', required=True, type=Path)
    offline = sub.add_parser('offline', help='零请求计算人工相关性排序指标')
    offline.add_argument('--dataset', required=True, type=Path)
    offline.add_argument('--qrels', type=Path)
    offline.add_argument('--k', type=int, default=4)
    offline.add_argument('--output', required=True, type=Path)
    judge = sub.add_parser('judge', help='使用显式配置的评判模型；会产生请求')
    judge.add_argument('--dataset', required=True, type=Path)
    judge.add_argument('--qrels', type=Path)
    judge.add_argument('--config', required=True, type=Path)
    judge.add_argument('--allow-model-requests', action='store_true')
    judge.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            data = prepare_dataset(args.batch, args.sample_id)
            args.output.mkdir(parents=True, exist_ok=False)
            durable_write(args.output / 'dataset.json', encode(data) + b'\n')
            durable_write(args.output / 'qrels.template.json', encode(qrels_template(data)) + b'\n')
            print(f'已导出 {len(data["rows"])} 个计划单元；模型请求 0 次。')
        else:
            data = decode(read_artifact(args.dataset))
            qrels = decode(read_artifact(args.qrels)) if args.qrels else None
            if args.command == 'judge':
                from ragas_judge import run_judge
                report = run_judge(data, qrels, decode(args.config.read_bytes()), args.output, args.allow_model_requests)
                print(f'语义评估已落盘：{report["status"]}；实际请求 {report["requestAttempts"]} 次。')
                return 0 if report['status'] == 'COMPLETED' else 1
            report = evaluate_offline(data, qrels, args.k)
            args.output.mkdir(parents=True, exist_ok=False)
            durable_write(args.output / 'report.json', encode(report) + b'\n')
            durable_write(args.output / 'report.md', render_report(report).encode('utf-8'))
            print('离线排序评估已落盘；未审核样本不计分，模型请求 0 次。')
        return 0
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f'评估未完成：{error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
