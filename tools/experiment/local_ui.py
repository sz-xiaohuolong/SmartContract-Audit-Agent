"""仅监听本机的合成样例实验页面；不会读取供应商凭证。"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from storage import durable_write, encode


DEMO = Path('docs/vibe/releases/R1-S3/evidence/demo')
S2_DEMO = Path('docs/vibe/releases/R1-S2/evidence/demo')
FRONTEND = Path(__file__).with_name('local_ui')
RUN_ID = re.compile(r'[0-9a-f]{32}')


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


def create_server(root, port=8765, store=None, runner=None):
    root = Path(root).resolve()
    store = Path(store) if store is not None else root / '.local/experiment-ui'
    runner = runner or (lambda: run_demo(root))
    run_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, data, content_type='application/json; charset=utf-8'):
            body = encode(data) if content_type.startswith('application/json') else data
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
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
            if self.path == '/api/demo':
                self._send(200, demo_record(root))
            elif self.path == '/api/context':
                self._send(200, demo_context(root))
            elif self.path == '/api/runs':
                rows = []
                for path in sorted(store.glob('*.json'), reverse=True)[:20]:
                    if RUN_ID.fullmatch(path.stem):
                        try:
                            row = _json(path)
                            rows.append({k: row[k] for k in ('runId', 'kind', 'createdAt')})
                        except (OSError, ValueError, KeyError):
                            continue
                self._send(200, {'runs': rows})
            elif self.path.startswith('/api/runs/'):
                identifier = self.path.removeprefix('/api/runs/')
                if not RUN_ID.fullmatch(identifier) or not (store / (identifier + '.json')).is_file():
                    self._not_found()
                else:
                    self._send(200, _json(store / (identifier + '.json')))
            elif self.path in ('/', '/index.html'):
                self._send(200, (FRONTEND / 'index.html').read_bytes(), 'text/html; charset=utf-8')
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
            if self.path != '/api/runs':
                self._not_found()
                return
            if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Content-Length') != '2' or self.rfile.read(2) != b'{}':
                self._send(400, {'error': '本页只能运行固定的离线演示样例'})
                return
            if not run_lock.acquire(blocking=False):
                self._send(409, {'error': '已有离线实验正在运行'})
                return
            try:
                result = runner()
                if result.get('tokenProfile', {}).get('purpose') != 'FIXTURE' or result.get('denominators', {}).get('researchEligible') != 0:
                    raise ValueError('演示结果不是合成样例')
                identifier = uuid.uuid4().hex
                record = {'runId': identifier, 'kind': 'SYNTHETIC_DEMO',
                          'createdAt': datetime.now(timezone.utc).isoformat(), 'result': result}
                store.mkdir(parents=True, exist_ok=True)
                durable_write(store / (identifier + '.json'), encode(record) + b'\n')
                self._send(201, record)
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
                self._send(500, {'error': '离线运行失败，请检查本机 Java 构建与固定演示样例。'})
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
