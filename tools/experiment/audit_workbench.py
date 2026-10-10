"""本机单合约六阶段审计：固定知识、显式调用、证据持久化和纯读取回放。"""
import re
import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from audit_run import _event, _model_error, tool_runner
from audit_target import MAX_MODEL_BYTES, hypothesis_matches_target, normalize_target, pasted_target
from d2_verify import evaluate
from formal_recall import CONTEXT_BYTES, STRATEGIES, select_strategy
from storage import atomic_json, decode, fingerprint

RUN_ID = re.compile(r'[0-9a-f]{32}')
STAGES = ('FACTS', 'D1', 'MODEL', 'TOOLS', 'D2', 'REPORT')


def assess(model, facts, tools, source=None, *, target=None):
    assessments = []
    if model.get('status') == 'COMPLETED':
        for index, hypothesis in enumerate(model.get('hypotheses', [])):
            bound = target is None or hypothesis_matches_target(hypothesis, target, source)
            assessment = evaluate(hypothesis, facts, tools, source=source if bound else None)
            if not bound:
                reason = '假设未绑定审计类别、源码或当前范围内的合约与函数'
                assessment['note'] = reason
                assessment['pathEvidence']['reason'] = reason
                for obligation in assessment['obligations']:
                    obligation['reason'] = reason
            assessments.append({**assessment, 'hypothesisIndex': index})
    verdict = 'UNKNOWN'
    if any(row['verdict'] == 'SUPPORTED' for row in assessments):
        verdict = 'SUPPORTED'
    elif (assessments and all(row['verdict'] == 'REFUTED' for row in assessments)
          and not model.get('rejectedHypotheses') and not model.get('validationIssue')):
        verdict = 'REFUTED'
    return {'schemaVersion': '2', 'verdict': verdict, 'verdictSubject': 'VULNERABILITY',
            'scope': target.get('scope') if target is not None else None, 'assessments': assessments}


def final_conclusion(model, d2, failed, mode):
    if failed or mode != 'real' or model.get('fixture') or model.get('status') != 'COMPLETED':
        return 'UNRESOLVED'
    if d2['verdict'] == 'SUPPORTED':
        return 'VULNERABILITY_SUPPORTED'
    if model.get('rejectedHypotheses') or model.get('validationIssue'):
        return 'UNRESOLVED'
    if d2['verdict'] == 'REFUTED':
        return 'HYPOTHESES_REFUTED'
    if not model.get('hypotheses'):
        return 'NO_CONFIRMED_FINDINGS'
    return 'UNRESOLVED'


