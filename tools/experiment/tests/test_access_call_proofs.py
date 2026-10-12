"""访问控制终止调用的有限证明；合成 AST 只验证离线适配契约。"""
import unittest

from access_call_proofs import _AccessCallGraph, prove_access_call
from compiler_facts import extract_compiler_facts
import test_compiled_d2 as compiled


class AccessCallProofTest(unittest.TestCase):
    def setUp(self):
        self.syntax = compiled.CompiledD2Test()
        self.syntax.setUp()
        self.addCleanup(self.syntax.doCleanups)
        self.fixture = self.syntax.fixture
        self.function = self.fixture.function()
        self.contract = self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        self.call = self.terminal()
        self.function['body']['statements'] = [self.statement(self.call)]

    def node(self, node_type, **fields):
        return self.syntax.node(node_type, **fields)

    def statement(self, expression):
        return self.node('ExpressionStatement', expression=expression)

    def sender(self):
        return self.node('MemberAccess', memberName='sender', typeDescriptions={'typeIdentifier': 't_address'},
            expression=self.node('Identifier', name='msg', referencedDeclaration=-15,
            typeDescriptions={'typeIdentifier': 't_magic_message'}))

    def literal(self, value):
        kind = 'bool' if type(value) is bool else 'number'
        identifier = 't_bool' if kind == 'bool' else 't_uint256'
        return self.node('Literal', kind=kind, value=str(value).lower(),
                         typeDescriptions={'typeIdentifier': identifier})

    def terminal(self, name='selfdestruct'):
        return self.node('FunctionCall', kind='functionCall', arguments=[self.sender()],
            expression=self.node('Identifier', name=name, referencedDeclaration=-900,
            typeDescriptions={'typeIdentifier': f't_function_{name}_nonpayable$_t_address_$returns$__$'}))

    def require(self, condition):
        return self.statement(self.node('FunctionCall', kind='functionCall', arguments=[condition],
            expression=self.node('Identifier', name='require', referencedDeclaration=-18,
            typeDescriptions={'typeIdentifier': 't_function_require_pure$_t_bool_$returns$__$'})))

    def state(self, name, identifier='t_bool', initial=None):
        type_name = {'t_bool': 'bool', 't_address': 'address', 't_uint256': 'uint256'}[identifier]
        result = self.node('VariableDeclaration', name=name, stateVariable=True, visibility='private',
            typeName=self.node('ElementaryTypeName', name=type_name),
            typeDescriptions={'typeIdentifier': identifier}, value=initial)
        self.contract['nodes'].insert(0, result)
        return result

    def state_read(self, state):
        return self.node('Identifier', name=state['name'], referencedDeclaration=state['id'],
                         typeDescriptions=state['typeDescriptions'])

    def write(self, state, value, operator='='):
        return self.statement(self.node('Assignment', operator=operator,
            leftHandSide=self.state_read(state), rightHandSide=value))

    def constructor(self, statements, parameters=None):
        function = self.node('FunctionDefinition', name='', kind='constructor', visibility='public',
            stateMutability='nonpayable', modifiers=[], parameters=self.node('ParameterList', parameters=parameters or []),
            returnParameters=self.node('ParameterList', parameters=[]), body=self.node('Block', statements=statements))
        self.contract['nodes'].append(function)
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'constructor', 'inputs': [], 'stateMutability': 'nonpayable'})
        return function

    def prove(self, **fields):
        self.fixture.seal()
        bundle = self.fixture.load()
        return prove_access_call(bundle, {'contract': 'C', 'function': 'f()', 'riskLine': 1,
            'riskOperation': 'CALL', 'vulnerabilityType': 'ACCESS_CONTROL', **fields})

    def test_无权限终止调用给出已初始化且正常终止的有限反例(self):
        proof = self.prove()
        self.assertEqual('COUNTEREXAMPLE', proof['status'])
        self.assertEqual('FEASIBLE', proof['pathEvidence']['status'])
        self.assertTrue(proof['candidateBound'])
        self.assertTrue(proof['pathEvidence']['normalExit'])
        initialization = proof['pathEvidence']['witness']['initialization']
        self.assertTrue(initialization['runtimeInitialized'])
        self.assertNotIn('funded', initialization)
        self.assertTrue(proof['proofScope']['counterexampleComplete'])
        self.assertFalse(proof['proofScope']['complete'])
        self.assertFalse(proof['proofScope']['universalProtection'])
        self.assertEqual({'actor', 'entry_coverage', 'bypass'},
            {item['name'] for item in proof['obligations'] if item['status'] == 'REFUTED'})

    def test_旧版suicide内置调用具有相同终止语义(self):
        self.call = self.terminal('suicide')
        self.function['body']['statements'] = [self.statement(self.call)]
        self.assertEqual('COUNTEREXAMPLE', self.prove()['status'])

    def test_成功终止后的断言回滚与未知副作用均不执行(self):
        for suffix in [self.require(self.literal(False)), self.node('RevertStatement', errorCall=None),
                       self.node('InlineAssembly')]:
            with self.subTest(suffix=suffix['nodeType']):
                self.function['body']['statements'] = [self.statement(self.call), suffix]
                proof = self.prove()
                self.assertEqual('COUNTEREXAMPLE', proof['status'])
                self.assertFalse(any(node['kind'] in {'CHECK', 'ABORT', 'UNKNOWN'} for node in proof['cfg']['nodes']))

    def test_内部终止不续接调用者或修饰器后缀(self):
        helper = self.syntax.fresh(self.function)
        helper.update(name='terminate', visibility='internal')
        helper['body']['statements'] = [self.statement(self.call)]
        self.contract['nodes'].append(helper)
        invocation = self.node('FunctionCall', kind='functionCall', arguments=[],
            expression=self.node('Identifier', name='terminate', referencedDeclaration=helper['id'],
            typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$__$returns$__$'}))
        modifier = self.node('ModifierDefinition', name='afterward', parameters=self.node('ParameterList', parameters=[]),
            body=self.node('Block', statements=[self.node('PlaceholderStatement'), self.require(self.literal(False))]))
        self.contract['nodes'].append(modifier)
        self.function['body']['statements'] = [self.statement(invocation), self.node('InlineAssembly')]
        self.function['modifiers'] = [self.node('ModifierInvocation', arguments=None,
            modifierName=self.node('IdentifierPath', name='afterward', referencedDeclaration=modifier['id']))]
        proof = self.prove()
        self.assertEqual('COUNTEREXAMPLE', proof['status'])
        self.assertFalse(any(node['kind'] in {'CHECK', 'ABORT', 'UNKNOWN'} for node in proof['cfg']['nodes']))

    def test_真实构造权限槽阻止无授权反例且不伪造负证明(self):
        owner = next(node for node in self.contract['nodes'] if node.get('id') == 2)
        self.constructor([self.write(owner, self.sender())])
        guard = self.node('BinaryOperation', operator='==', leftExpression=self.sender(),
                          rightExpression=self.state_read(owner))
        self.function['body']['statements'].insert(0, self.require(guard))
        self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_默认地址权限槽不会被任意枚举成调用者(self):
        owner = next(node for node in self.contract['nodes'] if node.get('id') == 2)
        condition = self.node('BinaryOperation', operator='==', leftExpression=self.sender(),
                              rightExpression=self.state_read(owner))
        self.function['body']['statements'].insert(0, self.require(condition))
        self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_默认布尔初态与简单构造写入严格重放(self):
        closed = self.state('closed')
        condition = self.node('UnaryOperation', operator='!', subExpression=self.state_read(closed))
        self.function['body']['statements'].insert(0, self.require(condition))
        proof = self.prove()
        self.assertEqual('COUNTEREXAMPLE', proof['status'])
        self.constructor([self.write(closed, self.literal(True))])
        self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_非默认声明初值不会被忽略(self):
        closed = self.state('closed', initial=self.literal(True))
        condition = self.node('UnaryOperation', operator='!', subExpression=self.state_read(closed))
        self.function['body']['statements'].insert(0, self.require(condition))
        self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_矛盾条件与常量false没有可满足反例(self):
        self.function['body']['statements'].insert(0, self.require(self.literal(False)))
        self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_未知构造与风险前汇编保持未知(self):
        self.constructor([self.node('InlineAssembly')])
        self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_未使用的未知表达式与复合算术写入均不能伪造可满足性(self):
        state = self.state('count', 't_uint256')
        self.function['body']['statements'].insert(0, self.write(state, self.literal(1), '+='))
        self.assertEqual('UNKNOWN', self.prove()['status'])
        self.function['body']['statements'][0] = self.statement(self.node('BinaryOperation', operator='/',
            leftExpression=self.literal(1), rightExpression=self.literal(0)))
        self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_唯一短函数名与完整签名绑定(self):
        self.assertEqual('COUNTEREXAMPLE', self.prove(function='f')['status'])
        self.assertEqual('FAILED', self.prove(function='g', functionSignature='f()')['status'])

    def test_风险行跨度与事实摘要漂移均失败(self):
        self.assertEqual('FAILED', self.prove(riskLine=2)['status'])
        self.assertEqual('FAILED', self.prove(riskSpan={'start': 9, 'length': 1, 'sourceUnit': 'contracts/C.sol'})['status'])
        self.assertEqual('FAILED', self.prove(riskFactId='错误事实')['status'])
        self.fixture.seal()
        bundle = self.fixture.load()
        fact = next(fact for fact in extract_compiler_facts(bundle)['facts'] if fact['nodeId'] == self.call['id'])
        self.assertEqual('COUNTEREXAMPLE', self.prove(riskFactId=fact['id'], riskSpan=fact['span'])['status'])

    def test_伪造未重编译bundle失败(self):
        self.assertEqual('FAILED', prove_access_call({}, {})['status'])
        self.assertEqual('FAILED', prove_access_call({'verificationStatus': 'RECOMPILED_MATCH'}, {})['status'])

    def test_其他漏洞类型与写入候选超出范围(self):
        self.assertEqual('UNKNOWN', self.prove(vulnerabilityType='REENTRANCY')['status'])
        self.assertEqual('UNKNOWN', self.prove(riskOperation='WRITE')['status'])

    def test_终止边直接连接总退出且后缀没有路径(self):
        self.fixture.seal()
        bundle = self.fixture.load()
        entry = next(entry for entry in bundle['entries'] if entry['signature'] == 'f()')
        graph = _AccessCallGraph(bundle, entry)
        terminal = next(node for node in graph.nodes if node.get('builtin') == 'selfdestruct')
        exit_node = next(node for node in graph.nodes if node['kind'] == 'EXIT')
        self.assertEqual([exit_node['id']], [edge['to'] for edge in graph.edges if edge['from'] == terminal['id']])

    def test_短函数名遇到重载不能猜测入口(self):
        overload = self.syntax.fresh(self.function)
        parameter = self.node('VariableDeclaration', name='amount', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='uint256'),
            typeDescriptions={'typeIdentifier': 't_uint256'})
        overload['parameters'] = self.node('ParameterList', parameters=[parameter])
        self.contract['nodes'].append(overload)
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'function', 'name': 'f', 'inputs': [{'type': 'uint256'}], 'outputs': [], 'stateMutability': 'nonpayable'})
        self.assertEqual('UNKNOWN', self.prove(function='f')['status'])
        self.assertEqual('COUNTEREXAMPLE', self.prove()['status'])

    def test_fallback与receive按实际ABI入口绑定(self):
        abi = self.fixture.output['contracts']['contracts/C.sol']['C']['abi']
        for kind in ['fallback', 'receive']:
            with self.subTest(kind=kind):
                self.function.update(kind=kind, name='', stateMutability='payable')
                abi[0] = {'type': kind, 'stateMutability': 'payable'}
                self.assertEqual('COUNTEREXAMPLE', self.prove(function=kind + '()')['status'])

    def test_用户同名函数不能冒充编译器终止内置(self):
        helper = self.syntax.fresh(self.function)
        parameter = self.node('VariableDeclaration', name='recipient', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='address'),
            typeDescriptions={'typeIdentifier': 't_address'})
        helper.update(name='selfdestruct', visibility='internal')
        helper['parameters'] = self.node('ParameterList', parameters=[parameter])
        helper['body']['statements'] = []
        self.contract['nodes'].append(helper)
        self.call['expression'].update(referencedDeclaration=helper['id'],
            typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$_t_address_$returns$__$'})
        self.assertNotEqual('COUNTEREXAMPLE', self.prove()['status'])

    def test_非终止编译类型不能套用内置证明(self):
        self.fixture.seal()
        bundle = self.fixture.load()
        bundle['nodes'][self.call['expression']['id']]['typeDescriptions']['typeIdentifier'] = 't_function_internal_nonpayable'
        proof = prove_access_call(bundle, {'contract': 'C', 'function': 'f()', 'riskLine': 1,
            'riskOperation': 'CALL', 'vulnerabilityType': 'ACCESS_CONTROL'})
        self.assertEqual('UNKNOWN', proof['status'])

    def test_transfer与delegatecall都保持范围外未知(self):
        for name, identifier, arguments in [
                ('transfer', 't_function_transfer_nonpayable$_t_uint256_$returns$__$', [self.literal(1)]),
                ('delegatecall', 't_function_baredelegatecall_nonpayable$_t_bytes_memory_ptr_$returns$_t_bool_$', [])]:
            with self.subTest(name=name):
                self.call['expression'] = self.node('MemberAccess', memberName=name, expression=self.sender(),
                    typeDescriptions={'typeIdentifier': identifier})
                self.call['arguments'] = arguments
                self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_内部终止作为返回表达式不会伪造调用者续接(self):
        helper = self.syntax.fresh(self.function)
        helper.update(name='terminate', visibility='internal')
        result = self.node('VariableDeclaration', name='', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='bool'), typeDescriptions={'typeIdentifier': 't_bool'})
        helper['returnParameters'] = self.node('ParameterList', parameters=[result])
        helper['body']['statements'] = [self.statement(self.call)]
        self.contract['nodes'].append(helper)
        self.function['returnParameters'] = self.node('ParameterList', parameters=[self.syntax.fresh(result)])
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][0]['outputs'] = [{'type': 'bool'}]
        invocation = self.node('FunctionCall', kind='functionCall', arguments=[],
            expression=self.node('Identifier', name='terminate', referencedDeclaration=helper['id'],
            typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$__$returns$_t_bool_$'}))
        self.function['body']['statements'] = [self.node('Return', expression=invocation), self.node('InlineAssembly')]
        proof = self.prove()
        self.assertEqual('COUNTEREXAMPLE', proof['status'])
        self.assertFalse(any(node['kind'] == 'RETURN' for node in proof['cfg']['nodes']))

    def test_布尔实参矛盾不能被逐条独立满足(self):
        parameter = self.node('VariableDeclaration', name='allow', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='bool'), typeDescriptions={'typeIdentifier': 't_bool'})
        self.function['parameters'] = self.node('ParameterList', parameters=[parameter])
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][0]['inputs'] = [{'type': 'bool'}]
        identifier = lambda: self.node('Identifier', name='allow', referencedDeclaration=parameter['id'],
                                      typeDescriptions={'typeIdentifier': 't_bool'})
        self.function['body']['statements'].insert(0, self.require(identifier()))
        self.assertEqual('COUNTEREXAMPLE', self.prove(function='f(bool)')['status'])
        self.function['body']['statements'].insert(1, self.require(self.node('UnaryOperation', operator='!', subExpression=identifier())))
        self.assertEqual('UNKNOWN', self.prove(function='f(bool)')['status'])

    def test_运行写入版本参与真实路径约束(self):
        closed = self.state('closed')
        self.function['body']['statements'].insert(0, self.write(closed, self.literal(True)))
        self.function['body']['statements'].insert(1, self.require(self.state_read(closed)))
        self.assertEqual('COUNTEREXAMPLE', self.prove()['status'])
        self.function['body']['statements'][1] = self.require(self.node('UnaryOperation', operator='!', subExpression=self.state_read(closed)))
        self.assertEqual('UNKNOWN', self.prove()['status'])

    def test_固定受款地址不因主体权限缺失被标为资源义务缺失(self):
        owner = next(node for node in self.contract['nodes'] if node.get('id') == 2)
        self.constructor([self.write(owner, self.sender())])
        self.call['arguments'] = [self.state_read(owner)]
        proof = self.prove()
        self.assertEqual('COUNTEREXAMPLE', proof['status'])
        self.assertEqual('UNKNOWN', next(item for item in proof['obligations'] if item['name'] == 'resource')['status'])

    def test_非权限前置条件已满足时不被笼统声称缺失(self):
        enabled = self.state('enabled', initial=self.literal(True))
        self.function['body']['statements'].insert(0, self.require(self.state_read(enabled)))
        proof = self.prove()
        self.assertEqual('COUNTEREXAMPLE', proof['status'])
        self.assertEqual('UNKNOWN', next(item for item in proof['obligations'] if item['name'] == 'pre_risk_guard')['status'])
        self.assertTrue(proof['pathEvidence']['witness']['conditions'][0]['conditionValue'])

    def test_普通外部调用的动态实现不进入终止内置证明(self):
        external = self.node('FunctionDefinition', name='close', kind='function', visibility='external',
            stateMutability='nonpayable', parameters=self.node('ParameterList', parameters=[]),
            returnParameters=self.node('ParameterList', parameters=[]), body=None, modifiers=[])
        remote = self.node('ContractDefinition', name='Remote', contractKind='interface',
            linearizedBaseContracts=[], nodes=[external])
        remote['linearizedBaseContracts'] = [remote['id']]
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'].append(remote)
        self.call['expression'] = self.node('MemberAccess', memberName='close', expression=self.sender(),
            referencedDeclaration=external['id'],
            typeDescriptions={'typeIdentifier': 't_function_external_nonpayable$__$returns$__$'})
        self.call['arguments'] = []
        self.assertEqual('UNKNOWN', self.prove()['status'])


if __name__ == '__main__':
    unittest.main()
