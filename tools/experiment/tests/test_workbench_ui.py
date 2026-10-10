"""工作台 HTTP 只接受明确源码和预览摘要，跨站与并发请求不会调用模型。"""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from audit_workbench import AuditWorkbench
from local_ui import create_server
from test_audit_workbench import Runtime, SOURCE


class WorkbenchUiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = Runtime()
        self.workbench = AuditWorkbench(Path(self.temp.name), runtime_factory=lambda profile: self.runtime,
            target_loader=lambda: [], tool=lambda *args: [{'engine': 'SLITHER', 'status': 'SKIPPED', 'issues': []}])
        self.server = create_server(Path(self.temp.name), 0, workbench=self.workbench)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.choice = {'source': SOURCE, 'mechanism': 'REENTRANCY', 'function': 'withdraw', 'riskLine': 4}

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2); self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def post(self, path, payload, headers=None):
        return self.request('POST', path, json.dumps(payload), headers or {'Content-Type': 'application/json'})

    def test_工作台响应拒绝跨站框架嵌入(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('GET', '/workbench.html')
            response = connection.getresponse()
            self.assertEqual(200, response.status)
            self.assertIn("frame-ancestors 'none'", response.getheader('Content-Security-Policy', ''))
            self.assertEqual('DENY', response.getheader('X-Frame-Options'))
            response.read()
        finally:
            connection.close()

    def test_跨站路径重复字段与未预览请求拒绝(self):
        for path in ('/workbench.html', '/workbench.js', '/workbench.css', '/api/workbench/targets', '/api/workbench/runs'):
            self.assertEqual(200, self.request('GET', path)[0])
        self.assertEqual(403, self.post('/api/workbench/preview', self.choice,
            {'Content-Type': 'application/json', 'Origin': 'https://example.com'})[0])
        self.assertEqual(403, self.request('GET', '/api/workbench/status', headers={'Host': 'evil.test'})[0])
        self.assertEqual(400, self.request('POST', '/api/workbench/preview', '{"source":"a","source":"b"}',
            {'Content-Type': 'application/json'})[0])
        self.assertEqual(400, self.post('/api/workbench/runs', self.choice)[0])
        self.assertEqual(400, self.post('/api/workbench/preview', {**self.choice, 'command': 'evil'})[0])
        self.assertEqual(404, self.request('GET', '/api/workbench/runs/../../config/providers.local.properties')[0])
        self.assertEqual([], self.runtime.calls)

    def test_单次运行报告历史与源码作为文本保存(self):
        code, body = self.post('/api/workbench/preview', self.choice)
        self.assertEqual(200, code)
        preview = json.loads(body)
        self.assertEqual([], self.runtime.calls)
        code, body = self.post('/api/workbench/runs', {**self.choice, 'planHash': preview['planHash']})
        self.assertEqual(202, code)
        run_id = json.loads(body)['runId']
        for _ in range(100):
            code, body = self.request('GET', '/api/workbench/runs/' + run_id)
            result = json.loads(body)
            if result.get('status') in ('COMPLETED', 'FAILED'):
                break
            threading.Event().wait(.01)
        self.assertEqual('COMPLETED', result['status'])
        self.assertEqual(6, len(result['stages']))
        self.assertEqual(SOURCE, result['target']['source'])
        self.assertEqual(200, self.request('GET', '/api/workbench/runs/' + run_id + '/report')[0])
        self.assertEqual(200, self.request('GET', '/api/workbench/runs')[0])
        self.assertEqual(['offline'], self.runtime.calls)

    def test_单样本与批量共用运行锁(self):
        started, finish = threading.Event(), threading.Event()
        prior = self.runtime.model_runner
        def slow_model(*args):
            started.set()
            finish.wait(3)
            return prior(*args)
        self.runtime.model_runner = slow_model
        preview = json.loads(self.post('/api/workbench/preview', self.choice)[1])
        payload = {**self.choice, 'planHash': preview['planHash']}
        try:
            self.assertEqual(202, self.post('/api/workbench/runs', payload)[0])
            self.assertTrue(started.wait(1))
            self.assertEqual(409, self.post('/api/workbench/runs', payload)[0])
            self.assertEqual([], self.runtime.calls)
        finally:
            finish.set()


if __name__ == '__main__': unittest.main()
