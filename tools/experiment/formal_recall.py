"""从正式 Milvus 快照为受限工程目标生成 D1 可审查预览。"""
import re
import subprocess
import tempfile
from pathlib import Path

from d1_embed import MODEL, REVISION, DIMENSION
from audit_target import normalize_target
from formal_targets import load_target
from program_facts import extract_facts
from recall import _recall_candidates
from snapshots import active_snapshot, verify_snapshot, vector32
from storage import decode, encode, fingerprint


SNAPSHOT_ROOT = Path('.local/d1-kb-snapshots')
CONTEXT_BYTES = 4096
STRATEGIES = frozenset({'DENSE', 'FIELD_FILTER', 'D1'})


def select_strategy(view, strategy):
    """在已固定的同一候选池上选择上下文；字节限制不表示 token 公平。"""
    if strategy not in STRATEGIES:
        raise ValueError('检索策略未登记')
    pool = view['pool']
    pool_hash = fingerprint(pool)
    if strategy == 'D1':
        # Java EvidenceBundle 不含执行 status；通过身份校验后以完成状态统一编排契约。
        return dict(view, d1={**view['d1'], 'status': view['d1'].get('status', 'COMPLETED')},
                    strategy='D1', poolHash=pool_hash)
    evaluations = view['d1'].get('evaluations', {})
    selected, parts, used = [], [], 0
    for candidate in pool['candidates']:
        if strategy == 'FIELD_FILTER' and view.get('targetMechanism') is not None and candidate['mechanism'] != view['targetMechanism']:
            continue
        if strategy == 'FIELD_FILTER' and pool.get('schemaVersion') != 'auto-1':
            if candidate['role'] == 'REFERENCE' or not candidate['conditions']:
                continue
            if evaluations.get(candidate['chunkId'], {}).get('applicability') not in ('SUPPORTED', 'CONTRADICTED'):
                continue
        snippet = f"[{candidate['caseId']}/{candidate['chunkId']}|{candidate['role']}]\n{candidate['text']}\n"
        length = len(snippet.encode('utf-8'))
        if used + length > CONTEXT_BYTES or len(selected) == 4:
            continue
        selected.append({'candidate': candidate, 'use': 'SUPPORT'})
        parts.append(snippet)
        used += length
    choice = {'status': 'COMPLETED', 'strategy': strategy, 'selected': selected,
              'context': ''.join(parts), 'gaps': [], 'evaluations': evaluations,
              'poolHash': pool_hash, 'budgetKind': 'UTF8_BYTES'}
    return dict(view, d1=choice, strategy=strategy, poolHash=pool_hash)


def java_retrieval(root, source, request):
    root = Path(root).resolve()
    jar = root / 'audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar'
    if not jar.is_file():
        raise ValueError('请先构建 audit-mvp 离线 JAR')
    with tempfile.TemporaryDirectory(prefix='formal-d1-') as directory:
        directory = Path(directory)
        (directory / 'source.sol').write_text(source, encoding='utf-8')
        (directory / 'request.json').write_bytes(encode(request))
        command = ['java', '-jar', str(jar), '--retrieval', '--source', str(directory / 'source.sol'),
                   '--request', str(directory / 'request.json'),
                   '--worker', str(root / 'tools/experiment/program_facts.py'), '--strategy', 'd1']
        completed = subprocess.run(command, cwd=root, capture_output=True, timeout=30)
        if completed.returncode != 0 or len(completed.stdout) > 8_388_608:
            raise ValueError('Java D1 检索失败')
        return decode(completed.stdout)


def _risk_fact(facts, target, catalog):
    task_kind = target.get('taskKind', 'DISCOVERY')
    if task_kind not in ('DISCOVERY', 'CLAIM_VALIDATION'):
        raise ValueError('正式审计任务类型无效')
    risk_line = target.get('riskLine') if task_kind == 'CLAIM_VALIDATION' else None
    if task_kind == 'CLAIM_VALIDATION' and risk_line is None and target.get('claimOrigin') != 'REGISTERED_FUNCTION_SCOPE':
        return None
    if risk_line is not None and (type(risk_line) is not int or risk_line < 1):
        return None
    risk_kinds = ({'CALL', 'WRITE'} if target['mechanism'] == 'ACCESS_CONTROL'
                  and any(not row['reviewed'] for row in catalog['cases'].values()) else
                  {row['riskKind'] for row in catalog['cases'].values()
                   if row['mechanism'] == target['mechanism']})
    function = target['function'].rsplit('.', 1)[-1]
    contract = target.get('contract') or (target['function'].rsplit('.', 1)[0] if '.' in target['function'] else None)
    scopes = {row['id'] for row in facts['scopes']
              if task_kind == 'DISCOVERY' and target.get('scope') == 'FULL'
              or row['name'] == function and (not contract or row['contract'] == contract)}
    matches = [fact for fact in facts['facts'] if fact['kind'] in risk_kinds
               and fact['scope'] in scopes and (risk_line is None or fact['line'] == risk_line)
               and target['lineStart'] <= fact['line'] <= target['lineEnd']]
    return matches[0] if len(matches) == 1 else None


