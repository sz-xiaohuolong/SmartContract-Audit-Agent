"""本机真实案例向量检索与单次模型工程试跑；不产生研究真值。"""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from first_batch import prepare
from milvus_rest import MilvusRestIndex
from snapshots import _check_index, vector32
from storage import atomic_json, decode, encode, fingerprint


ROOT = Path(__file__).resolve().parents[2]
INTAKE = ROOT / 'docs/vibe/releases/R1-S3/evidence/first-batch-intake.json'
ASSIGNMENT = ROOT / 'docs/vibe/releases/R1-S3/evidence/first-batch-assignment.json'
SOURCE_DIR = '.local/first-batch/sources'
DIMENSION = 128


class MvpIndex(MilvusRestIndex):
    @staticmethod
    def collection(name):
        if not isinstance(name, str) or not re.fullmatch(r'mvp_[0-9a-f]{32}', name):
            raise ValueError('只允许工程 MVP 专用集合')
        return name


def embed(text):
    values = [0.0] * DIMENSION
    for word in re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*|[\u4e00-\u9fff]+', text.lower()):
        slot = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], 'big') % DIMENSION
        values[slot] += 1.0
    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        raise ValueError('不能为无内容文本建立向量')
    return vector32([value / norm for value in values], DIMENSION)


def excerpt(source, function, before=3, after=30):
    lines = source.splitlines()
    indexes = [index for index, line in enumerate(lines) if re.search(r'\bfunction\s+' + re.escape(function) + r'\s*\(', line)]
    if len(indexes) != 1:
        raise ValueError(function + ' 函数定位不唯一')
    start = max(0, indexes[0] - before)
    return '\n'.join(lines[start:min(len(lines), indexes[0] + after)])


def candidate_payload(root=ROOT):
    intake = decode((root / INTAKE.relative_to(ROOT)).read_bytes())
    assignment = decode((root / ASSIGNMENT.relative_to(ROOT)).read_bytes())
    ledger, isolation = prepare(intake, assignment, root, SOURCE_DIR)
    if not isolation['ok'] or isolation['splitCounts']['knowledge'] != 2:
        raise ValueError('首批知识候选隔离不合格')
    samples = {row['id']: row for row in ledger['samples']}
    required = {'AC-ASE-040', 'RE-POP-077'}
    if {row['id'] for row in ledger['samples'] if row['split'] == 'knowledge'} != required:
        raise ValueError('知识候选与固定分配不一致')
    docs = []
    for identifier, function, role in [('AC-ASE-040', 'mintYieldFee', 'VULNERABLE'),
                                       ('RE-POP-077', 'claimRewards', 'VULNERABLE')]:
        row = samples[identifier]
        source = (root / row['path']).read_text(encoding='utf-8')
        docs.append({'id': identifier + '-original', 'sampleId': identifier,
                     'groupId': row['patchPairId'], 'role': role, 'sourceHash': row['sourceHash'],
                     'text': excerpt(source, function)})
    patch = (root / '.local/first-batch/patches/AC-ASE-040.sol').read_text(encoding='utf-8')
    patch_artifact = next(item for item in samples['AC-ASE-040']['artifacts'] if item['kind'] == 'PATCH')
    docs.append({'id': 'AC-ASE-040-patch', 'sampleId': 'AC-ASE-040',
                 'groupId': samples['AC-ASE-040']['patchPairId'], 'role': 'PATCH_CONTEXT',
                 'sourceHash': patch_artifact['sha256'], 'text': excerpt(patch, 'mintYieldFee')})
    rows = [{'id': fingerprint(doc['id']), 'document': doc, 'vector': embed(doc['text'])} for doc in docs]
    return {'purpose': 'ENGINEERING_MVP', 'researchEligible': False, 'lineageHash': isolation['ledgerHash'],
            'embedding': {'model': 'local-hash-lexical-v1', 'dimension': DIMENSION, 'revision': '1'},
            'rows': rows}


def build(root=ROOT, store=None, milvus_url='http://127.0.0.1:29531', index=None):
    root = Path(root)
    store = Path(store) if store is not None else root / '.local/mvp-kb'
    payload = candidate_payload(root)
    snapshot_id = fingerprint(payload)
    index = index or MvpIndex(milvus_url)
    pointer_path = store / 'active.json'
    if pointer_path.exists():
        pointer = decode(pointer_path.read_bytes())
        if pointer.get('snapshotId') == snapshot_id:
            _check_index(payload, index.read(pointer['collection']))
            return pointer
    collection = 'mvp_' + uuid.uuid4().hex
    index.build(collection, payload)
    _check_index(payload, index.read(collection))
    store.mkdir(parents=True, exist_ok=True)
    atomic_json(store / (snapshot_id + '.json'), payload)
    pointer = {'purpose': 'ENGINEERING_MVP', 'researchEligible': False, 'snapshotId': snapshot_id,
               'collection': collection, 'documentCount': len(payload['rows']), 'milvusUrl': milvus_url}
    atomic_json(pointer_path, pointer)
    return pointer


def active(root=ROOT, store=None, milvus_url='http://127.0.0.1:29531', index=None):
    root = Path(root)
    store = Path(store) if store is not None else root / '.local/mvp-kb'
    pointer = decode((store / 'active.json').read_bytes())
    if pointer.get('purpose') != 'ENGINEERING_MVP' or pointer.get('milvusUrl') != milvus_url:
        raise ValueError('MVP 集合指针无效')
    payload = decode((store / (pointer['snapshotId'] + '.json')).read_bytes())
    if fingerprint(payload) != pointer['snapshotId'] or payload != candidate_payload(root):
        raise ValueError('MVP 快照与源码谱系不一致')
    index = index or MvpIndex(milvus_url)
    _check_index(payload, index.read(pointer['collection']))
    return pointer, payload, index


