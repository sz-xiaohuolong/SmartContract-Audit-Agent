"""固定开发目标的单样本审计编排与只读回放。"""
import hashlib
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from d2_verify import evaluate
from formal_recall import preview, java_retrieval, select_strategy
from formal_targets import load_target
from storage import atomic_json, decode, durable_write, encode, fingerprint

STORE = Path('.local/audit-runs')
RUN_ID = re.compile(r'[0-9a-f]{32}')
MAX_PROMPT_BYTES = 10_000
HYPOTHESIS_SYSTEM = ('你是智能合约审计员。只输出一个 JSON 对象，不要 Markdown、代码围栏、解释文字或顶层数组。'
                     '对象必须且只能有 schemaVersion 和 hypotheses 两个字段；schemaVersion 固定为字符串 2。'
                     'hypotheses 最多 3 项，每项必须且只能有 vulnerabilityType、contract、function、riskLine、riskOperation、reason、evidenceIds。'
                     'riskLine 是源码左侧标注的绝对整数行号，不是范围或字符串。证据不足时只返回 {"schemaVersion":"2","hypotheses":[]}。'
                     '不得编造合约、函数、行号和证据 ID。')


@dataclass(frozen=True)
class RunDependencies:
    index: object
    encoder: object
    java_retriever: object
    model_runner: object
    tool_runner: object


def _event(path, kind, value=None):
    row = {'at': datetime.now(timezone.utc).isoformat(), 'kind': kind, 'value': value}
    with path.open('ab') as output:
        output.write(encode(row) + b'\n')
        output.flush()
        os.fsync(output.fileno())


def _model_error(category):
    return {'schemaVersion': '2', 'status': 'FAILED', 'conclusion': 'UNRESOLVED',
            'hypotheses': [], 'errorCategory': category, 'validationIssue': None,
            'inputTokens': None, 'outputTokens': None}


