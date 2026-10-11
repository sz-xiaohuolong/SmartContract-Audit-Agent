"""仅从保存的批次重算模型指标、D2 假设口径与中文实验报告，不发起模型请求。"""
import argparse
from collections import Counter
from pathlib import Path

from benchmark_batch import replay_batch
from d2_verify import OBLIGATIONS
from storage import atomic_json, decode


def summarize_d2(report):
    """缺失核验按未知计数；义务状态针对保护，假设裁决针对漏洞。"""
    strategies = {}
    reasons = Counter()
    tools = Counter()
    conclusions = Counter()
    hypotheses = []
    for strategy in report['plan']['strategies']:
        counts = Counter()
        obligations = {name: Counter() for name in OBLIGATIONS}
        rows = [row for row in report['samples'] if row['strategy'] == strategy]
        for row in rows:
            conclusions[row.get('conclusion', 'UNRESOLVED')] += 1
            for tool in row.get('tools', []):
                tools[tool.get('status', 'MISSING')] += 1
            model = row.get('model', {})
            counts['rejectedHypotheses'] += len(model.get('rejectedHypotheses', []))
            assessments = {item.get('hypothesisIndex'): item for item in row.get('d2', {}).get('assessments', [])}
            for index, hypothesis in enumerate(model.get('hypotheses', [])):
                assessment = assessments.get(index, {})
                verdict = assessment.get('verdict', 'UNKNOWN')
                if verdict not in ('SUPPORTED', 'REFUTED', 'UNKNOWN'):
                    raise ValueError('假设裁决状态无效')
                counts[verdict] += 1
                counts['hypotheses'] += 1
                counts['assessmentMissing'] += int(not assessment)
                counts['assessmentFailed'] += int(assessment.get('status') == 'FAILED')
                reason = assessment.get('note') or assessment.get('pathEvidence', {}).get('reason') or '核验记录缺失'
                if verdict == 'UNKNOWN':
                    reasons[reason] += 1
                by_name = {item['name']: item for item in assessment.get('obligations', [])}
                for name in OBLIGATIONS:
                    status = by_name.get(name, {}).get('status', 'UNKNOWN')
                    if status not in ('SUPPORTED', 'REFUTED', 'UNKNOWN'):
                        raise ValueError('保护义务状态无效')
                    obligations[name][status] += 1
                hypotheses.append({'sampleId': row['sampleId'], 'strategy': strategy, 'hypothesisIndex': index,
                                   'hypothesis': hypothesis, 'verdict': verdict, 'reason': reason,
                                   'assessmentPresent': bool(assessment)})
        total = counts['hypotheses']
        for name in ('hypotheses', 'SUPPORTED', 'REFUTED', 'UNKNOWN',
                     'assessmentMissing', 'assessmentFailed', 'rejectedHypotheses'):
            counts.setdefault(name, 0)
        strategies[strategy] = {**counts,
            'supportedRate': counts['SUPPORTED'] / total if total else None,
            'refutationRate': counts['REFUTED'] / total if total else None,
            'unknownRate': counts['UNKNOWN'] / total if total else None,
            'obligations': {name: {status: values[status] for status in ('SUPPORTED', 'REFUTED', 'UNKNOWN')}
                            for name, values in obligations.items()}}
    usage = {field: sum(row[field] for row in report['samples'] if type(row.get(field)) is int)
             for field in ('inputTokens', 'outputTokens', 'requestAttempts')}
    usage['usageMissing'] = sum(type(row.get('inputTokens')) is not int or type(row.get('outputTokens')) is not int
                               for row in report['samples'] if row.get('requestAttempts') != 0)
    usage['requestAttemptsMissing'] = sum(row.get('requestAttempts') is None for row in report['samples'])
    return {'batchId': report['batchId'], 'strategies': strategies, 'unknownReasons': dict(reasons),
            'toolExecutions': dict(tools), 'conclusions': dict(conclusions), 'usage': usage,
            'hypotheses': hypotheses, 'researchEligible': False}


def _number(value):
    return '未定义' if value is None else f'{value:.4f}'


