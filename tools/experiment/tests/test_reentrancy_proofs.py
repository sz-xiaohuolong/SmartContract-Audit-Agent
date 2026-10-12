"""有限重入规则的本地编译子进程夹具；断言数据不包含攻击执行代码。"""
import copy
import unittest

import test_compiled_d2 as syntax_fixtures
from compiler_facts import extract_compiler_facts
from reentrancy_proofs import prove_reentrancy


class ReentrancyProofTest(unittest.TestCase):
    def setUp(self):
        self.syntax = syntax_fixtures.CompiledD2Test()
        self.syntax.setUp()
        self.addCleanup(self.syntax.doCleanups)
        self.fixture = self.syntax.fixture
        self.node = self.syntax.node
        contract = self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        self.balance = self.node('VariableDeclaration', name='credit', stateVariable=True,
            visibility='private', typeName=self.node('Mapping',
                keyType=self.node('ElementaryTypeName', name='address'),
                valueType=self.node('ElementaryTypeName', name='uint256')))
        self.lock = self.node('VariableDeclaration', name='busy', stateVariable=True, visibility='private',
            typeName=self.node('ElementaryTypeName', name='bool'), typeDescriptions={'typeIdentifier': 't_bool'})
        contract['nodes'].extend([self.balance, self.lock])
        self.call = self.low_call()
        self.guard = self.check(self.node('BinaryOperation', operator='>',
            leftExpression=self.credit(), rightExpression=self.number(0)))
        self.write = self.assign(self.credit(), self.number(0))
        self.fixture.function()['body']['statements'] = [self.guard, self.statement(self.call), self.write]
        value = self.node('MemberAccess', memberName='value', expression=self.node('Identifier', name='msg',
            referencedDeclaration=-15, typeDescriptions={'typeIdentifier': 't_magic_message'}),
            typeDescriptions={'typeIdentifier': 't_uint256'})
        self.funding = self.add_entry([self.statement(self.node('Assignment', operator='+=',
            leftHandSide=self.credit(), rightHandSide=value))], name='deposit')
        self.funding['stateMutability'] = 'payable'
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][-1]['stateMutability'] = 'payable'

    def sender(self):
        return self.node('MemberAccess', memberName='sender', typeDescriptions={'typeIdentifier': 't_address'},
            expression=self.node('Identifier', name='msg', referencedDeclaration=-15,
                typeDescriptions={'typeIdentifier': 't_magic_message'}))

    def number(self, value):
        return self.node('Literal', kind='number', value=str(value), typeDescriptions={'typeIdentifier': 't_uint256'})

    def boolean(self, value):
        return self.node('Literal', kind='bool', value=str(value).lower(), typeDescriptions={'typeIdentifier': 't_bool'})

    def credit(self):
        return self.node('IndexAccess', typeDescriptions={'typeIdentifier': 't_uint256'},
            baseExpression=self.node('Identifier', name='credit', referencedDeclaration=self.balance['id']),
            indexExpression=self.sender())

    def busy(self):
        return self.node('Identifier', name='busy', referencedDeclaration=self.lock['id'],
            typeDescriptions={'typeIdentifier': 't_bool'})

    def statement(self, expression):
        return self.node('ExpressionStatement', expression=expression)

    def check(self, condition):
        return self.statement(self.node('FunctionCall', kind='functionCall', arguments=[condition],
            expression=self.node('Identifier', name='require', referencedDeclaration=-18,
                typeDescriptions={'typeIdentifier': 't_function_require_pure$_t_bool_$returns$__$'})))

    def assign(self, left, right):
        return self.statement(self.node('Assignment', operator='=', leftHandSide=left, rightHandSide=right))

    def low_call(self, *, old=False):
        bare = self.node('MemberAccess', memberName='call', expression=self.sender(),
            typeDescriptions={'typeIdentifier': ('t_function_barecall_payable$__$returns$_t_bool_$' if old else
                't_function_barecall_payable$_t_bytes_memory_ptr_$returns$_t_bool_$_t_bytes_memory_ptr_$')})
        if old:
            expression = self.node('FunctionCall', kind='functionCall', arguments=[self.credit()],
                expression=self.node('MemberAccess', memberName='value', expression=bare,
                    typeDescriptions={'typeIdentifier': 't_function_setvalue_nonpayable$_t_uint256_$returns$__$'}),
                typeDescriptions=bare['typeDescriptions'])
        else:
            expression = self.node('FunctionCallOptions', expression=bare, names=['value'], options=[self.credit()],
                typeDescriptions=bare['typeDescriptions'])
        return self.node('FunctionCall', kind='functionCall', expression=expression,
            arguments=[self.node('Literal', kind='string', value='')])

    def proof(self, **fields):
        self.fixture.seal()
        bundle = self.fixture.load()
        fact = next(f for f in extract_compiler_facts(bundle)['facts'] if f['nodeId'] == self.call['id'])
        hypothesis = {'contract': 'C', 'function': 'f()', 'riskLine': 1, 'riskOperation': 'CALL',
            'vulnerabilityType': 'REENTRANCY', 'riskFactId': fact['id'], **fields}
        return prove_reentrancy(bundle, hypothesis)

    def add_entry(self, statements, *, name='other', kind='function'):
        function = self.node('FunctionDefinition', name=name, kind=kind, visibility='public',
            stateMutability='nonpayable', parameters=self.node('ParameterList', parameters=[]),
            returnParameters=self.node('ParameterList', parameters=[]), modifiers=[],
            body=self.node('Block', statements=statements))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(function)
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': kind, 'name': name, 'inputs': [], 'outputs': [], 'stateMutability': 'nonpayable'})
        return function

    def lock_prefix(self):
        return [self.check(self.node('UnaryOperation', operator='!', subExpression=self.busy())),
                self.assign(self.busy(), self.boolean(True))]

    def test_先调用后归零有可满足约束且正常退出的防御断言反例(self):
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertEqual('FEASIBLE', result['pathEvidence']['status'])
        self.assertTrue(result['pathEvidence']['witness']['normalExit'])
        self.assertEqual('SATISFIABLE_ABSTRACTION', result['pathEvidence']['transactionFeasibility'])
        self.assertEqual('REFUTED', next(o for o in result['obligations'] if o['name'] == 'state_version')['status'])

    def test_旧Throw分支是回滚而非未知续接(self):
        self.fixture.function()['body']['statements'].append(self.node('IfStatement',
            condition=self.boolean(False), trueBody=self.node('Throw'), falseBody=None))
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])
        self.fixture.function()['body']['statements'][-1]['condition'] = self.boolean(True)
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_顶层风险图与专用重入证明使用相同CALL语义(self):
        from compiled_d2 import evaluate_compiled
        self.fixture.seal()
        result = evaluate_compiled({'contract': 'C', 'function': 'f()', 'riskLine': 1,
            'riskOperation': 'CALL', 'vulnerabilityType': 'REENTRANCY'},
            self.fixture.manifest, [], root=self.fixture.root)
        self.assertIn('riskBinding', result)
        self.assertNotIn('风险操作、字节跨度与调用上下文无法唯一绑定', result['proofScope']['gaps'])
        self.assertEqual('UNKNOWN', result['verdict'])

    def test_现代CALL布尔返回解构可核验而返回数据使用保持未知(self):
        success = self.node('VariableDeclaration', name='success', stateVariable=False,
            storageLocation='default', typeDescriptions={'typeIdentifier': 't_bool'})
        capture = self.node('VariableDeclarationStatement', declarations=[success, None], initialValue=self.call)
        checked = self.check(self.node('Identifier', name='success', referencedDeclaration=success['id']))
        self.fixture.function()['body']['statements'] = [self.guard, capture, checked, self.write]
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])
        # 未建模返回字节内容，不能把其断言看作已满足。
        data = self.node('VariableDeclaration', name='data', stateVariable=False,
            storageLocation='memory', typeDescriptions={'typeIdentifier': 't_bytes_memory_ptr'})
        capture['declarations'][1] = data
        checked['expression']['arguments'] = [self.node('Identifier', name='data', referencedDeclaration=data['id'])]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_旧版带数值调用链也必须使用编译类型与参数(self):
        self.call = self.low_call(old=True)
        self.fixture.function()['body']['statements'] = [self.guard, self.statement(self.call), self.write]
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])

    def test_CEI前置归零与余额检查闭合全部义务(self):
        self.fixture.function()['body']['statements'] = [self.guard, self.write, self.statement(self.call)]
        # 调用数值在写入前保存，避免把零转账误认为受保护的原始数值。
        captured = self.node('VariableDeclaration', name='amount', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='uint256'), typeDescriptions={'typeIdentifier': 't_uint256'})
        capture = self.node('VariableDeclarationStatement', declarations=[captured], initialValue=self.credit())
        self.call['expression']['options'] = [self.node('Identifier', name='amount', referencedDeclaration=captured['id'])]
        self.fixture.function()['body']['statements'].insert(1, capture)
        result = self.proof()
        self.assertEqual('PROVED', result['status'])
        self.assertEqual('BLOCKED', result['pathEvidence']['status'])
        self.assertTrue(result['proofScope']['complete'])
        self.assertEqual({'SUPPORTED'}, {o['status'] for o in result['obligations']})

    def test_前置归零没有余额条件不能补成安全证明(self):
        self.fixture.function()['body']['statements'] = [self.write, self.statement(self.call)]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_无余额检查的先CALL后写入须以实际正数与合法入账验证(self):
        self.fixture.function()['body']['statements'] = [self.statement(self.call), self.write]
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertEqual('REFUTED', next(o for o in result['obligations'] if o['name'] == 'pre_risk_guard')['status'])
        self.call['expression']['options'] = [self.number(0)]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_带ether单位的阈值不能按字面数字1证明小额路径(self):
        limit = self.guard['expression']['arguments'][0]['rightExpression']
        limit.update(value='1', subdenomination='ether')
        self.assertEqual('UNKNOWN', self.proof()['status'])
        limit.update(value='0.000000000000000001', subdenomination='ether')
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])

    def test_统一互斥锁可证明后置余额更新的回调窗口受保护(self):
        self.fixture.function()['body']['statements'] = self.lock_prefix() + [self.guard,
            self.statement(self.call), self.write, self.assign(self.busy(), self.boolean(False))]
        self.funding['body']['statements'] = self.lock_prefix() + self.funding['body']['statements'] + [
            self.assign(self.busy(), self.boolean(False))]
        result = self.proof()
        self.assertEqual('PROVED', result['status'])
        self.assertIn('GLOBAL_MUTEX', result['proofScope']['rules'])

    def test_只读取余额并转账的无扣减入口不能漏过统一锁覆盖(self):
        self.fixture.function()['body']['statements'] = self.lock_prefix() + [self.guard,
            self.statement(self.call), self.write, self.assign(self.busy(), self.boolean(False))]
        self.funding['body']['statements'] = self.lock_prefix() + self.funding['body']['statements'] + [
            self.assign(self.busy(), self.boolean(False))]
        self.add_entry([self.syntax.fresh(self.guard), self.statement(self.low_call())], name='readOnlyWithdraw')
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(next(e for e in result['proofScope']['entries'] if e['signature'] == 'readOnlyWithdraw()')['related'])

    def test_未使用余额读取仍须纳入包含转账的入口盘点(self):
        self.fixture.function()['body']['statements'] = self.lock_prefix() + [self.guard,
            self.statement(self.call), self.write, self.assign(self.busy(), self.boolean(False))]
        self.funding['body']['statements'] = self.lock_prefix() + self.funding['body']['statements'] + [
            self.assign(self.busy(), self.boolean(False))]
        call = self.low_call()
        call['expression']['options'] = [self.number(1)]
        self.add_entry([self.statement(self.credit()), self.statement(call)], name='observeAndTransfer')
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(next(e for e in result['proofScope']['entries'] if e['signature'] == 'observeAndTransfer()')['related'])

    def test_只读取余额转账的fallback不能漏过严格CEI入口覆盖(self):
        self.fixture.function()['body']['statements'] = [self.guard, self.write, self.statement(self.call)]
        captured = self.node('VariableDeclaration', name='amount', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='uint256'), typeDescriptions={'typeIdentifier': 't_uint256'})
        capture = self.node('VariableDeclarationStatement', declarations=[captured], initialValue=self.credit())
        self.call['expression']['options'] = [self.node('Identifier', name='amount', referencedDeclaration=captured['id'])]
        self.fixture.function()['body']['statements'].insert(1, capture)
        self.add_entry([self.syntax.fresh(self.guard), self.statement(self.low_call())], name='', kind='fallback')
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(next(e for e in result['proofScope']['entries'] if e['signature'] == 'fallback()')['related'])

    def test_其他入口可清除同一锁则保护证明未知(self):
        self.fixture.function()['body']['statements'] = self.lock_prefix() + [self.guard,
            self.statement(self.call), self.write, self.assign(self.busy(), self.boolean(False))]
        self.add_entry([self.assign(self.busy(), self.boolean(False))])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未保护fallback修改余额导致统一锁入口覆盖未知(self):
        self.fixture.function()['body']['statements'] = self.lock_prefix() + [self.guard,
            self.statement(self.call), self.write, self.assign(self.busy(), self.boolean(False))]
        self.add_entry([self.assign(self.credit(), self.number(2))], name='', kind='fallback')
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(any(e['signature'] == 'fallback()' for e in result['proofScope']['entries']))

    def test_先调用后取得锁不能覆盖早期窗口(self):
        self.fixture.function()['body']['statements'] = [self.guard, self.statement(self.call)] + self.lock_prefix() + [self.write]
        self.assertNotEqual('PROVED', self.proof()['status'])

    def test_矛盾前置条件不能声称可正常提交反例(self):
        impossible = self.check(self.node('BinaryOperation', operator='==',
            leftExpression=self.credit(), rightExpression=self.number(0)))
        self.fixture.function()['body']['statements'].insert(1, impossible)
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_后置必然失败检查不能声称可正常提交反例(self):
        self.fixture.function()['body']['statements'].append(self.check(self.boolean(False)))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未使用局部算术仍可能回退不能从CFG遗漏(self):
        local = self.node('VariableDeclaration', name='unused', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='uint256'))
        calculation = self.node('BinaryOperation', operator='/', leftExpression=self.number(1),
            rightExpression=self.number(0), typeDescriptions={'typeIdentifier': 't_uint256'})
        self.fixture.function()['body']['statements'].append(self.node('VariableDeclarationStatement',
            declarations=[local], initialValue=calculation))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_返回表达式的未证明求值不能冒充正常退出(self):
        self.fixture.function()['body']['statements'].append(self.node('Return', expression=self.node(
            'BinaryOperation', operator='/', leftExpression=self.number(1), rightExpression=self.number(0),
            typeDescriptions={'typeIdentifier': 't_uint256'})))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_窄整数加法溢出不能冒充正常退出(self):
        local = self.node('VariableDeclaration', name='narrow', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='uint8'))
        calculation = self.node('BinaryOperation', operator='+', leftExpression=self.number(255),
            rightExpression=self.number(1), typeDescriptions={'typeIdentifier': 't_uint8'})
        self.fixture.function()['body']['statements'].append(self.node('VariableDeclarationStatement',
            declarations=[local], initialValue=calculation))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_余额恒等比较不能替代有效前置余额条件(self):
        condition = self.guard['expression']['arguments'][0]
        condition['operator'] = '>='
        condition['rightExpression'] = self.credit()
        self.fixture.function()['body']['statements'] = [self.guard, self.write, self.statement(self.call)]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_后置未知函数结果检查不能声称可正常提交反例(self):
        local = self.node('VariableDeclaration', name='decision', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='bool'))
        self.fixture.function()['body']['statements'].append(self.check(self.node('Identifier',
            name='decision', referencedDeclaration=local['id'])))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(local)
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_CALL结果被require检查时须明确选择成功断言(self):
        self.call = self.low_call(old=True)
        local = self.node('VariableDeclaration', name='ok', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='bool'), typeDescriptions={'typeIdentifier': 't_bool'})
        declaration = self.node('VariableDeclarationStatement', declarations=[local], initialValue=self.call)
        self.fixture.function()['body']['statements'] = [self.guard, declaration,
            self.check(self.node('Identifier', name='ok', referencedDeclaration=local['id'])), self.write]
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertTrue(result['pathEvidence']['witness']['calls'][0]['success'])

    def test_显式调用失败约束不能声称外部效果成功(self):
        local = self.node('VariableDeclaration', name='ok', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='bool'), typeDescriptions={'typeIdentifier': 't_bool'})
        declaration = self.node('VariableDeclarationStatement', declarations=[local], initialValue=self.call)
        self.fixture.function()['body']['statements'] = [self.guard, declaration,
            self.check(self.node('UnaryOperation', operator='!', subExpression=self.node('Identifier',
                name='ok', referencedDeclaration=local['id']))), self.write]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_无相关余额写入仅有调用不能产生CEI反例(self):
        self.fixture.function()['body']['statements'] = [self.guard, self.statement(self.call)]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_循环与汇编使完整保护未知(self):
        self.fixture.function()['body']['statements'] = self.lock_prefix() + [self.guard,
            self.statement(self.call), self.write, self.assign(self.busy(), self.boolean(False)), self.node('InlineAssembly')]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_名称伪装和delegatecall类型不能冒充已证明数值调用(self):
        self.call['expression']['expression']['typeDescriptions']['typeIdentifier'] = 't_function_baredelegatecall_nonpayable$__$returns$_t_bool_$'
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_编译身份和风险事实漂移拒绝候选(self):
        self.assertEqual('FAILED', self.proof(riskFactId='0' * 64)['status'])
        self.assertEqual('FAILED', self.proof(contract='Other')['status'])
        self.fixture.seal()
        bundle = self.fixture.load()
        bundle['verificationStatus'] = 'UNVERIFIED'
        self.assertEqual('FAILED', prove_reentrancy(bundle, {})['status'])

    def amount_case(self, *, before=False, donate=False):
        amount = self.node('VariableDeclaration', name='amount', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='uint256'), typeDescriptions={'typeIdentifier': 't_uint256'})
        def argument():
            return self.node('Identifier', name='amount', referencedDeclaration=amount['id'],
                typeDescriptions={'typeIdentifier': 't_uint256'})
        self.fixture.function()['parameters']['parameters'] = [amount]
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][0]['inputs'] = [{'type': 'uint256'}]
        self.call['expression']['options'] = [argument()]
        condition = self.node('BinaryOperation', operator='>=', leftExpression=self.credit(), rightExpression=argument())
        debit = self.statement(self.node('Assignment', operator='-=', leftHandSide=self.credit(), rightHandSide=argument()))
        body = [debit, self.statement(self.call)] if before else [self.statement(self.call), debit]
        self.fixture.function()['body']['statements'] = [self.node('IfStatement', condition=condition,
            trueBody=self.node('Block', statements=body), falseBody=None)]
        if donate:
            to = self.node('VariableDeclaration', name='to', stateVariable=False,
                typeName=self.node('ElementaryTypeName', name='address'), typeDescriptions={'typeIdentifier': 't_address'})
            credit = self.credit()
            credit['indexExpression'] = self.node('Identifier', name='to', referencedDeclaration=to['id'])
            value = self.node('MemberAccess', memberName='value', expression=self.node('Identifier', name='msg',
                referencedDeclaration=-15, typeDescriptions={'typeIdentifier': 't_magic_message'}),
                typeDescriptions={'typeIdentifier': 't_uint256'})
            entry = self.add_entry([self.statement(self.node('Assignment', operator='+=',
                leftHandSide=credit, rightHandSide=value))], name='donate')
            entry['parameters']['parameters'] = [to]
            entry['stateMutability'] = 'payable'
            abi = self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][-1]
            abi.update(inputs=[{'type': 'address'}], stateMutability='payable')

    def test_经典DAO参数减法有可满足余额区间且正常提交(self):
        self.amount_case(donate=True)
        result = self.proof(function='f(uint256)')
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertGreater(result['pathEvidence']['witness']['parameters'][0]['value'], 0)
        self.assertTrue(result['pathEvidence']['witness']['initialization']['funded'])

    def test_只扣部分余额不能泛化为余额归零后的回调阻断(self):
        self.amount_case(before=True, donate=True)
        result = self.proof(function='f(uint256)')
        self.assertEqual('UNKNOWN', result['status'])

    def test_前置扣减全部余额与对应入账满足严格CEI(self):
        self.amount_case(before=True, donate=True)
        self.fixture.function()['body']['statements'][0]['condition']['operator'] = '=='
        result = self.proof(function='f(uint256)')
        self.assertEqual('PROVED', result['status'])
        self.assertIn('STRICT_CEI', result['proofScope']['rules'])

    def test_入账同时更新标量总账时必须重放全部槽且匹配提款初态(self):
        total = self.node('VariableDeclaration', name='total', stateVariable=True,
            typeName=self.node('ElementaryTypeName', name='uint256'),
            typeDescriptions={'typeIdentifier': 't_uint256'})
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(total)
        def total_ref():
            return self.node('Identifier', name='total', referencedDeclaration=total['id'],
                typeDescriptions={'typeIdentifier': 't_uint256'})
        value = self.syntax.fresh(self.funding['body']['statements'][0]['expression']['rightHandSide'])
        self.funding['body']['statements'].append(self.statement(self.node('Assignment', operator='+=',
            leftHandSide=total_ref(), rightHandSide=value)))
        self.fixture.function()['body']['statements'].insert(1, self.statement(self.node('Assignment',
            operator='-=', leftHandSide=total_ref(), rightHandSide=self.credit())))
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        initial = result['pathEvidence']['witness']['initialStorage']
        self.assertEqual(next(item['value'] for item in initial if item['root'] == self.balance['id']),
                         next(item['value'] for item in initial if item['root'] == total['id']))
        # 不一致的辅助总账断言不能靠独立枚举余额冒充可达初态。
        self.fixture.function()['body']['statements'].insert(1, self.check(self.node('BinaryOperation',
            operator='>', leftExpression=total_ref(), rightExpression=self.credit())))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未证明可达建态的条件反例必须保留未知(self):
        contract = self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        contract['nodes'].remove(self.funding)
        abi = self.fixture.output['contracts']['contracts/C.sol']['C']['abi']
        abi[:] = [entry for entry in abi if entry.get('name') != 'deposit']
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(result['proofScope']['conditionedOnInitialState'])
        self.assertFalse(result['pathEvidence']['witness']['initialization']['funded'])

    def test_非默认状态初值不能用任意False冒充可达建态(self):
        self.lock['value'] = self.boolean(True)
        self.fixture.function()['body']['statements'].insert(0,
            self.check(self.node('UnaryOperation', operator='!', subExpression=self.busy())))
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(any('初值' in gap for gap in result['proofScope']['gaps']))

    def test_构造函数非空语义不能假设运行期槽均为默认零(self):
        constructor = self.node('FunctionDefinition', name='', kind='constructor', visibility='public',
            stateMutability='nonpayable', parameters=self.node('ParameterList', parameters=[]),
            returnParameters=self.node('ParameterList', parameters=[]), modifiers=[],
            body=self.node('Block', statements=[self.assign(self.busy(), self.boolean(True))]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(constructor)
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(any('构造' in gap for gap in result['proofScope']['gaps']))

    def test_显式默认False状态初值仍允许已验证入账建态(self):
        self.lock['value'] = self.boolean(False)
        self.fixture.function()['body']['statements'].insert(0,
            self.check(self.node('UnaryOperation', operator='!', subExpression=self.busy())))
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])

    def test_入账后必然回退的入口不能作为资金建态证明(self):
        self.funding['body']['statements'].append(self.node('RevertStatement', errorCall=None))
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertFalse(result['pathEvidence']['witness']['initialization']['funded'])

    def test_入账返回未知求值的入口不能作为资金建态证明(self):
        self.funding['body']['statements'].append(self.node('Return', expression=self.node('BinaryOperation',
            operator='/', leftExpression=self.number(1), rightExpression=self.number(0),
            typeDescriptions={'typeIdentifier': 't_uint256'})))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_入账入口无关uint参数必须按实际类型给出数值(self):
        parameter = self.node('VariableDeclaration', name='unused', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='uint256'), typeDescriptions={'typeIdentifier': 't_uint256'})
        self.funding['parameters']['parameters'] = [parameter]
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][-1]['inputs'] = [{'type': 'uint256'}]
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        values = result['pathEvidence']['witness']['initialization']['parameters']
        self.assertEqual(0, values[0]['value'])
        self.assertIs(type(values[0]['value']), int)

    def test_唯一短函数名可绑定实际完整签名(self):
        self.amount_case(donate=True)
        result = self.proof(function='f')
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertTrue(result['pathEvidence']['normalExit'])
        self.assertIn('riskSpan', result['proofScope'])

    def test_没有资金来源的任意余额增加入口阻止CEI证明(self):
        self.amount_case(before=True)
        self.add_entry([self.assign(self.credit(), self.number(100))])
        self.assertEqual('UNKNOWN', self.proof(function='f(uint256)')['status'])


if __name__ == '__main__':
    unittest.main()