def preview(root, target, index, encoder, java_runner=None):
    root = Path(root).resolve()
    current = load_target(root, target.get('sampleId'))
    required = ('fullSourceHash', 'modelSourceHash', 'assignmentHash', 'formalLedgerHash', 'scope', 'groupId',
                'function', 'mechanism', 'lineStart', 'lineEnd', 'taskKind', 'riskLine', 'originalSourceHash')
    if any(target.get(key) != current.get(key) for key in required):
        raise ValueError('目标已变化，请重新选择并校验源码')
    current = normalize_target(current)
    store = root / SNAPSHOT_ROOT
    pointer = active_snapshot(store, index)
    if (pointer['backend'] != 'milvus' or not re.fullmatch(r's1b_[0-9a-f]{32}', pointer['collection'])):
        raise ValueError('正式知识快照未激活到受控 Milvus 集合')
    snapshot = verify_snapshot(store, pointer['snapshot_id'])
    if any(row['split'] == 'knowledge'
           and row['source_hash'] in (current['fullSourceHash'], current['originalSourceHash'])
           for row in snapshot['manifest']['samples']):
        raise ValueError('正式查询目标原件或消费源码属于知识划分')
    if snapshot['embedding'] != {'model': MODEL, 'dimension': DIMENSION, 'revision': REVISION}:
        raise ValueError('正式快照与本地固定 BGE 模型不一致')
    catalog = decode((store / 'catalogs' / (pointer['snapshot_id'] + '.json')).read_bytes())
    encoded = encoder([current['modelSource']])
    if len(encoded) != 1:
        raise ValueError('查询模型未返回唯一向量')
    vector = vector32([float(value) for value in encoded[0]], DIMENSION)
    recalled = _recall_candidates(store, pointer['snapshot_id'], catalog, vector,
        current['modelSource'], min(80, len(snapshot['rows'])),
        lambda query, limit: index.search(pointer['collection'], query, limit),
        current['fullSourceHash'], allow_external=True)
    if active_snapshot(store, index) != pointer:
        raise ValueError('查询期间正式知识快照发生变化')
    facts = extract_facts(current['fullSource'])
    if facts['sourceHash'] != current['fullSourceHash'] or facts['status'] == 'FAILED':
        raise ValueError('目标程序事实无法绑定完整源码')
    risk = _risk_fact(facts, current, catalog)
    if risk is None:
        d1 = {'status': 'NO_RISK_FACT', 'selected': [], 'context': '',
              'gaps': ['目标函数没有与正式知识案例风险类型一致的可绑定操作'], 'evaluations': {}}
    else:
        resource = risk['resource'] if risk['kind'] == 'WRITE' else (
            'balances' if current['mechanism'] == 'REENTRANCY' else 'owner')
        request = {'target': {'mechanism': current['mechanism'], 'riskFactId': risk['id'],
                              'bindings': {'actor': 'msg.sender', 'resource': resource, 'authority': resource}},
                   'pool': recalled['pool'], 'budget': {'maxBytes': CONTEXT_BYTES, 'maxCases': 4}}
        result = (java_runner or (lambda source, value: java_retrieval(root, source, value)))(current['fullSource'], request)
        if (not isinstance(result, dict) or not isinstance(result.get('results'), list)
                or len(result['results']) != 1 or result['results'][0].get('strategy') != 'D1'):
            raise ValueError('Java D1 返回结构无效')
        d1 = result['results'][0]
        d1 = {**d1, 'status': 'COMPLETED'}
        if d1.get('sourceHash') != current['fullSourceHash'] or d1.get('snapshotId') != pointer['snapshot_id']:
            raise ValueError('Java D1 结果未绑定目标或正式快照')
        if len(d1.get('context', '').encode('utf-8')) > CONTEXT_BYTES:
            raise ValueError('D1 检索上下文超过硬上限')
    return {'snapshotId': pointer['snapshot_id'], 'collection': pointer['collection'],
            'catalogHash': fingerprint(catalog), 'sampleId': current['sampleId'],
            'sourceHash': current['fullSourceHash'], 'modelSourceHash': current['modelSourceHash'],
            'originalSourceHash': current['originalSourceHash'], 'taskKind': current['taskKind'],
            'inputGovernanceReceipt': current['inputGovernanceReceipt'],
            'scope': current['scope'], 'pool': recalled['pool'], 'recall': recalled['recall'],
            'facts': facts, 'd1': d1, 'researchEligible': False}
