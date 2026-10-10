"""用真实 Java 网关、本机 HTTP 与 Slither 子进程夹具验证六阶段闭环。"""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from audit_run import model_runner, tool_runner
from audit_workbench import AuditWorkbench
from test_audit_workbench import Runtime
from test_d2_verify import ACCESS

ROOT = Path(__file__).resolve().parents[3]
JAR = ROOT / 'audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar'


@unittest.skipUnless(JAR.is_file(), '请先运行 mvn clean verify 构建本机网关')
class WorkbenchGatewayTest(unittest.TestCase):
    def test_本机模型与工具返回后六义务引用和最终裁决可回放(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append({'path': self.path, 'authorization': self.headers.get('Authorization'),
                                 **json.loads(self.rfile.read(int(self.headers['Content-Length'])))})
                hypotheses = {'schemaVersion': '2', 'hypotheses': [{
                    'vulnerabilityType': 'ACCESS_CONTROL', 'contract': 'Vault', 'function': 'withdraw',
                    'riskLine': 6, 'riskOperation': 'WRITE', 'reason': '待核查权限覆盖', 'evidenceIds': []}]}
                data = json.dumps({'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': 'deepseek-v4-flash',
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(hypotheses)},
                                 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 120, 'completion_tokens': 40, 'total_tokens': 160}}).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifact = root / 'audit-mvp/target'
                artifact.mkdir(parents=True); (artifact / JAR.name).symlink_to(JAR)
                config = root / 'config'; config.mkdir()
                values = {'providers.ark.base-url': f'http://127.0.0.1:{server.server_port}',
                          'providers.ark.model': 'deepseek-v4-flash', 'providers.ark.api-key': 'fixture-only',
                          'providers.ark.max-output-tokens': '2048', 'providers.ark.timeout-seconds': '10'}
                (config / 'providers.local.properties').write_text('\n'.join(key + '=' + value for key, value in values.items()))
                executable = root / 'slither-fixture.sh'
                executable.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo local-fixture; else echo \'{"success":true,"results":{"detectors":[]}}\'; fi\n')
                executable.chmod(0o700)
                (config / 'tools.local.properties').write_text('tools.slither.executable=' + str(executable))
                runtime = Runtime()
                def changed_config_model(*args):
                    # 执行身份检查后改变原配置；Java 必须消费冻结的模型与工具文件。
                    (config / 'providers.local.properties').write_text('providers.ark.base-url=http://127.0.0.1:1/changed\n')
                    (config / 'tools.local.properties').write_text('tools.slither.executable=/fixture/missing\n')
                    return model_runner(*args)
                runtime.model_runner = changed_config_model
                workbench = AuditWorkbench(root, runtime_factory=lambda profile: runtime,
                                           target_loader=lambda: [], tool=tool_runner)
                choice = {'source': ACCESS, 'function': 'withdraw', 'mechanism': 'ACCESS_CONTROL', 'mode': 'real'}
                # 仅替换 Python 的生产端点准入；Java 真实发送到 loopback，不调用任何外部模型。
                with patch('mvp_runtime._configuration_values', return_value=values):
                    preview = workbench.preview(choice)
                    result = workbench.execute(workbench.prepare({**choice, 'planHash': preview['planHash']}))
                self.assertEqual(1, len(requests), result)
                self.assertEqual('/chat/completions', requests[0]['path'])
                self.assertEqual('Bearer fixture-only', requests[0]['authorization'])
                self.assertEqual('json_schema', requests[0]['response_format']['type'])
                self.assertEqual('COMPLETED', result['status'])
                self.assertEqual('HYPOTHESES_REFUTED', result['conclusion'])
                self.assertEqual('SUPPORTED', result['d2']['assessments'][0]['protectionVerdict'])
                self.assertEqual(6, len(result['d2']['assessments'][0]['obligations']))
                self.assertEqual('local-fixture', result['tools'][0]['version'])
                self.assertEqual(result['target']['fullSourceHash'], result['tools'][0]['sourceHash'])
                self.assertEqual((120, 40), (result['model']['inputTokens'], result['model']['outputTokens']))
                self.assertEqual(['FACTS', 'D1', 'MODEL', 'TOOLS', 'D2', 'REPORT'], [row['name'] for row in result['stages']])
                self.assertEqual(result, workbench.read(result['runId']))
                self.assertEqual(1, len(requests))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__': unittest.main()
