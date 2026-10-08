"""新审计页面的只读与显式运行边界。"""
import http.client
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from local_ui import create_server, pending_knowledge_status
from storage import fingerprint

ROOT = Path(__file__).resolve().parents[3]


class PendingKnowledgeStatusTest(unittest.TestCase):
    def test_页面只展示已读回的待审数量(self):
        class Index:
            def request(self, endpoint, payload):
                if endpoint == 'collections/has': return {'has': True}
                if endpoint == 'entities/query':
                    return [{'id': 'candidate-a'}] if payload['offset'] == 0 else []
                raise AssertionError(endpoint)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(pending_knowledge_status(root, Index()))
            file = root / '.local/dataset-candidates/r1-pending/receipt.json'
            file.parent.mkdir(parents=True)
            receipt = {'collection': 'r1pending_' + 'a' * 32, 'candidateOnly': True,
                       'formalD1Enabled': False, 'vectorCount': 1, 'automescPairs': 1, 'forgeVfp': 0}
            file.write_text(json.dumps(receipt))
            self.assertEqual(1, pending_knowledge_status(root, Index())['vectors'])
            receipt['vectorCount'] = 2
            file.write_text(json.dumps(receipt))
            with self.assertRaises(ValueError): pending_knowledge_status(root, Index())


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
            agent_status=lambda: {'ready': True, 'snapshotId': 'f' * 64},
            agent_preview=lambda sample: {'sampleId': sample, 'pool': {'candidates': []},
                'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': '', 'evaluations': {}}},
            agent_runner=run,
            agent_store=Path(self.temp.name),
            exploratory_store=Path(self.temp.name) / 'exploratory',
            exploratory_runner=lambda: self.calls.append(('exploratory', 'offline')),
            auto_store=Path(self.temp.name) / 'auto',
            auto_targets=lambda: [{'sampleId': 'bench', 'sourceHash': 'b' * 64,
                'runnable': True, 'groundTruth': {'hasVulnerability': True,
                'vulnerabilityType': 'REENTRANCY', 'labelSource': 'fixture'}}],
            auto_runtime=lambda: type('Runner', (), {'pointer': {'snapshot_id': 'f' * 64},
                'run': lambda self, target, strategy, mode: {
                'status': 'COMPLETED', 'prediction': 'UNKNOWN', 'categoryHit': True,
                'selectedEvidence': 2, 'inputTokens': None, 'outputTokens': None,
                'durationMs': 0, 'model': {}}})())
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

    def test_探索入口只有点击才运行且不会接受请求正文(self):
        status, body = self.request('GET', '/api/agent/exploratory')
        self.assertEqual(200, status)
        self.assertIsNone(json.loads(body)['report'])
        self.assertEqual([], self.calls)
        self.assertEqual(409, self.request('POST', '/api/agent/exploratory', b'{}')[0])
        self.assertEqual(403, self.request('POST', '/api/agent/exploratory', None,
                                         {'Origin': 'https://example.com'})[0])
        self.assertEqual(202, self.request('POST', '/api/agent/exploratory')[0])
        for _ in range(20):
            if self.calls:
                break
            threading.Event().wait(.01)
        self.assertEqual([('exploratory', 'offline')], self.calls)

    def test_自动知识批量页面可启动读取并下载两种报告(self):
        status, body = self.request('GET', '/api/agent/auto-benchmark/targets')
        self.assertEqual(200, status)
        self.assertEqual('bench', json.loads(body)['targets'][0]['sampleId'])
        payload = {'sampleIds': ['bench'], 'strategies': ['D1'], 'mode': 'offline'}
        headers = {'Content-Type': 'application/json'}
        status, body = self.request('POST', '/api/agent/auto-benchmark/plan', json.dumps(payload), headers)
        self.assertEqual(200, status)
        payload['planHash'] = json.loads(body)['planHash']
        status, body = self.request('POST', '/api/agent/auto-benchmark/runs', json.dumps(payload), headers)
        self.assertEqual(202, status)
        batch_id = json.loads(body)['batchId']
        for _ in range(50):
            status, body = self.request('GET', '/api/agent/auto-benchmark/runs/' + batch_id)
            if status == 200 and json.loads(body)['status'] == 'COMPLETED':
                break
            threading.Event().wait(.01)
        self.assertEqual('COMPLETED', json.loads(body)['status'])
        self.assertEqual(200, self.request('GET', '/api/agent/auto-benchmark/runs/' + batch_id + '/samples.jsonl')[0])
        self.assertEqual(200, self.request('GET', '/api/agent/auto-benchmark/runs/' + batch_id + '/samples.csv')[0])


if __name__ == '__main__': unittest.main()