def render_report(report, detail, metadata=None):
    """全部数字来自重放结果；失败与未知不能进入安全真值分母。"""
    plan = report['plan']
    provider = plan.get('provider') or {}
    denominators = report['denominators']
    mode_name = '真实 API' if plan['mode'] == 'real' else '离线'
    lines = [f"# {mode_name} 三策略防御审计报告（批次 {report['batchId']}）", '',
        f"状态：{report['status']}。计划 {denominators['planned']} 单元，模型完成 {denominators['completed']}，"
        f"失败 {denominators['failed']}，模型未知 {denominators['unknown']}，待执行 {denominators['pending']}。", '']
    paired = report['pairedMetrics']
    baselines = [values['f1'] for name, values in paired.items() if name != 'D1' and values['f1'] is not None]
    if baselines and paired.get('D1', {}).get('f1') is not None:
        delta = paired['D1']['f1'] - max(baselines)
        lines += [f"共同有效目标上，D1 的 F1 与最高基线相比，差值为 {delta:+.4f}。"
                  '本次单批、自动标签结果不能证明普遍或显著方法增益。', '']
    total = sum(values['hypotheses'] for values in detail['strategies'].values())
    unknown = sum(values['UNKNOWN'] for values in detail['strategies'].values())
    if total:
        supported = sum(values['SUPPORTED'] for values in detail['strategies'].values())
        refuted = sum(values['REFUTED'] for values in detail['strategies'].values())
        lines += [f"D2 共核验 {total} 条保存假设：支持 {supported}、反驳 {refuted}、未知 {unknown}"
                  f"（{unknown / total:.2%}）。未知仍占多数，不宣称显著下降。", '']
    lines += [
        '## 实验身份与口径', '',
        '| 项目 | 保存结果 |', '| --- | --- |',
        f"| 目标／策略 | {len(plan['sampleIds'])} 个目标 × {'／'.join(plan['strategies'])} |",
        f"| 模型／端点 | {provider.get('model')}／{provider.get('endpoint')} |",
        f"| 嵌入配置／快照 | {plan.get('embeddingProfile')}／{plan['snapshotId']} |",
        f"| 计划摘要 | {plan['planHash']} |",
        f"| 请求／输出上限 | {plan['requestBounds']['maxRequests']} 次／{plan['requestBounds']['maxOutputTokens']} token |",
        f"| 已记录请求尝试 | {detail['usage']['requestAttempts']}；次数缺失 {detail['usage']['requestAttemptsMissing']} 单元 |",
        f"| 输入／输出 token | {detail['usage']['inputTokens']}／{detail['usage']['outputTokens']}；usage 缺失 {detail['usage']['usageMissing']} 个可能请求单元 |",
        f"| 同目标候选池冲突 | {len(report['poolConflicts'])} |", '',
        'Vanilla 的模型检索上下文及证据 ID 均为空。Dense 与 D1 共用同一固定候选池，'
        '检索上下文上限为 4096 UTF-8 字节；该限制不代表精确 token 公平。'
        '同池计算仅用于实验对照，Vanilla 模型不消费检索结果。', '',
        '标签沿用数据集与既有安全对照，知识库为自动标注层；本报告属于探索性标签评测，'
        '不能替代独立审核、正式预注册或整个 R2 研究效果验收。费用缺少价格与账单依据，保留未核实。', '',
        '## 原模型标签指标', '',
        '仅统计有效 REPORT／NO_REPORT。失败和 UNKNOWN 不记入 TN；NO_REPORT 也不构成形式化安全证明。', '',
        '| 策略 | 完成 | 失败 | 输入阻断 | TP | FP | FN | TN | 精确率 | 召回率 | F1 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for strategy, values in report['metrics'].items():
        fields = [strategy, values['completed'], values['failed'], values['inputBlocked'], values['tp'],
                  values['fp'], values['fn'], values['tn'], _number(values['precision']),
                  _number(values['recall']), _number(values['f1'])]
        lines.append('| ' + ' | '.join(map(str, fields)) + ' |')
    lines += ['', f"三策略共同有效目标 {len(report['pairedSamples'])} 个；配对比较使用下表的同一分母。", '',
              '| 策略 | 共同目标 | TP | FP | FN | TN | 精确率 | 召回率 | F1 |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for strategy, values in report['pairedMetrics'].items():
        lines.append('| ' + ' | '.join(map(str, [strategy, values['samples'], values['tp'], values['fp'], values['fn'],
                    values['tn'], _number(values['precision']), _number(values['recall']), _number(values['f1'])])) + ' |')
    lines += ['', '## 请求、检索与耗时', '',
              '| 策略 | 请求尝试 | 输入 token | 输出 token | 完整 usage 单元 | 平均模型耗时（毫秒） | 机制标签命中代理 |',
              '| --- | --- | --- | --- | --- | --- | --- |']
    for strategy, values in report['metrics'].items():
        rows = [row for row in report['samples'] if row['strategy'] == strategy]
        input_tokens = sum(row['inputTokens'] for row in rows if type(row.get('inputTokens')) is int)
        output_tokens = sum(row['outputTokens'] for row in rows if type(row.get('outputTokens')) is int)
        lines.append('| ' + ' | '.join(map(str, [strategy, values['requestAttemptsObserved'], input_tokens, output_tokens,
                    values['usageObserved'], _number(values['avgDurationMs']), _number(values['retrievalHitAtK'])])) + ' |')
    lines += ['', '机制标签命中代理只表示入选案例与目标类别一致，未取得独立适用性标注，'
              '不能当作真实检索 Recall@K。Vanilla 无检索，该指标不适用。']
    lines += ['', '## D2 单元与逐假设裁决', '',
              '漏洞假设的 SUPPORTED 表示已获程序证据与工具佐证，REFUTED 表示该假设的完整保护已获证明。'
              'UNKNOWN 表示证据不足；无假设时的单元 UNKNOWN 与实际候选未知分别计数。', '',
              '| 策略 | 流水线失败 | 单元支持 | 单元反驳 | 单元未知 | 假设数 | 假设支持 | 假设反驳 | 假设未知 | 反驳率 | 未知率 |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for strategy, values in report['metrics'].items():
        d2 = detail['strategies'][strategy]
        lines.append('| ' + ' | '.join(map(str, [strategy, values['pipelineFailed'], values['d2Supported'],
                    values['d2Refuted'], values['d2Unknown'], d2['hypotheses'], d2['SUPPORTED'], d2['REFUTED'], d2['UNKNOWN'],
                    _number(d2['refutationRate']), _number(d2['unknownRate'])])) + ' |')
    lines += ['', '反驳率的分母为保存的有效模型假设；UNKNOWN 只保留未决，不当作已证实误报或安全。'
              '缺失 assessment 仍计入未知。保护义务的 SUPPORTED／REFUTED 针对保护本身，语义与漏洞假设相反。', '',
              '| 策略 | 保护义务 | 保护成立 | 保护被反证 | 保护未知 |', '| --- | --- | --- | --- | --- |']
    for strategy, values in detail['strategies'].items():
        for name, counts in values['obligations'].items():
            lines.append(f"| {strategy} | {name} | {counts['SUPPORTED']} | {counts['REFUTED']} | {counts['UNKNOWN']} |")
    lines += ['', '## 工具、未知原因与输入阻断', '',
              '工具计数的单位为执行项，多合约可能有多项；输入阻断没有工具执行。', '',
              '| 工具状态 | 执行项 |', '| --- | --- |']
    lines += [f'| {status} | {count} |' for status, count in sorted(detail['toolExecutions'].items())]
    lines += ['', '| 假设未知原因 | 假设数 |', '| --- | --- |']
    lines += [f"| {reason.replace('|', '／').replace(chr(10), ' ')} | {count} |"
              for reason, count in sorted(detail['unknownReasons'].items(), key=lambda item: (-item[1], item[0]))]
    lines += ['', '| 阻断目标 | 原因 |', '| --- | --- |']
    lines += [f"| {sample} | {value.get('reason')} |" for sample, value in plan.get('inputEligibility', {}).items()
              if not value['runnable']]
    lines += ['', '## 复现与限制', '',
              '本报告只读取 plan.json、events.jsonl、samples.jsonl，通过计划摘要与逐单元身份校验重算。'
              '原件保存在本机 .local/auto-benchmark-runs/；报告生成不运行模型或静态工具。', '',
              '历史批次与本次发现任务的源码治理、策略及有效样本范围不同，不能将两批未知比例之差解释为同候选的因果改善。'
              'D2 仅证明已支持范围内的特定假设；未覆盖、工具失败、无告警和未报告均不能推断整个合约安全。', '']
    if metadata is not None:
        lines += ['## 本机执行身份与冒烟', '', '| 项目 | 记录 |', '| --- | --- |',
                  f"| 开始／结束（UTC） | {metadata['startedAt']}／{metadata['endedAt']} |",
                  f"| 配置执行前后摘要一致 | {'是' if metadata['configurationUnchanged'] else '否'} |",
                  f"| 工程提交基点 | {metadata['gitHead']} |",
                  f"| 实际 JAR SHA-256 | {metadata['jarHash']} |",
                  f"| 嵌入模型修订 | {metadata['embeddingRevision']} |",
                  f"| 冒烟批次／请求／输入／输出 token | {metadata['smokeBatchId']}／"
                  f"{metadata['smokeRequests']}／{metadata['smokeInputTokens']}／{metadata['smokeOutputTokens']} |", '',
                  *metadata.get('notes', []), '',
                  '原始执行与回归证据：`.evidence/R2-20261010/API-batch-20261011/`。'
                  '源码、测试和报告可版本控制；凭证与新增原始运行记录继续留在本机，不提交到 Git。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='从保存的真实批次生成中文防御审计报告，零模型请求')
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--detail-output', type=Path)
    parser.add_argument('--metadata', type=Path, help='本机执行身份与冒烟的脱敏摘要')
    args = parser.parse_args()
    report = replay_batch(args.run.parent, args.run.name)
    detail = summarize_d2(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    metadata = decode(args.metadata.read_bytes()) if args.metadata else None
    args.output.write_text(render_report(report, detail, metadata), encoding='utf-8')
    if args.detail_output:
        atomic_json(args.detail_output, detail)


if __name__ == '__main__':
    main()