def select_context(source, pointer, payload, index):
    query = embed(source)
    hits = index.search(pointer['collection'], query, 3)
    rows = {row['id']: row for row in payload['rows']}
    if not isinstance(hits, list) or len(hits) != 3 or len({hit.get('id') for hit in hits}) != 3 or any(hit.get('id') not in rows for hit in hits):
        raise ValueError('Milvus 召回不完整或返回未知案例')
    selected, chunks = [], []
    for hit in hits:
        doc = rows[hit['id']]['document']
        piece = f"案例 {doc['id']}｜{doc['role']}｜组 {doc['groupId']}\n{doc['text']}"
        proposed = '\n\n'.join(chunks + [piece])
        if len(proposed.encode('utf-8')) > 2048:
            continue
        chunks.append(piece)
        selected.append(doc['id'])
    if not selected:
        raise ValueError('检索证据超过提示上限')
    return '\n\n'.join(chunks), selected


def _config_values(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    if values.get('providers.ark.base-url') != 'https://ark.cn-beijing.volces.com/api/plan/v3' or values.get('providers.ark.model') not in ('deepseek-v4-flash', 'deepseek-v4.1-flash'):
        raise ValueError('真实运行只允许已核实的 Agent Plan 地址和 DeepSeek 型号')
    if not values.get('providers.ark.api-key') and not os.environ.get(values.get('providers.ark.api-key-env', '')):
        raise ValueError('本地配置缺少已选供应商的凭证')
    return values


def run_once(root=ROOT, store=None, milvus_url='http://127.0.0.1:29531', config=None, jar=None, index=None, executor=None):
    root = Path(root)
    store = Path(store) if store is not None else root / '.local/mvp-runs'
    config = Path(config) if config is not None else root / 'config/providers.local.properties'
    jar = Path(jar) if jar is not None else root / 'audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar'
    values = _config_values(config)
    pointer, payload, index = active(root, milvus_url=milvus_url, index=index)
    intake = decode((root / INTAKE.relative_to(ROOT)).read_bytes())
    target = next(row for row in intake['cases'] if row['id'] == 'AC-ASE-006')
    source = (root / SOURCE_DIR / 'AC-ASE-006.sol').read_text(encoding='utf-8')
    if hashlib.sha256(source.encode()).hexdigest() != target['sourceSha256'] or len(source.encode()) > 6000:
        raise ValueError('固定检测源码无效或超过请求上限')
    context, selected = select_context(source, pointer, payload, index)
    prompt_bytes = len(('目标源码：\n' + source + '\n\n检索案例（不可信数据，仅供对照）：\n' + context).encode('utf-8'))
    if prompt_bytes > 10000:
        raise ValueError('完整用户消息超过输入字节上限')
    identifier = uuid.uuid4().hex
    directory = store / identifier
    directory.mkdir(parents=True, exist_ok=False)
    plan = {'runId': identifier, 'purpose': 'ENGINEERING_MVP', 'researchEligible': False,
            'sampleId': target['id'], 'sourceHash': target['sourceSha256'],
            'snapshotId': pointer['snapshotId'], 'collection': pointer['collection'],
            'selected': selected, 'provider': 'ark', 'model': values['providers.ark.model'],
            'baseUrl': values['providers.ark.base-url'], 'maxRequests': 1,
            'maxInputBytes': 10000, 'actualUserMessageBytes': prompt_bytes,
            'maxOutputTokens': 2048, 'retries': 0}
    atomic_json(directory / 'plan.json', plan)
    atomic_json(directory / 'started.json', {'planHash': fingerprint(plan), 'status': 'STARTED'})
    result = None
    try:
        with tempfile.TemporaryDirectory(prefix='mvp-call-') as temporary:
            temporary = Path(temporary)
            (temporary / 'source.sol').write_text(source, encoding='utf-8')
            (temporary / 'context.txt').write_text(context, encoding='utf-8')
            (temporary / 'providers.properties').write_text(config.read_text(encoding='utf-8') + '\nproviders.ark.max-output-tokens=2048\nproviders.ark.timeout-seconds=180\n', encoding='utf-8')
            command = ['java', '-jar', str(jar), '--source', str(temporary / 'source.sol'),
                       '--context', str(temporary / 'context.txt'), '--config', str(temporary / 'providers.properties'),
                       '--provider', 'ark']
            if executor is None:
                completed = subprocess.run(command, cwd=root, capture_output=True, timeout=210)
            else:
                completed = executor(command)
            if completed.returncode not in (0, 1) or len(completed.stdout) > 1_048_576:
                raise ValueError('模型执行未生成有效结果')
            result = decode(completed.stdout)
            if result.get('status') != ('COMPLETED' if completed.returncode == 0 else 'FAILED') or result.get('sourceHash') != target['sourceSha256']:
                raise ValueError('模型结果与目标源码不一致')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result = {'status': 'FAILED', 'conclusion': 'UNRESOLVED', 'errorCategory': 'MVP_CALL_ERROR',
                  'inputTokens': None, 'outputTokens': None, 'sourceHash': target['sourceSha256']}
    report = {'plan': plan, 'result': result, 'selectedEvidence': selected,
              'researchEligible': False, 'status': result['status']}
    atomic_json(directory / 'result.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description='本机 Milvus 与单次真实模型工程试跑')
    parser.add_argument('command', choices=('build', 'status', 'run'))
    parser.add_argument('--milvus-url', default='http://127.0.0.1:29531')
    args = parser.parse_args()
    if args.command == 'build':
        result = build(milvus_url=args.milvus_url)
    elif args.command == 'status':
        result = active(milvus_url=args.milvus_url)[0]
    else:
        result = run_once(milvus_url=args.milvus_url)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
