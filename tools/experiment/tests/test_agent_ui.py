"""新审计页面的只读与显式运行边界。"""
import http.client
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from local_ui import create_server
from storage import fingerprint

ROOT = Path(__file__).resolve().parents[3]


class AgentUiTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.calls = []
        target = {'sampleId': 'AC-ASE-006', 'runnable': True, 'scope': 'FULL'}
        plan = {'sampleId': 'AC-ASE-006', 'mode': 'offline', 'maxRequests': 0,
                'createdAt': '2026-10-05T00:00:00+00:00'}
        report = {'runId': 'a'*32, 'status': 'COMPLETED', 'researchEligible': False,
                  'plan': plan, 'planHash': fingerprint(plan), 'model': {}, 'tools': [], 'd2': {},
                  'conclusion': 'UNRESOLVED'}
        def run(sample, mode, strategy='D1'):
            self.calls.append((sample, mode) if strategy == 'D1' else (sample, mode, strategy))
            directory = Path(self.temp.name) / ('a'*32)
            directory.mkdir()
            (directory / 'plan.json').write_text(json.dumps(plan))
            (directory / 'result.json').write_text(json.dumps(report))
            (directory / 'sample.jsonl').write_text(json.dumps({'sampleId': sample, 'model': {}, 'tools': [],
                'd2': {}, 'status': 'COMPLETED', 'conclusion': 'UNRESOLVED'}) + '\n')
            (directory / 'events.jsonl').write_text(json.dumps({'kind':'PLAN_DURABLE','value':{'planHash':fingerprint(plan)}})+'\n'
                + json.dumps({'kind':'RUN_COMPLETE','value':{'resultHash':fingerprint(report)}})+'\n')
            return report
        self.server = create_server(ROOT, 0, agent_targets=lambda: [target],
            agent_status=lambda: {'ready': True, 'snapshotId': 's'},
            agent_preview=lambda sample: {'sampleId': sample, 'pool': {'candidates': []},
                'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': '', 'evaluations': {}}},
            agent_runner=run,
            agent_store=Path(self.temp.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2); self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path, body, headers or {})
        response = conn.getresponse(); data = response.read(); status = response.status; conn.close()
        return status, data

    def test_reads_never_run_and_post_is_restricted(self):
        for path in ('/agent.html', '/agent.js', '/api/agent/status', '/api/agent/targets',
                     '/api/agent/preview?sampleId=AC-ASE-006', '/api/agent/runs'):
            self.assertEqual(200, self.request('GET', path)[0], path)
        self.assertEqual([], self.calls)
        headers = {'Content-Type': 'application/json'}
        self.assertEqual(400, self.request('POST', '/api/agent/runs', b'{"sampleId":"AC-ASE-006","mode":"offline","x":1}', headers)[0])
        self.assertEqual(400, self.request('POST', '/api/agent/runs', b'{"sampleId":"UNKNOWN","mode":"offline"}', headers)[0])
        self.assertEqual(400, self.request('POST', '/api/agent/runs', b'{"sampleId":"AC-ASE-006","sampleId":"AC-ASE-006","mode":"real"}', headers)[0])
        self.assertEqual(400, self.request('POST', '/api/agent/runs', b'x'*257, headers)[0])
        self.assertEqual(403, self.request('POST', '/api/agent/runs', b'{"sampleId":"AC-ASE-006","mode":"real"}',
                                      {**headers, 'Origin': 'https://example.com'})[0])
        self.assertEqual([], self.calls)
        status, body = self.request('POST', '/api/agent/runs', b'{"sampleId":"AC-ASE-006","mode":"offline"}', headers)
        self.assertEqual(201, status)
        self.assertEqual('a'*32, json.loads(body)['runId'])
        self.assertEqual([('AC-ASE-006', 'offline')], self.calls)
        self.assertEqual(200, self.request('GET', '/api/agent/runs/' + 'a'*32)[0])
        self.assertEqual(200, self.request('GET', '/api/agent/runs/' + 'a'*32 + '/report')[0])
        self.assertEqual([('AC-ASE-006', 'offline')], self.calls)

    def test_strategy_whitelist_and_read_only_preview(self):
        code, body = self.request('GET', '/api/agent/preview?sampleId=AC-ASE-006&strategy=DENSE')
        self.assertEqual(200, code)
        self.assertEqual('DENSE', json.loads(body)['strategy'])
        self.assertEqual([], self.calls)
        self.assertEqual(400, self.request('GET', '/api/agent/preview?sampleId=AC-ASE-006&strategy=UNKNOWN')[0])
        headers = {'Content-Type': 'application/json'}
        self.assertEqual(400, self.request('POST', '/api/agent/runs',
            b'{"sampleId":"AC-ASE-006","mode":"offline","strategy":"UNKNOWN"}', headers)[0])
        self.assertEqual([], self.calls)
        status, _ = self.request('POST', '/api/agent/runs',
            b'{"sampleId":"AC-ASE-006","mode":"offline","strategy":"FIELD_FILTER"}', headers)
        self.assertEqual(201, status)
        self.assertEqual([('AC-ASE-006', 'offline', 'FIELD_FILTER')], self.calls)


if __name__ == '__main__': unittest.main()
