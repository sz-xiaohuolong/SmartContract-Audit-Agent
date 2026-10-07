"""批量页面接口必须先预览计划并持久化对照。"""
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from local_ui import create_server
from batch_compare import make_plan, prepare_batch
from storage import encode

ROOT = Path(__file__).resolve().parents[3]


class BatchUiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        targets = [{'sampleId': 'A', 'split': 'validation', 'runnable': True},
                   {'sampleId': 'B', 'split': 'validation', 'runnable': True}]
        state = {'ready': True, 'realReady': True, 'snapshotId': 's' * 64,
                 'collection': 's1b_' + 'a' * 32, 'endpoint': 'https://example.test', 'model': 'fixed'}
        def runner(sample, mode, strategy):
            self.calls.append((sample, mode, strategy))
            return {'runId': str(len(self.calls)).zfill(32), 'status': 'COMPLETED',
                    'researchEligible': False, 'conclusion': 'UNRESOLVED',
                    'plan': {'sampleId': sample, 'mode': mode, 'strategy': strategy,
                             'snapshotId': 's' * 64, 'poolHash': sample},
                    'retrieval': {'d1': {'selected': []}},
                    'model': {'status': 'COMPLETED', 'inputTokens': None, 'outputTokens': None},
                    'd2': {'verdict': 'UNKNOWN'}}
        self.server = create_server(ROOT, 0, agent_targets=lambda: targets, agent_status=lambda: state,
                                    agent_preview=lambda _: {}, agent_runner=runner,
                                    agent_store=Path(self.temp.name) / 'single',
                                    batch_store=Path(self.temp.name) / 'batch')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2); self.temp.cleanup()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        connection.request(method, path, body, {'Content-Type': 'application/json'} if body else {})
        response = connection.getresponse()
        result = response.read(); status = response.status; connection.close()
        return status, json.loads(result) if result and response.getheader('Content-Type', '').startswith('application/json') else result

    def test_preview_does_not_run_and_batch_reports_unknown(self):
        choice = {'sampleIds': ['A', 'B'], 'strategies': ['DENSE', 'FIELD_FILTER', 'D1'], 'mode': 'offline'}
        code, plan = self.request('POST', '/api/agent/batches/plan', choice)
        self.assertEqual(200, code)
        self.assertEqual([], self.calls)
        self.assertEqual(400, self.request('POST', '/api/agent/batches', {**choice, 'planHash': 'wrong'})[0])
        code, created = self.request('POST', '/api/agent/batches', {**choice, 'planHash': plan['planHash']})
        self.assertEqual(202, code)
        for _ in range(100):
            code, report = self.request('GET', '/api/agent/batches/' + created['batchId'])
            if report['status'] == 'COMPLETED': break
            time.sleep(.01)
        self.assertEqual(200, code)
        self.assertEqual(6, report['denominators']['planned'])
        self.assertEqual(6, report['denominators']['unknown'])
        self.assertIsNone(report['metrics']['D1']['detectionRecall'])
        self.assertEqual(6, len(self.calls))
        self.assertEqual(200, self.request('GET', '/api/agent/batches')[0])
        self.assertEqual(200, self.request('GET', '/api/agent/batches/' + created['batchId'] + '/report')[0])

    def test_explicit_real_batch_runs_with_fixed_request_count(self):
        code, plan = self.request('POST', '/api/agent/batches/plan',
                                  {'sampleIds': ['A'], 'strategies': ['D1'], 'mode': 'real'})
        self.assertEqual(200, code)
        self.assertIsNone(plan['requestBounds']['maxInputTokens'])
        code, created = self.request('POST', '/api/agent/batches',
                               {'sampleIds': ['A'], 'strategies': ['D1'], 'mode': 'real',
                                'planHash': plan['planHash']})
        self.assertEqual(202, code)
        for _ in range(100):
            _, report = self.request('GET', '/api/agent/batches/' + created['batchId'])
            if report['status'] == 'COMPLETED': break
            time.sleep(.01)
        self.assertEqual([('A', 'real', 'D1')], self.calls)
        self.assertEqual(1, plan['requestBounds']['maxRequests'])
        self.assertEqual(1, report['denominators']['unknown'])

    def test_offline_interrupted_batch_can_resume_without_repeating_started_item(self):
        choice = {'sampleIds': ['A'], 'strategies': ['DENSE', 'D1'], 'mode': 'offline'}
        _, plan = self.request('POST', '/api/agent/batches/plan', choice)
        directory = prepare_batch(Path(self.temp.name) / 'batch', plan, 'c' * 32)
        with (directory / 'events.jsonl').open('ab') as output:
            output.write(encode({'kind': 'STARTED', 'sampleId': 'A', 'strategy': 'DENSE'}) + b'\n')
        code, _ = self.request('POST', '/api/agent/batches/' + 'c' * 32 + '/resume',
                               {'planHash': plan['planHash']})
        self.assertEqual(202, code)
        for _ in range(100):
            _, report = self.request('GET', '/api/agent/batches/' + 'c' * 32)
            if report['status'] == 'COMPLETED': break
            time.sleep(.01)
        self.assertEqual([('A', 'offline', 'D1')], self.calls)
        self.assertEqual(1, report['denominators']['failed'])
        self.assertEqual(2, report['denominators']['unknown'])


if __name__ == '__main__':
    unittest.main()
