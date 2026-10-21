"""有限重入规则的本地编译子进程夹具；断言数据不包含攻击执行代码。"""
import copy
import unittest

import test_compiled_d2 as syntax_fixtures
from verirag.analysis.compiler_facts import extract_compiler_facts
from verirag.analysis.reentrancy_proofs import prove_reentrancy


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

    def proof(self, *, effect_summaries=None, **fields):
        self.fixture.seal()
        bundle = self.fixture.load()
        fact = next(f for f in extract_compiler_facts(bundle)['facts'] if f['nodeId'] == self.call['id'])
        hypothesis = {'contract': 'C', 'function': 'f()', 'riskLine': 1, 'riskOperation': 'CALL',
            'vulnerabilityType': 'REENTRANCY', 'riskFactId': fact['id'], **fields}
        if effect_summaries is not None:
            return prove_reentrancy(bundle, hypothesis, effect_summaries=effect_summaries)
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

    def test_重入调用两行漂移绑定保留原候选而窗口外拒绝(self):
        result = self.proof(riskLine=3)
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertEqual(3, result['riskBinding']['originalLine'])
        self.assertEqual(1, result['riskBinding']['boundLine'])
        self.assertEqual('FAILED', self.proof(riskLine=4)['status'])

    def test_旧Throw分支是回滚而非未知续接(self):
        self.fixture.function()['body']['statements'].append(self.node('IfStatement',
            condition=self.boolean(False), trueBody=self.node('Throw'), falseBody=None))
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])
        self.fixture.function()['body']['statements'][-1]['condition'] = self.boolean(True)
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_顶层风险图与专用重入证明使用相同CALL语义(self):
        from verirag.analysis.compiled_d2 import evaluate_compiled
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
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertGreater(result['pathEvidence']['witness']['calls'][0]['value'], 10 ** 18)
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

    def struct_case(self, *, storage_location='default', alias=True):
        """模拟旧编译器 var 推导的 storage ptr；字段与结构类型都带声明身份。"""
        contract = self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        field = self.node('VariableDeclaration', name='balance', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='uint256'),
            typeDescriptions={'typeIdentifier': 't_uint256'})
        other = self.syntax.fresh(field)
        other['name'] = 'otherBalance'
        holder = self.node('StructDefinition', name='Holder', members=[field, other])
        contract['nodes'].append(holder)
        identity = f't_struct$_Holder_${holder["id"]}_storage'
        self.balance['typeName']['valueType'] = self.node('UserDefinedTypeName',
            namePath='Holder', referencedDeclaration=holder['id'])
        self.balance['typeDescriptions'] = {'typeIdentifier': f't_mapping$_t_address_$_{identity}_$'}

        def account():
            return self.node('IndexAccess', typeDescriptions={'typeIdentifier': identity},
                baseExpression=self.node('Identifier', name='credit', referencedDeclaration=self.balance['id']),
                indexExpression=self.sender())

        def declaration():
            return self.node('VariableDeclaration', name='acc', stateVariable=False,
                storageLocation=storage_location, typeName=None,
                typeDescriptions={'typeIdentifier': identity + '_ptr'})

        withdrawal, deposit = declaration(), declaration()

        def member(local=None, selected=field):
            base = (account() if local is None else self.node('Identifier', name='acc',
                referencedDeclaration=local['id'], typeDescriptions=local['typeDescriptions']))
            return self.node('MemberAccess', expression=base, memberName=selected['name'],
                referencedDeclaration=selected['id'], typeDescriptions={'typeIdentifier': 't_uint256'})

        self.credit = lambda: member(withdrawal if alias else None)
        self.guard = self.check(self.node('BinaryOperation', operator='>',
            leftExpression=self.credit(), rightExpression=self.number(0)))
        self.call = self.low_call()
        self.write = self.assign(self.credit(), self.number(0))
        capture = self.node('VariableDeclarationStatement', declarations=[withdrawal], initialValue=account())
        self.fixture.function()['body']['statements'] = ([capture] if alias else []) + [
            self.guard, self.statement(self.call), self.write]
        value = self.funding['body']['statements'][0]['expression']['rightHandSide']
        deposit_capture = self.node('VariableDeclarationStatement', declarations=[deposit], initialValue=account())
        self.funding['body']['statements'] = ([deposit_capture] if alias else []) + [self.statement(self.node(
            'Assignment', operator='+=', leftHandSide=member(deposit if alias else None), rightHandSide=value))]
        return {'field': field, 'other': other, 'holder': holder, 'withdrawal': withdrawal,
                'deposit': deposit, 'capture': capture, 'member': member, 'account': account}

    def test_旧default_storage_ptr别名与结构uint余额有合法建态反例(self):
        case = self.struct_case()
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        witness = result['pathEvidence']['witness']
        self.assertTrue(witness['initialization']['funded'])
        self.assertIn(('member', case['field']['id']), result['proofScope']['balanceResource'][2])
        item = next(item for item in witness['initialStorage'] if item['root'] == self.balance['id'])
        self.assertEqual(['调用主体 A'], item['keys'])
        self.assertEqual({'kind': 'member', 'declarationId': case['field']['id']}, item['storagePath'][-1])

    def test_显式storage别名与直接结构字段均按声明资源核验(self):
        self.struct_case(storage_location='storage')
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])

    def test_直接结构余额字段不需要局部别名(self):
        self.struct_case(alias=False)
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])

    def test_结构余额扣减按同字段同caller和合法入账核验(self):
        case = self.struct_case()
        self.amount_case()
        self.fixture.function()['body']['statements'].insert(0, case['capture'])
        result = self.proof(function='f(uint256)')
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertTrue(result['pathEvidence']['witness']['initialization']['funded'])

    def test_结构字段先归零且全入口闭包完整才可反驳(self):
        case = self.struct_case()
        captured = self.node('VariableDeclaration', name='amount', stateVariable=False,
            typeDescriptions={'typeIdentifier': 't_uint256'})
        declaration = self.node('VariableDeclarationStatement', declarations=[captured], initialValue=self.credit())
        self.call['expression']['options'] = [self.node('Identifier', name='amount', referencedDeclaration=captured['id'])]
        self.fixture.function()['body']['statements'] = [case['capture'], self.guard, declaration,
            self.write, self.statement(self.call)]
        self.assertEqual('PROVED', self.proof()['status'])

    def test_结构别名错key不能当作同主体余额(self):
        case = self.struct_case()
        case['capture']['initialValue']['indexExpression'] = self.number(0)
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构扣账错字段不能声称已绑定余额反例(self):
        case = self.struct_case()
        self.write['expression']['leftHandSide'] = case['member'](case['withdrawal'], case['other'])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构入账错字段不能把默认余额补成正数(self):
        case = self.struct_case()
        self.funding['body']['statements'][-1]['expression']['leftHandSide'] = case['member'](case['deposit'], case['other'])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构转账错caller不能套用主体余额(self):
        self.struct_case()
        self.call['expression']['expression']['expression'] = self.number(0)
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构memory类型不能冒充storage别名(self):
        case = self.struct_case(storage_location='memory')
        case['withdrawal']['typeDescriptions']['typeIdentifier'] = case['withdrawal']['typeDescriptions']['typeIdentifier'].replace('_storage_ptr', '_memory_ptr')
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构别名编译类型不一致与整结构重写均保留未知(self):
        case = self.struct_case()
        case['capture']['initialValue']['typeDescriptions']['typeIdentifier'] = 't_struct$_Wrong_$999_storage'
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构别名重赋值不能继续复用旧资源绑定(self):
        case = self.struct_case()
        left = self.node('Identifier', name='acc', referencedDeclaration=case['withdrawal']['id'],
            typeDescriptions=case['withdrawal']['typeDescriptions'])
        self.fixture.function()['body']['statements'].insert(1, self.assign(left, case['account']()))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构字段声明须确实属于编译结构(self):
        case = self.struct_case()
        case['holder']['members'].remove(case['field'])
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(case['field'])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构其他字段写入使已观察余额版本失效不能复用保护(self):
        case = self.struct_case()
        captured = self.node('VariableDeclaration', name='amount', stateVariable=False,
            typeDescriptions={'typeIdentifier': 't_uint256'})
        saved = self.node('VariableDeclarationStatement', declarations=[captured], initialValue=self.credit())
        self.call['expression']['options'] = [self.node('Identifier', name='amount', referencedDeclaration=captured['id'])]
        other_write = self.assign(case['member'](case['withdrawal'], case['other']), self.number(1))
        self.fixture.function()['body']['statements'] = [case['capture'], self.guard, saved, self.write,
            other_write, self.statement(self.call)]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构别名链须保持同一编译结构与字段身份(self):
        case = self.struct_case()
        original = self.syntax.fresh(case['withdrawal'])
        original['name'] = 'original'
        source = self.node('Identifier', name='original', referencedDeclaration=original['id'],
            typeDescriptions=original['typeDescriptions'])
        first = self.node('VariableDeclarationStatement', declarations=[original], initialValue=case['account']())
        case['capture']['initialValue'] = source
        self.fixture.function()['body']['statements'].insert(0, first)
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])

    def test_结构非payable入账仍不能证明资金可达(self):
        self.struct_case()
        self.funding['stateMutability'] = 'nonpayable'
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][-1]['stateMutability'] = 'nonpayable'
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertFalse(result['pathEvidence']['witness']['initialization']['funded'])

    def timestamp(self, *, old=False):
        if old:
            return self.node('Identifier', name='now', referencedDeclaration=-22,
                typeDescriptions={'typeIdentifier': 't_uint256'})
        return self.node('MemberAccess', memberName='timestamp', typeDescriptions={'typeIdentifier': 't_uint256'},
            expression=self.node('Identifier', name='block', referencedDeclaration=-21,
                typeDescriptions={'typeIdentifier': 't_magic_block'}))

    def time_case(self, *, old=False):
        last = self.node('VariableDeclaration', name='lastWithdrawTime', stateVariable=True,
            typeName=self.node('Mapping', keyType=self.node('ElementaryTypeName', name='address'),
                valueType=self.node('ElementaryTypeName', name='uint256')))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(last)
        def last_time():
            return self.node('IndexAccess', typeDescriptions={'typeIdentifier': 't_uint256'},
                baseExpression=self.node('Identifier', name='lastWithdrawTime', referencedDeclaration=last['id']),
                indexExpression=self.sender())
        period = self.number(1)
        period['subdenomination'] = 'weeks'
        condition = self.node('BinaryOperation', operator='>=', leftExpression=self.timestamp(old=old),
            rightExpression=self.node('BinaryOperation', operator='+', leftExpression=last_time(),
                rightExpression=period, typeDescriptions={'typeIdentifier': 't_uint256'}))
        self.fixture.function()['body']['statements'].insert(1, self.check(condition))
        self.fixture.function()['body']['statements'].append(self.assign(last_time(), self.timestamp(old=old)))
        return last

    def test_now加weeks保护可有限求值且默认时间槽可合法建态(self):
        self.time_case(old=True)
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertGreaterEqual(result['pathEvidence']['witness']['environment']['blockTimestamp'], 604800)

    def test_block_timestamp与now在同一调用共享时间值(self):
        self.time_case()
        self.fixture.function()['body']['statements'].insert(1, self.check(self.node('BinaryOperation',
            operator='==', leftExpression=self.timestamp(), rightExpression=self.timestamp(old=True))))
        self.assertEqual('COUNTEREXAMPLE', self.proof()['status'])

    def test_时间条件矛盾与无法求值仍保持未知(self):
        self.time_case()
        period = self.number(1)
        period['subdenomination'] = 'weeks'
        self.fixture.function()['body']['statements'].insert(1, self.check(self.node('BinaryOperation',
            operator='<', leftExpression=self.timestamp(), rightExpression=period)))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_同名用户时间变量不冒充编译内置时间(self):
        now = self.node('VariableDeclaration', name='now', stateVariable=False,
            typeDescriptions={'typeIdentifier': 't_uint256'})
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(now)
        self.fixture.function()['body']['statements'].insert(1, self.check(self.node('BinaryOperation',
            operator='>', leftExpression=self.node('Identifier', name='now', referencedDeclaration=now['id'],
                typeDescriptions={'typeIdentifier': 't_uint256'}), rightExpression=self.number(0))))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_源码常量超过uint范围不能产生正常整数见证(self):
        self.guard['expression']['arguments'][0]['rightExpression'] = self.number(2 ** 256 - 1)
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未验证非默认金额初值即使常量域覆盖也不能确认(self):
        limit = self.node('VariableDeclaration', name='limit', stateVariable=True,
            typeName=self.node('ElementaryTypeName', name='uint256'),
            typeDescriptions={'typeIdentifier': 't_uint256'}, value=self.number(1))
        limit['value']['subdenomination'] = 'ether'
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(limit)
        self.fixture.function()['body']['statements'].insert(1, self.check(self.node('BinaryOperation',
            operator='<=', leftExpression=self.credit(), rightExpression=self.node('Identifier',
                name='limit', referencedDeclaration=limit['id'], typeDescriptions=limit['typeDescriptions']))))
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertIn(10 ** 18, result['proofScope']['finiteSearch']['numericCandidates'])
        self.assertTrue(any('非默认初值' in gap for gap in result['proofScope']['gaps']))

    def test_有限枚举预算耗尽不能变为安全证明(self):
        from unittest.mock import patch
        with patch('verirag.analysis.reentrancy_proofs._MAX_ASSIGNMENTS', 1):
            result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(any('预算耗尽' in gap for gap in result['proofScope']['gaps']))

    def test_CALL前后同初始槽不重复枚举独立值(self):
        from unittest.mock import patch
        self.amount_case()
        self.time_case()
        with patch('verirag.analysis.reentrancy_proofs._MAX_ASSIGNMENTS', 500):
            result = self.proof(function='f(uint256)')
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertTrue(result['pathEvidence']['witness']['initialization']['funded'])

    def test_block_number支持非负数值比较(self):
        timestamp = self.timestamp()
        timestamp['memberName'] = 'number'
        self.fixture.function()['body']['statements'].insert(1, self.check(self.node('BinaryOperation',
            operator='>', leftExpression=timestamp, rightExpression=self.number(0))))
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        self.assertGreater(result['pathEvidence']['witness']['environment']['blockNumber'], 0)

    def test_区块环境负数布尔及越界值不能求值(self):
        from verirag.analysis.reentrancy_proofs import _value, _Unevaluated
        for name in ('block.timestamp', 'block.number'):
            term = ('builtin', name)
            for value in (-1, True, 2 ** 256):
                with self.subTest(name=name, value=value), self.assertRaises(_Unevaluated):
                    _value(term, {term: value}, {}, {}, {})

    def test_block_number与timestamp分别求值且矛盾分支保持未知(self):
        timestamp, number = self.timestamp(), self.timestamp()
        number['memberName'] = 'number'
        self.fixture.function()['body']['statements'].insert(1, self.check(self.node('BinaryOperation',
            operator='>', leftExpression=timestamp, rightExpression=number)))
        result = self.proof()
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        environment = result['pathEvidence']['witness']['environment']
        self.assertGreater(environment['blockTimestamp'], environment['blockNumber'])
        self.fixture.function()['body']['statements'].insert(1, self.check(self.node('BinaryOperation',
            operator='<', leftExpression=self.syntax.fresh(timestamp), rightExpression=self.number(0))))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def ir_aliases(self, case):
        """模拟独立工具收据中的引用事实，使用编译声明和真实字节跨度。"""
        from verirag.analysis.compiler_facts import source_span
        self.fixture.seal()
        bundle = self.fixture.load()
        result = []
        for function, local, capture in ((self.fixture.function(), case['withdrawal'], case['capture']),
                (self.funding, case['deposit'], self.funding['body']['statements'][0])):
            result.append({'declarationId': function['id'],
                'stateAccessCoverage': 'DIRECT_FUNCTION_OPERATIONS',
                'referenceBindings': [{'irKind': 'Assignment', 'definitionCount': 1,
                    'declarationId': local['id'], 'astNodeId': capture['initialValue']['id'],
                    'expressionSpan': source_span(capture['initialValue'], bundle['units']),
                    'bindingStatus': 'BOUND', 'rootDeclarationId': self.balance['id'],
                    'path': [{'kind': 'INDEX', 'key': {'bindingStatus': 'BOUND',
                        'value': {'kind': 'BUILTIN', 'name': 'msg.sender'}}}]}]})
        return result

    def test_IR引用与AST别名交叉核验且输出根key和字段(self):
        case = self.struct_case()
        result = self.proof(effect_summaries=self.ir_aliases(case))
        self.assertEqual('COUNTEREXAMPLE', result['status'])
        bindings = result['proofScope']['storageAliasBindings']
        binding = next(item for item in bindings if item['declarationId'] == case['withdrawal']['id'])
        self.assertEqual('AST_AND_SLITHIR', binding['basis'])
        self.assertEqual(self.balance['id'], binding['resource'][1])

    def test_同跨度索引定义与别名赋值分别绑定不互相制造歧义(self):
        case = self.struct_case()
        effects = self.ir_aliases(case)
        for summary in effects:
            summary['referenceBindings'].append(dict(summary['referenceBindings'][0], irKind='Index', declarationId=None))
        self.assertEqual('COUNTEREXAMPLE', self.proof(effect_summaries=effects)['status'])

    def test_IR别名错根错key多定义和未绑定状态阻止反例(self):
        case = self.struct_case()
        effects = self.ir_aliases(case)
        for field, value in (('rootDeclarationId', self.lock['id']), ('definitionCount', 2),
                ('bindingStatus', 'UNRESOLVED'), ('expressionSpan', {'sourceUnit': 'Wrong.sol', 'start': 0, 'length': 1}),
                ('path', [{'kind': 'INDEX', 'key': {'bindingStatus': 'BOUND',
                    'value': {'kind': 'BUILTIN', 'name': 'tx.origin'}}}])):
            changed = copy.deepcopy(effects)
            changed[0]['referenceBindings'][0][field] = value
            with self.subTest(field=field):
                result = self.proof(effect_summaries=changed)
                self.assertEqual('UNKNOWN', result['status'])
                self.assertTrue(any('SlithIR' in gap for gap in result['proofScope']['gaps']))

    def test_IR缺失别名证据不能由AST成功绑定掩盖(self):
        case = self.struct_case()
        effects = self.ir_aliases(case)
        effects[0]['referenceBindings'] = []
        self.assertEqual('UNKNOWN', self.proof(effect_summaries=effects)['status'])

    def helper(self, *, view=True):
        function = self.add_entry([], name='query')
        function['stateMutability'] = 'view' if view else 'nonpayable'
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][-1]['stateMutability'] = function['stateMutability']
        return self.node('FunctionCall', kind='functionCall', arguments=[],
            expression=self.node('MemberAccess', memberName='query', referencedDeclaration=function['id'],
                expression=self.busy(), typeDescriptions={'typeIdentifier':
                    't_function_external_view$__$returns$__$' if view else 't_function_external_nonpayable$__$returns$__$'}))

    def test_只读查询正常返回路径有条件见证而非直接丢弃(self):
        self.fixture.function()['body']['statements'].append(self.statement(self.helper()))
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertEqual('CONDITIONAL', result['pathEvidence']['status'])
        witness = result['pathEvidence']['witness']
        self.assertTrue(witness['normalExit'])
        self.assertEqual('READ_ONLY', witness['calls'][-1]['helperKind'])
        self.assertTrue(witness['externalCallConditions'])

    def test_已绑定非转账日志也保留实现正常返回与无回调前提(self):
        helper = self.helper(view=False)
        helper['arguments'] = [self.node('Literal', kind='string', value='Withdraw'), self.sender(), self.timestamp()]
        self.fixture.function()['body']['statements'].append(self.statement(helper))
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertEqual('CONDITIONAL', result['pathEvidence']['status'])
        self.assertEqual('AUXILIARY', result['pathEvidence']['witness']['calls'][-1]['helperKind'])

    def test_IR工具收据仅匹配后传入证明和展示图(self):
        from unittest.mock import patch
        from verirag.analysis.compiled_d2 import evaluate_compiled
        case = self.struct_case()
        effects = self.ir_aliases(case)
        self.fixture.seal()
        hypothesis = {'contract': 'C', 'function': 'f()', 'riskLine': 1,
            'riskOperation': 'CALL', 'vulnerabilityType': 'REENTRANCY'}
        for status in ('MATCH', 'UNKNOWN'):
            with self.subTest(status=status), patch('verirag.analysis.compiled_d2._tool_binding', return_value={
                    'status': status, 'receipts': [{'effectSummaries': effects}]}):
                result = evaluate_compiled(hypothesis, self.fixture.manifest, [], root=self.fixture.root)
            bindings = result['proofScope']['storageAliasBindings']
            self.assertEqual({'AST_AND_SLITHIR' if status == 'MATCH' else 'COMPILED_AST'},
                             {item['basis'] for item in bindings})

    def test_只读辅助调用后确定回滚不能生成正常退出见证(self):
        self.fixture.function()['body']['statements'].extend([
            self.statement(self.helper()), self.check(self.boolean(False))])
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertNotIn('witness', result['pathEvidence'])

    def test_旧view实际IR为CALL时保留无回调前提(self):
        from verirag.analysis.compiler_facts import source_span
        helper = self.helper()
        self.fixture.function()['body']['statements'].append(self.statement(helper))
        self.fixture.seal()
        effects = [{'declarationId': self.fixture.function()['id'], 'calls': [{
            'targetDeclarationId': helper['expression']['referencedDeclaration'],
            'expressionSpan': source_span(helper, self.fixture.load()['units']), 'semantics': 'CALL'}]}]
        result = self.proof(effect_summaries=effects)
        self.assertEqual('CONDITIONAL', result['pathEvidence']['status'])
        self.assertEqual('AUXILIARY', result['pathEvidence']['witness']['calls'][-1]['helperKind'])

    def test_顶层保留辅助调用条件见证且裁决未知(self):
        from verirag.analysis.compiled_d2 import evaluate_compiled
        self.fixture.function()['body']['statements'].append(self.statement(self.helper()))
        self.fixture.seal()
        fact = next(fact for fact in extract_compiler_facts(self.fixture.load())['facts']
                    if fact['nodeId'] == self.call['id'])
        result = evaluate_compiled({'contract': 'C', 'function': 'f()', 'riskLine': 1,
            'riskOperation': 'CALL', 'vulnerabilityType': 'REENTRANCY', 'riskFactId': fact['id']},
            self.fixture.manifest, [], root=self.fixture.root)
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('CONDITIONAL', result['pathEvidence']['status'])
        self.assertTrue(result['proofScope']['conditionedOnExternalCalls'])

    def test_辅助调用返回值没有求值语义时仍未知(self):
        self.fixture.function()['body']['statements'].append(self.check(self.helper()))
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertNotIn('witness', result['pathEvidence'])

    def test_日志调用名称不能替代真实正常返回绑定(self):
        external = self.node('FunctionCall', kind='functionCall', arguments=[],
            expression=self.node('MemberAccess', memberName='AddMessage',
                expression=self.busy(), typeDescriptions={'typeIdentifier': 't_function_external_nonpayable$__$returns$__$'}))
        self.fixture.function()['body']['statements'].append(self.statement(external))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_结构入账日志未绑定仍不能证明资金建态(self):
        self.struct_case()
        external = self.node('FunctionCall', kind='functionCall', arguments=[],
            expression=self.node('MemberAccess', memberName='AddMessage',
                expression=self.busy(), typeDescriptions={'typeIdentifier': 't_function_external_nonpayable$__$returns$__$'}))
        self.funding['body']['statements'].append(self.statement(external))
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertFalse(result['pathEvidence']['witness']['initialization']['funded'])


if __name__ == '__main__':
    unittest.main()
