"""原生调用须在发现与访问控制核验中绑定同一事实；定位不代表证明。"""
import unittest

from verirag.analysis.access_call_proofs import _AccessCallGraph, prove_access_call
from verirag.analysis.compiler_facts import extract_compiler_facts
from verirag.analysis.risk_binding import bind_risks
from verirag.analysis.risk_catalog import build_risk_catalog
import test_compiled_d2 as fixtures


class NativeCallTest(unittest.TestCase):
    def setUp(self):
        self.syntax = fixtures.CompiledD2Test()
        self.syntax.setUp()
        self.addCleanup(self.syntax.doCleanups)
        self.fixture = self.syntax.fixture

    def call(self, name, type_name, *, options=False, declared=False):
        node = self.syntax.node
        receiver = node('MemberAccess', memberName='sender',
            typeDescriptions={'typeIdentifier': 't_address_payable'},
            expression=node('Identifier', name='msg', referencedDeclaration=-15,
                typeDescriptions={'typeIdentifier': 't_magic_message'}))
        expression = node('MemberAccess', memberName=name, expression=receiver,
            typeDescriptions={'typeIdentifier': type_name})
        if declared:
            expression['referencedDeclaration'] = 4
        amount = node('Literal', kind='number', value='1', typeDescriptions={'typeIdentifier': 't_uint256'})
        arguments = [amount]
        if options:
            expression = node('FunctionCallOptions', expression=expression,
                names=['value'], options=[amount], typeDescriptions={'typeIdentifier': type_name})
            arguments = []
        return node('FunctionCall', kind='functionCall', expression=expression, arguments=arguments)

    def bound(self, call):
        self.fixture.function()['body']['statements'] = [self.syntax.node('ExpressionStatement', expression=call)]
        self.fixture.seal()
        bundle = self.fixture.load()
        catalog = build_risk_catalog(bundle)
        operations = [o for o in catalog['operations'] if o['nodeId'] == call['id']]
        self.assertEqual(1, len(operations))
        operation = operations[0]
        hypothesis = {'contract': 'C', 'function': 'f()', 'riskLine': operation['line'],
            'riskOperation': 'CALL', 'vulnerabilityType': 'ACCESS_CONTROL',
            'riskFactId': operation['factId'], 'riskSpan': operation['span']}
        graph = _AccessCallGraph(bundle, next(e for e in bundle['entries'] if e['signature'] == 'f()'))
        risks = bind_risks(graph, hypothesis, bundle, extract_compiler_facts(bundle))
        return bundle, operation, hypothesis, risks

    def test_transfer和send可定位且不会因未支持证明而失败(self):
        for name in ('transfer', 'send'):
            with self.subTest(name=name):
                call = self.call(name, f't_function_{name}_nonpayable$_t_uint256_$returns$__$')
                bundle, operation, hypothesis, risks = self.bound(call)
                self.assertEqual(1, len(risks))
                self.assertEqual('CALL', operation['callKind'])
                self.assertIn('NATIVE_TRANSFER', operation['semanticTags'])
                proof = prove_access_call(bundle, hypothesis)
                self.assertTrue(proof['candidateBound'])
                self.assertEqual('UNKNOWN', proof['status'])
                self.assertFalse(proof['proofScope']['complete'])

    def test_value调用在两个图中保持同一操作身份(self):
        call = self.call('call', 't_function_barecall_payable$__$returns$_t_bool_$_t_bytes_memory_ptr_$', options=True)
        bundle, operation, hypothesis, risks = self.bound(call)
        self.assertEqual(1, len(risks))
        self.assertEqual(operation['span'], risks[0]['span'])
        self.assertTrue(prove_access_call(bundle, hypothesis)['candidateBound'])

    def test_委托和静态调用与转账分别标注(self):
        for name, type_name, kind, tag in (
            ('delegatecall', 'baredelegatecall', 'DELEGATECALL', 'DELEGATE_EXECUTION'),
            ('staticcall', 'barestaticcall', 'STATICCALL', 'STATIC_CALL')):
            with self.subTest(name=name):
                call = self.call(name, f't_function_{type_name}_nonpayable$__$returns$_t_bool_$')
                _, operation, _, risks = self.bound(call)
                self.assertEqual(1, len(risks))
                self.assertEqual(kind, operation['callKind'])
                self.assertIn(tag, operation['semanticTags'])
                self.assertNotIn('NATIVE_TRANSFER', operation['semanticTags'])

    def test_同名内部函数不伪装成原生转账(self):
        call = self.call('transfer', 't_function_internal_nonpayable$__$returns$__$', declared=True)
        self.fixture.function()['body']['statements'] = [self.syntax.node('ExpressionStatement', expression=call)]
        self.fixture.seal()
        self.assertEqual([], build_risk_catalog(self.fixture.load())['operations'])

    def test_value选项中的嵌套调用同样可以从目录绑定(self):
        call = self.call('call', 't_function_barecall_payable$__$returns$_t_bool_$_t_bytes_memory_ptr_$', options=True)
        nested = self.call('f', 't_function_external_view$__$returns$_t_uint256_$', declared=True)
        nested['arguments'] = []
        call['expression']['options'] = [nested]
        bundle, _, _, _ = self.bound(call)
        operation = next(o for o in build_risk_catalog(bundle)['operations'] if o['nodeId'] == nested['id'])
        hypothesis = {'contract': 'C', 'function': 'f()', 'riskLine': operation['line'],
            'riskOperation': 'CALL', 'vulnerabilityType': 'ACCESS_CONTROL',
            'riskFactId': operation['factId'], 'riskSpan': operation['span']}
        graph = _AccessCallGraph(bundle, next(e for e in bundle['entries'] if e['signature'] == 'f()'))
        self.assertEqual(1, len(bind_risks(graph, hypothesis, bundle, extract_compiler_facts(bundle))))


if __name__ == '__main__':
    unittest.main()
