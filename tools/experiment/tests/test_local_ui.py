"""本地实验页面的离线接口回归。"""
import http.client
import json
import hashlib
from copy import deepcopy
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from local_ui import create_server
import local_ui


ROOT = Path(__file__).resolve().parents[3]
DEMO = json.loads((ROOT / 'tools/experiment/fixtures/research-pilot/pilot.json').read_text(encoding='utf-8'))


class WorkspaceCaseTest(unittest.TestCase):
    def test_公开案例的登记候选不读取真值行(self):
        from benchmark_targets import load_benchmark_targets
        rows = load_benchmark_targets(ROOT, [])
        registered = local_ui.workspace_case_targets(ROOT, rows)
        cases = [row for row in registered if row.get('caseGroup') == 'SMARTBUGS_DEFENSIVE']
        self.assertEqual({'ACCESS_CONTROL', 'REENTRANCY'}, {row['mechanism'] for row in cases})
        self.assertTrue(all(row['savedHypotheses'] and not row['researchEligible'] for row in cases))
        altered = deepcopy(rows)
        for row in altered:
            row['vulnerableLines'] = [1]
            row['groundTruth'] = {'hasVulnerability': False}
        repeated = local_ui.workspace_case_targets(ROOT, altered)
        self.assertEqual({row['sampleId']: row['savedHypotheses'] for row in cases},
            {row['sampleId']: row['savedHypotheses'] for row in repeated
             if row.get('caseGroup') == 'SMARTBUGS_DEFENSIVE'})
        self.assertEqual(['changeOwner(address)', 'withdraw(uint256)'],
                         [row['savedHypotheses'][0]['function'] for row in cases])

    def test_离线演练保留核验矩阵且不能升级为学术安全结论(self):
        from audit_target import pasted_target
        target = pasted_target('contract C { uint x; function f() public { x = 1; } }', 'ACCESS_CONTROL')
        target.update(savedHypotheses=[{'contract': 'C', 'function': 'f()', 'riskLine': 1}],
                      caseLabel='公开案例的登记候选', claimOrigin='REGISTERED_DEFENSIVE_DEMONSTRATION')
        calls = []
        def analyze(root, current, hypotheses):
            calls.append((current, hypotheses))
            return {'facts': {'status': 'COMPLETE'}, 'tools': [{'engine': 'SLITHER', 'status': 'OK'}],
                    'd2': {'verdict': 'SUPPORTED', 'assessments': [{'obligations': [
                        {'name': 'actor', 'status': 'REFUTED', 'references': [{'line': 1}]}]}]},
                    'newModelRequests': 0}
        result = local_ui.workspace_rehearsal(ROOT, target, analyzer=analyze)
        self.assertEqual('OFFLINE_REHEARSAL', result['kind'])
        self.assertEqual('SUPPORTED', result['d2']['verdict'])
        self.assertEqual('REFUTED', result['d2']['assessments'][0]['obligations'][0]['status'])
        self.assertEqual(6, len(result['d2']['assessments'][0]['obligations']))
        self.assertEqual('UNRESOLVED', result['conclusion'])
        self.assertEqual(0, result['newModelRequests'])
        self.assertIsNone(result['telemetry']['totalTokens'])
        self.assertFalse(result['researchEligible'])
        self.assertEqual(1, len(calls))

    def test_离线演练工具失败仍未知(self):
        from audit_target import pasted_target
        target = pasted_target('contract C { uint x; function f() public { x = 1; } }', 'ACCESS_CONTROL')
        target['savedHypotheses'] = [{'contract': 'C', 'function': 'f()', 'riskLine': 1}]
        def analyze(*args):
            raise RuntimeError('编译工具不可用')
        result = local_ui.workspace_rehearsal(ROOT, target, analyzer=analyze)
        self.assertEqual('FAILED', result['status'])
        self.assertEqual('UNKNOWN', result['d2']['verdict'])
        self.assertEqual({'UNKNOWN'}, {row['status'] for row in result['d2']['assessments'][0]['obligations']})
        self.assertEqual('UNRESOLVED', result['conclusion'])

    def test_显式演练接口只接受登记候选且读取不执行工具(self):
        from audit_target import pasted_target
        target = pasted_target('contract C { uint x; function f() public { x = 1; } }', 'ACCESS_CONTROL')
        target.update(sampleId='academic-ac', savedHypotheses=[{'contract': 'C', 'function': 'f()', 'riskLine': 1}])
        calls = []
        class Workbench:
            def target_loader(self):
                return [target]
            def targets(self):
                return [{'sampleId': target['sampleId'], 'runnable': True, 'savedHypotheses': target['savedHypotheses']}]
            def status(self, profile):
                return {'ready': False}
            def preview(self, payload):
                raise RuntimeError('固定快照不可用')
        def analyze(*args):
            calls.append(args)
            return {'newModelRequests': 0, 'tools': [{'engine': 'SLITHER', 'status': 'OK'}],
                    'd2': {'verdict': 'REFUTED', 'assessments': [{'obligations': [
                        {'name': 'actor', 'status': 'SUPPORTED'}]}]}}
        server = create_server(ROOT, 0, workbench=Workbench(), workspace_analyzer=analyze,
            agent_targets=lambda: [], agent_status=lambda: {}, agent_preview=lambda _: {},
            agent_runner=lambda *args: self.fail('离线演练不能调用模型'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, path, payload=None, headers=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            body = json.dumps(payload) if payload is not None else None
            connection.request(method, path, body, headers or {'Content-Type': 'application/json'})
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result
        try:
            self.assertEqual(200, request('GET', '/api/agent/workspace')[0])
            self.assertEqual([], calls)
            payload = {'sampleId': 'academic-ac', 'strategy': 'D1', 'embeddingProfile': 'nomic'}
            self.assertEqual(400, request('POST', '/api/agent/workspace/rehearsal', {**payload, 'source': '替身'})[0])
            self.assertEqual(400, request('POST', '/api/agent/workspace/rehearsal', {**payload, 'sampleId': 'missing'})[0])
            self.assertEqual([], calls)
            code, result = request('POST', '/api/agent/workspace/rehearsal', payload)
            self.assertEqual(200, code)
            self.assertEqual('REFUTED', result['d2']['verdict'])
            self.assertEqual('SUPPORTED', result['d2']['assessments'][0]['obligations'][0]['status'])
            self.assertEqual(1, len(calls))
        finally:
            server.shutdown(); server.server_close(); thread.join(2)

    def test_派生报告读回核对封口摘要和原件且不重跑(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'original'
            original.mkdir()
            (original / 'samples.jsonl').write_text('原批次\n', encoding='utf-8')
            provenance = {'originalRun': str(original), 'originalBatchId': 'original-batch',
                'originalSamplesSha256': hashlib.sha256((original / 'samples.jsonl').read_bytes()).hexdigest(),
                'originalFileHashes': {'samples.jsonl': hashlib.sha256((original / 'samples.jsonl').read_bytes()).hexdigest()},
                'newModelRequests': 0}
            store = root / 'derived'
            identifier = 'a' * 32
            output = store / identifier
            output.mkdir(parents=True)
            values = {'samples.jsonl': json.dumps({'sampleId': 'public-sample', 'provenance': provenance}) + '\n',
                'assessments.jsonl': '{}\n', 'REPORT.md': '派生报告',
                'summary.json': json.dumps({'units': 1, 'newModelRequests': 0,
                    'researchEligible': False, 'provenance': provenance,
                    'unknownComparison': {'denominator': 1, 'beforeRate': 1, 'afterRate': 0}})}
            for name, content in values.items():
                (output / name).write_text(content, encoding='utf-8')
            manifest = {'status': 'COMPLETED', 'provenance': provenance, 'completedUnits': 1,
                        'outputHashes': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in values}}
            (output / 'manifest.json').write_text(json.dumps(manifest))
            result = local_ui.workspace_derived_report(root, store, identifier)
            self.assertEqual(0, result['summary']['newModelRequests'])
            self.assertTrue(result['originalAvailable'])
            self.assertEqual('public-sample', result['samples'][0]['sampleId'])
            server = create_server(root, 0, derived_store=store, workbench=object(),
                agent_targets=lambda: [], agent_status=lambda: {}, agent_preview=lambda _: {},
                agent_runner=lambda *args: self.fail('派生读回不得执行模型'))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def get(path):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                connection.request('GET', path)
                response = connection.getresponse()
                result = response.status, response.getheader('Content-Disposition'), response.read()
                connection.close()
                return result
            try:
                code, _, body = get('/api/agent/workspace/derived')
                self.assertEqual(200, code)
                self.assertEqual(identifier, json.loads(body)['runs'][0]['runId'])
                code, _, body = get('/api/agent/workspace/derived/' + identifier)
                self.assertEqual(200, code)
                self.assertEqual('public-sample', json.loads(body)['samples'][0]['sampleId'])
                for name in values:
                    code, disposition, body = get('/api/agent/workspace/derived/' + identifier + '/' + name)
                    self.assertEqual(200, code)
                    self.assertIn(name, disposition)
                    self.assertEqual((output / name).read_bytes(), body)
                self.assertEqual(404, get('/api/agent/workspace/derived/' + identifier + '/secret')[0])
            finally:
                server.shutdown(); server.server_close(); thread.join(2)
            (original / 'samples.jsonl').write_text('原件被修改')
            with self.assertRaises(ValueError):
                local_ui.workspace_derived_report(root, store, identifier)
            (original / 'samples.jsonl').unlink()
            original.rmdir()
            self.assertFalse(local_ui.workspace_derived_report(root, store, identifier)['originalAvailable'])
            (output / 'samples.jsonl').write_text('结果被修改')
            with self.assertRaises(ValueError):
                local_ui.workspace_derived_report(root, store, identifier)
            with self.assertRaises(ValueError):
                local_ui.workspace_derived_report(root, store, '../original')


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
