"""编译风险目录的全合约、原件跨度与能力缺口；夹具不证明真实漏洞。"""
import copy
import unittest
from unittest.mock import patch

from compiler_facts import CompilationBindingError
from risk_catalog import build_risk_catalog, prepare_model_context
import test_compiler_facts as fixtures


class RiskCatalogTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompilerFactsTest('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.temporary.cleanup)

    def catalog(self):
        return build_risk_catalog(self.fixture.load())

    def test_发现目录不覆盖后续候选编译入口(self):
        fixture = self.fixture
        bundle = fixture.load()
        target = {'fullSourceHash': bundle['sourceHash'], '_toolConfiguration': {'tools.compiler.directory': 'fixture'}}
        view = {}
        with patch('compilation_runtime.prepare_discovery_compilation', return_value={'fixture': True}), \
                patch('risk_catalog.load_bound_compilation', return_value=bundle):
            prepare_model_context(fixture.root, target, view, 'real')
        self.assertNotIn('compilerManifest', target)
        self.assertEqual('BOUND', view['riskCatalogDiagnostic']['status'])
        self.assertEqual(bundle['sourceHash'], view['riskCatalog']['sourceHash'])

    def test_编译失败不制造空成功目录(self):
        target = {'_toolConfiguration': {'tools.compiler.directory': 'fixture'}}
        view = {}
        with patch('compilation_runtime.prepare_discovery_compilation', side_effect=ValueError('编译协议不支持')):
            prepare_model_context(self.fixture.root, target, view, 'real')
        self.assertNotIn('riskCatalog', view)
        self.assertEqual({'status': 'UNAVAILABLE', 'reason': '编译协议不支持'}, view['riskCatalogDiagnostic'])

    def test_目录保留真实摘要跨度与结构能力而非安全标签(self):
        catalog = self.catalog()
        self.assertEqual('compiler-risk-1', catalog['schemaVersion'])
        self.assertEqual(fixtures.digest(self.fixture.source.encode()), catalog['sourceHash'])
        self.assertEqual('RECOMPILED_MATCH', catalog['verificationStatus'])
        self.assertEqual(['C'], [row['contract'] for row in catalog['contracts']])
        self.assertEqual({'f()', 'owner()'}, {row['signature'] for row in catalog['contracts'][0]['entries']})
        self.assertEqual(1, len(catalog['operations']))
        operation = catalog['operations'][0]
        self.assertEqual('WRITE', operation['riskOperation'])
        self.assertEqual('f', operation['function'])
        self.assertEqual(64, len(operation['factId']))
        self.assertEqual('STRUCTURAL_ONLY', operation['capability']['status'])
        span = operation['span']
        selected = self.fixture.source.encode()[span['start']:span['start'] + span['length']]
        self.assertEqual(fixtures.digest(selected), span['contentSha256'])
        self.assertNotIn(operation['capability']['status'], {'SAFE', 'SUPPORTED', 'REFUTED'})

    def test_全部编译合约和fallback_receive均保留(self):
        fixture = self.fixture
        second = copy.deepcopy(fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0])
        def shift(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {'id', 'referencedDeclaration'} and isinstance(child, int) and child >= 0:
                        value[key] = child + 100
                    elif key == 'linearizedBaseContracts':
                        value[key] = [identity + 100 for identity in child]
                    else:
                        shift(child)
            elif isinstance(value, list):
                for child in value:
                    shift(child)
        shift(second)
        second['name'] = 'D'
        fixture.output['sources']['contracts/C.sol']['ast']['nodes'].append(second)
        artifact = copy.deepcopy(fixture.output['contracts']['contracts/C.sol']['C'])
        fixture.output['contracts']['contracts/C.sol']['D'] = artifact
        for offset, kind in [(200, 'fallback'), (300, 'receive')]:
            function = copy.deepcopy(fixture.function())
            def move(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key == 'id' and isinstance(child, int):
                            value[key] = child + offset
                        else:
                            move(child)
                elif isinstance(value, list):
                    for child in value:
                        move(child)
            move(function)
            function.update(kind=kind, name='', visibility='external', stateMutability='payable')
            fixture.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'].append(function)
            fixture.output['contracts']['contracts/C.sol']['C']['abi'].append({'type': kind, 'stateMutability': 'payable'})
        fixture.seal()
        catalog = self.catalog()
        self.assertEqual({'C', 'D'}, {row['contract'] for row in catalog['contracts']})
        first = next(row for row in catalog['contracts'] if row['contract'] == 'C')
        self.assertEqual({'f()', 'owner()', 'fallback()', 'receive()'}, {row['signature'] for row in first['entries']})
        self.assertEqual({'C', 'D'}, {row['contract'] for row in catalog['operations']})

    def test_其他合约缺ABI时记录能力缺口而非忽略(self):
        bundle = self.fixture.load()
        other = copy.deepcopy(bundle['contracts'][1])
        other['node']['id'] = 500
        other['node']['name'] = 'NotNamedSafe'
        other['linearizedBaseContracts'] = [500]
        other['effectiveFunctions'] = []
        other['effectiveStateVariables'] = []
        bundle['contracts'][500] = other
        catalog = build_risk_catalog(bundle)
        entry = next(row for row in catalog['contracts'] if row['contract'] == 'NotNamedSafe')
        self.assertEqual('UNAVAILABLE', entry['capability']['status'])
        self.assertTrue(entry['capability']['gaps'])

    def test_目录不读取真值或首个目标合约的评分字段(self):
        bundle = self.fixture.load()
        first = build_risk_catalog(bundle)
        bundle['groundTruth'] = {'hasVulnerability': False}
        bundle['vulnerableLines'] = [999]
        bundle['targetContract'] = '名字不参与安全判断'
        self.assertEqual(first, build_risk_catalog(bundle))

    def test_未实际重新编译的输入不得生成已绑定目录(self):
        bundle = self.fixture.load()
        bundle['verificationStatus'] = 'HASH_ONLY'
        with self.assertRaises(CompilationBindingError):
            build_risk_catalog(bundle)

    def test_目录生成不修改预编译bundle(self):
        bundle = self.fixture.load()
        original = copy.deepcopy(bundle)
        build_risk_catalog(bundle)
        self.assertEqual(original, bundle)

    def test_未覆盖循环中的真实调用与写入保留结构位置(self):
        function = self.fixture.function()
        statements = function['body']['statements']
        call = statements[0]['expression']
        call['arguments'] = []
        call['expression'].update(name='f', referencedDeclaration=4,
            typeDescriptions={'typeIdentifier': 't_function_external_nonpayable$__$returns$__$'})
        function['body']['statements'] = [{'nodeType': 'WhileStatement', 'id': 500,
            'src': function['src'], 'condition': {'nodeType': 'Literal', 'id': 501,
                'src': function['src'], 'kind': 'bool', 'value': 'true'},
            'body': {'nodeType': 'Block', 'id': 502, 'src': function['src'], 'statements': statements}}]
        self.fixture.seal()
        catalog = self.catalog()
        self.assertEqual({'CALL', 'WRITE'}, {row['riskOperation'] for row in catalog['operations']})
        self.assertTrue(all(row['candidateEligible'] for row in catalog['operations']))
        self.assertTrue(all(row['capability']['status'] == 'MECHANISM_UNSUPPORTED' for row in catalog['operations']))
        self.assertTrue(any('WhileStatement' in gap for gap in catalog['limitations']))

    def test_入口图预算缺口须传播且不能变成完整覆盖(self):
        import risk_catalog
        original = risk_catalog._ReentrancyGraph
        def exhausted(bundle, entry):
            graph = original(bundle, entry)
            graph.exhausted = True
            graph.gaps = ['CFG 节点预算超限']
            return graph
        with patch('risk_catalog._ReentrancyGraph', side_effect=exhausted):
            catalog = self.catalog()
        entry = next(row for row in catalog['contracts'][0]['entries'] if row['function'] == 'f')
        self.assertEqual('BUDGET_EXHAUSTED', entry['capability']['status'])
        self.assertIn('CFG 节点预算超限', catalog['limitations'])

    def test_图提取失败仍保留已确定的主入口结构写入(self):
        with patch('risk_catalog._ReentrancyGraph', side_effect=CompilationBindingError('夹具失败')):
            catalog = self.catalog()
        self.assertEqual(1, len(catalog['operations']))
        self.assertEqual('WRITE', catalog['operations'][0]['riskOperation'])
        self.assertEqual('MECHANISM_UNSUPPORTED', catalog['operations'][0]['capability']['status'])
        self.assertTrue(any('提取失败' in gap for gap in catalog['limitations']))


if __name__ == '__main__':
    unittest.main()