def run_once(root: Path, sample_id: str, mode: str, dependencies: RunDependencies, strategy='D1') -> dict:
    root = Path(root).resolve()
    if mode not in ('offline', 'real'):
        raise ValueError('运行模式无效')
    provider = None
    if mode == 'real':
        from mvp_runtime import _config_values
        values = _config_values(root / 'config/providers.local.properties')
        if int(values.get('providers.ark.max-output-tokens', '2048')) > 2048:
            raise ValueError('真实模型输出上限超过 2048')
        provider = {'endpoint': values['providers.ark.base-url'], 'model': values['providers.ark.model']}
    target = load_target(root, sample_id)
    view = select_strategy(preview(root, target, dependencies.index, dependencies.encoder,
                                   dependencies.java_retriever), strategy)
    if view['sourceHash'] != target['fullSourceHash'] or view['modelSourceHash'] != target['modelSourceHash']:
        raise ValueError('检索结果与待审源码不一致')
    context = view['d1'].get('context', '')
    first_line = target['lineStart'] if target['scope'] == 'FUNCTION' else 1
    numbered = '\n'.join(f'{first_line + offset} | {line}'
                         for offset, line in enumerate(target['modelSource'].split('\n')))
    contract = None
    source_lines = target['fullSource'].splitlines()
    for offset, line in enumerate(source_lines, 1):
        found = re.match(r'^\s*(?:abstract\s+)?(?:contract|library|interface)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b', line)
        if found:
            contract = found.group(1)
        if (target['scope'] == 'FUNCTION' and offset == target['lineStart']
                or target['scope'] == 'FULL' and re.match(r'^\s*function\s+' + re.escape(target['function']) + r'\b', line)):
            break
    else:
        contract = None
    contract = contract or '请从完整源码中的真实声明判断'
    ids = selected_ids(view['d1'].get('selected', []))
    # 与 Java 的请求正文保持相同结构，完整消息字节数只用作本地硬上限。
    user_message = ('机制：' + target['mechanism'] + '\n函数：' + target['function']
                    + '\n范围：' + target['scope'] + '，原始行号 '
                    + str(target['lineStart']) + '-' + str(target['lineEnd'])
                    + '\n目标所属合约：' + contract
                    + '\n可引用证据 ID：' + '[' + ', '.join(ids) + ']'
                    + '\n检索上下文：' + context
                    + '\n每条假设的 vulnerabilityType 必须等于上述机制，function 必须等于上述函数；'
                    + '若给出目标所属合约，contract 必须等于该名称；evidenceIds 只能从可引用 ID 中选择，也可以为空数组。'
                    + '\n待审源码（左侧为原始行号）：\n' + numbered)
    message_bytes = len((HYPOTHESIS_SYSTEM + user_message).encode('utf-8'))
    if message_bytes > MAX_PROMPT_BYTES:
        raise ValueError('完整模型输入超过硬上限')
    # 再次读取目标，封闭预览与发起模型之间的源码变化窗口。
    latest = load_target(root, sample_id)
    if any(latest[key] != target[key] for key in ('fullSourceHash', 'modelSourceHash', 'assignmentHash', 'formalLedgerHash')):
        raise ValueError('模型调用前目标源码或谱系变化')
    directory = root / STORE / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    plan = {'schemaVersion': '1', 'runId': directory.name, 'sampleId': sample_id, 'mode': mode,
            'scope': target['scope'], 'lineStart': target['lineStart'], 'lineEnd': target['lineEnd'],
            'sourceHash': target['fullSourceHash'], 'modelSourceHash': target['modelSourceHash'],
            'assignmentHash': target['assignmentHash'], 'formalLedgerHash': target['formalLedgerHash'],
            'groupId': target['groupId'], 'snapshotId': view['snapshotId'], 'collection': view['collection'],
            'strategy': strategy, 'poolHash': view['poolHash'],
            'maxRequests': 0 if mode == 'offline' else 1, 'maxOutputTokens': 2048,
            'maxInputBytes': MAX_PROMPT_BYTES, 'actualInputBytes': message_bytes, 'retries': 0,
            'provider': provider, 'researchEligible': False, 'createdAt': datetime.now(timezone.utc).isoformat()}
    atomic_json(directory / 'plan.json', plan)
    events = directory / 'events.jsonl'
    _event(events, 'PLAN_DURABLE', {'planHash': fingerprint(plan)})
    _event(events, 'D1_READY', {'snapshotId': view['snapshotId'], 'status': view['d1']['status']})
    model = _model_error('MODEL_NOT_STARTED')
    tools = []
    d2 = {'schemaVersion': '1', 'verdict': 'UNKNOWN', 'obligations': [], 'references': []}
    execution_failed = False
    try:
        _event(events, 'MODEL_REQUEST_STARTED', {'mode': mode, 'maxRequests': plan['maxRequests']})
        model = dependencies.model_runner(root, target, view, mode)
        if not isinstance(model, dict) or model.get('status') not in ('COMPLETED', 'FAILED'):
            raise ValueError('模型结果无效')
        raw_response = model.pop('_rawResponse', None)
        if model['status'] == 'FAILED' and isinstance(raw_response, str):
            diagnostic = directory / 'raw-response.txt'
            durable_write(diagnostic, raw_response.encode('utf-8'))
            diagnostic.chmod(0o600)
        if model.get('status') == 'FAILED':
            model = {**_model_error(model.get('errorCategory', 'MODEL_OUTPUT_INVALID')),
                     'validationIssue': model.get('validationIssue'),
                     'inputTokens': model.get('inputTokens'), 'outputTokens': model.get('outputTokens')}
        _event(events, 'MODEL_RESULT', {'status': model['status'], 'conclusion': model.get('conclusion')})
        tools = dependencies.tool_runner(root, target, mode)
        if not isinstance(tools, list): raise ValueError('工具结果无效')
        _event(events, 'TOOL_RESULT', {'statuses': [item.get('status') for item in tools]})
        if model['status'] == 'COMPLETED':
            assessments = [evaluate(item, view['facts'], tools) for item in model.get('hypotheses', [])]
            d2 = {'schemaVersion': '1', 'verdict': 'REFUTED' if any(x['verdict'] == 'REFUTED' for x in assessments)
                  else 'UNKNOWN', 'assessments': assessments}
        _event(events, 'D2_RESULT', {'verdict': d2['verdict']})
    except Exception:
        execution_failed = True
        model = _model_error('MODEL_OR_TOOL_EXECUTION_ERROR') if model.get('status') != 'COMPLETED' else model
        _event(events, 'EXECUTION_FAILED', {'category': 'MODEL_OR_TOOL_EXECUTION_ERROR'})
    failed = execution_failed or model['status'] != 'COMPLETED' or any(item.get('status') not in ('OK', 'SKIPPED') for item in tools)
    result = {'schemaVersion': '1', 'runId': directory.name, 'plan': plan, 'planHash': fingerprint(plan),
              'status': 'FAILED' if failed else 'COMPLETED',
              'conclusion': 'UNRESOLVED' if failed else model.get('conclusion', 'UNRESOLVED'),
              'target': {key: value for key, value in target.items() if key not in ('fullSource', 'modelSource')},
              'retrieval': view, 'model': model, 'tools': tools, 'd2': d2,
              'denominators': {'planned': 1, 'failed': int(failed), 'unknown': int(d2['verdict'] == 'UNKNOWN')},
              'researchEligible': False}
    with (directory / 'sample.jsonl').open('xb') as output:
        output.write(encode({'sampleId': sample_id, 'status': result['status'], 'conclusion': result['conclusion'],
                             'model': model, 'tools': tools, 'd2': d2}) + b'\n')
        output.flush()
        os.fsync(output.fileno())
    atomic_json(directory / 'result.json', result)
    _event(events, 'RUN_COMPLETE', {'status': result['status'], 'resultHash': fingerprint(result)})
    return result


