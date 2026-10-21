"""候选相关权限闭包的反驳证明；合成 AST 只验证证明规则。"""
import copy
import unittest

import test_compiled_d2 as syntax_fixtures
from verirag.analysis.compiler_facts import extract_compiler_facts
from verirag.analysis.candidate_proofs import prove_candidate


class CandidateProofTest(unittest.TestCase):
    def setUp(self):
        self.syntax = syntax_fixtures.CompiledD2Test()
        self.syntax.setUp()
        self.addCleanup(self.syntax.doCleanups)
        self.fixture = self.syntax.fixture

    def proof(self, *, risk_expression=None, **changes):
        self.fixture.seal()
        bundle = self.fixture.load()
        assignment = risk_expression or self.fixture.function()['body']['statements'][-1]['expression']
        risk = next(f for f in extract_compiler_facts(bundle)['facts'] if f['nodeId'] == assignment['id'])
        hypothesis = {'contract': 'C', 'function': 'f()', 'vulnerabilityType': 'ACCESS_CONTROL',
                      'riskOperation': 'WRITE', 'riskLine': 1, 'riskFactId': risk['id'], **changes}
        return prove_candidate(bundle, hypothesis)

    def add_entry(self, name, statements, *, view=False):
        function = self.syntax.fresh(self.fixture.function())
        function.update(name=name, body=self.syntax.node('Block', statements=statements),
                        stateMutability='view' if view else 'nonpayable')
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(function)
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'function', 'name': name, 'inputs': [], 'outputs': [],
             'stateMutability': function['stateMutability']})
        return function

    def test_同主体同版本保护给出完整反驳证据(self):
        result = self.proof()
        self.assertEqual('PROVED', result['status'])
        self.assertEqual('REFUTATION', result['proofKind'])
        self.assertTrue(result['proofScope']['complete'])
        self.assertEqual({'SUPPORTED'}, {item['status'] for item in result['obligations']})
        self.assertEqual('BLOCKED', result['pathEvidence']['status'])
        self.assertTrue(result['authorityClosure'])
        self.assertTrue(result['references'])

    def test_权限写入两行漂移绑定保留原候选而窗口外拒绝(self):
        result = self.proof(riskLine=3)
        self.assertEqual('PROVED', result['status'])
        self.assertEqual(3, result['riskBinding']['originalLine'])
        self.assertEqual(1, result['riskBinding']['boundLine'])
        self.assertEqual('FAILED', self.proof(riskLine=4)['status'])

    def test_裸比较不能产生反驳证明(self):
        guard = self.fixture.function()['body']['statements'][0]
        guard['expression'] = guard['expression']['arguments'][0]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_旧编译AST无括号修饰器的null实参等价于无实参(self):
        guard, write = self.fixture.function()['body']['statements']
        modifier = self.syntax.node('ModifierDefinition', name='onlyRole',
            parameters=self.syntax.node('ParameterList', parameters=[]),
            body=self.syntax.node('Block', statements=[guard, self.syntax.node('PlaceholderStatement')]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(modifier)
        self.fixture.function()['body']['statements'] = [write]
        self.fixture.function()['modifiers'] = [self.syntax.node('ModifierInvocation', arguments=None,
            modifierName=self.syntax.node('Identifier', name='onlyRole', referencedDeclaration=modifier['id']))]
        result = self.proof()
        self.assertEqual('PROVED', result['status'])
        self.assertTrue(result['proofScope']['complete'])
        self.assertEqual({'SUPPORTED'}, {item['status'] for item in result['obligations']})

    def test_未保护权限_setter_使候选未知(self):
        write = self.syntax.fresh(self.fixture.function()['body']['statements'][1])
        self.add_entry('set', [write])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_仅一次未保护初始化仍是权限绕过缺口(self):
        write = self.syntax.fresh(self.fixture.function()['body']['statements'][1])
        self.add_entry('initialize', [write])
        result = self.proof(proofScope={'complete': True}, initialization={'initialized': True})
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(result['proofScope']['gaps'])

    def test_只保护一侧分支不能反驳(self):
        guard, write = self.fixture.function()['body']['statements']
        self.fixture.function()['body']['statements'] = [self.syntax.node('IfStatement',
            condition=self.syntax.node('Literal', kind='bool', value='true'), trueBody=guard, falseBody=None), write]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_风险前权限版本变化使旧检查失效(self):
        guard, write = self.fixture.function()['body']['statements']
        self.fixture.function()['body']['statements'] = [guard, self.syntax.fresh(write), write]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_风险前未覆盖语义不能从切片移除(self):
        self.fixture.function()['body']['statements'].insert(1, self.syntax.node('WhileStatement'))
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未知汇编可能写权限使全入口覆盖失败(self):
        self.add_entry('unrelatedName', [self.syntax.node('InlineAssembly')])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_无状态效果的其他入口不引入候选缺口(self):
        # 完整 AST 盘点证明循环只读取参数或字面量，不凭函数名称排除入口。
        self.add_entry('administrativeLookingName', [self.syntax.node('ForStatement',
            body=self.syntax.node('Block', statements=[]))], view=True)
        result = self.proof()
        self.assertEqual('PROVED', result['status'])
        other = next(item for item in result['proofScope']['entries'] if item['signature'] == 'administrativeLookingName()')
        self.assertFalse(other['related'])

    def test_未调用内部未保护函数不构成运行入口(self):
        internal = self.syntax.fresh(self.fixture.function())
        internal.update(name='hidden', visibility='internal')
        internal['body']['statements'].pop(0)
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(internal)
        self.assertEqual('PROVED', self.proof()['status'])

    def test_委派主体自身可被未保护入口改写则未知(self):
        contract = self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        delegate = self.syntax.node('VariableDeclaration', name='arbitraryRole', stateVariable=True,
            visibility='private', typeName=self.syntax.node('ElementaryTypeName', name='address'),
            typeDescriptions={'typeIdentifier': 't_address'})
        contract['nodes'].append(delegate)
        guard, write = [self.syntax.fresh(item) for item in self.fixture.function()['body']['statements']]
        guard['expression']['arguments'][0]['rightExpression']['referencedDeclaration'] = delegate['id']
        self.add_entry('delegate', [guard, write])
        unprotected = self.syntax.fresh(write)
        unprotected['expression']['leftHandSide']['referencedDeclaration'] = delegate['id']
        self.add_entry('resetDelegate', [unprotected])
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(any(str(delegate['id']) in gap for gap in result['proofScope']['gaps']))

    def test_完整函数签名错绑失败(self):
        self.assertEqual('FAILED', self.proof(functionSignature='other()')['status'])

    def test_未验证人工_bundle_不能产生证明(self):
        self.fixture.seal()
        bundle = self.fixture.load()
        bundle['verificationStatus'] = 'MANUALLY_ASSERTED'
        result = prove_candidate(bundle, {'contract': 'C', 'function': 'f()',
            'vulnerabilityType': 'ACCESS_CONTROL', 'riskOperation': 'WRITE', 'riskLine': 1})
        self.assertEqual('FAILED', result['status'])

    def test_非权限机制保持未知(self):
        self.assertEqual('UNKNOWN', self.proof(vulnerabilityType='REENTRANCY')['status'])

    def test_事件无直接存储效果但仍遍历参数(self):
        event = self.syntax.node('EventDefinition', name='UnrelatedEvent',
            parameters=self.syntax.node('ParameterList', parameters=[]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(event)
        emit = self.syntax.node('EmitStatement', eventCall=self.syntax.node('FunctionCall',
            kind='functionCall', arguments=[], expression=self.syntax.node('Identifier',
            name='UnrelatedEvent', referencedDeclaration=event['id'],
            typeDescriptions={'typeIdentifier': 't_function_event_nonpayable$__$returns$__$'})))
        self.add_entry('emitOnly', [emit])
        self.assertEqual('PROVED', self.proof()['status'])

    def test_内存数组分配不冒充合约部署(self):
        allocation = self.syntax.node('FunctionCall', kind='functionCall',
            arguments=[self.syntax.node('Literal', kind='number', value='1')],
            expression=self.syntax.node('NewExpression', typeName=self.syntax.node('ArrayTypeName',
                baseType=self.syntax.node('ElementaryTypeName', name='uint256'), length=None)))
        self.add_entry('allocate', [self.syntax.node('ExpressionStatement', expression=allocation)], view=True)
        self.assertEqual('PROVED', self.proof()['status'])

    def test_汇编仅内存写入可排除但_sstore_保留缺口(self):
        def assembly(operation):
            return self.syntax.node('InlineAssembly', AST={'nodeType': 'YulBlock', 'src': '0:1:0',
                'statements': [{'nodeType': 'YulExpressionStatement', 'src': '0:1:0',
                'expression': {'nodeType': 'YulFunctionCall', 'src': '0:1:0',
                    'functionName': {'nodeType': 'YulIdentifier', 'src': '0:1:0', 'name': operation},
                    'arguments': []}}]})
        entry = self.add_entry('assemblyAction', [assembly('mstore')])
        self.assertEqual('PROVED', self.proof()['status'])
        entry['body']['statements'] = [assembly('sstore')]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_动态数组_push_未证明物理隔离不能仅按声明根排除(self):
        storage = self.syntax.node('VariableDeclaration', name='unrelatedArray', stateVariable=True,
            visibility='private', typeName=self.syntax.node('ArrayTypeName',
                baseType=self.syntax.node('ElementaryTypeName', name='uint256'), length=None))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(storage)
        push = self.syntax.node('FunctionCall', kind='functionCall',
            arguments=[self.syntax.node('Literal', kind='number', value='1')],
            expression=self.syntax.node('MemberAccess', memberName='push',
                expression=self.syntax.node('Identifier', name='unrelatedArray', referencedDeclaration=storage['id']),
                typeDescriptions={'typeIdentifier': 't_function_arraypush_nonpayable$_t_uint256_$returns$__$'}))
        self.add_entry('changeArray', [self.syntax.node('ExpressionStatement', expression=push)])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未知语句不冒充无状态效果(self):
        self.add_entry('futureSyntax', [self.syntax.node('UnknownStorageEffectStatement')])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_未知_Yul_节点不能通过空操作清单(self):
        self.add_entry('futureAssembly', [self.syntax.node('InlineAssembly',
            AST={'nodeType': 'YulUnknownStorageAction', 'src': '0:1:0'})])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_候选源码摘要错绑失败(self):
        self.assertEqual('FAILED', self.proof(sourceHash='0' * 64)['status'])

    def test_原有短函数名与完整签名兼容(self):
        self.assertEqual('PROVED', self.proof(function='f', functionSignature='f()')['status'])

    def test_历史唯一短函数名也绑定实际签名(self):
        self.assertEqual('PROVED', self.proof(function='f')['status'])

    def test_历史短函数名遇到重载仍保持未知(self):
        overloaded = self.add_entry('f', [])
        parameter = self.syntax.node('VariableDeclaration', name='value', stateVariable=False,
            typeName=self.syntax.node('ElementaryTypeName', name='uint256'))
        overloaded['parameters']['parameters'] = [parameter]
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][-1]['inputs'] = [
            {'name': 'value', 'type': 'uint256'}]
        self.assertEqual('UNKNOWN', self.proof(function='f')['status'])

    def test_修饰器实参权限写入必须计入入口闭包(self):
        parameter = self.syntax.node('VariableDeclaration', name='input', stateVariable=False,
            typeName=self.syntax.node('ElementaryTypeName', name='address'))
        modifier = self.syntax.node('ModifierDefinition', name='passThrough',
            parameters=self.syntax.node('ParameterList', parameters=[parameter]),
            body=self.syntax.node('Block', statements=[self.syntax.node('PlaceholderStatement')]))
        contract = self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        contract['nodes'].append(modifier)
        entry = self.add_entry('argumentEffects', [])
        argument = self.syntax.fresh(self.fixture.function()['body']['statements'][1]['expression'])
        entry['modifiers'] = [self.syntax.node('ModifierInvocation', arguments=[argument],
            modifierName=self.syntax.node('IdentifierPath', name='passThrough',
                referencedDeclaration=modifier['id']))]
        result = self.proof()
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(any('argumentEffects' in gap for gap in result['proofScope']['gaps']))

    def test_修饰器返回续接未证明不能称范围完整(self):
        guard, write = self.fixture.function()['body']['statements']
        modifier = self.syntax.node('ModifierDefinition', name='guarded',
            parameters=self.syntax.node('ParameterList', parameters=[]),
            body=self.syntax.node('Block', statements=[guard, self.syntax.node('PlaceholderStatement')]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(modifier)
        self.fixture.function()['modifiers'] = [self.syntax.node('ModifierInvocation', arguments=[],
            modifierName=self.syntax.node('IdentifierPath', name='guarded', referencedDeclaration=modifier['id']))]
        self.fixture.function()['body']['statements'] = [write, self.syntax.node('Return', expression=None)]
        result = self.proof(risk_expression=write['expression'])
        self.assertEqual('UNKNOWN', result['status'])
        self.assertTrue(any('return 续接' in gap for gap in result['proofScope']['gaps']))

    def test_相关入口修饰器多次续接不能称范围完整(self):
        guard, write = [self.syntax.fresh(item) for item in self.fixture.function()['body']['statements']]
        modifier = self.syntax.node('ModifierDefinition', name='repeatBody',
            parameters=self.syntax.node('ParameterList', parameters=[]),
            body=self.syntax.node('Block', statements=[self.syntax.node('PlaceholderStatement'),
                self.syntax.node('PlaceholderStatement')]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(modifier)
        other = self.add_entry('repeatedGuard', [guard, write])
        other['modifiers'] = [self.syntax.node('ModifierInvocation', arguments=[], modifierName=self.syntax.node(
            'IdentifierPath', name='repeatBody', referencedDeclaration=modifier['id']))]
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_fallback_receive_权限写入与普通入口同等核验(self):
        for kind in ('fallback', 'receive'):
            with self.subTest(kind=kind):
                write = self.syntax.fresh(self.fixture.function()['body']['statements'][1])
                entry = self.add_entry('callback', [write])
                entry.update(kind=kind, name='', stateMutability='payable')
                abi = self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][-1]
                abi.clear()
                abi.update(type=kind, stateMutability='payable')
                result = self.proof()
                self.assertEqual('UNKNOWN', result['status'])
                self.assertTrue(any(item['signature'] == kind + '()' and item['related']
                    for item in result['proofScope']['entries']))
                self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].remove(entry)
                self.fixture.output['contracts']['contracts/C.sol']['C']['abi'].remove(abi)

    def test_交易来源不能冒充实际调用主体(self):
        sender = self.fixture.function()['body']['statements'][0]['expression']['arguments'][0]['leftExpression']
        sender['memberName'] = 'origin'
        sender['expression'].update(name='tx', referencedDeclaration=-16,
            typeDescriptions={'typeIdentifier': 't_magic_transaction'})
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_风险行号布尔值不能作为整数(self):
        self.assertEqual('FAILED', self.proof(riskLine=True)['status'])

    def test_事件参数权限写入不能遗漏(self):
        parameter = self.syntax.node('VariableDeclaration', name='addressValue', stateVariable=False,
            typeName=self.syntax.node('ElementaryTypeName', name='address'))
        event = self.syntax.node('EventDefinition', name='Record', parameters=self.syntax.node('ParameterList', parameters=[parameter]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(event)
        argument = self.syntax.fresh(self.fixture.function()['body']['statements'][1]['expression'])
        emit = self.syntax.node('EmitStatement', eventCall=self.syntax.node('FunctionCall',
            kind='functionCall', arguments=[argument], expression=self.syntax.node('Identifier',
            name='Record', referencedDeclaration=event['id'], typeDescriptions={'typeIdentifier': 't_function_event_nonpayable$_t_address_$returns$__$'})))
        self.add_entry('emitWithSideEffect', [emit])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def storage_library(self):
        """使用实际 storage 形参结构构造静态内部库方法，名称不参与规则。"""
        contract = self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        array_type = lambda: self.syntax.node('ArrayTypeName',
            baseType=self.syntax.node('ElementaryTypeName', name='uint256'), length=None)
        storage = self.syntax.node('VariableDeclaration', name='records', stateVariable=True,
            visibility='private', typeName=array_type())
        parameter = self.syntax.node('VariableDeclaration', name='storageInput', stateVariable=False,
            storageLocation='storage', typeName=array_type())
        access = lambda declaration: self.syntax.node('IndexAccess',
            baseExpression=self.syntax.node('Identifier', name='data', referencedDeclaration=declaration),
            indexExpression=self.syntax.node('Literal', kind='number', value='0'))
        assignment = self.syntax.node('Assignment', operator='+=', leftHandSide=access(parameter['id']),
            rightHandSide=self.syntax.node('Literal', kind='number', value='1'))
        method = self.syntax.node('FunctionDefinition', name='mutate', kind='function',
            visibility='internal', stateMutability='nonpayable',
            parameters=self.syntax.node('ParameterList', parameters=[parameter]),
            returnParameters=self.syntax.node('ParameterList', parameters=[]), modifiers=[],
            body=self.syntax.node('Block', statements=[self.syntax.node('UncheckedBlock',
                statements=[self.syntax.node('ExpressionStatement', expression=assignment)])]))
        library = self.syntax.node('ContractDefinition', name='ArbitraryLibrary', contractKind='library',
            nodes=[method], linearizedBaseContracts=[])
        library['linearizedBaseContracts'] = [library['id']]
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'].append(library)
        contract['nodes'].append(storage)
        call = self.syntax.node('FunctionCall', kind='functionCall', arguments=[],
            expression=self.syntax.node('MemberAccess', memberName='mutate', referencedDeclaration=method['id'],
                expression=self.syntax.node('Identifier', name='records', referencedDeclaration=storage['id']),
                typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$_t_array$_t_uint256_$dyn_storage_ptr_$returns$__$bound_to$_t_array$_t_uint256_$dyn_storage_ptr_$'}))
        return storage, call, access

    def test_storage_库动态数组_receiver_缺物理隔离不能完整证明(self):
        _, call, _ = self.storage_library()
        self.fixture.function()['body']['statements'].insert(1, self.syntax.node('ExpressionStatement', expression=call))
        proof = self.proof()
        self.assertEqual('UNKNOWN', proof['status'])
        self.assertTrue(any('物理分离' in gap for gap in proof['proofScope']['gaps']))

    def test_storage_库未保护同风险根不能排除(self):
        storage, call, access = self.storage_library()
        self.fixture.function()['body']['statements'][-1]['expression']['leftHandSide'] = access(storage['id'])
        self.fixture.function()['body']['statements'][-1]['expression']['rightHandSide'] = self.syntax.node('Literal', kind='number', value='1')
        self.add_entry('unprotectedLibraryEntry', [self.syntax.node('ExpressionStatement', expression=call)])
        self.assertEqual('UNKNOWN', self.proof()['status'])

    def test_外部_CALL_位于权限检查与写入之间不得维持旧版本(self):
        remote = self.syntax.node('FunctionDefinition', name='invoke', kind='function', visibility='external',
            stateMutability='nonpayable', parameters=self.syntax.node('ParameterList', parameters=[]),
            returnParameters=self.syntax.node('ParameterList', parameters=[]), modifiers=[], body=None)
        interface = self.syntax.node('ContractDefinition', name='Remote', contractKind='interface',
            linearizedBaseContracts=[], nodes=[remote])
        interface['linearizedBaseContracts'] = [interface['id']]
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'].append(interface)
        call = self.syntax.node('FunctionCall', kind='functionCall', arguments=[], expression=self.syntax.node('MemberAccess',
            memberName='invoke', referencedDeclaration=remote['id'],
            expression=self.syntax.node('Identifier', name='owner', referencedDeclaration=2),
            typeDescriptions={'typeIdentifier': 't_function_external_nonpayable$__$returns$__$'}))
        self.fixture.function()['body']['statements'].insert(1, self.syntax.node('ExpressionStatement', expression=call))
        self.assertEqual('UNKNOWN', self.proof()['status'])


if __name__ == '__main__':
    unittest.main()
