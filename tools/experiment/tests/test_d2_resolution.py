"""编译证明与独立工具接缝共同决定候选裁决，缺任一项仍未知。"""
import copy
import unittest
from unittest.mock import patch

import test_compiler_facts as fixtures
from compiled_d2 import evaluate_compiled


class D2ResolutionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompilerFactsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.hypothesis = {'contract': 'C', 'function': 'f', 'riskLine': 1,
            'vulnerabilityType': 'ACCESS_CONTROL', 'riskOperation': 'WRITE'}
        self.tool = {'engine': 'SLITHER', 'status': 'OK', 'issues': [],
                     'sourceHash': self.fixture.manifest['expectedSourceHash']}

    def evaluate(self, tools=None):
        return evaluate_compiled(self.hypothesis, self.fixture.manifest,
                                 [self.tool] if tools is None else tools, root=self.fixture.root)

    def test_完整权限闭包与独立双收据匹配才反驳(self):
        with patch('bound_slither.verify_bound_tool', return_value={'status': 'MATCH'}):
            result = self.evaluate()
        self.assertEqual('PROVED', result['candidateProof']['status'])
        self.assertEqual('REFUTED', result['verdict'])
        self.assertEqual('SUPPORTED', result['protectionVerdict'])
        self.assertEqual('COMPLETED', result['status'])
        self.assertTrue(result['proofScope']['complete'])

    def test_缺少工具或双收据不匹配不能继承安全(self):
        with patch('bound_slither.verify_bound_tool', return_value={'status': 'UNKNOWN'}):
            result = self.evaluate()
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('UNKNOWN', self.evaluate([])['verdict'])

    def test_后置条件与不完整入口即使工具一致也未知(self):
        self.fixture.function()['body']['statements'].reverse()
        self.fixture.seal()
        self.tool['sourceHash'] = self.fixture.manifest['expectedSourceHash']
        with patch('bound_slither.verify_bound_tool', return_value={'status': 'MATCH'}):
            result = self.evaluate()
        self.assertEqual('UNKNOWN', result['verdict'])

    def test_编译输出数值类型漂移不能重封为真实AST(self):
        # bool 与 int 在 Python 比较相等，但 JSON 类型是编译身份的一部分。
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['fullyImplemented'] = 1
        self.fixture.seal()
        original = copy.deepcopy(self.fixture.output)
        original['sources']['contracts/C.sol']['ast']['nodes'][0]['fullyImplemented'] = True
        (self.fixture.root / 'fixture-compiled-output.json').write_bytes(fixtures.canonical(original))
        result = self.evaluate()
        self.assertEqual('FAILED', result['status'])
        self.assertEqual('UNKNOWN', result['verdict'])

    def test_旧AST构造与fallback依编译属性区分(self):
        from compiler_facts import _function_kind, _signature
        constructor = {'nodeType': 'FunctionDefinition', 'name': 'C', 'isConstructor': True,
                       'parameters': {'parameters': []}}
        fallback = {'nodeType': 'FunctionDefinition', 'name': '', 'isConstructor': False,
                    'parameters': {'parameters': []}}
        self.assertEqual('constructor', _function_kind(constructor))
        self.assertEqual('constructor()', _signature(constructor, {}))
        self.assertEqual('fallback()', _signature(fallback, {}))

    def test_未获得独立匹配收据的工具不能补正裁决佐证(self):
        from compiled_d2 import _corroboration
        bundle = self.fixture.load()
        fake = {**self.tool, 'sourceFile': 'wrong.sol', 'targetContract': 'Other',
                'issues': [{'check': 'protected-vars'}]}
        refs = _corroboration(self.hypothesis, [fake], bundle,
            {'sourceUnit': 'contracts/C.sol', 'start': 0, 'length': 1}, self.fixture.root, [])
        self.assertEqual([], refs)


if __name__ == '__main__':
    unittest.main()
