"""转账调用的权限证明只约束谁能到达该操作，不证明收款方代码或资产业务。"""
import copy
import unittest

from candidate_proofs import prove_guarded_call
from compiler_facts import extract_compiler_facts
from compiled_d2 import evaluate_compiled
import test_access_call_proofs as fixtures


class GuardedCallTest(unittest.TestCase):
    def setUp(self):
        self.helper = fixtures.AccessCallProofTest(); self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.fixture = self.helper.fixture
        self.owner = next(n for n in self.helper.contract['nodes'] if n.get('id') == 2)
        self.guard = self.helper.require(self.helper.node('BinaryOperation', operator='==',
            leftExpression=self.helper.sender(), rightExpression=self.helper.state_read(self.owner)))
        self.call = self.transfer()
        self.helper.function['body']['statements'] = [self.guard, self.helper.statement(self.call)]

    def transfer(self, name='transfer'):
        return self.helper.node('FunctionCall', kind='functionCall', arguments=[self.helper.literal(1)],
            expression=self.helper.node('MemberAccess', memberName=name, expression=self.helper.sender(),
                typeDescriptions={'typeIdentifier': f't_function_{name}_nonpayable$_t_uint256_$returns$__$'}))

    def add_entry(self, name, statements, kind='function'):
        function = self.helper.syntax.fresh(self.helper.function)
        function.update(name=name, kind=kind)
        function['body']['statements'] = statements
        self.helper.contract['nodes'].append(function)
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'function' if kind == 'function' else kind, 'name': name, 'inputs': [],
             'outputs': [], 'stateMutability': 'nonpayable'})
        return function

    def inputs(self):
        self.fixture.seal(); bundle = self.fixture.load()
        fact = next(f for f in extract_compiler_facts(bundle)['facts'] if f['nodeId'] == self.call['id'])
        return bundle, {'contract': 'C', 'function': 'f()', 'riskLine': 1, 'riskFactId': fact['id'],
            'riskOperation': 'CALL', 'vulnerabilityType': 'ACCESS_CONTROL'}

    def proof(self):
        return prove_guarded_call(*self.inputs())

    def test_地址保护转账完成六义务并明确外部效果范围(self):
        proof = self.proof()
        self.assertEqual('PROVED', proof['status'])
        self.assertEqual('ACCESS_CONTROL_GUARDED_CALL', proof['proofKind'])
        self.assertTrue(proof['proofScope']['complete'])
        self.assertEqual({'SUPPORTED'}, {o['status'] for o in proof['obligations']})
        self.assertEqual('CALL_REACHABILITY_ONLY', proof['proofScope']['property'])
        self.assertEqual('BLOCKED', proof['pathEvidence']['status'])

    def test_发送调用可用同一授权规则(self):
        self.call = self.transfer('send')
        self.helper.function['body']['statements'][-1] = self.helper.statement(self.call)
        self.assertEqual('PROVED', self.proof()['status'])

    def test_未保护setter及fallback改写权限均保持未知(self):
        for name, kind in [('initialize', 'function'), ('', 'fallback')]:
            with self.subTest(kind=kind):
                self.add_entry(name, [self.helper.write(self.owner, self.helper.sender())], kind)
                proof = self.proof()
                self.assertEqual('UNKNOWN', proof['status'])
                self.assertFalse(proof['proofScope']['complete'])

    def test_检查后权限改写或前置回调不能复用旧主体(self):
        self.helper.function['body']['statements'].insert(1, self.helper.write(self.owner, self.helper.sender()))
        self.assertEqual('UNKNOWN', self.proof()['status'])
        self.helper.function['body']['statements'][1] = self.helper.statement(self.transfer())
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_分支旁路及txorigin检查均不能反驳(self):
        self.helper.function['body']['statements'][0] = self.helper.node('IfStatement',
            condition=self.helper.literal(True), trueBody=self.guard, falseBody=None)
        self.assertEqual('UNKNOWN', self.proof()['status'])
        origin = self.guard['expression']['arguments'][0]['leftExpression']
        origin['memberName'] = 'origin'
        origin['expression'].update(name='tx', referencedDeclaration=-16,
            typeDescriptions={'typeIdentifier': 't_magic_transaction'})
        self.helper.function['body']['statements'][0] = self.guard
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未知汇编及委托效果阻止完整权限闭包(self):
        self.add_entry('opaque', [self.helper.node('InlineAssembly')])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_缺少工具双收据不能把静态证明升级为最终反驳(self):
        bundle, hypothesis = self.inputs()
        result = evaluate_compiled(hypothesis, self.fixture.manifest, [], root=self.fixture.root)
        self.assertEqual('PROVED', result['candidateProof']['status'])
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('BLOCKED', result['pathEvidence']['status'])

    def test_真实子进程双收据夹具匹配才可最终反驳(self):
        bundle, hypothesis = self.inputs()
        hypothesis['claimProperty'] = 'UNAUTHORIZED_CALL_REACHABILITY'
        span = next(f['span'] for f in extract_compiler_facts(bundle)['facts'] if f['nodeId'] == self.call['id'])
        tool = self.helper.syntax.terminal_tool()
        result = evaluate_compiled(hypothesis, self.fixture.manifest, [tool], root=self.fixture.root)
        self.assertEqual('MATCH', result['toolBinding']['status'])
        self.assertEqual('REFUTED', result['verdict'])
        self.assertEqual('COMPLETED', result['status'])

    def test_调用前保护不能反驳未绑定属性或资金锁死主张(self):
        bundle, hypothesis = self.inputs()
        for claim in (None, 'AUTHORIZED_CALL_LIVENESS'):
            with self.subTest(claim=claim):
                candidate = dict(hypothesis)
                if claim is not None:
                    candidate['claimProperty'] = claim
                result = evaluate_compiled(candidate, self.fixture.manifest,
                    [self.helper.syntax.terminal_tool()], root=self.fixture.root)
                self.assertEqual('PROVED', result['candidateProof']['status'])
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertEqual('UNVERIFIED', result['claimBinding']['status'])

    def test_可写数组长度不能假定与权限槽物理分离(self):
        array = self.helper.node('VariableDeclaration', name='map', stateVariable=True,
            visibility='private', typeName=self.helper.node('ArrayTypeName',
                baseType=self.helper.node('ElementaryTypeName', name='uint256'), length=None),
            typeDescriptions={'typeIdentifier': 't_array$_t_uint256_$dyn_storage'})
        self.helper.contract['nodes'].append(array)
        length = self.helper.node('MemberAccess', memberName='length',
            expression=self.helper.state_read(array), typeDescriptions={'typeIdentifier': 't_uint256'})
        self.add_entry('resize', [self.helper.statement(self.helper.node('Assignment', operator='=',
            leftHandSide=length, rightHandSide=self.helper.literal(2**256-1)))])
        proof = self.proof()
        self.assertEqual('UNKNOWN', proof['status'])
        self.assertTrue(any('数组长度' in gap for gap in proof['proofScope']['gaps']))

    def test_没有运行期长度写入的数组索引仍需初始化和槽隔离证明(self):
        array = self.helper.node('VariableDeclaration', name='items', stateVariable=True,
            visibility='private', typeName=self.helper.node('ArrayTypeName',
                baseType=self.helper.node('ElementaryTypeName', name='uint256'), length=None),
            typeDescriptions={'typeIdentifier': 't_array$_t_uint256_$dyn_storage'})
        self.helper.contract['nodes'].append(array)
        element = self.helper.node('IndexAccess', baseExpression=self.helper.state_read(array),
            indexExpression=self.helper.literal(1), typeDescriptions={'typeIdentifier': 't_uint256'})
        self.add_entry('set', [self.helper.statement(self.helper.node('Assignment', operator='=',
            leftHandSide=element, rightHandSide=self.helper.literal(1)))])
        proof = self.proof()
        self.assertEqual('UNKNOWN', proof['status'])
        self.assertTrue(any('物理分离' in gap for gap in proof['proofScope']['gaps']))

    def test_动态字节类型不能因AST不是数组而遗漏隔离检查(self):
        data = self.helper.node('VariableDeclaration', name='data', stateVariable=True,
            visibility='private', typeName=self.helper.node('ElementaryTypeName', name='bytes'),
            typeDescriptions={'typeIdentifier': 't_bytes_storage'})
        self.helper.contract['nodes'].append(data)
        element = self.helper.node('IndexAccess', baseExpression=self.helper.state_read(data),
            indexExpression=self.helper.literal(1), typeDescriptions={'typeIdentifier': 't_bytes1'})
        self.add_entry('setByte', [self.helper.statement(self.helper.node('Assignment', operator='=',
            leftHandSide=element, rightHandSide=self.helper.literal(1)))])
        proof = self.proof()
        self.assertEqual('UNKNOWN', proof['status'])
        self.assertTrue(any('动态字节' in gap for gap in proof['proofScope']['gaps']))

    def role_setup(self):
        role = self.helper.state('roles')
        role['typeDescriptions']['typeIdentifier'] = 't_mapping$_t_address_$_t_bool_$'
        def lookup(key=None):
            return self.helper.node('IndexAccess', baseExpression=self.helper.state_read(role),
                indexExpression=key or self.helper.sender(), typeDescriptions={'typeIdentifier': 't_bool'})
        self.helper.function['body']['statements'][0] = self.helper.require(lookup())
        grant = self.helper.statement(self.helper.node('Assignment', operator='=', leftHandSide=lookup(),
            rightHandSide=self.helper.literal(True)))
        self.add_entry('grant', [self.helper.syntax.fresh(self.guard), grant])
        return role, lookup, grant

    def test_直接角色映射的管理闭包完整才可证明(self):
        role, lookup, _ = self.role_setup()
        revoke = self.helper.statement(self.helper.node('Assignment', operator='=', leftHandSide=lookup(),
            rightHandSide=self.helper.literal(False)))
        self.add_entry('revoke', [self.helper.syntax.fresh(self.guard), revoke])
        proof = self.proof()
        self.assertEqual('PROVED', proof['status'])
        self.assertIn(role['id'], proof['proofScope']['protectedRoots'])
        self.assertTrue(proof['authorityClosure'])

    def test_未保护角色授予或管理主体可写均保持未知(self):
        self.role_setup()
        grant = next(n for n in self.helper.contract['nodes'] if n.get('name') == 'grant')
        grant['body']['statements'].pop(0)
        self.assertEqual('UNKNOWN', self.proof()['status'])
        grant['body']['statements'].insert(0, self.helper.syntax.fresh(self.guard))
        self.add_entry('initialize', [self.helper.write(self.owner, self.helper.sender())])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_角色错误键或允许常量旁路不能当作调用者保护(self):
        _, lookup, _ = self.role_setup()
        self.helper.function['body']['statements'][0] = self.helper.require(lookup(self.helper.state_read(self.owner)))
        self.assertEqual('UNKNOWN', self.proof()['status'])
        self.helper.function['body']['statements'][0] = self.helper.require(self.helper.node('BinaryOperation',
            operator='||', leftExpression=lookup(), rightExpression=self.helper.literal(True)))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_角色检查后同根写入使旧版本失效(self):
        _, _, grant = self.role_setup()
        self.helper.function['body']['statements'].insert(1, self.helper.syntax.fresh(grant))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def gate_setup(self, initial=None):
        gate = self.helper.state('enabled', initial=initial)
        self.helper.function['body']['statements'][0] = self.helper.require(self.helper.state_read(gate))
        return gate

    def test_默认关闭且全入口不能改写的布尔门可证明不可到达(self):
        self.gate_setup()
        proof = self.proof()
        self.assertEqual('PROVED', proof['status'])
        self.assertEqual('CALL_UNREACHABLE_INVARIANT', proof['proofScope']['property'])
        self.assertTrue(proof['initialization']['runtimeInitialized'])
        self.assertTrue(proof['proofScope']['complete'])

    def test_公开或受控setter能开启状态时都不能冒充主体授权(self):
        gate = self.gate_setup()
        write = self.helper.write(gate, self.helper.literal(True))
        setter = self.add_entry('enable', [self.helper.syntax.fresh(self.guard), write])
        self.assertEqual('UNKNOWN', self.proof()['status'])
        setter['body']['statements'].pop(0)
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_开启初值与未知构造均不构成关闭不变量(self):
        self.gate_setup(self.helper.literal(True))
        self.assertEqual('UNKNOWN', self.proof()['status'])
        self.helper.constructor([self.helper.node('InlineAssembly')])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_构造参数不能枚举成false来制造不变量(self):
        gate = self.gate_setup()
        parameter = self.helper.node('VariableDeclaration', name='initialEnabled', stateVariable=False,
            typeName=self.helper.node('ElementaryTypeName', name='bool'),
            typeDescriptions={'typeIdentifier': 't_bool'})
        self.helper.constructor([self.helper.write(gate, self.helper.node('Identifier', name='initialEnabled',
            referencedDeclaration=parameter['id'], typeDescriptions={'typeIdentifier': 't_bool'}))], [parameter])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未知其他入口可能写开关时不能证明不变量(self):
        self.gate_setup()
        self.add_entry('opaque', [self.helper.node('InlineAssembly')])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_命名实参不能按位置代入而制造虚假授权(self):
        actor = self.helper.node('VariableDeclaration', name='actor', stateVariable=False,
            typeName=self.helper.node('ElementaryTypeName', name='address'),
            typeDescriptions={'typeIdentifier': 't_address'})
        next_owner = self.helper.syntax.fresh(actor); next_owner['name'] = 'next'
        def parameter_read(parameter):
            return self.helper.node('Identifier', name=parameter['name'], referencedDeclaration=parameter['id'],
                typeDescriptions={'typeIdentifier': 't_address'})
        internal = self.helper.syntax.fresh(self.helper.function)
        internal.update(name='give', visibility='internal')
        internal['parameters']['parameters'] = [actor, next_owner]
        internal['body']['statements'] = [self.helper.require(self.helper.node('BinaryOperation', operator='==',
            leftExpression=parameter_read(actor), rightExpression=self.helper.state_read(self.owner))),
            self.helper.write(self.owner, parameter_read(next_owner))]
        self.helper.contract['nodes'].append(internal)
        call = self.helper.node('FunctionCall', kind='functionCall', names=['next', 'actor'],
            arguments=[self.helper.sender(), self.helper.state_read(self.owner)],
            expression=self.helper.node('Identifier', name='give', referencedDeclaration=internal['id'],
                typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$_t_address_$_t_address_$returns$__$'}))
        self.add_entry('grant', [self.helper.statement(call)])
        proof = self.proof()
        self.assertEqual('UNKNOWN', proof['status'])
        self.assertFalse(proof['proofScope']['complete'])
        self.assertTrue(any('命名实参' in gap for gap in proof['proofScope']['gaps']))

    def test_低级调用只绑定而不套用转账证明(self):
        self.call['expression'].update(memberName='delegatecall',
            typeDescriptions={'typeIdentifier': 't_function_baredelegatecall_nonpayable$_t_bytes_memory_ptr_$returns$_t_bool_$'})
        proof = self.proof()
        self.assertNotEqual('PROVED', proof['status'])
        self.assertFalse(proof['applicable'])

    def test_子合约覆盖修饰器不能沿用父合约保护(self):
        modifier = self.helper.node('ModifierDefinition', name='onlyOwner', virtual=True,
            parameters=self.helper.node('ParameterList', parameters=[]),
            body=self.helper.node('Block', statements=[self.guard, self.helper.node('PlaceholderStatement')]))
        base = self.helper.node('ContractDefinition', name='Base', contractKind='contract',
            linearizedBaseContracts=[], nodes=[modifier, self.helper.function])
        base['linearizedBaseContracts'] = [base['id']]
        override = self.helper.syntax.fresh(modifier)
        override['body']['statements'] = [self.helper.node('PlaceholderStatement')]
        self.helper.contract['nodes'].remove(self.helper.function)
        self.helper.contract['nodes'].append(override)
        self.helper.contract['linearizedBaseContracts'].append(base['id'])
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'].append(base)
        self.helper.function['body']['statements'].pop(0)
        self.helper.function['modifiers'] = [self.helper.node('ModifierInvocation',
            modifierName=self.helper.node('IdentifierPath', name='onlyOwner', referencedDeclaration=modifier['id']), arguments=[])]
        proof = self.proof()
        self.assertEqual('UNKNOWN', proof['status'])
        self.assertFalse(proof['proofScope']['complete'])
        self.assertTrue(any('修饰器覆盖' in gap for gap in proof['proofScope']['gaps']))
