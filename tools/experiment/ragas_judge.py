"""显式、限额、零重试的 Ragas 评判适配；原始响应保留于独立运行目录。"""
import asyncio
import importlib.metadata
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from eval_ragas import query_for, reviewed_queries, summarize, validate_dataset
from storage import durable_write, encode, fingerprint


METRICS = ('context_precision', 'context_recall', 'context_relevance', 'faithfulness')


def validate_config(config):
    required = {'baseUrl', 'model', 'apiKeyEnv', 'maxRequests', 'maxOutputTokens', 'timeoutSeconds', 'metrics'}
    if not required <= set(config) or set(config) - required - {'responseFormat', 'temperature'}:
        raise ValueError('评判配置字段不完整或包含未支持字段；凭证只能引用环境变量')
    url = urlsplit(config['baseUrl'])
    if (url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password or url.query or url.fragment
            or url.scheme == 'http' and url.hostname not in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('端点必须显式指定 HTTPS，或本机 HTTP；不能在 URL 中携带凭证')
    for key in ('maxRequests', 'maxOutputTokens'):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError('请求和输出上限必须是正整数')
    if type(config['timeoutSeconds']) not in (int, float) or not 0 < config['timeoutSeconds'] <= 600:
        raise ValueError('请求超时必须在 0 到 600 秒之间')
    if (not isinstance(config['metrics'], list) or not config['metrics']
            or len(set(config['metrics'])) != len(config['metrics']) or not set(config['metrics']) <= set(METRICS)):
        raise ValueError('评估指标无效或重复')
    if config.get('responseFormat', 'json_schema') not in ('json_schema', 'json_object'):
        raise ValueError('仅支持显式 JSON 结构化响应')
    if type(config.get('temperature', 0)) not in (int, float) or not 0 <= config.get('temperature', 0) <= 2:
        raise ValueError('评判温度无效')
    if not all(isinstance(config[k], str) and config[k].strip() for k in ('model', 'apiKeyEnv')):
        raise ValueError('必须显式指定评判模型与凭证环境变量')
    key = os.environ.get(config['apiKeyEnv'])
    if not key:
        raise ValueError('指定的评判凭证环境变量未设置；本地服务也需显式设置占位值')
    return key


def _write(path, data):
    durable_write(path, data)
    path.chmod(0o600)


def _validate_verdicts(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('verdict', 'attributed') and (type(item) is not int or item not in (0, 1)):
                raise ValueError('评判必须返回二值判断')
            if key == 'rating' and (type(item) is not int or item not in (0, 1, 2)):
                raise ValueError('相关性等级无效')
            _validate_verdicts(item)
    elif isinstance(value, list):
        for item in value:
            _validate_verdicts(item)


def _backend(config, api_key, output):
    import httpx
    from openai import AsyncOpenAI, APIStatusError
    from ragas.llms.base import InstructorBaseRagasLLM

    class RecordedLLM(InstructorBaseRagasLLM):
        """只实现 Ragas 所需结构化生成；不使用内部自动重试和默认端点。"""
        def __init__(self):
            self.calls = []
            self.failed = False
            self.failure_reason = None
            self.expected_statements = None
            self.identity = {}
            self.client = AsyncOpenAI(api_key=api_key, base_url=config['baseUrl'], max_retries=0,
                timeout=config['timeoutSeconds'], http_client=httpx.AsyncClient(follow_redirects=False, trust_env=False))

        def generate(self, prompt, response_model):
            raise ValueError('本评估入口只使用顺序异步评分')

        async def agenerate(self, prompt, response_model):
            if self.failed:
                raise ValueError('本指标已有请求失败，禁止隐式重试或部分成功')
            if len(self.calls) >= config['maxRequests']:
                self.failed = True
                self.failure_reason = 'REQUEST_BUDGET_EXHAUSTED'
                raise ValueError('评判请求预算已用尽')
            index = len(self.calls) + 1
            schema = response_model.model_json_schema()
            response_format = {'type': 'json_schema', 'json_schema': {'name': response_model.__name__, 'schema': schema}}
            if config.get('responseFormat') == 'json_object':
                response_format = {'type': 'json_object'}
                prompt += '\n请仅返回符合以下结构的 JSON：\n' + encode(schema).decode('utf-8')
            request = {'model': config['model'], 'messages': [{'role': 'user', 'content': prompt}],
                       'response_format': response_format, 'temperature': config.get('temperature', 0),
                       'max_tokens': config['maxOutputTokens']}
            stem = output / 'requests' / f'{index:05d}'
            request_path = stem.with_suffix('.request.json')
            _write(request_path, encode(request) + b'\n')
            record = {'index': index, **self.identity, 'status': 'STARTED',
                      'startedAt': datetime.now(timezone.utc).isoformat(), 'requestHash': fingerprint(request),
                      'requestArtifact': str(request_path.relative_to(output)), 'responseArtifact': None,
                      'inputTokens': None, 'outputTokens': None, 'errorCategory': None}
            self.calls.append(record)
            # 每次尝试前后落盘；即使进程中断，也能知道哪次可能已发送。
            _write(stem.with_suffix('.started.json'), encode(record) + b'\n')
            try:
                raw = await self.client.chat.completions.with_raw_response.create(**request)
                response_path = stem.with_suffix('.response.json')
                _write(response_path, raw.http_response.content)
                record['responseArtifact'] = str(response_path.relative_to(output))
                result = raw.parse()
                usage = result.usage
                if usage is not None:
                    for field, value in (('inputTokens', usage.prompt_tokens), ('outputTokens', usage.completion_tokens)):
                        record[field] = value if type(value) is int and value >= 0 else None
                if len(result.choices) != 1 or result.choices[0].finish_reason != 'stop':
                    raise ValueError('评判输出未完整结束')
                parsed = response_model.model_validate_json(result.choices[0].message.content, strict=True)
                _validate_verdicts(parsed.model_dump())
                if response_model.__name__ == 'StatementGeneratorOutput':
                    statements = parsed.statements
                    if not statements or any(not s.strip() for s in statements) or len(statements) != len(set(statements)):
                        raise ValueError('忠实度陈述为空或重复，无法确定评分分母')
                    self.expected_statements = statements
                elif response_model.__name__ == 'NLIStatementOutput':
                    actual = [s.statement for s in parsed.statements]
                    if (self.expected_statements is None or len(actual) != len(set(actual))
                            or set(actual) != set(self.expected_statements)):
                        raise ValueError('忠实度逐条判断与待判陈述不完整对应')
                record['status'] = 'COMPLETED'
                return parsed
            except Exception as error:
                self.failed = True
                self.failure_reason = type(error).__name__
                record.update(status='FAILED', errorCategory=type(error).__name__)
                if isinstance(error, APIStatusError):
                    response_path = stem.with_suffix('.response.json')
                    _write(response_path, error.response.content)
                    record.update(responseArtifact=str(response_path.relative_to(output)), httpStatus=error.status_code)
                raise
            finally:
                _write(stem.with_suffix('.receipt.json'), encode(record) + b'\n')

    return RecordedLLM()


async def _evaluate(data, indexed, config, output, api_key):
    from ragas.metrics.collections import ContextPrecision, ContextRecall, ContextRelevance, Faithfulness
    llm = _backend(config, api_key, output)
    constructors = {'context_precision': ContextPrecision, 'context_recall': ContextRecall,
                    'context_relevance': ContextRelevance, 'faithfulness': Faithfulness}
    rows = []
    try:
        for row in data['rows']:
            item = {'sampleId': row['sampleId'], 'strategy': row['strategy'], 'scores': {}, 'metrics': {}}
            for name in config['metrics']:
                llm.failed = False
                llm.failure_reason = None
                llm.expected_statements = None
                llm.identity = {'sampleId': row['sampleId'], 'strategy': row['strategy'], 'metric': name}
                q = query_for(row, indexed)
                detail = {'status': row['inputStatus'], 'value': None, 'requestIndexes': []}
                reference = q.get('reference') if q and q.get('reviewStatus') == 'REVIEWED' else None
                if row['inputStatus'] != 'READY':
                    pass
                elif name != 'faithfulness' and row['strategy'] == 'VANILLA':
                    detail['status'] = 'NOT_APPLICABLE'
                elif name != 'faithfulness' and not row['retrieved_contexts']:
                    detail['status'] = 'EMPTY_RETRIEVAL'
                elif name in ('context_precision', 'context_recall') and not reference:
                    detail['status'] = 'MISSING_REFERENCE'
                elif name == 'faithfulness' and (not row.get('response') or not row.get('hypothesesCount')):
                    detail['status'] = 'NO_VALID_CLAIMS'
                else:
                    start = len(llm.calls)
                    try:
                        kwargs = {'user_input': row['user_input'], 'retrieved_contexts': row['retrieved_contexts']}
                        if name in ('context_precision', 'context_recall'):
                            kwargs['reference'] = reference
                        if name == 'faithfulness':
                            kwargs.update(response=row['response'],
                                retrieved_contexts=['【待审源码与任务】\n' + row['user_input'],
                                    *['【历史参考案例，不是待审合约】\n' + c for c in row['retrieved_contexts']]])
                        scorer = constructors[name](llm=llm, **({'max_retries': 1} if name == 'context_relevance' else {}))
                        result = await scorer.ascore(**kwargs)
                        value = float(result.value)
                        if llm.failed or not math.isfinite(value) or not 0 <= value <= 1:
                            raise ValueError('指标包含失败或非有限评分')
                        detail.update(status='SCORED', value=value)
                    except Exception as error:
                        detail.update(status='FAILED', errorCategory=llm.failure_reason or type(error).__name__)
                    detail['requestIndexes'] = list(range(start + 1, len(llm.calls) + 1))
                item['scores'][name] = detail['value']
                item['metrics'][name] = detail
            item['status'] = 'SCORED' if all(d['status'] in ('SCORED', 'NOT_APPLICABLE') for d in item['metrics'].values()) else 'PARTIAL'
            rows.append(item)
            _write(output / f'row-{len(rows):05d}.json', encode(item) + b'\n')
    finally:
        await llm.client.close()
    missing = sum(c['inputTokens'] is None or c['outputTokens'] is None for c in llm.calls)
    usage = {k: (sum(c[k] for c in llm.calls) if all(c[k] is not None for c in llm.calls) else None)
             for k in ('inputTokens', 'outputTokens')}
    usage['missingRequests'] = missing
    paired = {}
    for name in config['metrics']:
        strategies = sorted({r['strategy'] for r in rows if name == 'faithfulness' or r['strategy'] != 'VANILLA'})
        common = set.intersection(*[{r['sampleId'] for r in rows if r['strategy'] == s and r['scores'][name] is not None}
                                   for s in strategies]) if len(strategies) >= 2 else set()
        common = {sample for sample in common if len({(r['poolHash'], r['sourceHash'], r['snapshotId'])
                  for r in data['rows'] if r['sampleId'] == sample and r['strategy'] in strategies}) == 1}
        paired[name] = {'sampleIds': sorted(common), 'strategies': strategies,
                        'metrics': summarize([r for r in rows if r['sampleId'] in common and r['strategy'] in strategies], [name])}
    return {'schemaVersion': 'ragas-report-1', 'status': 'COMPLETED' if rows and all(r['status'] == 'SCORED' for r in rows) else 'PARTIAL',
            'datasetHash': data['datasetHash'], 'rows': rows, 'strategies': summarize(rows, config['metrics']),
            'requestAttempts': len(llm.calls), 'usage': usage, 'requests': llm.calls, 'paired': paired, 'researchEligible': False,
            'faithfulnessScope': 'TARGET_SOURCE_AND_RETRIEVED_CONTEXTS', 'ragasVersion': '0.4.3'}


def run_judge(data, qrels, config, output, allow_model_requests=False):
    if not allow_model_requests:
        raise ValueError('真实评判需显式启用 --allow-model-requests，并选择端点、模型和请求上限')
    validate_dataset(data)
    indexed = reviewed_queries(data, qrels)
    api_key = validate_config(config)
    # 必须在导入 Ragas 前关闭可选遥测；不向仪表盘上传样本。
    os.environ['RAGAS_DO_NOT_TRACK'] = 'true'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    os.environ['LANGSMITH_TRACING'] = 'false'
    try:
        if importlib.metadata.version('ragas') != '0.4.3':
            raise ValueError('请安装已验证的 Ragas 0.4.3 依赖锁')
        from ragas.metrics import collections  # noqa: F401
    except ImportError as error:
        raise ValueError('Ragas 可选依赖不可用，请按 ragas-requirements.lock 安装') from error
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    (output / 'requests').mkdir(mode=0o700)
    plan = {'datasetHash': data['datasetHash'], 'qrelsHash': fingerprint(qrels), 'config': config,
            'requestRetries': 0, 'ragasVersion': '0.4.3', 'createdAt': datetime.now(timezone.utc).isoformat(),
            'codeHash': fingerprint({name: Path(__file__).with_name(name).read_text(encoding='utf-8')
                                     for name in ('eval_ragas.py', 'ragas_judge.py')}),
            'dependencies': {name: importlib.metadata.version(name) for name in ('ragas', 'openai', 'httpx', 'pydantic', 'langchain-community')}}
    _write(output / 'plan.json', encode(plan) + b'\n')
    report = asyncio.run(_evaluate(data, indexed, config, output, api_key))
    report['planHash'] = fingerprint(plan)
    _write(output / 'report.json', encode(report) + b'\n')
    lines = ['# Ragas 语义评估报告', '',
             f"执行状态：{'完成' if report['status'] == 'COMPLETED' else '部分完成'}；实际请求 {report['requestAttempts']} 次。",
             '这些分数表示评判模型对相关性和证据支撑程度的判断，不参与 D2 裁决，也不等同漏洞正确率。', '',
             '| 策略 | 指标 | 均值 | 有效单元数 |', '| --- | --- | ---: | ---: |']
    for strategy, stats in report['strategies'].items():
        for name in config['metrics']:
            value = stats[name]['mean']
            lines.append(f"| {strategy} | {name} | {'未定义' if value is None else f'{value:.4f}'} | {stats[name]['count']} |")
    lines += ['', '上表使用各策略有效单元；比较算法时应使用 report.json 的 paired 中各指标共同目标统计。',
              '忠实度的证据范围包含待审源码与历史案例。未报告漏洞的样本不做忠实度评分，不记为满分。',
              '缺失参考、空检索、请求失败、预算耗尽及用量缺失均保留在 JSON 中；不同指标可能有不同分母。', '']
    _write(output / 'report.md', '\n'.join(lines).encode('utf-8'))
    return report
