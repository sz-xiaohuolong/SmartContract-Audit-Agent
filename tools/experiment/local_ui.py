"""仅监听本机的实验页面；真实工程试跑须点击独立入口。"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from storage import atomic_json, durable_write, encode, sync_directory
import mvp_runtime
from urllib.parse import urlsplit, parse_qs
from storage import decode


DEMO = Path('docs/vibe/releases/R1-S3/evidence/demo')
S2_DEMO = Path('docs/vibe/releases/R1-S2/evidence/demo')
FRONTEND = Path(__file__).with_name('local_ui')
RUN_ID = re.compile(r'[0-9a-f]{32}')
PENDING_COLLECTION = re.compile(r'r1pending_[0-9a-f]{32}')


def _json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def demo_record(root):
    return {'runId': 'checked-in-demo', 'kind': 'SYNTHETIC_DEMO', 'createdAt': None,
            'result': _json(root / DEMO / 'pilot.json')}


def demo_context(root):
    request = _json(root / S2_DEMO / 'request.json')
    comparison = _json(root / S2_DEMO / 'comparison.json')
    labels = _json(root / DEMO / 'judgments.json')
    source = (root / S2_DEMO / 'target.sol').read_text(encoding='utf-8')
    cases = {case['caseId']: {'role': case['role'], 'text': case['text'], 'score': case['denseScore'],
                              'conditions': case['conditions'], 'binding': comparison['results'][0]['evaluations'][case['chunkId']]}
             for case in request['pool']['candidates']}
    return {'target': {'id': 'target', 'source': source, 'question': '权限检查是否位于风险写入之前？'},
            'cases': cases, 'judgments': {row['caseId']: row for row in labels},
            'notice': '合成机制样例仅用于检查实验流程，不能作为论文效果证据。'}


def run_demo(root):
    with tempfile.TemporaryDirectory(prefix='s3-ui-') as directory:
        output = Path(directory) / 'result.json'
        command = [sys.executable, str(root / 'tools/experiment/s3_pilot.py'),
                   '--ledger', str(root / DEMO / 'ledger.json'), '--root', str(root),
                   '--plan', str(root / DEMO / 'plan.json'), '--labels', str(root / DEMO / 'judgments.json'),
                   '--tokenizer', str(root / DEMO / 'codepoint_tokenizer.py'),
                   '--jar', str(root / 'audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar'),
                   '--worker', str(root / 'tools/experiment/program_facts.py'), '--output', str(output)]
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=45)
        if completed.returncode != 0:
            raise RuntimeError('固定夹具离线运行失败')
        return _json(output)


def publish_report(store, record):
    result = record['result']
    samples = result.get('samples')
    if (not isinstance(samples, list) or not samples or
            result.get('denominators', {}).get('planned') != len(samples) or
            any(not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] for row in samples) or
            len({row['id'] for row in samples}) != len(samples)):
        raise ValueError('逐样本结果无效')
    reports = store / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.pending-', dir=reports))
    final = reports / record['runId']
    try:
        with (temporary / 'samples.jsonl').open('xb') as output:
            for sample in samples:
                output.write(encode(sample) + b'\n')
                output.flush()
                os.fsync(output.fileno())
        atomic_json(temporary / 'summary.json', {
            'runId': record['runId'], 'kind': record['kind'], 'createdAt': record['createdAt'],
            'denominators': result['denominators'], 'planHash': result['planHash'],
            'ledgerHash': result['ledgerHash'], 'tokenProfile': result['tokenProfile']})
        os.replace(temporary, final)
        sync_directory(reports)
        record['report'] = {'directory': str(final), 'sampleCount': len(samples)}
        durable_write(store / (record['runId'] + '.json'), encode(record) + b'\n')
        sync_directory(store)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _agent_dependencies(root):
    from functools import lru_cache
    from audit_run import RunDependencies, model_runner, tool_runner
    from d1_embed import MODEL_MANIFEST, load_local_encoder
    from formal_recall import java_retrieval
    from milvus_rest import MilvusRestIndex
    index = MilvusRestIndex('http://127.0.0.1:29531')
    @lru_cache(maxsize=1)
    def encoder():
        from sentence_transformers import SentenceTransformer
        return load_local_encoder(SentenceTransformer, root / '.local/d1-embedding-model',
                                  decode(MODEL_MANIFEST.read_bytes()))
    return RunDependencies(index, lambda texts: encoder()(texts),
                           lambda source, request: java_retrieval(root, source, request),
                           model_runner, tool_runner)


def pending_knowledge_status(root, index):
    receipt_path = Path(root) / '.local/dataset-candidates/r1-pending/receipt.json'
    if not receipt_path.is_file():
        return None
    receipt = decode(receipt_path.read_bytes())
    collection = receipt.get('collection')
    count = receipt.get('vectorCount')
    if (receipt.get('candidateOnly') is not True or receipt.get('formalD1Enabled') is not False
            or not isinstance(collection, str) or not PENDING_COLLECTION.fullmatch(collection)
            or type(count) is not int or count <= 0):
        raise ValueError('待审集合收据无效')
    if not index.request('collections/has', {'collectionName': collection})['has']:
        raise ValueError('待审集合不存在')
    ids = set()
    for offset in range(0, count, 256):
        batch = index.request('entities/query', {'collectionName': collection, 'filter': '',
            'outputFields': ['id'], 'limit': 256, 'offset': offset, 'consistencyLevel': 'Strong'})
        if not isinstance(batch, list):
            raise ValueError('待审集合读回无效')
        for item in batch:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or item['id'] in ids:
                raise ValueError('待审集合 ID 重复或无效')
            ids.add(item['id'])
    if len(ids) != count:
        raise ValueError('待审集合数量与收据不符')
    extra = index.request('entities/query', {'collectionName': collection, 'filter': '',
        'outputFields': ['id'], 'limit': 1, 'offset': count, 'consistencyLevel': 'Strong'})
    if extra:
        raise ValueError('待审集合存在收据以外的向量')
    return {'collection': collection, 'vectors': count,
            'automescPairs': receipt['automescPairs'], 'forgeVfp': receipt['forgeVfp'],
            'formalD1Enabled': False}


def create_server(root, port=8765, store=None, runner=None, mvp_runner=None, mvp_status=None,
                  agent_targets=None, agent_status=None, agent_preview=None, agent_runner=None, agent_store=None,
                  batch_store=None, exploratory_store=None, exploratory_runner=None,
                  auto_store=None, auto_targets=None, auto_runtime=None):
    root = Path(root).resolve()
    store = Path(store) if store is not None else root / '.local/experiment-ui'
    runner = runner or (lambda: run_demo(root))
    mvp_runner = mvp_runner or (lambda: mvp_runtime.run_once(root))
    mvp_status = mvp_status or (lambda: mvp_runtime.active(root)[0])
    agent_store = Path(agent_store) if agent_store is not None else root / '.local/audit-runs'
    batch_store = Path(batch_store) if batch_store is not None else root / '.local/audit-batches'
    exploratory_store = Path(exploratory_store) if exploratory_store is not None else root / '.local/d1-exploratory-runs'
    auto_store = Path(auto_store) if auto_store is not None else root / '.local/auto-benchmark-runs'
    if agent_targets is None or agent_status is None or agent_preview is None or agent_runner is None:
        from audit_run import run_once
        from formal_targets import list_targets, load_target
        from formal_recall import preview as formal_preview
        from snapshots import active_snapshot, verify_snapshot
        dependencies = _agent_dependencies(root)
        agent_targets = agent_targets or (lambda: list_targets(root))
        def default_status():
            pointer = active_snapshot(root / '.local/d1-kb-snapshots', dependencies.index)
            snapshot = verify_snapshot(root / '.local/d1-kb-snapshots', pointer['snapshot_id'])
            values = {'ready': True, 'snapshotId': pointer['snapshot_id'],
                      'collection': pointer['collection'], 'maxRequestsPerClick': 1,
                      'maxOutputTokens': 2048, 'researchEligible': False,
                      'formalVectors': len(snapshot['rows']),
                      'knowledgeTier': ('AUTO_LABELED' if all(row['review_status'] == 'AUTO_LABELED'
                          for row in snapshot['manifest']['samples']) else 'REVIEWED')}
            try:
                values['pendingKnowledge'] = pending_knowledge_status(root, dependencies.index)
            except (OSError, ValueError, KeyError, TypeError):
                values['pendingKnowledge'] = None
            try:
                from mvp_runtime import _config_values
                config = _config_values(root / 'config/providers.local.properties')
                values.update({'realReady': True, 'endpoint': config['providers.ark.base-url'],
                               'model': config['providers.ark.model']})
            except (OSError, ValueError, KeyError):
                values['realReady'] = False
            return values
        agent_status = agent_status or default_status
        agent_preview = agent_preview or (lambda sample: formal_preview(root, load_target(root, sample),
            dependencies.index, dependencies.encoder, dependencies.java_retriever))
        agent_runner = agent_runner or (lambda sample, mode, strategy='D1': run_once(root, sample, mode, dependencies, strategy))
    if auto_targets is None:
        from functools import lru_cache
        from benchmark_targets import load_benchmark_targets
        from exploratory_corpus import load_corpus
        @lru_cache(maxsize=1)
        def default_auto_targets():
            corpus = load_corpus(root / '.local/dataset-candidates/r1-pending')
            return load_benchmark_targets(root, list(corpus['rows'].values()))
        auto_targets = default_auto_targets
    if auto_runtime is None:
        from benchmark_runtime import BenchmarkRuntime
        def default_auto_runtime():
            prepared = _agent_dependencies(root)
            return BenchmarkRuntime(root, prepared.index, prepared.encoder,
                                    prepared.model_runner, prepared.java_retriever)
        auto_runtime = default_auto_runtime
    run_lock = threading.Lock()
    exploratory_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, data, content_type='application/json; charset=utf-8', filename=None):
            body = encode(data) if content_type.startswith('application/json') else data
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            if content_type.startswith('text/html'):
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _not_found(self):
            self._send(404, {'error': '页面不存在'})

        def _allowed_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self._allowed_host():
                self._send(403, {'error': '仅允许本机访问'})
                return
            parsed = urlsplit(self.path)
            if parsed.path == '/api/agent/auto-benchmark/targets' and not parsed.query:
                try:
                    rows = [{key: value for key, value in row.items()
                             if key not in ('source', 'fullSource', 'modelSource')} for row in auto_targets()]
                    self._send(200, {'targets': rows})
                except (OSError, ValueError, KeyError, TypeError):
                    self._send(503, {'error': '自动知识验证目标暂不可用'})
            elif parsed.path == '/api/agent/auto-benchmark/runs' and not parsed.query:
                from benchmark_batch import replay_batch as replay_auto
                rows = []
                for path in auto_store.glob('*/plan.json'):
                    if RUN_ID.fullmatch(path.parent.name):
                        try:
                            report = replay_auto(auto_store, path.parent.name)
                            rows.append({'batchId': path.parent.name, 'status': report['status'],
                                         'planned': report['denominators']['planned'],
                                         'mode': report['plan']['mode'], 'time': path.stat().st_mtime_ns})
                        except (OSError, ValueError, KeyError, TypeError):
                            continue
                rows.sort(key=lambda row: row['time'], reverse=True)
                self._send(200, {'batches': rows[:20]})
            elif parsed.path.startswith('/api/agent/auto-benchmark/runs/') and not parsed.query:
                from benchmark_batch import export_csv, replay_batch as replay_auto
                suffix = parsed.path.removeprefix('/api/agent/auto-benchmark/runs/')
                parts = suffix.split('/')
                identifier = parts[0]
                if (not RUN_ID.fullmatch(identifier) or len(parts) > 2
                        or len(parts) == 2 and parts[1] not in ('samples.jsonl', 'samples.csv')
                        or not (auto_store / identifier / 'plan.json').is_file()):
                    self._not_found()
                else:
                    try:
                        report = replay_auto(auto_store, identifier)
                        if len(parts) == 1:
                            error = auto_store / identifier / 'error.json'
                            self._send(200, {**report, 'error': _json(error).get('error') if error.is_file() else None})
                        elif parts[1] == 'samples.csv':
                            self._send(200, export_csv(report).encode(), 'text/csv; charset=utf-8', 'samples.csv')
                        else:
                            path = auto_store / identifier / 'samples.jsonl'
                            self._send(200, path.read_bytes() if path.is_file() else b'',
                                       'application/x-ndjson; charset=utf-8', 'samples.jsonl')
                    except (OSError, ValueError, KeyError, TypeError):
                        self._send(500, {'error': '自动知识批量报告损坏'})
            elif parsed.path == '/api/agent/exploratory' and not parsed.query:
                from exploratory_probe import replay_probe
                plans = sorted((path for path in exploratory_store.glob('*/plan.json')
                                if RUN_ID.fullmatch(path.parent.name)),
                               key=lambda path: path.stat().st_mtime, reverse=True)
                if not plans:
                    self._send(200, {'running': exploratory_lock.locked(), 'report': None})
                else:
                    try:
                        report = replay_probe(exploratory_store, plans[0].parent.name)
                        self._send(200, {'running': exploratory_lock.locked(), 'report': report})
                    except (OSError, ValueError, KeyError, TypeError):
                        self._send(500, {'error': '探索性逐样本报告损坏'})
            elif parsed.path == '/api/agent/batches' and not parsed.query:
                from batch_compare import replay_batch
                rows = []
                for path in batch_store.glob('*/plan.json'):
                    if RUN_ID.fullmatch(path.parent.name):
                        try:
                            report = replay_batch(batch_store, path.parent.name)
                            rows.append({'batchId': path.parent.name, 'status': report['status'],
                                         'planned': report['denominators']['planned'], 'mode': report['plan']['mode'],
                                         'time': path.stat().st_mtime_ns})
                        except (OSError, ValueError, KeyError):
                            continue
                rows.sort(key=lambda row: row['time'], reverse=True)
                self._send(200, {'batches': rows[:20]})
            elif parsed.path.startswith('/api/agent/batches/') and not parsed.query:
                from batch_compare import replay_batch
                suffix = parsed.path.removeprefix('/api/agent/batches/')
                report_file = suffix.endswith('/report')
                identifier = suffix.removesuffix('/report') if report_file else suffix
                if not RUN_ID.fullmatch(identifier) or not (batch_store / identifier / 'plan.json').is_file():
                    self._not_found()
                else:
                    try:
                        result = replay_batch(batch_store, identifier)
                        if report_file:
                            path = batch_store / identifier / 'samples.jsonl'
                            self._send(200, path.read_bytes() if path.is_file() else b'',
                                       'application/x-ndjson; charset=utf-8', 'samples.jsonl')
                        else:
                            self._send(200, result)
                    except (OSError, ValueError, KeyError):
                        self._send(500, {'error': '批量运行记录损坏'})
            elif parsed.path == '/api/agent/status' and not parsed.query:
                try: self._send(200, agent_status())
                except (OSError, ValueError, RuntimeError, KeyError, ImportError):
                    self._send(200, {'ready': False, 'researchEligible': False})
            elif parsed.path == '/api/agent/targets' and not parsed.query:
                try: self._send(200, {'targets': agent_targets()})
                except (OSError, ValueError, RuntimeError, KeyError):
                    self._send(503, {'error': '开发目标或谱系暂不可用'})
            elif parsed.path == '/api/agent/preview':
                query = parse_qs(parsed.query, strict_parsing=True)
                if (set(query) not in ({'sampleId'}, {'sampleId', 'strategy'}) or len(query['sampleId']) != 1
                        or len(query.get('strategy', ['D1'])) != 1
                        or query.get('strategy', ['D1'])[0] not in ('DENSE', 'FIELD_FILTER', 'D1')):
                    self._send(400, {'error': '样本参数无效'})
                else:
                    sample = query['sampleId'][0]
                    try:
                        if sample not in {row['sampleId'] for row in agent_targets() if row.get('runnable')}:
                            raise ValueError('样本不可运行')
                        from formal_recall import select_strategy
                        self._send(200, select_strategy(agent_preview(sample), query.get('strategy', ['D1'])[0]))
                    except (OSError, ValueError, RuntimeError, KeyError, ImportError):
                        self._send(503, {'error': '正式检索预览不可用'})
            elif parsed.path == '/api/agent/runs' and not parsed.query:
                from audit_run import replay_at
                rows = []
                for path in agent_store.glob('*/result.json'):
                    if RUN_ID.fullmatch(path.parent.name):
                        try:
                            row = replay_at(agent_store, path.parent.name)
                            rows.append({'runId': row['runId'], 'sampleId': row['plan']['sampleId'],
                                         'status': row['status'], 'mode': row['plan']['mode'],
                                         'strategy': row['plan'].get('strategy', 'D1'),
                                         'createdAt': row['plan']['createdAt']})
                        except (OSError, ValueError, KeyError): pass
                rows.sort(key=lambda row: row['createdAt'], reverse=True)
                self._send(200, {'runs': rows[:20]})
            elif parsed.path.startswith('/api/agent/runs/') and not parsed.query:
                from audit_run import replay_at
                suffix = parsed.path.removeprefix('/api/agent/runs/')
                report = suffix.endswith('/report')
                identifier = suffix.removesuffix('/report') if report else suffix
                if not RUN_ID.fullmatch(identifier):
                    self._not_found()
                else:
                    path = agent_store / identifier / ('sample.jsonl' if report else 'result.json')
                    if not path.is_file(): self._not_found()
                    else:
                        try:
                            row = replay_at(agent_store, identifier)
                            if report: self._send(200, path.read_bytes(), 'application/x-ndjson; charset=utf-8', 'sample.jsonl')
                            else: self._send(200, row)
                        except (OSError, ValueError): self._send(500, {'error': '运行记录损坏'})
            elif self.path == '/agent.html':
                self._send(200, (FRONTEND / 'agent.html').read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/agent.js':
                self._send(200, (FRONTEND / 'agent.js').read_bytes(), 'text/javascript; charset=utf-8')
            elif self.path == '/api/demo':
                self._send(200, demo_record(root))
            elif self.path == '/api/mvp/status':
                try:
                    self._send(200, {'ready': True, 'snapshot': mvp_status(),
                                     'sampleId': 'AC-ASE-006', 'maxRequestsPerClick': 1,
                                     'maxOutputTokens': 2048, 'researchEligible': False})
                except (OSError, ValueError, KeyError, RuntimeError):
                    self._send(200, {'ready': False, 'researchEligible': False})
            elif self.path == '/api/mvp/runs':
                directory = root / '.local/mvp-runs'
                rows = []
                for path in directory.glob('*/result.json'):
                    if RUN_ID.fullmatch(path.parent.name):
                        try:
                            result = _json(path)
                            rows.append({'runId': path.parent.name, 'status': result['status'],
                                         'sampleId': result['plan']['sampleId'], 'time': path.stat().st_mtime_ns})
                        except (OSError, ValueError, KeyError):
                            continue
                rows.sort(key=lambda row: row['time'], reverse=True)
                self._send(200, {'runs': rows[:20]})
            elif self.path.startswith('/api/mvp/runs/'):
                identifier = self.path.removeprefix('/api/mvp/runs/')
                path = root / '.local/mvp-runs' / identifier / 'result.json'
                if not RUN_ID.fullmatch(identifier) or not path.is_file():
                    self._not_found()
                else:
                    self._send(200, _json(path))
            elif self.path == '/api/context':
                self._send(200, demo_context(root))
            elif self.path == '/api/runs':
                rows = []
                for path in store.glob('*.json'):
                    if RUN_ID.fullmatch(path.stem):
                        try:
                            row = _json(path)
                            if isinstance(row['createdAt'], str):
                                rows.append({k: row[k] for k in ('runId', 'kind', 'createdAt')})
                        except (OSError, ValueError, KeyError):
                            continue
                rows.sort(key=lambda row: (row['createdAt'], row['runId']), reverse=True)
                self._send(200, {'runs': rows[:20]})
            elif self.path.startswith('/api/runs/'):
                identifier = self.path.removeprefix('/api/runs/')
                if identifier.endswith('/report'):
                    identifier = identifier.removesuffix('/report')
                    path = store / 'reports' / identifier / 'samples.jsonl'
                    if not RUN_ID.fullmatch(identifier) or not (store / (identifier + '.json')).is_file() or not path.is_file():
                        self._not_found()
                    else:
                        self._send(200, path.read_bytes(), 'application/x-ndjson; charset=utf-8', 'samples.jsonl')
                elif not RUN_ID.fullmatch(identifier) or not (store / (identifier + '.json')).is_file():
                    self._not_found()
                else:
                    self._send(200, _json(store / (identifier + '.json')))
            elif self.path in ('/', '/index.html'):
                self._send(200, (FRONTEND / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/mvp.html':
                self._send(200, (FRONTEND / 'mvp.html').read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/mvp.js':
                self._send(200, (FRONTEND / 'mvp.js').read_bytes(), 'text/javascript; charset=utf-8')
            elif self.path == '/app.js':
                self._send(200, (FRONTEND / 'app.js').read_bytes(), 'text/javascript; charset=utf-8')
            elif self.path == '/style.css':
                self._send(200, (FRONTEND / 'style.css').read_bytes(), 'text/css; charset=utf-8')
            else:
                self._not_found()

        def do_POST(self):
            if not self._allowed_host():
                self._send(403, {'error': '仅允许本机访问'})
                return
            origin = self.headers.get('Origin')
            if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
                self._send(403, {'error': '请求来源不允许'})
                return
            resume_match = re.fullmatch(r'/api/agent/batches/([0-9a-f]{32})/resume', self.path)
            auto_resume_match = re.fullmatch(r'/api/agent/auto-benchmark/runs/([0-9a-f]{32})/resume', self.path)
            if self.path not in ('/api/runs', '/api/mvp/run', '/api/agent/runs',
                                 '/api/agent/batches/plan', '/api/agent/batches',
                                 '/api/agent/exploratory', '/api/agent/auto-benchmark/plan',
                                 '/api/agent/auto-benchmark/runs') and not resume_match and not auto_resume_match:
                self._not_found()
                return
            if self.path in ('/api/agent/auto-benchmark/plan', '/api/agent/auto-benchmark/runs') or auto_resume_match:
                from benchmark_batch import make_plan as make_auto_plan, prepare_batch as prepare_auto
                from benchmark_batch import replay_batch as replay_auto, run_batch as run_auto
                length = self.headers.get('Content-Length')
                if (self.headers.get('Content-Type') != 'application/json' or length is None
                        or not length.isdecimal() or int(length) > 65536):
                    self._send(400, {'error': '自动知识批量请求无效'}); return
                try:
                    payload = decode(self.rfile.read(int(length)))
                    if auto_resume_match:
                        identifier = auto_resume_match.group(1)
                        previous = replay_auto(auto_store, identifier)
                        stored = previous['plan']
                        if set(payload) != {'planHash'} or payload['planHash'] != stored['planHash'] or previous['status'] != 'RUNNING':
                            raise ValueError('续跑摘要或状态无效')
                        choice = {key: stored[key] for key in ('sampleIds', 'strategies', 'mode')}
                    else:
                        expected = {'sampleIds', 'strategies', 'mode'}
                        if not isinstance(payload, dict) or set(payload) != (expected if self.path.endswith('/plan') else expected | {'planHash'}):
                            raise ValueError('批量字段无效')
                        choice = payload
                    state = agent_status()
                    if (not state.get('ready') or state.get('knowledgeTier') not in (None, 'AUTO_LABELED')
                            or choice['mode'] == 'real' and not state.get('realReady')):
                        raise ValueError('知识快照或真实模型不可用')
                    provider = {'endpoint': state.get('endpoint'), 'model': state.get('model')} if choice['mode'] == 'real' else None
                    plan = make_auto_plan(choice['sampleIds'], choice['strategies'], choice['mode'],
                                          auto_targets(), state['snapshotId'], provider)
                    if ((auto_resume_match and plan != stored)
                            or (not self.path.endswith('/plan') and payload['planHash'] != plan['planHash'])):
                        raise ValueError('自动知识批量计划已变化')
                    if self.path.endswith('/plan'):
                        self._send(200, plan); return
                except (OSError, ValueError, KeyError, TypeError):
                    self._send(400, {'error': '自动知识批量选择、快照或计划摘要无效'}); return
                if not run_lock.acquire(blocking=False):
                    self._send(409, {'error': '已有批量实验正在运行'}); return
                identifier = auto_resume_match.group(1) if auto_resume_match else uuid.uuid4().hex
                try:
                    auto_store.mkdir(parents=True, exist_ok=True)
                    if not auto_resume_match:
                        prepare_auto(auto_store, plan, identifier)
                except (OSError, ValueError):
                    run_lock.release()
                    self._send(500, {'error': '自动知识批量计划保存失败'}); return
                def auto_work():
                    try:
                        runtime = auto_runtime()
                        if runtime.pointer['snapshot_id'] != plan['snapshotId']:
                            raise ValueError('自动知识快照已变化')
                        indexed = {row['sampleId']: row for row in auto_targets()}
                        run_auto(auto_store, plan, lambda sample, strategy, mode:
                                 runtime.run(indexed[sample], strategy, mode), identifier)
                    except Exception:
                        atomic_json(auto_store / identifier / 'error.json', {'error': '批量执行失败，请检查本机模型、Milvus 或逐样本日志'})
                    finally:
                        run_lock.release()
                threading.Thread(target=auto_work, daemon=True).start()
                self._send(202, {'batchId': identifier, 'planHash': plan['planHash']})
                return
            if self.path == '/api/agent/exploratory':
                if self.headers.get('Content-Length', '0') != '0' or not exploratory_lock.acquire(blocking=False):
                    self._send(409, {'error': '探索任务正在运行或请求含有多余正文'}); return
                def explore_work():
                    try:
                        if exploratory_runner is not None:
                            exploratory_runner()
                        else:
                            python = root / '.local/d1-embed-venv/bin/python'
                            script = root / 'tools/experiment/exploratory_probe.py'
                            environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                                               PYTHONPATH=str(root / 'tools/experiment'))
                            completed = subprocess.run([str(python), str(script)], cwd=root,
                                env=environment, capture_output=True, timeout=300)
                            if completed.returncode != 0:
                                raise RuntimeError('探索性检索失败')
                    except (OSError, subprocess.TimeoutExpired, RuntimeError):
                        exploratory_store.mkdir(parents=True, exist_ok=True)
                        atomic_json(exploratory_store / 'last-error.json', {'error': '探索性检索失败，请检查固定模型、Milvus 与报告目录'})
                    finally:
                        exploratory_lock.release()
                threading.Thread(target=explore_work, daemon=True).start()
                self._send(202, {'running': True, 'mode': 'EXPLORATORY_RETRIEVAL_ONLY', 'modelCalls': 0})
                return
            if resume_match:
                from batch_compare import make_plan, replay_batch, run_batch
                length = self.headers.get('Content-Length')
                if (self.headers.get('Content-Type') != 'application/json' or length is None
                        or not length.isdecimal() or int(length) > 256):
                    self._send(400, {'error': '续跑请求无效'}); return
                identifier = resume_match.group(1)
                try:
                    payload = decode(self.rfile.read(int(length)))
                    report = replay_batch(batch_store, identifier)
                    plan = report['plan']
                    current = make_plan(plan['sampleIds'], plan['strategies'], plan['mode'], agent_targets(), agent_status())
                    if (not isinstance(payload, dict) or set(payload) != {'planHash'}
                            or payload['planHash'] != plan['planHash'] or current != plan
                            or report['status'] != 'RUNNING'):
                        raise ValueError('续跑计划已变化或运行已结束')
                except (OSError, ValueError, KeyError, TypeError):
                    self._send(400, {'error': '续跑计划无效或正式快照已变化'}); return
                if not run_lock.acquire(blocking=False):
                    self._send(409, {'error': '已有实验正在运行'}); return
                def resume_work():
                    try:
                        run_batch(batch_store, plan, agent_runner, identifier)
                    except Exception:
                        atomic_json(batch_store / identifier / 'error.json', {'error': '批量续跑失败'})
                    finally:
                        run_lock.release()
                threading.Thread(target=resume_work, daemon=True).start()
                self._send(202, {'batchId': identifier, 'planHash': plan['planHash']})
                return
            if self.path in ('/api/agent/batches/plan', '/api/agent/batches'):
                from batch_compare import make_plan, prepare_batch, run_batch
                length = self.headers.get('Content-Length')
                if (self.headers.get('Content-Type') != 'application/json' or length is None
                        or not length.isdecimal() or int(length) > 1024):
                    self._send(400, {'error': '批量请求无效'}); return
                try:
                    payload = decode(self.rfile.read(int(length)))
                    expected = {'sampleIds', 'strategies', 'mode'}
                    if not isinstance(payload, dict) or set(payload) != (expected if self.path.endswith('/plan') else expected | {'planHash'}):
                        raise ValueError('批量字段无效')
                    plan = make_plan(payload['sampleIds'], payload['strategies'], payload['mode'],
                                     agent_targets(), agent_status())
                    if self.path.endswith('/plan'):
                        self._send(200, plan); return
                    if payload['planHash'] != plan['planHash']:
                        raise ValueError('批量预览已失效，请重新查看计划')
                except (ValueError, TypeError, KeyError, OSError, RuntimeError):
                    self._send(400, {'error': '批量选择或预览摘要无效'}); return
                if not run_lock.acquire(blocking=False):
                    self._send(409, {'error': '已有实验正在运行'}); return
                identifier = uuid.uuid4().hex
                try:
                    batch_store.mkdir(parents=True, exist_ok=True)
                    prepare_batch(batch_store, plan, identifier)
                except (OSError, ValueError):
                    run_lock.release()
                    self._send(500, {'error': '无法持久化批量运行计划'}); return
                def execute():
                    try:
                        run_batch(batch_store, plan, agent_runner, identifier)
                    except Exception:
                        directory = batch_store / identifier
                        directory.mkdir(parents=True, exist_ok=True)
                        atomic_json(directory / 'error.json', {'error': '批量执行失败，请检查本机环境'})
                    finally:
                        run_lock.release()
                threading.Thread(target=execute, daemon=True).start()
                self._send(202, {'batchId': identifier, 'planHash': plan['planHash']})
                return
            if self.path == '/api/agent/runs':
                length = self.headers.get('Content-Length')
                if self.headers.get('Content-Type') != 'application/json' or length is None or not length.isdecimal() or int(length) > 256:
                    self._send(400, {'error': '运行请求无效'}); return
                try:
                    payload = decode(self.rfile.read(int(length)))
                    if (not isinstance(payload, dict) or set(payload) not in ({'sampleId', 'mode'}, {'sampleId', 'mode', 'strategy'})
                            or payload['mode'] not in ('offline', 'real')
                            or payload.get('strategy', 'D1') not in ('DENSE', 'FIELD_FILTER', 'D1')):
                        raise ValueError()
                    if payload['sampleId'] not in {row['sampleId'] for row in agent_targets() if row.get('runnable')}:
                        raise ValueError()
                except (ValueError, KeyError, TypeError):
                    self._send(400, {'error': '只能选择已登记可运行样本和明确模式'}); return
                if not run_lock.acquire(blocking=False):
                    self._send(409, {'error': '已有实验正在运行'}); return
                try:
                    result = (agent_runner(payload['sampleId'], payload['mode'], payload['strategy'])
                              if 'strategy' in payload else agent_runner(payload['sampleId'], payload['mode']))
                    if result.get('researchEligible') is not False or result.get('plan', {}).get('sampleId') != payload['sampleId']:
                        raise ValueError()
                    self._send(201, result)
                except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.TimeoutExpired, ImportError):
                    self._send(500, {'error': '审计运行失败，请检查本机正式快照、模型及工具配置。'})
                finally: run_lock.release()
                return
            if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Content-Length') != '2' or self.rfile.read(2) != b'{}':
                self._send(400, {'error': '只能运行固定样本，且请求内容必须是空对象'})
                return
            if not run_lock.acquire(blocking=False):
                self._send(409, {'error': '已有实验正在运行'})
                return
            try:
                if self.path == '/api/mvp/run':
                    result = mvp_runner()
                    if result.get('researchEligible') is not False or result.get('plan', {}).get('maxRequests') != 1:
                        raise ValueError('工程试跑结果无效')
                    self._send(201, result)
                    return
                result = runner()
                if (not isinstance(result, dict) or not isinstance(result.get('tokenProfile'), dict) or
                        not isinstance(result.get('denominators'), dict) or
                        result['tokenProfile'].get('purpose') != 'FIXTURE' or
                        result['denominators'].get('researchEligible') != 0):
                    raise ValueError('演示结果不是合成样例')
                identifier = uuid.uuid4().hex
                record = {'runId': identifier, 'kind': 'SYNTHETIC_DEMO',
                          'createdAt': datetime.now(timezone.utc).isoformat(), 'result': result}
                store.mkdir(parents=True, exist_ok=True)
                publish_report(store, record)
                self._send(201, record)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.TimeoutExpired):
                self._send(500, {'error': '工程试跑失败；请检查本机快照、模型配置和运行记录。' if self.path == '/api/mvp/run' else '离线运行失败，请检查本机 Java 构建与固定演示样例。'})
            finally:
                run_lock.release()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='启动仅供本机访问的合成样例实验页面')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    server = create_server(root, args.port)
    print(f'离线实验台：http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
