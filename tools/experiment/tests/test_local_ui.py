"""本地实验页面的离线接口回归。"""
import http.client
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from local_ui import create_server


ROOT = Path(__file__).resolve().parents[3]
DEMO = json.loads((ROOT / 'docs/vibe/releases/R1-S3/evidence/demo/pilot.json').read_text(encoding='utf-8'))


class LocalUiTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.calls = []
        self.server = create_server(ROOT, 0, Path(self.directory.name), lambda: self.calls.append(1) or DEMO)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        connection.close()
        return result

    def test_demo_is_clearly_synthetic_and_does_not_run_model(self):
        status, _, body = self.request('GET', '/api/demo')
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result['kind'], 'SYNTHETIC_DEMO')
        self.assertEqual(result['result']['denominators']['researchEligible'], 0)
        self.assertEqual(self.calls, [])
        status, _, body = self.request('GET', '/api/context')
        context = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(context['target']['id'], 'target')
        self.assertEqual(set(context['cases']), {'vulnerable', 'defense'})

    def test_run_persists_result_and_replay_does_not_rerun(self):
        status, _, body = self.request('POST', '/api/runs', b'{}', {'Content-Type': 'application/json'})
        result = json.loads(body)
        self.assertEqual(status, 201)
        self.assertEqual(result['kind'], 'SYNTHETIC_DEMO')
        self.assertEqual(len(self.calls), 1)
        run_id = result['runId']
        status, _, body = self.request('GET', '/api/runs/' + run_id)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['result']['planHash'], DEMO['planHash'])
        status, _, body = self.request('GET', '/api/runs')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['runs'][0]['runId'], run_id)
        self.assertEqual(len(self.calls), 1)

    def test_rejects_untrusted_origin_and_unknown_routes(self):
        status, _, _ = self.request('POST', '/api/runs', b'{}', {'Origin': 'https://elsewhere.example', 'Content-Type': 'application/json'})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.request('GET', '/api/runs/../../config/providers.local.properties')[0], 404)
        self.assertEqual(self.request('POST', '/api/runs', b'{"provider":"ark"}', {'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.calls, [])

    def test_serves_frontend(self):
        status, headers, body = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', headers['Content-Type'])
        self.assertIn('离线实验台'.encode(), body)


if __name__ == '__main__':
    unittest.main()
