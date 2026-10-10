"""Apple 工作台的完整响应、只读模拟及未知语义回归。"""
import http.client
import json
import threading
import unittest
from pathlib import Path

import local_ui
from audit_target import pasted_target

ROOT = Path(__file__).resolve().parents[3]


class WorkspaceDocumentTest(unittest.TestCase):
    def test_失败与缺失用量不能变成安全或零成本(self):
        result = local_ui.workspace_document({
            'status': 'FAILED', 'conclusion': 'UNRESOLVED',
            'target': {'fullSource': 'contract X {}', 'fullSourceLineStart': 7},
            'model': {'inputTokens': 13, 'outputTokens': None},
            'tools': [{'engine': 'SLITHER', 'status': 'PROCESS_ERROR'}],
        })
        self.assertEqual('UNRESOLVED', result['conclusion'])
        self.assertIsNone(result['telemetry']['totalTokens'])
        self.assertIsNone(result['telemetry']['cost'])
        self.assertIsNone(result['telemetry']['durationMs'])
        self.assertEqual(13, result['telemetry']['inputTokens'])
        self.assertEqual('UNKNOWN', result['d2']['verdict'])
        self.assertEqual(6, len(result['d2']['assessments'][0]['obligations']))
        self.assertEqual(7, result['source']['lineStart'])
        self.assertEqual('PROCESS_ERROR', result['tools'][0]['status'])

    def test_保留全部假设配对路径和原始行号(self):
        value = {'target': {'fullSource': 'a\nb', 'modelSource': 'b', 'modelLineStart': 12},
                 'retrieval': {'d1': {'selected': [{'candidate': {'caseId': 'c', 'text': '源码'}}]},
                               'facts': {'status': 'PARTIAL'}},
                 'model': {'inputTokens': 10, 'outputTokens': 2, '_rawResponse': '不得暴露'},
                 'd2': {'verdict': 'REFUTED', 'assessments': [
                     {'hypothesisIndex': 0, 'obligations': [{'name': 'actor', 'status': 'SUPPORTED',
                       'references': [{'line': 12}]}], 'pathEvidence': {'status': 'BLOCKED'}},
                     {'hypothesisIndex': 1, 'obligations': []}]},
                 'stages': [{'durationMs': 3}, {'durationMs': 4}]}
        result = local_ui.workspace_document(value)
        self.assertEqual(12, result['telemetry']['totalTokens'])
        self.assertEqual(7, result['telemetry']['durationMs'])
        self.assertNotIn('_rawResponse', result['model'])
        self.assertEqual(2, len(result['d2']['assessments']))
        self.assertEqual([{'line': 12}], result['d2']['assessments'][0]['obligations'][0]['references'])
        self.assertEqual('BLOCKED', result['d2']['assessments'][0]['pathEvidence']['status'])
        self.assertEqual('c', result['retrieval']['d1']['selected'][0]['candidate']['caseId'])


class WorkspaceHttpTest(unittest.TestCase):
    def setUp(self):
        target = pasted_target('contract Vault { uint funds; function update() public { funds = 0; } }', 'ACCESS_CONTROL')
        target.update(sampleId='test', runnable=True)
        class Workbench:
            def status(self, profile):
                return {'ready': False, 'realReady': False, 'embeddingProfile': profile}

            def targets(self):
                return [{'sampleId': 'test', 'runnable': True}]

            def history(self):
                return [{'runId': 'a' * 32, 'sampleId': 'test', 'status': 'FAILED', 'createdAt': '2026-10-10'}]

            def read(self, identifier):
                return {'runId': identifier, 'status': 'FAILED', 'conclusion': 'UNRESOLVED',
                        'plan': {'mode': 'real', 'strategy': 'DENSE', 'embeddingProfile': 'bge'},
                        'target': target, 'tools': [{'status': 'TIMEOUT', 'engine': 'SLITHER'}]}

            def target_loader(self):
                return [target]

        self.server = local_ui.create_server(ROOT, 0, workbench=Workbench(),
            agent_targets=lambda: [], agent_status=lambda: {}, agent_preview=lambda _: {},
            agent_runner=lambda *args: self.fail('读取界面不能执行模型'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def get(self, path):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request('GET', path)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, json.loads(body)

    def test_无知识服务也可读界面状态与模拟(self):
        code, state = self.get('/api/agent/workspace?embeddingProfile=nomic')
        self.assertEqual(200, code)
        self.assertFalse(state['status']['ready'])
        self.assertEqual('test', state['targets'][0]['sampleId'])
        code, demo = self.get('/api/agent/workspace/simulation?strategy=D1')
        self.assertEqual(200, code)
        self.assertEqual('SYNTHETIC_DEMO', demo['kind'])
        self.assertEqual(0, demo['modelCalls'])
        self.assertFalse(demo['researchEligible'])
        self.assertEqual('UNRESOLVED', demo['conclusion'])
        self.assertEqual(2, len(demo['retrieval']['d1']['selected']))
        self.assertEqual(6, len(demo['d2']['assessments'][0]['obligations']))
        self.assertIsNone(demo['telemetry']['totalTokens'])

    def test_源码只读和历史模式按原记录返回(self):
        code, target = self.get('/api/agent/workspace/target?sampleId=test')
        self.assertEqual(200, code)
        self.assertIn('contract Vault', target['source']['full'])
        self.assertNotIn('groundTruth', target['target'])
        code, history = self.get('/api/agent/workspace/runs')
        self.assertEqual(200, code)
        self.assertEqual('real', history['runs'][0]['mode'])
        self.assertEqual('DENSE', history['runs'][0]['strategy'])
        code, result = self.get('/api/agent/workspace/runs/' + 'a' * 32)
        self.assertEqual(200, code)
        self.assertEqual('UNRESOLVED', result['conclusion'])
        self.assertEqual('TIMEOUT', result['tools'][0]['status'])
        self.assertIsNone(result['telemetry']['totalTokens'])

    def test_无效策略和重复参数返回JSON错误(self):
        for path in ('/api/agent/workspace?embeddingProfile=bad',
                     '/api/agent/workspace/simulation?strategy=Vanilla',
                     '/api/agent/workspace/simulation?strategy=D1&strategy=DENSE',
                     '/api/agent/workspace?broken'):
            code, body = self.get(path)
            self.assertEqual(400, code, path)
            self.assertIn('error', body)


if __name__ == '__main__':
    unittest.main()
