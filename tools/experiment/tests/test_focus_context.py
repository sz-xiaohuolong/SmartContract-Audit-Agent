"""焦点索引不能丢失原字节或把语法能力升级为证明。"""
import hashlib
import copy
import unittest
import test_compiler_facts as fixtures


class FocusContextTest(unittest.TestCase):
    def test_权限事实连接检查读状态写入与入口且不当作证明(self):
        from verirag.analysis.focus_context import build_focus_context
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bundle = fixture.load()
        original = copy.deepcopy(bundle)
        context = build_focus_context(bundle)
        self.assertIn('permissionFacts', context)
        index = context['permissionFacts']
        self.assertEqual('permission-facts-1', index['schemaVersion'])
        self.assertEqual(bundle['receiptDigest'], index['receiptDigest'])
        kinds = {row['kind'] for row in index['relations']}
        self.assertTrue({'FUNCTION_WRITES_STATE', 'CHECK_READS_STATE', 'ENTRY_REACHES_FUNCTION',
                         'CHECK_DOMINATES_OPERATION'} <= kinds)
        writes = [r for r in index['relations'] if r['kind'] == 'FUNCTION_WRITES_STATE']
        self.assertEqual([2], [r['stateDeclarationId'] for r in writes])
        self.assertEqual(21, writes[0]['nodeId'])
        self.assertTrue(all(r['references'] for r in index['relations']))
        self.assertFalse(index['protectionProved'])
        self.assertFalse(index['complete'])
        self.assertEqual(original, bundle)

    def test_索引写盘回读不改变字段类型(self):
        import json
        from verirag.analysis.focus_context import build_focus_context
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        context = build_focus_context(fixture.load())
        self.assertEqual(context, json.loads(json.dumps(context)))

    def test_检查中的纯赋值只记写入而复合赋值保留读取(self):
        from verirag.analysis.focus_context import build_focus_context
        import test_access_call_proofs as access
        helper = access.AccessCallProofTest(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        state = helper.state('enabled')
        assignment = helper.write(state, helper.literal(True))['expression']
        helper.function['body']['statements'] = [helper.require(assignment)]
        helper.fixture.seal()
        index = build_focus_context(helper.fixture.load())['permissionFacts']
        self.assertFalse(any(r['kind'] == 'CHECK_READS_STATE' and r['stateDeclarationId'] == state['id']
                             for r in index['relations']))
        self.assertTrue(any(r['kind'] == 'FUNCTION_WRITES_STATE' and r['stateDeclarationId'] == state['id']
                            for r in index['relations']))

    def test_条件内部函数读取及外部未知效果均可追溯(self):
        from verirag.analysis.focus_context import build_focus_context, build_fact_guidance
        from verirag.analysis.risk_catalog import build_risk_catalog
        import test_access_call_proofs as access
        helper = access.AccessCallProofTest(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        owner = next(n for n in helper.contract['nodes'] if n.get('id') == 2)
        guard = helper.node('BinaryOperation', operator='==', leftExpression=helper.sender(),
                            rightExpression=helper.state_read(owner))
        allowed = helper.syntax.fresh(helper.function)
        allowed.update(name='allowed', visibility='internal', stateMutability='view')
        allowed['body']['statements'] = [helper.node('Return', expression=guard)]
        helper.contract['nodes'].append(allowed)
        call = helper.node('FunctionCall', kind='functionCall', arguments=[],
            expression=helper.node('Identifier', name='allowed', referencedDeclaration=allowed['id'],
                typeDescriptions={'typeIdentifier': 't_function_internal_view$__$returns$_t_bool_$'}))
        external = helper.node('FunctionCall', kind='functionCall', arguments=[],
            expression=helper.node('MemberAccess', memberName='hook', expression=helper.sender(),
                referencedDeclaration=allowed['id'],
                typeDescriptions={'typeIdentifier': 't_function_external_nonpayable$__$returns$__$'}))
        helper.function['body']['statements'] = [helper.require(call), helper.statement(external)]
        helper.fixture.seal(); bundle = helper.fixture.load()
        context = build_focus_context(bundle); index = context['permissionFacts']
        reads = [r for r in index['relations'] if r['kind'] == 'CHECK_READS_STATE']
        self.assertTrue(any(r['stateDeclarationId'] == owner['id'] for r in reads))
        self.assertTrue(any(len(r['references']) > 1 for r in reads))
        self.assertTrue(any(r['kind'] == 'EXTERNAL_EFFECT' and r['nodeId'] == external['id']
                            for r in index['unknownEdges']))
        self.assertTrue(any('外部调用' in gap for gap in index['gaps']))
        guidance = build_fact_guidance(context, build_risk_catalog(bundle))
        self.assertIn('EXTERNAL_EFFECT', guidance['text'])

    def test_条件内部虚调用按实际合约读取覆盖实现(self):
        from verirag.analysis.focus_context import build_focus_context
        import test_access_call_proofs as access
        helper = access.AccessCallProofTest(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        first = helper.state('baseFlag'); second = helper.state('realFlag')
        allowed = helper.syntax.fresh(helper.function)
        allowed.update(name='allowed', visibility='internal', stateMutability='view', virtual=True)
        allowed['body']['statements'] = [helper.node('Return', expression=helper.state_read(first))]
        override = helper.syntax.fresh(allowed)
        override['body']['statements'] = [helper.node('Return', expression=helper.state_read(second))]
        helper.contract['nodes'].append(allowed)
        call = helper.node('FunctionCall', kind='functionCall', arguments=[], expression=helper.node('Identifier',
            name='allowed', referencedDeclaration=allowed['id'],
            typeDescriptions={'typeIdentifier': 't_function_internal_view$__$returns$_t_bool_$'}))
        helper.function['body']['statements'] = [helper.require(call)]
        derived = helper.node('ContractDefinition', name='D', contractKind='contract', fullyImplemented=True,
            baseContracts=[], linearizedBaseContracts=[], nodes=[override])
        derived['linearizedBaseContracts'] = [derived['id'], helper.contract['id']]
        helper.fixture.output['sources']['contracts/C.sol']['ast']['nodes'].append(derived)
        helper.fixture.output['contracts']['contracts/C.sol']['D'] = copy.deepcopy(
            helper.fixture.output['contracts']['contracts/C.sol']['C'])
        helper.fixture.seal()
        index = build_focus_context(helper.fixture.load())['permissionFacts']
        reads = [r for r in index['relations'] if r['kind'] == 'CHECK_READS_STATE']
        self.assertTrue(any(r['stateDeclarationId'] == second['id']
                            and r['contractDeclarationId'] == derived['id'] for r in reads))
        self.assertFalse(any(r['stateDeclarationId'] == first['id']
                             and r['contractDeclarationId'] == derived['id'] for r in reads))

    def test_编译器纯编码不伪造外部回调(self):
        from verirag.analysis.focus_context import build_focus_context
        import test_access_call_proofs as access
        helper = access.AccessCallProofTest(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        call = helper.node('FunctionCall', kind='functionCall', arguments=[helper.literal(1)],
            expression=helper.node('MemberAccess', memberName='encode', expression=helper.node('Identifier', name='abi'),
                typeDescriptions={'typeIdentifier': 't_function_abiencode_pure$__$returns$_t_bytes_memory_ptr_$'}))
        helper.function['body']['statements'] = [helper.statement(call)]
        helper.fixture.seal()
        index = build_focus_context(helper.fixture.load())['permissionFacts']
        self.assertFalse(any(r['kind'] == 'EXTERNAL_EFFECT' for r in index['unknownEdges']))

    def test_权限事实预算不足明确记录遗漏(self):
        from verirag.analysis.focus_context import build_focus_context
        from unittest.mock import patch
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch('verirag.analysis.focus_context._PERMISSION_RELATION_LIMIT', 1):
            index = build_focus_context(fixture.load())['permissionFacts']
        self.assertEqual(1, len(index['relations']))
        self.assertGreater(index['omittedRelationCount'], 0)
        self.assertTrue(any('预算' in gap for gap in index['gaps']))

    def test_事实提示固定排序超限拒绝且不包含真值(self):
        from verirag.analysis.focus_context import build_focus_context, build_fact_guidance
        from verirag.analysis.risk_catalog import build_risk_catalog
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bundle = fixture.load()
        context, catalog = build_focus_context(bundle), build_risk_catalog(bundle)
        first = build_fact_guidance(context, catalog)
        context['permissionFacts']['groundTruth'] = '禁止泄漏的目标答案'
        context['permissionFacts']['relations'].reverse()
        self.assertEqual(first, build_fact_guidance(context, catalog))
        self.assertNotIn('禁止泄漏的目标答案', first['text'])
        self.assertEqual(hashlib.sha256(first['text'].encode()).hexdigest(), first['textSha256'])
        self.assertIn('检查读取状态', first['text'])
        with self.assertRaisesRegex(ValueError, '预算'):
            build_fact_guidance(context, catalog, max_bytes=1)

    def test_普通同名初始化函数的未保护写入不能从索引遗漏(self):
        from verirag.analysis.focus_context import build_focus_context
        import test_compiled_d2 as compiled
        syntax = compiled.CompiledD2Test(); syntax.setUp()
        self.addCleanup(syntax.doCleanups)
        fixture = syntax.fixture
        setter = syntax.fresh(fixture.function())
        setter['name'] = 'C'
        setter['body']['statements'] = setter['body']['statements'][1:]
        fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(setter)
        fixture.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'function', 'name': 'C', 'inputs': [], 'outputs': [], 'stateMutability': 'nonpayable'})
        fixture.seal()
        context = build_focus_context(fixture.load())
        index = context['permissionFacts']
        self.assertIn('C()', [e['signature'] for e in index['entries']])
        self.assertEqual([], index['constructors'])
        self.assertTrue(any(r['kind'] == 'FUNCTION_WRITES_STATE' and r['functionDeclarationId'] == setter['id']
                            for r in index['relations']))
        self.assertIn('C()', [e['signature'] for e in context['entries'][0]['relatedEntries']])

    def test_角色映射保留调用者键而构造初始化单独展示(self):
        from verirag.analysis.focus_context import build_focus_context
        import test_access_call_proofs as access
        helper = access.AccessCallProofTest(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        state = helper.state('roles')
        state['typeDescriptions']['typeIdentifier'] = 't_mapping$_t_address_$_t_bool_$'
        lookup = helper.node('IndexAccess', baseExpression=helper.state_read(state), indexExpression=helper.sender(),
                             typeDescriptions={'typeIdentifier': 't_bool'})
        helper.function['body']['statements'] = [helper.require(lookup), helper.statement(helper.call)]
        constructor = helper.constructor([helper.write(state, helper.literal(True))])
        helper.fixture.seal()
        index = build_focus_context(helper.fixture.load())['permissionFacts']
        reads = [r for r in index['relations'] if r['kind'] == 'CHECK_READS_STATE' and r['resource']['segments']]
        self.assertTrue(reads)
        self.assertEqual('sender', reads[0]['resource']['segments'][0]['expression']['memberName'])
        self.assertIn(constructor['id'], [c['declarationId'] for c in index['constructors']])
        self.assertNotIn(constructor['id'], [e['declarationId'] for e in index['entries']])
        self.assertFalse(index['constructors'][0]['executed'])

    def test_语法回退保留中文跨度空权限修饰器及导入缺口(self):
        from verirag.analysis.focus_context import build_syntax_context
        source = '// 中文\nimport "missing.sol";\ncontract C { modifier onlyOwner(){_;} function f() public onlyOwner {} }'
        result = build_syntax_context(source)
        self.assertEqual('SYNTAX_ONLY', result['capability'])
        self.assertFalse(result['complete'])
        self.assertTrue(any('导入' in gap for gap in result['gaps']))
        blocks = result['blocks']
        texts = [block['text'] for block in blocks]
        self.assertIn('modifier onlyOwner(){_;}', texts)
        self.assertIn('function f() public onlyOwner {}', texts)
        for block in blocks:
            span = block['span']
            raw = source.encode()[span['start']:span['start'] + span['length']]
            self.assertEqual(block['text'].encode(), raw)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), block['bytesSha256'])

    def test_编译索引绑定声明和状态写入不消费真值(self):
        from verirag.analysis.focus_context import build_focus_context
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        result = build_focus_context(fixture.load())
        entry = next(row for row in result['entries'] if row['signature'] == 'f()')
        self.assertEqual(4, entry['declarationId'])
        self.assertEqual([2], entry['stateDeclarations'])
        self.assertTrue(entry['ff'])
        self.assertTrue(entry['fv'])
        self.assertFalse(result['complete'])
        self.assertFalse(entry['protectionClosureComplete'])
        self.assertIn('f()', [e['signature'] for e in entry['relatedEntries']])

    def test_未闭合源码回退必须显式失败(self):
        from verirag.analysis.focus_context import build_syntax_context
        result = build_syntax_context('contract C { function f() public {')
        self.assertEqual('UNAVAILABLE', result['capability'])
        self.assertEqual([], result['blocks'])
        self.assertFalse(result['complete'])

    def test_全文多合约入口均进入索引(self):
        from verirag.analysis.focus_context import build_focus_context
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        second = copy.deepcopy(fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0])
        def shift(value):
            if isinstance(value, dict):
                for key, child in list(value.items()):
                    if key in {'id', 'referencedDeclaration'} and type(child) is int and child >= 0:
                        value[key] = child + 100
                    elif key == 'linearizedBaseContracts': value[key] = [x + 100 for x in child]
                    else: shift(child)
            elif isinstance(value, list):
                for child in value: shift(child)
        shift(second); second['name'] = 'D'
        fixture.output['sources']['contracts/C.sol']['ast']['nodes'].append(second)
        fixture.output['contracts']['contracts/C.sol']['D'] = copy.deepcopy(fixture.output['contracts']['contracts/C.sol']['C'])
        fixture.seal()
        result = build_focus_context(fixture.load())
        self.assertEqual({4, 104}, {e['declarationId'] for e in result['entries']})

    def test_内部函数指针未解析必须登记闭包缺口(self):
        from verirag.analysis.focus_context import build_focus_context
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        expression = fixture.function()['body']['statements'][0]['expression']['expression']
        expression.update(name='pointer', referencedDeclaration=2,
            typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$__$returns$__$'})
        fixture.seal()
        entry = build_focus_context(fixture.load())['entries'][0]
        self.assertFalse(entry['internalClosureComplete'])
        self.assertTrue(any('内部调用' in gap for gap in entry['gaps']))
