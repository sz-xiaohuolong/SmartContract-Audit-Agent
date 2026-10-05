"""从正式 Milvus 快照为受限工程目标生成 D1 可审查预览。"""
import re
import subprocess
import tempfile
from pathlib import Path

from d1_embed import MODEL, REVISION, DIMENSION
from formal_targets import load_target
from program_facts import extract_facts
from recall import _recall_candidates
from snapshots import active_snapshot, verify_snapshot, vector32
from storage import decode, encode, fingerprint


SNAPSHOT_ROOT = Path('.local/d1-kb-snapshots')
CONTEXT_BYTES = 2048


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
    risk_kinds = {row['riskKind'] for row in catalog['cases'].values()
                  if row['mechanism'] == target['mechanism']}
    matches = [fact for fact in facts['facts'] if fact['kind'] in risk_kinds
               and target['function'] in fact['scope']
               and target['lineStart'] <= fact['line'] <= target['lineEnd']]
    if target['sampleId'] == 'RE-SCRUBD-001':
        matches = [fact for fact in matches if fact['line'] == 608 and fact['kind'] == 'CALL']
    return matches[0] if len(matches) == 1 else None


def preview(root, target, index, encoder, java_runner=None):
    root = Path(root).resolve()
    current = load_target(root, target.get('sampleId'))
    required = ('fullSourceHash', 'modelSourceHash', 'assignmentHash', 'formalLedgerHash', 'scope', 'groupId')
    if any(target.get(key) != current[key] for key in required):
        raise ValueError('目标已变化，请重新选择并校验源码')
    store = root / SNAPSHOT_ROOT
    pointer = active_snapshot(store, index)
    if (pointer['backend'] != 'milvus' or not re.fullmatch(r's1b_[0-9a-f]{32}', pointer['collection'])):
        raise ValueError('正式知识快照未激活到受控 Milvus 集合')
    snapshot = verify_snapshot(store, pointer['snapshot_id'])
    if snapshot['embedding'] != {'model': MODEL, 'dimension': DIMENSION, 'revision': REVISION}:
        raise ValueError('正式快照与本地固定 BGE 模型不一致')
    catalog = decode((store / 'catalogs' / (pointer['snapshot_id'] + '.json')).read_bytes())
    encoded = encoder([current['modelSource']])
    if len(encoded) != 1:
        raise ValueError('查询模型未返回唯一向量')
    vector = vector32([float(value) for value in encoded[0]], DIMENSION)
    recalled = _recall_candidates(store, pointer['snapshot_id'], catalog, vector,
        current['modelSource'], len(snapshot['rows']),
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
        resource = 'balances' if current['mechanism'] == 'REENTRANCY' else 'owner'
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
            'scope': current['scope'], 'pool': recalled['pool'], 'recall': recalled['recall'],
            'facts': facts, 'd1': d1, 'researchEligible': False}
