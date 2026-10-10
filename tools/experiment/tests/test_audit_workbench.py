"""审计闭环使用本机依赖夹具，验证失败、预算、漂移和历史不可重发。"""
import tempfile
import unittest
from pathlib import Path

from audit_target import pasted_target
from audit_workbench import AuditWorkbench, assess, final_conclusion
from benchmark_runtime import BenchmarkRuntime
from program_facts import extract_facts
from storage import fingerprint

SOURCE = '''contract Vault {
 mapping(address => uint) balances;
 function withdraw() public {
   msg.sender.call("");
   balances[msg.sender] = 0;
 }
}'''

ACCESS_SOURCE = '''contract Vault {
 address owner;
 uint balance;
 function withdraw() public {
   require(msg.sender == owner);
   balance = 1;
 }
}'''


def model_reply(contract='Vault', function='withdraw', line=6, **extra):
    return {'schemaVersion': '2', 'status': 'COMPLETED', 'conclusion': 'VULNERABILITY_REPORTED',
            'hypotheses': [{'contract': contract, 'function': function, 'riskLine': line,
                            'vulnerabilityType': 'ACCESS_CONTROL', 'riskOperation': 'WRITE',
                            'reason': '核查目标权限', 'evidenceIds': []}],
            'inputTokens': None, 'outputTokens': None, **extra}


class Runtime:
    def __init__(self):
        self.calls = []
        self.pointer = {'snapshot_id': 'a' * 64, 'collection': 's1b_' + 'b' * 32}
        self.snapshot = {'embedding': {'model': 'ollama/nomic-embed-text', 'dimension': 768, 'revision': 'digest'}}
        self.model_runner = self.model

    def model(self, root, target, view, mode):
        self.calls.append(mode)
        return {'schemaVersion': '2', 'status': 'COMPLETED', 'conclusion': 'VULNERABILITY_REPORTED',
                'hypotheses': [{'contract': 'Vault', 'function': 'withdraw', 'vulnerabilityType': 'REENTRANCY',
                                'riskLine': 4, 'riskOperation': 'CALL', 'reason': '状态更新在调用后', 'evidenceIds': []}],
                'inputTokens': None, 'outputTokens': None, 'fixture': True}

    def preview(self, target):
        return {'sourceHash': target['sourceHash'], 'snapshotId': self.pointer['snapshot_id'],
                'collection': self.pointer['collection'], 'pool': {'candidates': []},
                'facts': extract_facts(target['fullSource']),
                'd1': {'status': 'COMPLETED', 'selected': [], 'context': '', 'gaps': []}}


