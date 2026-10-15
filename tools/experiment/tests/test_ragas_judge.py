"""真实 Ragas 包连接本地 HTTP 夹具，不调用外部模型。"""
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from eval_ragas import qrels_template
from test_eval_ragas import dataset
from ragas_judge import run_judge


class JudgeBoundaryTest(unittest.TestCase):
    def test_未明确启用不能导入评估依赖或发出请求(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                run_judge(dataset(), None, {}, Path(temp) / 'result', False)
            self.assertFalse((Path(temp) / 'result').exists())


@unittest.skipUnless(importlib.util.find_spec('ragas'), '可选集成测试需安装固定的 Ragas 环境')
class LocalRagasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'result'
        self.requests = []
        self.mode = 'ok'
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append(body)
                if owner.mode == 'http_error':
                    self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"fixture"}'); return
                name = body['response_format']['json_schema']['name']
                payloads = {'ContextPrecisionOutput': {'reason': '相关', 'verdict': 1},
                            'ContextRecallOutput': {'classifications': [{'statement': '付款后扣余额', 'reason': '有关', 'attributed': 1}]},
                            'ContextRelevanceOutput': {'rating': 2},
                            'StatementGeneratorOutput': {'statements': ['付款后扣余额']},
                            'NLIStatementOutput': {'statements': [{'statement': '付款后扣余额', 'reason': '有源码依据', 'verdict': 1}]}}
                payload = payloads[name]
                if owner.mode == 'missing_statement' and name == 'StatementGeneratorOutput':
                    payload = {'statements': ['付款后扣余额', '回调可以再次提取余额']}
                if owner.mode == 'invalid': payload = {'rating': 9, 'verdict': 7, 'reason': '无效'}
                content = json.dumps(payload, ensure_ascii=False)
                response = {'id': 'local-fixture', 'object': 'chat.completion', 'created': 1, 'model': 'fixture',
                            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}]}
                if owner.mode != 'missing_usage': response['usage'] = {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}
                raw = json.dumps(response, ensure_ascii=False).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.config = {'baseUrl': f'http://127.0.0.1:{self.server.server_port}/v1', 'model': 'fixture',
                       'apiKeyEnv': 'TEST_RAGAS_KEY', 'maxRequests': 7, 'maxOutputTokens': 512,
                       'timeoutSeconds': 5, 'metrics': ['context_precision', 'context_recall', 'context_relevance', 'faithfulness']}
        self.env = patch.dict(os.environ, {'TEST_RAGAS_KEY': 'fixture-secret-do-not-save'})
        self.env.start(); self.addCleanup(self.env.stop)

    def run_fixture(self):
        data = dataset(); qrels = qrels_template(data)
        qrels['queries'][0].update(reviewStatus='REVIEWED', reviewer='夹具审核人', rationale='合成样本',
                                   grades={'a': 2, 'b': 1, 'c': 0}, reference='withdraw 付款后扣余额。')
        return run_judge(data, qrels, self.config, self.output, True)

    def test_真实指标完成且原始响应与用量可追溯(self):
        report = self.run_fixture()
        self.assertEqual('COMPLETED', report['status'])
        self.assertEqual(7, report['requestAttempts'])
        self.assertEqual(7, len(self.requests))
        self.assertAlmostEqual(1.0, report['rows'][0]['scores']['context_precision'])
        self.assertEqual(1.0, report['rows'][0]['scores']['faithfulness'])
        self.assertEqual(70, report['usage']['inputTokens'])
        raw = '\n'.join(p.read_text() for p in self.output.rglob('*.json'))
        self.assertNotIn('fixture-secret-do-not-save', raw)
        self.assertEqual(7, len(list(self.output.glob('requests/*.response.json'))))
        nli = next(r for r in self.requests if r['response_format']['json_schema']['name'] == 'NLIStatementOutput')
        self.assertIn('contract C', str(nli))

    def test_请求上限在一个指标内部也生效(self):
        self.config.update(maxRequests=1, metrics=['faithfulness'])
        report = self.run_fixture()
        self.assertEqual(1, len(self.requests))
        self.assertEqual('PARTIAL', report['status'])
        self.assertIsNone(report['rows'][0]['scores']['faithfulness'])

    def test_HTTP失败不重试且不记零分(self):
        self.mode = 'http_error'; self.config['metrics'] = ['context_precision']
        report = self.run_fixture()
        self.assertEqual(1, len(self.requests))
        self.assertIsNone(report['rows'][0]['scores']['context_precision'])
        self.assertIsNone(report['usage']['inputTokens'])
        self.assertEqual('PARTIAL', report['status'])

    def test_相关性内置双提示不能掩盖失败或重试(self):
        self.mode = 'invalid'; self.config['metrics'] = ['context_relevance']
        report = self.run_fixture()
        self.assertEqual(1, len(self.requests))
        self.assertIsNone(report['rows'][0]['scores']['context_relevance'])

    def test_usage缺失保留null(self):
        self.mode = 'missing_usage'; self.config['metrics'] = ['context_precision']
        report = self.run_fixture()
        self.assertEqual(2, len(self.requests))
        self.assertIsNone(report['usage']['inputTokens'])
        self.assertEqual(2, report['usage']['missingRequests'])

    def test_忠实度漏判陈述不能缩小分母抬高得分(self):
        self.mode = 'missing_statement'; self.config['metrics'] = ['faithfulness']
        report = self.run_fixture()
        self.assertEqual(2, len(self.requests))
        self.assertIsNone(report['rows'][0]['scores']['faithfulness'])
        self.assertEqual('PARTIAL', report['status'])

    def test_无参考答案不偷偷改用模型答案(self):
        self.config['metrics'] = ['context_precision', 'context_recall']
        report = run_judge(dataset(), None, self.config, self.output, True)
        self.assertEqual(0, len(self.requests))
        self.assertEqual('MISSING_REFERENCE', report['rows'][0]['metrics']['context_precision']['status'])


if __name__ == '__main__':
    unittest.main()
