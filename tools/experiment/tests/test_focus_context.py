"""焦点索引不能丢失原字节或把语法能力升级为证明。"""
import hashlib
import copy
import unittest
import test_compiler_facts as fixtures


class FocusContextTest(unittest.TestCase):
    def test_语法回退保留中文跨度空权限修饰器及导入缺口(self):
        from focus_context import build_syntax_context
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
        from focus_context import build_focus_context
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
        from focus_context import build_syntax_context
        result = build_syntax_context('contract C { function f() public {')
        self.assertEqual('UNAVAILABLE', result['capability'])
        self.assertEqual([], result['blocks'])
        self.assertFalse(result['complete'])

    def test_全文多合约入口均进入索引(self):
        from focus_context import build_focus_context
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
        from focus_context import build_focus_context
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        expression = fixture.function()['body']['statements'][0]['expression']['expression']
        expression.update(name='pointer', referencedDeclaration=2,
            typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$__$returns$__$'})
        fixture.seal()
        entry = build_focus_context(fixture.load())['entries'][0]
        self.assertFalse(entry['internalClosureComplete'])
        self.assertTrue(any('内部调用' in gap for gap in entry['gaps']))