def replay(root: Path, run_id: str) -> dict:
    return replay_at(Path(root).resolve() / STORE, run_id)


def replay_at(store: Path, run_id: str) -> dict:
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError('运行编号无效')
    directory = Path(store) / run_id
    plan = decode((directory / 'plan.json').read_bytes())
    result = decode((directory / 'result.json').read_bytes())
    if result.get('runId') != run_id or result.get('plan') != plan or result.get('planHash') != fingerprint(plan):
        raise ValueError('运行计划或结果遭到修改')
    sample = decode((directory / 'sample.jsonl').read_bytes())
    if (sample.get('sampleId') != plan['sampleId'] or sample.get('model') != result['model']
            or sample.get('tools') != result['tools'] or sample.get('d2') != result['d2']
            or sample.get('status') != result['status'] or sample.get('conclusion') != result['conclusion']):
        raise ValueError('逐样本记录不一致')
    events = [decode(line) for line in (directory / 'events.jsonl').read_bytes().splitlines()]
    if (not events or events[0].get('kind') != 'PLAN_DURABLE'
            or events[0].get('value', {}).get('planHash') != fingerprint(plan)
            or events[-1].get('kind') != 'RUN_COMPLETE'
            or events[-1].get('value', {}).get('resultHash') != fingerprint(result)):
        raise ValueError('运行事件或结果摘要不一致')
    return result


