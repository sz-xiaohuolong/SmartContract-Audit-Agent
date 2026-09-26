"""本地实验页面的离线接口回归。"""
import http.client
import json
from copy import deepcopy
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
        report = Path(self.directory.name) / 'reports' / run_id
        lines = (report / 'samples.jsonl').read_text(encoding='utf-8').splitlines()
        self.assertEqual([json.loads(line) for line in lines], DEMO['samples'])
        summary = json.loads((report / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['denominators'], DEMO['denominators'])
        self.assertEqual(result['report']['sampleCount'], len(lines))
        status, headers, body = self.request('GET', '/api/runs/' + run_id + '/report')
        self.assertEqual(status, 200)
        self.assertIn('application/x-ndjson', headers['Content-Type'])
        self.assertIn('samples.jsonl', headers['Content-Disposition'])
        self.assertEqual([json.loads(line) for line in body.splitlines()], DEMO['samples'])
        self.assertEqual(len(self.calls), 1)

    def test_invalid_sample_result_does_not_publish_partial_report(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        invalid = dict(DEMO, samples=[])
        self.server = create_server(ROOT, 0, Path(self.directory.name), lambda: invalid)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        status, _, _ = self.request('POST', '/api/runs', b'{}', {'Content-Type': 'application/json'})
        self.assertEqual(status, 500)
        self.assertEqual(list(Path(self.directory.name).glob('*.json')), [])
        self.assertEqual(list((Path(self.directory.name) / 'reports').glob('*')), [])

    def test_multiple_samples_get_separate_report_lines(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        result = deepcopy(DEMO)
        second = deepcopy(result['samples'][0])
        second['id'] = 'target-2'
        result['samples'].append(second)
        result['denominators']['planned'] = 2
        result['denominators']['completed'] = 2
        self.server = create_server(ROOT, 0, Path(self.directory.name), lambda: result)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        status, _, body = self.request('POST', '/api/runs', b'{}', {'Content-Type': 'application/json'})
        self.assertEqual(status, 201)
        run_id = json.loads(body)['runId']
        lines = (Path(self.directory.name) / 'reports' / run_id / 'samples.jsonl').read_text(encoding='utf-8').splitlines()
        self.assertEqual([json.loads(line)['id'] for line in lines], ['target', 'target-2'])

    def test_malformed_runner_result_is_reported_without_server_crash(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server = create_server(ROOT, 0, Path(self.directory.name), lambda: {'tokenProfile': {'purpose': 'FIXTURE'}, 'denominators': None})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        status, _, body = self.request('POST', '/api/runs', b'{}', {'Content-Type': 'application/json'})
        self.assertEqual(status, 500)
        self.assertIn('离线运行失败'.encode(), body)

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

    def test_history_uses_run_time_instead_of_random_file_name(self):
        old_id = 'f' * 32
        new_id = '0' * 32
        for identifier, created_at in [(old_id, '2026-09-24T00:00:00+00:00'),
                                       (new_id, '2026-09-26T00:00:00+00:00')]:
            (Path(self.directory.name) / (identifier + '.json')).write_text(json.dumps({
                'runId': identifier, 'kind': 'SYNTHETIC_DEMO', 'createdAt': created_at}))
        status, _, body = self.request('GET', '/api/runs')
        self.assertEqual(status, 200)
        self.assertEqual([row['runId'] for row in json.loads(body)['runs']], [new_id, old_id])

    def test_mvp_is_explicit_and_history_does_not_call_model(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        model_calls = []
        report = {'plan': {'runId': 'a' * 32, 'maxRequests': 1, 'sampleId': 'AC-ASE-006'},
                  'result': {'status': 'FAILED', 'conclusion': 'UNRESOLVED',
                             'inputTokens': None, 'outputTokens': None},
                  'status': 'FAILED', 'researchEligible': False}
        self.server = create_server(ROOT, 0, Path(self.directory.name), lambda: DEMO,
                                    lambda: model_calls.append(1) or report,
                                    lambda: {'snapshotId': 's', 'documentCount': 3})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.assertEqual(self.request('GET', '/api/mvp/status')[0], 200)
        self.assertEqual(self.request('GET', '/mvp.html')[0], 200)
        self.assertEqual(self.request('GET', '/api/mvp/runs')[0], 200)
        self.assertEqual(model_calls, [])
        self.assertEqual(self.request('POST', '/api/mvp/run', b'{"sample":"other"}', {'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(model_calls, [])
        status, _, body = self.request('POST', '/api/mvp/run', b'{}', {'Content-Type': 'application/json'})
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)['result']['conclusion'], 'UNRESOLVED')
        self.assertEqual(model_calls, [1])


if __name__ == '__main__':
    unittest.main()