class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = Runtime()
        self.tools = []
        def tool(*args):
            self.tools.append(args[-1])
            return [{'engine': 'SLITHER', 'status': 'SKIPPED', 'issues': [], 'durationMs': 0}]
        self.workbench = AuditWorkbench(self.root, runtime_factory=lambda profile: self.runtime,
                                       target_loader=lambda: [], tool=tool)
        self.choice = {'source': SOURCE, 'mechanism': 'REENTRANCY', 'function': 'withdraw', 'riskLine': 4}

    def tearDown(self):
        self.temp.cleanup()

    def _bound_tools(self, root, target, mode):
        return [{'engine': 'SLITHER', 'status': 'OK', 'sourceHash': target['fullSourceHash'],
                 'sourceFile': 'Contract.sol', 'issues': []}]

    def _audit_result(self, choice, model):
        self.runtime.model_runner = lambda *args: model
        self.workbench.tool = self._bound_tools
        preview = self.workbench.preview(choice)
        return self.workbench.execute(self.workbench.prepare({**choice, 'planHash': preview['planHash']}))

    def test_目标摘要列表不携带源码原件与评分答案(self):
        target = {**pasted_target(SOURCE, 'REENTRANCY'), 'originalSource': '// answer\n' + SOURCE,
                  'groundTruth': {'hasVulnerability': True}, 'vulnerableLines': [4]}
        self.workbench.target_loader = lambda: [target]
        listed = self.workbench.targets()[0]
        self.assertNotIn('originalSource', listed)
        self.assertNotIn('groundTruth', listed)
        self.assertNotIn('vulnerableLines', listed)

    def _batch_result(self, target, model):
        runtime = BenchmarkRuntime.__new__(BenchmarkRuntime)
        runtime.root = self.root
        runtime.preview = self.runtime.preview
        runtime.model_runner = lambda *args: model
        runtime.tool_runner = self._bound_tools
        return runtime.run({**target, 'groundTruth': {'hasVulnerability': True}}, 'D1', 'real')

    def test_预览不调用模型且源码与六阶段完整保存重放(self):
        preview = self.workbench.preview(self.choice)
        self.assertEqual([], self.runtime.calls)
        self.assertEqual(768, preview['embedding']['dimension'])
        self.assertEqual('WRITE_AFTER_CALL', preview['target']['syntax']['contracts'][0]['functions'][0]['cei'])
        prepared = self.workbench.prepare({**self.choice, 'planHash': preview['planHash']})
        result = self.workbench.execute(prepared)
        self.assertEqual(['offline'], self.runtime.calls)
        self.assertEqual(SOURCE, result['target']['source'])
        self.assertEqual(6, len(result['stages']))
        self.assertEqual(6, len(result['d2']['assessments'][0]['obligations']))
        self.assertEqual(result, self.workbench.read(result['runId']))
        self.assertEqual(result, self.workbench.read(result['runId']))
        self.assertEqual(['offline'], self.runtime.calls)
        self.assertIsNone(result['model']['inputTokens'])
        self.assertEqual(1, len(self.workbench.report(result['runId']).splitlines()))
        directory = self.workbench.store / result['runId']
        (directory / 'target.json').write_text('{}')
        with self.assertRaises(ValueError): self.workbench.read(result['runId'])

    def test_字段范围源码漂移预算拒绝都没有模型请求(self):
        for payload in ({**self.choice, 'endpoint': 'http://evil'},
                        {**self.choice, 'source': 'contract {'},
                        {**self.choice, 'riskLine': True},
                        {**self.choice, 'embeddingProfile': 'evil'}):
            with self.assertRaises(ValueError): self.workbench.preview(payload)
        first = self.workbench.preview(self.choice)
        changed = {**self.choice, 'source': SOURCE + '\n// 改变源码', 'planHash': first['planHash']}
        with self.assertRaises(ValueError): self.workbench.prepare(changed)
        prior = self.runtime.preview
        self.runtime.preview = lambda target: {**prior(target), 'd1': {'selected': [], 'context': '字' * 1400}}
        with self.assertRaises(ValueError): self.workbench.preview(self.choice)
        self.assertEqual([], self.runtime.calls)

    def test_工具异常保留模型假设并且最终未决(self):
        self.workbench.tool = lambda *args: (_ for _ in ()).throw(RuntimeError('private secret'))
        preview = self.workbench.preview(self.choice)
        result = self.workbench.execute(self.workbench.prepare({**self.choice, 'planHash': preview['planHash']}))
        self.assertEqual('FAILED', result['status'])
        self.assertEqual('UNRESOLVED', result['conclusion'])
        self.assertEqual(1, len(result['model']['hypotheses']))
        self.assertEqual(1, result['denominators']['failed'])
        self.assertNotIn('private secret', str(result))

    def test_服务重启后未封口运行不可自动续发(self):
        preview = self.workbench.preview(self.choice)
        prepared = self.workbench.prepare({**self.choice, 'planHash': preview['planHash']})
        self.assertEqual('RUNNING', self.workbench.read(prepared['runId'])['status'])
        reopened = AuditWorkbench(self.root, runtime_factory=lambda profile: self.runtime, target_loader=lambda: [])
        self.assertEqual('INTERRUPTED', reopened.read(prepared['runId'])['status'])
        self.assertEqual([], self.runtime.calls)

    def test_同名函数须唯一定位(self):
        source = 'contract A { function f() public {} }\ncontract B { function f() public {} }'
        with self.assertRaises(ValueError): pasted_target(source, 'ACCESS_CONTROL', 'f')
        target = pasted_target(source, 'ACCESS_CONTROL', 'B.f')
        self.assertEqual('B', target['contract'])
        self.assertEqual('B', pasted_target(source.replace('\n', ' '), 'ACCESS_CONTROL', 'B.f')['contract'])
        with self.assertRaises(ValueError): pasted_target(source.replace('\n', ' '), 'ACCESS_CONTROL', risk_line=1)

    def test_crlf_片段保留绝对行号(self):
        target = pasted_target(SOURCE.replace('\n', '\r\n'), 'REENTRANCY', 'withdraw', 4)
        self.assertEqual((3, 6), (target['lineStart'], target['lineEnd']))
        self.assertEqual(4, target['syntax']['contracts'][0]['functions'][0]['externalCalls'][0]['line'])

    def test_真实_java_检索返回无状态字段仍可完成(self):
        previous = self.runtime.preview
        def java_shape(target):
            result = previous(target)
            result['d1'].pop('status')
            result['d1']['strategy'] = 'D1'
            return result
        self.runtime.preview = java_shape
        preview = self.workbench.preview(self.choice)
        result = self.workbench.execute(self.workbench.prepare({**self.choice, 'planHash': preview['planHash']}))
        self.assertEqual('COMPLETED', result['status'])
        self.assertEqual('COMPLETED', result['stages'][1]['status'])

    def test_执行前快照漂移封口为失败且不调用模型(self):
        preview = self.workbench.preview(self.choice)
        prepared = self.workbench.prepare({**self.choice, 'planHash': preview['planHash']})
        self.runtime.store = self.root / 'snapshots'
        self.runtime.store.mkdir()
        (self.runtime.store / 'active.json').write_text('{}')
        result = self.workbench.execute(prepared)
        self.assertEqual('FAILED', result['status'])
        self.assertEqual('UNRESOLVED', result['conclusion'])
        self.assertEqual(result, self.workbench.read(result['runId']))
        self.assertEqual([], self.runtime.calls)

    def test_已消费预览与超预算隐式缩范围被拒绝(self):
        preview = self.workbench.preview(self.choice)
        payload = {**self.choice, 'planHash': preview['planHash']}
        self.workbench.prepare(payload)
        with self.assertRaises(ValueError): self.workbench.prepare(payload)
        with self.assertRaises(ValueError): pasted_target(SOURCE + '\n//' + 'x' * 17000, 'REENTRANCY')

    def test_同一行多合约的假设不能替代所选合约(self):
        source = ('contract A { address owner; uint x; function f() public { '
                  'require(msg.sender == owner); x = 1; } } '
                  'contract B { uint y; function f() public { y = 2; } }')
        result = self._audit_result({'source': source, 'mechanism': 'ACCESS_CONTROL', 'function': 'B.f'},
                                    model_reply('A', 'f', 1))
        self.assertEqual('FUNCTION', result['d2'].get('scope'))
        self.assertEqual('UNKNOWN', result['d2']['verdict'])
        self.assertEqual('UNKNOWN', result['d2']['assessments'][0]['protectionVerdict'])
        self.assertEqual([], result['d2']['assessments'][0]['references'])
        self.assertEqual('UNRESOLVED', final_conclusion(result['model'], result['d2'], False, 'real'))

    def test_同一行其他函数不能替代所选函数(self):
        source = ('contract Vault { address owner; uint balance; uint otherBalance; '
                  'function withdraw() public { balance = 1; } '
                  'function other() public { require(msg.sender == owner); otherBalance = 2; } }')
        result = self._audit_result({'source': source, 'mechanism': 'ACCESS_CONTROL', 'function': 'withdraw'},
                                    model_reply(function='other', line=1))
        self.assertEqual('UNKNOWN', result['d2']['verdict'])
        self.assertEqual([], result['d2']['assessments'][0]['references'])

    def test_片段前后的同名重载假设均保持未知(self):
        source = '''contract Vault {
 address owner;
 uint balance;
 function withdraw() public {
   require(msg.sender == owner);
   balance = 1;
 }
 function withdraw(uint amount) public {
   require(msg.sender == owner);
   balance = amount;
 }
 function withdraw(address recipient) public {
   require(msg.sender == owner);
   balance = 2;
 }
}'''
        choice = {'source': source, 'mechanism': 'ACCESS_CONTROL', 'function': 'withdraw', 'riskLine': 10}
        for line in (6, 14):
            with self.subTest(line=line):
                result = self._audit_result(choice, model_reply(line=line))
                self.assertEqual('UNKNOWN', result['d2']['verdict'])
                self.assertEqual([], result['d2']['assessments'][0]['references'])
        selected = self._audit_result(choice, model_reply(line=10))
        self.assertEqual('REFUTED', selected['d2']['verdict'])

    def test_只指定风险行也必须限定函数片段(self):
        source = ACCESS_SOURCE.replace('\n}', '\n function other() public { balance = 2; }\n}')
        target = pasted_target(source, 'ACCESS_CONTROL', risk_line=6)
        self.assertEqual(('FUNCTION', 4, 7), (target['scope'], target['lineStart'], target['lineEnd']))
        self.assertNotIn('function other', target['modelSource'])

    def test_模型源码允许完整16KiB而拒绝多一个字节(self):
        source = ACCESS_SOURCE + '\n//' + 'x' * (16384 - len(ACCESS_SOURCE.encode('utf-8')) - 3)
        try:
            target = pasted_target(source, 'ACCESS_CONTROL')
        except ValueError as error:
            self.fail('16 KiB 预算内的源码被拒绝：' + str(error))
        self.assertEqual(16384, len(target['modelSource'].encode('utf-8')))
        with self.assertRaises(ValueError): pasted_target(source + 'x', 'ACCESS_CONTROL')

    def test_16KiB源码与4096字节上下文可一起预览(self):
        source = ACCESS_SOURCE + '\n//' + 'x' * (16384 - len(ACCESS_SOURCE.encode('utf-8')) - 3)
        previous = self.runtime.preview
        def full_context(target):
            view = previous(target)
            view['d1']['context'] = 'x' * 4096
            return view
        self.runtime.preview = full_context
        try:
            preview = self.workbench.preview({'source': source, 'mechanism': 'ACCESS_CONTROL'})
        except ValueError as error:
            self.fail('16 KiB 源码与 4096 字节上下文被拒绝：' + str(error))
        self.assertEqual(4096, preview['plan']['contextBytes'])
        self.assertEqual([], self.runtime.calls)

    def test_完整范围仍能核验同合约其他函数(self):
        source = ACCESS_SOURCE.replace('\n}',
            '\n function other() public { require(msg.sender == owner); balance = 2; }\n}')
        result = self._audit_result({'source': source, 'mechanism': 'ACCESS_CONTROL'},
                                    model_reply(function='other', line=8))
        self.assertEqual('FULL', result['target']['scope'])
        self.assertEqual('FULL', result['d2'].get('scope'))
        self.assertEqual('REFUTED', result['d2']['verdict'])

    def test_完整范围允许其他合约的合法函数假设(self):
        source = ACCESS_SOURCE + ('\ncontract Other { address owner; uint balance; '
                                  'function other() public { require(msg.sender == owner); balance = 1; } }')
        result = self._audit_result({'source': source, 'mechanism': 'ACCESS_CONTROL'},
                                    model_reply('Other', 'other', 9))
        self.assertEqual('REFUTED', result['d2']['verdict'])
        self.assertEqual('FULL', result['d2'].get('scope'))
        self.assertTrue(any(ref['scope'].startswith('Other.other@')
                            for ref in result['d2']['assessments'][0]['references']))

    def test_完整与函数范围均拒绝错误审计类别(self):
        for function in (None, 'withdraw'):
            with self.subTest(function=function):
                choice = {'source': ACCESS_SOURCE, 'mechanism': 'REENTRANCY'}
                if function is not None:
                    choice['function'] = function
                result = self._audit_result(choice, model_reply())
                self.assertEqual('UNKNOWN', result['d2']['verdict'])
                self.assertEqual([], result['d2']['assessments'][0]['references'])

    def test_批量旧目标缺少合约字段时按唯一函数推导(self):
        target = pasted_target(ACCESS_SOURCE, 'ACCESS_CONTROL', 'withdraw')
        target.pop('contract')
        result = self._batch_result(target, model_reply())
        self.assertEqual('REFUTED', result['d2']['verdict'])
        self.assertEqual('HYPOTHESES_REFUTED', result['conclusion'])

    def test_批量错误合约假设未决但模型统计不改写(self):
        source = ('contract A { address owner; uint x; function f() public { '
                  'require(msg.sender == owner); x = 1; } } '
                  'contract B { uint y; function f() public { y = 2; } }')
        target = pasted_target(source, 'ACCESS_CONTROL', 'B.f')
        result = self._batch_result(target, model_reply('A', 'f', 1))
        self.assertEqual('UNKNOWN', result['d2']['verdict'])
        self.assertEqual('UNRESOLVED', result['conclusion'])
        self.assertEqual(('COMPLETED', 'REPORT', 'REPORT'),
                         (result['status'], result['prediction'], result['modelPrediction']))
        self.assertIsNone(result['inputTokens'])

    def test_拒绝假设或校验问题阻止全部反驳聚合(self):
        facts = extract_facts(ACCESS_SOURCE)
        tools = self._bound_tools(self.root, pasted_target(ACCESS_SOURCE, 'ACCESS_CONTROL'), 'real')
        for diagnostic in ({'rejectedHypotheses': [{'index': 1, 'issue': 'RISK_LINE_INVALID'}]},
                           {'validationIssue': 'PARTIAL_HYPOTHESES_REJECTED'}):
            with self.subTest(diagnostic=diagnostic):
                model = model_reply(**diagnostic)
                result = assess(model, facts, tools, ACCESS_SOURCE)
                self.assertEqual('REFUTED', result['assessments'][0]['verdict'])
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertEqual('UNRESOLVED', final_conclusion(model, result, False, 'real'))

    def test_最终裁决不能用已有反驳掩盖模型校验问题(self):
        for diagnostic in ({'rejectedHypotheses': [{'index': 1, 'issue': 'RISK_LINE_INVALID'}]},
                           {'validationIssue': 'PARTIAL_HYPOTHESES_REJECTED'}):
            with self.subTest(diagnostic=diagnostic):
                self.assertEqual('UNRESOLVED', final_conclusion(model_reply(**diagnostic),
                                                               {'verdict': 'REFUTED'}, False, 'real'))
        model = model_reply(hypotheses=[], validationIssue='PARTIAL_HYPOTHESES_REJECTED')
        self.assertEqual('UNRESOLVED', final_conclusion(model, {'verdict': 'UNKNOWN'}, False, 'real'))

    def test_批量部分假设被拒绝时保持未决和原模型用量(self):
        target = pasted_target(ACCESS_SOURCE, 'ACCESS_CONTROL', 'withdraw')
        model = model_reply(rejectedHypotheses=[{'index': 1, 'issue': 'RISK_LINE_INVALID'}],
                            validationIssue='PARTIAL_HYPOTHESES_REJECTED', inputTokens=120, outputTokens=40)
        result = self._batch_result(target, model)
        self.assertEqual('UNKNOWN', result['d2']['verdict'])
        self.assertEqual('REFUTED', result['d2']['assessments'][0]['verdict'])
        self.assertEqual('UNRESOLVED', result['conclusion'])
        self.assertEqual(('REPORT', 120, 40), (result['prediction'], result['inputTokens'], result['outputTokens']))

    def test_已证实漏洞不被其他假设校验问题抹去(self):
        model = model_reply(rejectedHypotheses=[{'index': 1, 'issue': 'RISK_LINE_INVALID'}],
                            validationIssue='PARTIAL_HYPOTHESES_REJECTED')
        self.assertEqual('VULNERABILITY_SUPPORTED', final_conclusion(model, {'verdict': 'SUPPORTED'}, False, 'real'))


if __name__ == '__main__': unittest.main()