def model_runner(root, target, view, mode):
    if mode == 'offline':
        return {'schemaVersion': '2', 'status': 'COMPLETED', 'conclusion': 'UNRESOLVED',
                'hypotheses': [], 'errorCategory': None, 'inputTokens': None, 'outputTokens': None,
                'fixture': True}
    from mvp_runtime import _config_values
    config = root / 'config/providers.local.properties'
    values = _config_values(config)
    if int(values.get('providers.ark.max-output-tokens', '2048')) > 2048:
        raise ValueError('真实模型输出上限超过 2048')
    jar = root / 'audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar'
    with tempfile.TemporaryDirectory(prefix='audit-hypothesis-') as temp:
        temp = Path(temp)
        (temp / 'source.sol').write_bytes(target['fullSource'].encode('utf-8'))
        ids = selected_ids(view['d1'].get('selected', []))
        request = {'schemaVersion': '1', 'sourceHash': target['fullSourceHash'],
                   'modelSource': target['modelSource'], 'scope': target['scope'],
                   'lineStart': target['lineStart'], 'lineEnd': target['lineEnd'],
                   'mechanism': target['mechanism'], 'function': target['function'],
                   'context': view['d1'].get('context', ''), 'evidenceIds': ids}
        (temp / 'request.json').write_bytes(encode(request))
        provider_config = temp / 'providers.properties'
        provider_config.write_text(config.read_text(encoding='utf-8') +
            '\nproviders.ark.max-output-tokens=2048\nproviders.ark.response-format=json_schema\n'
            'providers.ark.thinking=disabled\n', encoding='utf-8')
        provider_config.chmod(0o600)
        command = ['java', '-jar', str(jar), '--hypotheses', '--source', str(temp / 'source.sol'),
                   '--request', str(temp / 'request.json'), '--config', str(provider_config), '--provider', 'ark',
                   '--diagnostic-output', str(temp / 'raw-response.txt')]
        completed = subprocess.run(command, cwd=root, capture_output=True, timeout=210)
        if completed.returncode not in (0, 1) or len(completed.stdout) > 1_048_576:
            raise ValueError('模型运行未返回受控结果')
        result = decode(completed.stdout)
        diagnostic = temp / 'raw-response.txt'
        if result.get('status') == 'FAILED' and diagnostic.is_file():
            result['_rawResponse'] = diagnostic.read_text(encoding='utf-8')
        return result


def selected_ids(selected):
    ids = []
    for item in selected:
        if isinstance(item, str): ids.append(item)
        elif isinstance(item, dict) and isinstance(item.get('candidate'), dict):
            chunk_id = item['candidate'].get('chunkId')
            if isinstance(chunk_id, str): ids.append(chunk_id)
    if len(ids) != len(selected) or len(set(ids)) != len(ids):
        raise ValueError('D1 入选证据 ID 无效')
    return ids


def tool_runner(root, target, mode):
    if mode == 'offline':
        return [{'engine': 'SLITHER', 'status': 'SKIPPED', 'issues': [], 'durationMs': 0,
                 'version': None, 'reason': '固定离线演练不运行真实静态工具'}]
    if re.search(r'^\s*import\b', target['fullSource'], re.MULTILINE):
        return [{'engine': 'SLITHER', 'status': 'SKIPPED', 'issues': [], 'durationMs': 0,
                 'version': None, 'reason': '目标依赖原项目导入路径与固定编译器版本；单文件环境无法可靠编译，静态工具未运行'}]
    jar = root / 'audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar'
    config = root / 'config/tools.local.properties'
    if not config.is_file():
        return [{'engine': 'SLITHER', 'status': 'NOT_CONFIGURED', 'issues': [], 'durationMs': None, 'version': None}]
    with tempfile.TemporaryDirectory(prefix='audit-tool-') as temp:
        source = Path(temp) / 'source.sol'
        source.write_bytes(target['fullSource'].encode('utf-8'))
        results = []
        configs = config.read_text(encoding='utf-8')
        for engine, timeout in (('slither', 45), ('mythril', 75)):
            if 'tools.' + engine + '.executable=' not in configs:
                if engine == 'mythril': continue
                results.append({'engine': 'SLITHER', 'status': 'NOT_CONFIGURED', 'issues': [],
                                'durationMs': None, 'version': None})
                continue
            try:
                completed = subprocess.run(['java', '-jar', str(jar), '--tools', '--source', str(source),
                                            '--config', str(config), '--engine', engine],
                                           cwd=root, capture_output=True, timeout=timeout)
                if completed.returncode not in (0, 1) or not completed.stdout:
                    raise ValueError('工具输出无效')
                results.append(decode(completed.stdout))
            except (ValueError, OSError, subprocess.TimeoutExpired):
                results.append({'engine': engine.upper(), 'status': 'PROCESS_ERROR', 'issues': [],
                                'durationMs': None, 'version': None})
        return results