class AuditWorkbench:
    def __init__(self, root, runtime_factory=None, target_loader=None, tool=tool_runner, store=None):
        self.root = Path(root).resolve()
        self.store = Path(store) if store is not None else self.root / '.local/audit-workbench-runs'
        self.runtime_factory = runtime_factory or self._runtime
        self.target_loader = target_loader or self._targets
        self.tool = tool
        self.running = set()
        self.previews = {}

    def _runtime(self, profile):
        from benchmark_cli import prepare_runtime
        return prepare_runtime(self.root, embedding_profile=profile)[1]

    def _targets(self):
        from benchmark_targets import load_benchmark_targets
        from exploratory_corpus import load_corpus
        from formal_targets import _records
        corpus = load_corpus(self.root / '.local/dataset-candidates/r1-pending')
        rows = load_benchmark_targets(self.root, list(corpus['rows'].values()))
        try:
            existing = {row['sampleId'] for row in rows}
            rows += [row for row in _records(self.root) if row['sampleId'] not in existing]
        except (OSError, ValueError):
            pass
        return rows

    def targets(self):
        return [{key: value for key, value in row.items()
                 if key not in ('source', 'fullSource', 'modelSource', 'originalSource', 'groundTruth', 'vulnerableLines')}
                for row in self.target_loader()]

    def _provider(self, mode):
        if mode == 'offline':
            return None
        from mvp_runtime import _config_values
        values = _config_values(self.root / 'config/providers.local.properties')
        if int(values.get('providers.ark.max-output-tokens', '2048')) > 2048:
            raise ValueError('真实模型输出上限超过 2048')
        return {'model': values['providers.ark.model'], 'endpoint': values['providers.ark.base-url']}

    def _capture_configuration(self, mode):
        if mode == 'offline':
            return {'hash': None, 'provider': None}
        captured, digests = {}, {}
        for name in ('providers.local.properties', 'tools.local.properties'):
            path = self.root / 'config' / name
            content = path.read_bytes() if path.is_file() else None
            captured[name] = content.decode('utf-8') if content is not None else None
            digests[name] = hashlib.sha256(content).hexdigest() if content is not None else None
        from mvp_runtime import _configuration_values, _properties_text
        environment = dict(os.environ)
        provider = _configuration_values(captured['providers.local.properties'], environment)
        if int(provider.get('providers.ark.max-output-tokens', '2048')) > 2048:
            raise ValueError('真实模型输出上限超过 2048')
        credential = provider.get('providers.ark.api-key') or environment.get(provider.get('providers.ark.api-key-env', ''), '')
        digests['credentialHash'] = hashlib.sha256(credential.encode('utf-8')).hexdigest()
        # 只消费校验后的属性，原文本中的分隔与续行不能影响 Java 的读取。
        captured['providers.local.properties'] = _properties_text({**provider, 'providers.ark.api-key': credential})
        return {**captured, 'hash': fingerprint(digests),
                'provider': {'model': provider['providers.ark.model'], 'endpoint': provider['providers.ark.base-url']}}

    def _configuration_hash(self, mode):
        return self._capture_configuration(mode)['hash']

    def status(self, profile='nomic'):
        if profile not in ('nomic', 'bge'):
            raise ValueError('嵌入模型未登记')
        state = {'ready': False, 'embeddingProfile': profile, 'researchEligible': False,
                 'maxRequests': 2, 'maxOutputTokens': 2048, 'contextBytes': CONTEXT_BYTES}
        try:
            provider = self._provider('real')
            state.update(realReady=True, model=provider['model'])
        except (OSError, ValueError, KeyError):
            state['realReady'] = False
        try:
            runtime = self.runtime_factory(profile)
            state.update(ready=True, snapshotId=runtime.pointer['snapshot_id'],
                         dimension=runtime.snapshot['embedding']['dimension'],
                         embedding=runtime.snapshot['embedding'], knowledgeTier='AUTO_LABELED')
        except (OSError, ValueError, RuntimeError, KeyError, ImportError):
            state['reason'] = '固定知识快照或本机嵌入服务暂不可用'
        return state

    def _preview(self, payload, preview_id):
        optional = {'strategy', 'embeddingProfile', 'mode'}
        if not isinstance(payload, dict):
            raise ValueError('请求必须是 JSON 对象')
        if 'sampleId' in payload:
            if set(payload) - ({'sampleId'} | optional) or not isinstance(payload['sampleId'], str):
                raise ValueError('预置样本请求字段无效')
            targets = self.target_loader()
            matches = [row for row in targets if row['sampleId'] == payload['sampleId']]
            if len(matches) != 1:
                raise ValueError('预置样本未登记')
            target = normalize_target(matches[0])
        else:
            if set(payload) - ({'source', 'mechanism', 'function', 'riskLine'} | optional):
                raise ValueError('粘贴源码请求字段无效')
            target = pasted_target(payload.get('source'), payload.get('mechanism'),
                                   payload.get('function'), payload.get('riskLine'))
        mode = payload.get('mode', 'offline')
        profile = payload.get('embeddingProfile', 'nomic')
        strategy = payload.get('strategy', 'D1')
        if mode not in ('offline', 'real') or profile not in ('nomic', 'bge') or strategy not in STRATEGIES:
            raise ValueError('运行模式、嵌入模型或检索策略无效')
        configuration = self._capture_configuration(mode)
        started = monotonic()
        runtime = self.runtime_factory(profile)
        view = select_strategy(runtime.preview(target), strategy)
        view['modelSourceHash'] = target['modelSourceHash']
        if view.get('sourceHash') != target['fullSourceHash']:
            raise ValueError('检索源码摘要与目标不一致')
        context = view['d1'].get('context', '')
        if not isinstance(context, str) or len(context.encode('utf-8')) > CONTEXT_BYTES:
            raise ValueError('检索上下文超过 4096 字节')
        if len((target['modelSource'] + context).encode('utf-8')) > MAX_MODEL_BYTES + CONTEXT_BYTES:
            raise ValueError('模型源码与上下文超过单次输入上限')
        duration = round((monotonic() - started) * 1000)
        plan = {'schemaVersion': '2', 'pipelineVersion': 's9-v1', 'sampleId': target['sampleId'],
                'taskKind': target.get('taskKind', 'DISCOVERY'),
                'originalSourceHash': target.get('originalSourceHash'),
                'inputGovernanceReceipt': target.get('inputGovernanceReceipt'),
                'previewId': preview_id,
                'mode': mode, 'strategy': strategy, 'embeddingProfile': profile,
                'sourceHash': target['fullSourceHash'], 'modelSourceHash': target['modelSourceHash'],
                'targetHash': fingerprint(target), 'retrievalHash': fingerprint(view),
                'poolHash': fingerprint(view['pool']), 'snapshotId': view['snapshotId'],
                'embedding': runtime.snapshot['embedding'], 'maxContextBytes': CONTEXT_BYTES,
                'configurationHash': configuration['hash'],
                'contextBytes': len(context.encode('utf-8')), 'maxOutputTokens': 2048,
                'maxRequests': 2 if mode == 'real' else 0, 'provider': configuration['provider'], 'researchEligible': False}
        return {'target': target, 'retrieval': view, 'plan': plan, 'planHash': fingerprint(plan),
                'embedding': runtime.snapshot['embedding'], 'previewDurationMs': duration}, runtime, configuration

    def preview(self, payload):
        value = self._preview(payload, uuid.uuid4().hex)[0]
        now = monotonic()
        self.previews = {key: row for key, row in self.previews.items() if row['expires'] > now}
        if len(self.previews) >= 128:
            self.previews.pop(next(iter(self.previews)))
        self.previews[value['planHash']] = {'previewId': value['plan']['previewId'], 'expires': now + 600}
        return value

    def prepare(self, payload):
        if not isinstance(payload, dict) or 'planHash' not in payload:
            raise ValueError('请先预览并确认输入')
        choice = {key: value for key, value in payload.items() if key != 'planHash'}
        ticket = self.previews.get(payload['planHash'])
        if ticket is None or ticket['expires'] <= monotonic():
            raise ValueError('预览已过期或已用于运行，请重新预览')
        prepared, runtime, configuration = self._preview(choice, ticket['previewId'])
        if payload['planHash'] != prepared['planHash']:
            raise ValueError('源码、模式、配置或知识预览已改变，请重新预览')
        run_id = uuid.uuid4().hex
        directory = self.store / run_id
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        plan = {**prepared['plan'], 'runId': run_id, 'createdAt': datetime.now(timezone.utc).isoformat()}
        atomic_json(directory / 'plan.json', plan)
        atomic_json(directory / 'target.json', prepared['target'])
        atomic_json(directory / 'preview.json', prepared['retrieval'])
        _event(directory / 'events.jsonl', 'PLAN_DURABLE', {'planHash': fingerprint(plan)})
        self.running.add(run_id)
        self.previews.pop(payload['planHash'])
        return {**prepared, 'plan': plan, 'planHash': fingerprint(plan), 'runId': run_id,
                'runtime': runtime, '_configuration': configuration}

    def execute(self, prepared):
        identifier = prepared['runId']
        directory = self.store / identifier
        events = directory / 'events.jsonl'
        target, view, plan = prepared['target'], prepared['retrieval'], prepared['plan']
        configuration = prepared.pop('_configuration', {})
        temporary = tempfile.TemporaryDirectory(prefix='audit-config-')
        model, tools = _model_error('MODEL_NOT_STARTED'), []
        d2 = {'schemaVersion': '2', 'verdict': 'UNKNOWN', 'assessments': []}
        stages, errors = [], []
        def stage(name, status, duration, reason=None):
            row = {'name': name, 'status': status, 'durationMs': duration, 'reason': reason}
            stages.append(row)
            _event(events, name + '_RESULT', row)
        def finish(failed, conclusion):
            result = {'schemaVersion': '2', 'runId': identifier, 'plan': plan, 'planHash': fingerprint(plan),
                      'status': 'FAILED' if failed else 'COMPLETED', 'conclusion': conclusion,
                      'target': target, 'retrieval': view, 'model': model, 'tools': tools, 'd2': d2,
                      'stages': stages, 'errors': errors, 'researchEligible': False,
                      'denominators': {'planned': 1, 'failed': int(failed),
                                       'unknown': int(conclusion == 'UNRESOLVED')}}
            atomic_json(directory / 'sample.jsonl', result)
            atomic_json(directory / 'result.json', result)
            _event(events, 'RUN_COMPLETE', {'resultHash': fingerprint(result)})
            return result
        try:
            if (fingerprint(target) != plan['targetHash'] or fingerprint(view) != plan['retrievalHash']):
                raise ValueError('执行输入已改变')
            if self._configuration_hash(plan['mode']) != plan['configurationHash']:
                raise ValueError('真实模型或工具配置已改变')
            if configuration.get('hash') != plan['configurationHash']:
                raise ValueError('冻结配置与运行计划不一致')
            call_target = dict(target)
            if plan['mode'] == 'real':
                for name, field in (('providers.local.properties', '_providerConfigPath'),
                                    ('tools.local.properties', '_toolConfigPath')):
                    path = Path(temporary.name) / name
                    content = configuration[name]
                    if content is not None:
                        path.touch(mode=0o600)
                        path.write_text(content, encoding='utf-8')
                    call_target[field] = str(path)
            configuration.clear()
            runtime = prepared['runtime']
            if hasattr(runtime, 'store') and decode((runtime.store / 'active.json').read_bytes()) != runtime.pointer:
                raise ValueError('执行前知识快照已改变')
            stage('FACTS', view['facts']['status'], 0, '受限语法结构与程序事实已在预览绑定')
            stage('D1', view['d1']['status'], prepared['previewDurationMs'])
            for name in ('MODEL', 'TOOLS', 'D2'):
                _event(events, name + '_STARTED', {'mode': plan['mode']})
                started = monotonic()
                try:
                    if name == 'MODEL':
                        candidate = prepared['runtime'].model_runner(self.root, call_target, view, plan['mode'])
                        if not isinstance(candidate, dict) or candidate.get('status') not in ('COMPLETED', 'FAILED'):
                            raise ValueError('模型结果无效')
                        # 原始诊断不进入浏览器；失败信息保持结构化并且 usage 缺失为 null。
                        model = {key: value for key, value in candidate.items() if key != '_rawResponse'}
                        raw = candidate.get('_rawResponse')
                        if isinstance(raw, str):
                            from storage import durable_write
                            diagnostic = directory / 'raw-response.txt'
                            durable_write(diagnostic, raw.encode('utf-8'))
                            diagnostic.chmod(0o600)
                        if model['status'] == 'FAILED':
                            errors.append('MODEL_FAILED')
                        status = model['status']
                    elif name == 'TOOLS':
                        tools = self.tool(self.root, call_target, plan['mode'])
                        if not isinstance(tools, list) or not tools or any(not isinstance(row, dict) for row in tools):
                            raise ValueError('工具结果缺失或无效')
                        failed_tools = any(row.get('status') not in ('OK', 'SKIPPED') for row in tools)
                        if failed_tools:
                            errors.append('TOOLS_FAILED')
                        status = 'FAILED' if failed_tools else 'SKIPPED' if all(row['status'] == 'SKIPPED' for row in tools) else 'COMPLETED'
                    else:
                        d2 = assess(model, view['facts'], tools, target['fullSource'], target=target)
                        status = d2['verdict']
                    stage(name, status, round((monotonic() - started) * 1000))
                except Exception:
                    errors.append(name + '_EXECUTION_ERROR')
                    if name == 'MODEL':
                        model = _model_error('MODEL_EXECUTION_ERROR')
                    elif name == 'TOOLS':
                        tools = [{'engine': 'SLITHER', 'status': 'PROCESS_ERROR', 'issues': [],
                                  'durationMs': round((monotonic() - started) * 1000), 'version': None}]
                    stage(name, 'FAILED', round((monotonic() - started) * 1000), '阶段执行失败，判断保持未决')
            failed = bool(errors) or view['facts']['status'] == 'FAILED'
            conclusion = final_conclusion(model, d2, failed, plan['mode'])
            stage('REPORT', 'COMPLETED', 0)
            return finish(failed, conclusion)
        except Exception:
            errors.append('PIPELINE_EXECUTION_ERROR')
            for name in STAGES[len(stages):]:
                stage(name, 'FAILED' if name != 'REPORT' else 'COMPLETED', 0,
                      '执行身份校验或前置阶段失败，未追加模型调用')
            return finish(True, 'UNRESOLVED')
        finally:
            configuration.clear()
            temporary.cleanup()
            self.running.discard(identifier)

    def read(self, identifier):
        if not isinstance(identifier, str) or not RUN_ID.fullmatch(identifier):
            raise ValueError('运行编号无效')
        directory = self.store / identifier
        plan = decode((directory / 'plan.json').read_bytes())
        target = decode((directory / 'target.json').read_bytes())
        view = decode((directory / 'preview.json').read_bytes())
        if plan['runId'] != identifier or fingerprint(target) != plan['targetHash'] or fingerprint(view) != plan['retrievalHash']:
            raise ValueError('运行目标或检索快照被修改')
        event_bytes = (directory / 'events.jsonl').read_bytes()
        events = [decode(line) for line in event_bytes.splitlines()]
        if not events or events[0]['value']['planHash'] != fingerprint(plan):
            raise ValueError('运行计划摘要不一致')
        if not (directory / 'result.json').is_file():
            return {'runId': identifier, 'status': 'RUNNING' if identifier in self.running else 'INTERRUPTED',
                    'events': events, 'plan': plan, 'target': target, 'retrieval': view}
        result = decode((directory / 'result.json').read_bytes())
        if (result.get('plan') != plan or result.get('planHash') != fingerprint(plan)
                or result.get('target') != target or result.get('retrieval') != view
                or result != decode((directory / 'sample.jsonl').read_bytes())
                or events[-1].get('kind') != 'RUN_COMPLETE'
                or events[-1].get('value', {}).get('resultHash') != fingerprint(result)):
            # 写入末尾事件之前属于正在封口的瞬间，轮询应继续等候。
            if identifier in self.running:
                return {'runId': identifier, 'status': 'RUNNING', 'events': events}
            raise ValueError('报告、逐样本文件或完成摘要不一致')
        return result

    def history(self):
        rows = []
        for path in self.store.glob('*/plan.json'):
            if RUN_ID.fullmatch(path.parent.name):
                try:
                    result = self.read(path.parent.name)
                    rows.append({'runId': path.parent.name, 'status': result['status'],
                                 'createdAt': result['plan']['createdAt'], 'sampleId': result['plan']['sampleId']})
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(rows, key=lambda row: row['createdAt'], reverse=True)[:50]

    def report(self, identifier):
        if self.read(identifier)['status'] not in ('COMPLETED', 'FAILED'):
            raise ValueError('运行尚未形成完整报告')
        return (self.store / identifier / 'sample.jsonl').read_bytes()
