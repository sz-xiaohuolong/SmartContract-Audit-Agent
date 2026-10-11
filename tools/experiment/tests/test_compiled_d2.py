"""编译 D2 的有限控制流与保守边界；合成 AST 不代表真实漏洞。"""
import copy
import unittest

import test_compiler_facts as fixtures
from compiler_facts import extract_compiler_facts
from compiled_d2 import evaluate_compiled


class CompiledD2Test(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompilerFactsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.counter = 100

    def node(self, node_type, **fields):
        self.counter += 1
        return dict(nodeType=node_type, id=self.counter, src='0:1:0', **fields)

    def fresh(self, value):
        value = copy.deepcopy(value)
        def update(item):
            if isinstance(item, dict):
                if 'nodeType' in item:
                    self.counter += 1
                    item['id'] = self.counter
                for child in item.values(): update(child)
            elif isinstance(item, list):
                for child in item: update(child)
        update(value)
        return value

    def function(self):
        return self.fixture.function()

    def run_case(self, **fields):
        self.fixture.seal()
        hypothesis = {'contract': 'C', 'function': 'f()', 'riskLine': 1,
                      'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL', **fields}
        bundle = self.fixture.load()
        tools = [{'engine': 'SLITHER', 'status': 'OK', 'issues': [], 'sourceHash': bundle['sourceHash']}]
        # 合成运行对象仅测试绑定缺口，不能手填编译摘要冒充真实工具收据。
        return evaluate_compiled(hypothesis, self.fixture.manifest, tools, root=self.fixture.root)

    def obligation(self, result, name):
        return next(o for o in result['obligations'] if o['name'] == name)['status']

    def test_guarded_write_has_real_dominance_and_complete_six_obligations(self):
        result = self.run_case()
        self.assertEqual('BLOCKED', result['localPathEvidence']['status'])
        self.assertEqual('BLOCKED', result['pathEvidence']['status'])
        self.assertTrue(result['proofScope']['complete'])
        self.assertEqual({'SUPPORTED'}, {o['status'] for o in result['obligations']})
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('TOOL_ENVIRONMENT_BINDING', result['toolBinding']['errorCategory'])
        self.assertTrue(any(e['kind'] == 'abort' for e in result['cfg']['edges']))

    def test_bare_comparison_is_not_guard_or_feasible_witness(self):
        statement = self.function()['body']['statements'][0]
        statement['expression'] = statement['expression']['arguments'][0]
        result = self.run_case()
        self.assertEqual('REACHABLE', result['localPathEvidence']['status'])
        self.assertEqual('REFUTED', self.obligation(result, 'pre_risk_guard'))
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertFalse(any(n['kind'] == 'CHECK' for n in result['cfg']['nodes']))

    def test_guard_in_only_one_branch_does_not_dominate_write(self):
        guard, write = self.function()['body']['statements']
        condition = self.node('Literal', kind='bool', value='true', typeDescriptions={'typeIdentifier': 't_bool'})
        # 未进行常量优化也必须保守；存在未检查分支就不能补全保护。
        branch = self.node('IfStatement', condition=condition, trueBody=guard, falseBody=None)
        self.function()['body']['statements'] = [branch, write]
        result = self.run_case()
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertNotEqual('SUPPORTED', self.obligation(result, 'pre_risk_guard'))

    def test_false_branch_revert_provides_guard_without_guard_name(self):
        guard, write = self.function()['body']['statements']
        condition = guard['expression']['arguments'][0]
        abort = self.node('RevertStatement', errorCall=None)
        self.function()['body']['statements'] = [self.node('IfStatement', condition=condition,
                                                        trueBody=None, falseBody=abort), write]
        result = self.run_case()
        self.assertEqual('BLOCKED', result['localPathEvidence']['status'])

    def test_late_guard_does_not_prove_committed_vulnerability(self):
        self.function()['body']['statements'].reverse()
        result = self.run_case()
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertNotEqual('BLOCKED', result['pathEvidence']['status'])

    def test_intervening_authority_write_invalidates_state_version(self):
        guard, write = self.function()['body']['statements']
        second = self.fresh(write)
        self.function()['body']['statements'] = [guard, second, write]
        result = self.run_case(riskFactId=next(f['id'] for f in extract_compiler_facts(
            self._sealed_bundle())['facts'] if f['nodeId'] == write['expression']['id']))
        self.assertEqual('REFUTED', self.obligation(result, 'state_version'))
        self.assertEqual('UNKNOWN', result['verdict'])

    def _sealed_bundle(self):
        self.fixture.seal()
        return self.fixture.load()

    def test_unguarded_public_setter_prevents_entry_coverage(self):
        setter = self.fresh(self.function())
        setter.update(name='set', parameters=self.node('ParameterList', parameters=[]),
                      returnParameters=self.node('ParameterList', parameters=[]))
        setter['body']['statements'] = setter['body']['statements'][1:]
        ast = self.fixture.output['sources']['contracts/C.sol']['ast']
        ast['nodes'][0]['nodes'].append(setter)
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'function', 'name': 'set', 'inputs': [], 'outputs': [], 'stateMutability': 'nonpayable'})
        result = self.run_case()
        self.assertEqual('BLOCKED', result['localPathEvidence']['status'])
        self.assertEqual('UNKNOWN', self.obligation(result, 'entry_coverage'))
        self.assertEqual('UNKNOWN', result['pathEvidence']['status'])

    def test_binding_drift_and_injected_scope_are_not_trusted(self):
        self.fixture.seal()
        (self.fixture.root / 'output.json').write_bytes(b'{}')
        result = evaluate_compiled({'contract': 'C', 'function': 'f()', 'riskLine': 1,
                                    'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL',
                                    'proofScope': {'complete': True}}, self.fixture.manifest, [], root=self.fixture.root)
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('FAILED', result['status'])

    def test_loops_assembly_and_storage_alias_are_gaps(self):
        for kind in ['ForStatement', 'InlineAssembly', 'WhileStatement']:
            with self.subTest(kind=kind):
                self.function()['body']['statements'].append(self.node(kind))
                result = self.run_case()
                self.assertFalse(result['proofScope']['complete'])
                self.assertTrue(any(kind in gap for gap in result['proofScope']['gaps']))
                self.assertEqual('UNKNOWN', result['verdict'])
                self.function()['body']['statements'].pop()

    def test_modifier_continuation_preserves_post_guard(self):
        guard, write = self.function()['body']['statements']
        modifier = self.node('ModifierDefinition', name='arbitrary', parameters=self.node('ParameterList', parameters=[]),
                             body=self.node('Block', statements=[self.node('PlaceholderStatement'), guard]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(modifier)
        self.function()['body']['statements'] = [write]
        self.function()['modifiers'] = [self.node('ModifierInvocation', modifierName=self.node(
            'IdentifierPath', name='arbitrary', referencedDeclaration=modifier['id']))]
        result = self.run_case()
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertNotEqual('SUPPORTED', self.obligation(result, 'pre_risk_guard'))
        self.assertTrue(any(n['kind'] == 'CHECK' for n in result['cfg']['nodes']))

    def test_modifier_prefix_guard_blocks_and_multiple_placeholders_are_gap(self):
        guard, write = self.function()['body']['statements']
        modifier = self.node('ModifierDefinition', name='arbitrary', parameters=self.node('ParameterList', parameters=[]),
                             body=self.node('Block', statements=[guard, self.node('PlaceholderStatement')]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(modifier)
        self.function()['body']['statements'] = [write]
        self.function()['modifiers'] = [self.node('ModifierInvocation', modifierName=self.node(
            'IdentifierPath', name='arbitrary', referencedDeclaration=modifier['id']))]
        self.assertEqual('BLOCKED', self.run_case()['localPathEvidence']['status'])
        modifier['body']['statements'].append(self.node('PlaceholderStatement'))
        self.assertFalse(self.run_case()['proofScope']['complete'])

    def test_missing_tool_or_wrong_binding_cannot_be_completed(self):
        self.fixture.seal()
        hypothesis = {'contract': 'C', 'function': 'f()', 'riskLine': 1,
                      'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL'}
        for tools in [[], [{'status': 'OK', 'issues': [], 'sourceHash': 'wrong'}], [{'status': 'TIMEOUT'}],
                      [{'status': 'OK', 'issues': [], 'sourceHash': self.fixture.load()['sourceHash'],
                        'environmentHash': self.fixture.load()['environmentHash']}]]:
            result = evaluate_compiled(hypothesis, self.fixture.manifest, tools, root=self.fixture.root)
            self.assertEqual('BLOCKED', result['localPathEvidence']['status'])
            self.assertEqual('UNKNOWN', result['verdict'])

    def mapping_case(self, *, write_first=True, different_field=False, different_key=False, prior_call=False):
        """构造同 key struct 锁与真实声明绑定的内部 getter/外部调用结构。"""
        contract = self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        boolean = lambda: self.node('ElementaryTypeName', name='bool')
        field = self.node('VariableDeclaration', name='closed', stateVariable=False, typeName=boolean())
        alternate = self.node('VariableDeclaration', name='other', stateVariable=False, typeName=boolean())
        structure = self.node('StructDefinition', name='Flags', members=[field, alternate])
        mapping = self.node('VariableDeclaration', name='flags', stateVariable=True, visibility='private',
            typeName=self.node('Mapping', keyType=self.node('ElementaryTypeName', name='bytes32'),
            valueType=self.node('UserDefinedTypeName', namePath='Flags', referencedDeclaration=structure['id'])))
        parameter = self.node('VariableDeclaration', name='key', stateVariable=False,
                              typeName=self.node('ElementaryTypeName', name='bytes32'))
        other_parameter = self.node('VariableDeclaration', name='otherKey', stateVariable=False,
                                    typeName=self.node('ElementaryTypeName', name='bytes32'))
        def resource(key_id, member_id=field['id']):
            return self.node('MemberAccess', referencedDeclaration=member_id, memberName='closed',
                typeDescriptions={'typeIdentifier': 't_bool'}, expression=self.node('IndexAccess',
                baseExpression=self.node('Identifier', name='flags', referencedDeclaration=mapping['id']),
                indexExpression=self.node('Identifier', name='key', referencedDeclaration=key_id)))
        getter_parameter = self.node('VariableDeclaration', name='sameName', stateVariable=False,
                                     typeName=self.node('ElementaryTypeName', name='bytes32'))
        getter = self.node('FunctionDefinition', name='readFlag', kind='function', visibility='public',
            stateMutability='view', parameters=self.node('ParameterList', parameters=[getter_parameter]),
            returnParameters=self.node('ParameterList', parameters=[self.node('VariableDeclaration', name='',
            stateVariable=False, typeName=boolean())]), modifiers=[],
            body=self.node('Block', statements=[self.node('Return', expression=resource(getter_parameter['id']))]))
        call_getter = self.node('FunctionCall', kind='functionCall', arguments=[self.node(
            'Identifier', name='key', referencedDeclaration=parameter['id'])], expression=self.node('Identifier',
            name='readFlag', referencedDeclaration=getter['id'],
            typeDescriptions={'typeIdentifier': 't_function_internal_view$_t_bytes32_$returns$_t_bool_$'}))
        guard = self.node('ExpressionStatement', expression=self.node('FunctionCall', kind='functionCall',
            arguments=[self.node('UnaryOperation', operator='!', subExpression=call_getter)],
            expression=self.node('Identifier', name='require', referencedDeclaration=-18,
            typeDescriptions={'typeIdentifier': 't_function_require_pure$_t_bool_$returns$__$'})))
        external = self.node('FunctionDefinition', name='invoke', kind='function', visibility='external',
            stateMutability='nonpayable', parameters=self.node('ParameterList', parameters=[]),
            returnParameters=self.node('ParameterList', parameters=[self.node('VariableDeclaration', name='',
            stateVariable=False, typeName=boolean())]), body=None, modifiers=[])
        external_contract = self.node('ContractDefinition', name='Remote', contractKind='interface',
                                      linearizedBaseContracts=[], nodes=[external])
        external_contract['linearizedBaseContracts'] = [external_contract['id']]
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'].append(external_contract)
        call = self.node('FunctionCall', kind='functionCall', arguments=[], expression=self.node('MemberAccess',
            memberName='invoke', referencedDeclaration=external['id'],
            expression=self.node('Identifier', name='owner', referencedDeclaration=2),
            typeDescriptions={'typeIdentifier': 't_function_external_nonpayable$__$returns$_t_bool_$'}))
        transfer = self.node('ExpressionStatement', expression=self.node('FunctionCall', kind='functionCall',
            arguments=[call], expression=self.node('Identifier', name='require', referencedDeclaration=-18,
            typeDescriptions={'typeIdentifier': 't_function_require_pure$_t_bool_$returns$__$'})))
        write = self.node('ExpressionStatement', expression=self.node('Assignment', operator='=',
            leftHandSide=resource(other_parameter['id'] if different_key else parameter['id'],
                alternate['id'] if different_field else field['id']),
            rightHandSide=self.node('Literal', kind='bool', value='true', typeDescriptions={'typeIdentifier': 't_bool'})))
        parameters = [parameter, other_parameter] if different_key else [parameter]
        self.function()['parameters'] = self.node('ParameterList', parameters=parameters)
        self.function()['body']['statements'] = [guard] + ([write, transfer] if write_first else [transfer, write])
        earlier = None
        if prior_call:
            earlier = self.fresh(call)
            self.function()['body']['statements'].insert(1, self.node('ExpressionStatement', expression=earlier))
        contract['nodes'].extend([structure, mapping, getter])
        abi = self.fixture.output['contracts']['contracts/C.sol']['C']['abi']
        abi[0]['inputs'] = [{'type': 'bytes32'} for _ in parameters]
        abi.append({'type': 'function', 'name': 'readFlag', 'inputs': [{'type': 'bytes32'}],
                    'outputs': [{'type': 'bool'}], 'stateMutability': 'view'})
        self.fixture.seal()
        facts = extract_compiler_facts(self.fixture.load())
        risk_id = next(f['id'] for f in facts['facts'] if f['nodeId'] == call['id'])
        return {'function': 'f(' + ','.join('bytes32' for _ in parameters) + ')', 'riskOperation': 'CALL',
                'vulnerabilityType': 'REENTRANCY', 'riskFactId': risk_id}, earlier, mapping['id'], field['id']

    def test_internal_getter_key_and_struct_member_lock_before_or_after_call(self):
        fields, _, mapping_id, member_id = self.mapping_case(write_first=True)
        result = self.run_case(**fields)
        self.assertEqual('BLOCKED', result['localPathEvidence']['status'])
        self.assertEqual('UNKNOWN', result['pathEvidence']['status'])
        self.assertEqual('UNKNOWN', result['verdict'])
        writes = [n for n in result['cfg']['nodes'] if n['kind'] == 'WRITE']
        self.assertEqual(mapping_id, writes[0]['resource'][1])
        self.assertIn(['member', member_id], writes[0]['resource'][2])
        self.function()['body']['statements'][1:3] = reversed(self.function()['body']['statements'][1:3])
        fields['riskFactId'] = next(f['id'] for f in extract_compiler_facts(self._sealed_bundle())['facts']
                                   if f['nodeId'] == result['riskBinding']['nodeId'])
        result = self.run_case(**fields)
        self.assertEqual('REACHABLE', result['localPathEvidence']['status'])
        self.assertEqual('UNKNOWN', result['verdict'])

    def test_different_mapping_key_or_struct_field_cannot_supply_same_lock(self):
        for option in ['different_key', 'different_field']:
            with self.subTest(option=option):
                self.setUp()
                fields, _, _, _ = self.mapping_case(**{option: True})
                result = self.run_case(**fields)
                self.assertNotEqual('BLOCKED', result['localPathEvidence']['status'])
                self.assertNotEqual('SUPPORTED', self.obligation(result, 'state_version'))

    def test_require_argument_call_is_before_check_and_prior_window_stays_unknown(self):
        fields, earlier, _, _ = self.mapping_case(prior_call=True)
        result = self.run_case(**fields)
        self.assertEqual('BLOCKED', result['localPathEvidence']['status'])
        self.assertEqual('UNKNOWN', result['pathEvidence']['status'])
        nodes = result['cfg']['nodes']
        risk = next(n for n in nodes if n.get('nodeId') == result['riskBinding']['nodeId'])
        after_checks = [n for n in nodes if n['kind'] == 'CHECK' and n['id'] > risk['id']]
        self.assertTrue(after_checks)
        self.assertTrue(any(n.get('nodeId') == earlier['id'] and n['kind'] == 'CALL' for n in nodes))
        facts = extract_compiler_facts(self._sealed_bundle())
        earlier_id = next(f['id'] for f in facts['facts'] if f['nodeId'] == earlier['id'])
        fields['riskFactId'] = earlier_id
        result = self.run_case(**fields)
        self.assertEqual('REACHABLE', result['localPathEvidence']['status'])
        self.assertEqual('UNKNOWN', result['verdict'])

    def test_receiver_side_effect_invalidates_lock_before_actual_external_call(self):
        fields, _, _, _ = self.mapping_case()
        call = self.function()['body']['statements'][2]['expression']['arguments'][0]
        # 调用目标表达式先经过另一个真实外部调用；不能漏掉这一前置窗口。
        inner = self.fresh(call)
        call['expression']['expression'] = inner
        call_id = call['id']
        fields['riskFactId'] = next(f['id'] for f in extract_compiler_facts(self._sealed_bundle())['facts']
                                   if f['nodeId'] == call_id)
        result = self.run_case(**fields)
        self.assertEqual('UNKNOWN', result['localPathEvidence']['status'])
        self.assertEqual('UNKNOWN', self.obligation(result, 'state_version'))
        self.assertTrue(any('receiver' in gap for gap in result['proofScope']['gaps']))

    def test_storage_alias_before_risk_does_not_keep_stable_authority(self):
        guard, write = self.function()['body']['statements']
        declaration = self.node('VariableDeclaration', name='alias', storageLocation='storage', stateVariable=False,
                                typeName=self.node('ElementaryTypeName', name='address'))
        alias = self.node('VariableDeclarationStatement', declarations=[declaration],
                          initialValue=self.node('Identifier', name='owner', referencedDeclaration=2))
        self.function()['body']['statements'] = [guard, alias, write]
        result = self.run_case()
        self.assertEqual('UNKNOWN', self.obligation(result, 'state_version'))
        self.assertNotEqual('BLOCKED', result['localPathEvidence']['status'])

    def test_invalid_structure_source_identity_and_risk_span_are_failed_unknown(self):
        for fields in [{'riskLine': True}, {'sourceHash': 'wrong'}, {'riskSpan': []}, {'function': None},
                       {'riskOperation': 'EXPRESSION'}, {'mechanism': 'REENTRANCY'}, {'riskKind': 'CALL'}]:
            with self.subTest(fields=fields):
                result = self.run_case(**fields)
                self.assertEqual('FAILED', result['status'])
                self.assertTrue(result.get('errorCategory'))
                self.assertEqual('UNKNOWN', result['verdict'])

    def test_renaming_contract_function_and_state_preserves_semantics(self):
        ast = self.fixture.output['sources']['contracts/C.sol']['ast']
        ast['nodes'][0]['name'] = 'Other'
        ast['nodes'][0]['nodes'][0]['name'] = 'authority'
        self.function()['name'] = 'changed'
        self.fixture.output['contracts']['contracts/C.sol']['Other'] = self.fixture.output['contracts']['contracts/C.sol'].pop('C')
        abi = self.fixture.output['contracts']['contracts/C.sol']['Other']['abi']
        abi[0]['name'], abi[1]['name'] = 'changed', 'authority'
        self.fixture.manifest['targetContract'] = 'Other'
        result = self.run_case(contract='Other', function='changed()')
        self.assertEqual('BLOCKED', result['localPathEvidence']['status'])
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('TOOL_ENVIRONMENT_BINDING', result['toolBinding']['errorCategory'])

    def test_authority_read_before_require_argument_write_is_stale_at_check(self):
        guard, write = self.function()['body']['statements']
        mutation = self.node('FunctionDefinition', name='changeDuringArgument', kind='function', visibility='internal',
            stateMutability='nonpayable', parameters=self.node('ParameterList', parameters=[]),
            returnParameters=self.node('ParameterList', parameters=[self.node('VariableDeclaration', name='', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='string'))]), modifiers=[],
            body=self.node('Block', statements=[self.fresh(write), self.node('Return',
            expression=self.node('Literal', kind='string', value='信息'))]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(mutation)
        guard['expression']['arguments'].append(self.node('FunctionCall', kind='functionCall', arguments=[],
            expression=self.node('Identifier', name='changeDuringArgument', referencedDeclaration=mutation['id'],
            typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$__$returns$_t_string_memory_ptr_$'})))
        self.fixture.seal()
        fields = {'riskFactId': next(f['id'] for f in extract_compiler_facts(self.fixture.load())['facts']
                                    if f['nodeId'] == write['expression']['id'])}
        result = self.run_case(**fields)
        self.assertNotEqual('SUPPORTED', self.obligation(result, 'state_version'))
        self.assertNotEqual('BLOCKED', result['localPathEvidence']['status'])

    def test_recursive_unknown_callee_invalidates_previously_closed_lock(self):
        fields, _, _, _ = self.mapping_case()
        helper = self.node('FunctionDefinition', name='unresolvedEffect', kind='function', visibility='internal',
            stateMutability='nonpayable', parameters=self.node('ParameterList', parameters=[]),
            returnParameters=self.node('ParameterList', parameters=[]), modifiers=[], body=self.node('Block', statements=[]))
        call = self.node('FunctionCall', kind='functionCall', arguments=[], expression=self.node('Identifier',
            name='unresolvedEffect', referencedDeclaration=helper['id'],
            typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$__$returns$__$'}))
        helper['body']['statements'] = [self.node('ExpressionStatement', expression=call)]
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(helper)
        self.function()['body']['statements'].insert(2, self.node('ExpressionStatement', expression=self.fresh(call)))
        risk = self.function()['body']['statements'][3]['expression']['arguments'][0]
        fields['riskFactId'] = next(f['id'] for f in extract_compiler_facts(self._sealed_bundle())['facts'] if f['nodeId'] == risk['id'])
        result = self.run_case(**fields)
        self.assertEqual('UNKNOWN', result['localPathEvidence']['status'])
        self.assertEqual('UNKNOWN', self.obligation(result, 'state_version'))

    def test_symbolically_different_key_write_may_clear_same_runtime_lock(self):
        fields, _, _, _ = self.mapping_case()
        other = self.node('VariableDeclaration', name='other', stateVariable=False,
                          typeName=self.node('ElementaryTypeName', name='bytes32'))
        self.function()['parameters']['parameters'].append(other)
        self.fixture.output['contracts']['contracts/C.sol']['C']['abi'][0]['inputs'].append({'type': 'bytes32'})
        reset = self.fresh(self.function()['body']['statements'][1])
        reset['expression']['leftHandSide']['expression']['indexExpression']['referencedDeclaration'] = other['id']
        reset['expression']['rightHandSide']['value'] = 'false'
        self.function()['body']['statements'].insert(2, reset)
        risk = self.function()['body']['statements'][3]['expression']['arguments'][0]
        fields.update(function='f(bytes32,bytes32)', riskFactId=next(f['id'] for f in
            extract_compiler_facts(self._sealed_bundle())['facts'] if f['nodeId'] == risk['id']))
        result = self.run_case(**fields)
        self.assertNotEqual('BLOCKED', result['localPathEvidence']['status'])
        self.assertNotEqual('SUPPORTED', self.obligation(result, 'state_version'))

    def test_unknown_statement_after_lock_invalidates_state_fact(self):
        fields, _, _, _ = self.mapping_case()
        self.function()['body']['statements'].insert(2, self.node('InlineAssembly'))
        risk = self.function()['body']['statements'][3]['expression']['arguments'][0]
        fields['riskFactId'] = next(f['id'] for f in extract_compiler_facts(self._sealed_bundle())['facts'] if f['nodeId'] == risk['id'])
        result = self.run_case(**fields)
        self.assertEqual('UNKNOWN', self.obligation(result, 'state_version'))
        self.assertEqual('UNKNOWN', result['localPathEvidence']['status'])

    def test_binary_mutation_and_authority_read_order_is_not_guessed(self):
        guard, write = self.function()['body']['statements']
        authority = guard['expression']['arguments'][0]['rightExpression']
        mutation = self.node('FunctionDefinition', name='changeBeforeCompare', kind='function', visibility='internal',
            stateMutability='nonpayable', parameters=self.node('ParameterList', parameters=[]),
            returnParameters=self.node('ParameterList', parameters=[self.node('VariableDeclaration', name='', stateVariable=False,
            typeName=self.node('ElementaryTypeName', name='address'))]), modifiers=[],
            body=self.node('Block', statements=[self.fresh(write), self.node('Return', expression=self.node('MemberAccess',
            memberName='sender', expression=self.node('Identifier', name='msg', referencedDeclaration=-15,
            typeDescriptions={'typeIdentifier': 't_magic_message'})))]))
        self.fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(mutation)
        guard['expression']['arguments'][0]['leftExpression'] = self.node('FunctionCall', kind='functionCall', arguments=[],
            expression=self.node('Identifier', name='changeBeforeCompare', referencedDeclaration=mutation['id'],
            typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$__$returns$_t_address_$'}))
        fields = {'riskFactId': next(f['id'] for f in extract_compiler_facts(self._sealed_bundle())['facts']
                                    if f['nodeId'] == write['expression']['id'])}
        result = self.run_case(**fields)
        self.assertNotEqual('BLOCKED', result['localPathEvidence']['status'])
        self.assertNotEqual('SUPPORTED', self.obligation(result, 'state_version'))
        self.assertTrue(any('求值顺序' in gap for gap in result['proofScope']['gaps']))

    def test_function_and_complete_signature_must_agree(self):
        for fields in [{'function': 'other', 'functionSignature': 'f()'},
                       {'function': 'f(uint256)', 'functionSignature': 'f()'}]:
            with self.subTest(fields=fields):
                result = self.run_case(**fields)
                self.assertEqual('FAILED', result['status'])
                self.assertEqual('HYPOTHESIS_BINDING_MISMATCH', result['errorCategory'])

    def test_wrong_actor_and_repeated_names_are_not_authority(self):
        condition = self.function()['body']['statements'][0]['expression']['arguments'][0]
        condition['leftExpression']['memberName'] = 'origin'
        condition['leftExpression']['expression'].update(name='tx', referencedDeclaration=-20,
                                                       typeDescriptions={'typeIdentifier': 't_magic_transaction'})
        result = self.run_case()
        self.assertNotEqual('SUPPORTED', self.obligation(result, 'actor'))
        self.assertEqual('UNKNOWN', result['verdict'])


if __name__ == '__main__':
    unittest.main()
