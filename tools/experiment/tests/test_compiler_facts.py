"""固定编译产物的绑定、声明身份、字节跨度和 ABI 全入口回归。"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from verirag.analysis import compiler_facts

from verirag.analysis.compiler_facts import CompilationBindingError, extract_compiler_facts, load_bound_compilation


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def compact_fixture():
    """合成 compact AST，仅检验适配契约，不冒充真实编译证据。"""
    source = '// 中文\ncontract C { address public owner; function f() public {} }\n'
    end = len(source.encode())
    def node(node_type, identity, **kwargs):
        return dict(nodeType=node_type, id=identity, src=f'0:{end}:0', **kwargs)
    address = node('ElementaryTypeName', 3, name='address')
    state = node('VariableDeclaration', 2, name='owner', stateVariable=True,
                 visibility='public', typeName=address, typeDescriptions={'typeIdentifier': 't_address'})
    sender = node('MemberAccess', 13, memberName='sender', expression=node('Identifier', 12,
                  name='msg', referencedDeclaration=-15, typeDescriptions={'typeIdentifier': 't_magic_message'}))
    state_ref = node('Identifier', 14, name='owner', referencedDeclaration=2)
    compare = node('BinaryOperation', 15, operator='==', leftExpression=sender, rightExpression=state_ref)
    require = node('FunctionCall', 17, kind='functionCall', arguments=[compare], expression=node(
        'Identifier', 16, name='require', referencedDeclaration=-18,
        typeDescriptions={'typeIdentifier': 't_function_require_pure$_t_bool_$returns$__$'}))
    write = node('Assignment', 21, operator='=', leftHandSide=node('Identifier', 19,
                 name='owner', referencedDeclaration=2), rightHandSide=sender)
    # 同一 AST 节点不能重复嵌入；赋值右侧保留独立身份。
    write['rightHandSide'] = node('MemberAccess', 23, memberName='sender', expression=node(
        'Identifier', 24, name='msg', referencedDeclaration=-15,
        typeDescriptions={'typeIdentifier': 't_magic_message'}))
    function = node('FunctionDefinition', 4, name='f', kind='function', implemented=True,
                    visibility='public', stateMutability='nonpayable', parameters=node('ParameterList', 5, parameters=[]),
                    returnParameters=node('ParameterList', 6, parameters=[]), modifiers=[], body=node('Block', 7,
                    statements=[node('ExpressionStatement', 18, expression=require),
                                node('ExpressionStatement', 22, expression=write)]))
    contract = node('ContractDefinition', 1, name='C', contractKind='contract', fullyImplemented=True,
                    linearizedBaseContracts=[1], baseContracts=[], nodes=[state, function])
    ast = node('SourceUnit', 0, absolutePath='contracts/C.sol', nodes=[contract])
    abi = [{'type': 'function', 'name': 'f', 'inputs': [], 'outputs': [], 'stateMutability': 'nonpayable'},
           {'type': 'function', 'name': 'owner', 'inputs': [], 'outputs': [{'type': 'address'}], 'stateMutability': 'view'}]
    return source, {'sources': {'contracts/C.sol': {'id': 0, 'ast': ast}},
                    'contracts': {'contracts/C.sol': {'C': {'abi': abi}}}}


class CompilerFactsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source, self.output = compact_fixture()
        self.binary = self.root / 'fixed-solc'
        self.write_compiler('0.8.15+fixture')
        (self.root / 'contracts').mkdir()
        (self.root / 'contracts/C.sol').write_bytes(self.source.encode())
        self.input = {'language': 'Solidity', 'sources': {'contracts/C.sol': {'content': self.source}},
                      'settings': {'optimizer': {'enabled': False, 'runs': 200},
                                   'outputSelection': {'*': {'*': ['abi'], '': ['ast']}}}}
        self.binding = {'mainSource': 'contracts/C.sol', 'environment': '.',
                        'sourceUnits': {'contracts/C.sol': {'path': 'contracts/C.sol',
                         'resolvedPath': str(self.root / 'contracts/C.sol'), 'sha256': digest(self.source.encode())}},
                        'compiler': str(self.binary), 'compilerSha256': digest(self.binary.read_bytes()),
                        'compilerVersion': 'solc fixture\nVersion: 0.8.15+fixture',
                        'command': [str(self.binary), '--standard-json'], 'settings': self.input['settings'],
                        'exitCode': 0, 'errors': []}
        self.manifest = {'schemaVersion': '1', 'provider': 'solc-standard-json',
                         'bindingPath': 'binding.json', 'inputPath': 'input.json', 'outputPath': 'output.json',
                         'targetSourceUnit': 'contracts/C.sol', 'targetContract': 'C',
                         'expectedSourceHash': digest(self.source.encode())}
        self.seal()

    def seal(self):
        (self.root / 'input.json').write_bytes(canonical(self.input))
        (self.root / 'output.json').write_bytes(canonical(self.output))
        (self.root / 'fixture-compiled-output.json').write_bytes(canonical(self.output))
        self.binding['inputSha256'] = digest((self.root / 'input.json').read_bytes())
        self.binding['outputSha256'] = digest((self.root / 'output.json').read_bytes())
        self.binding['sourceClosureSha256'] = digest(canonical({k: v['sha256'] for k, v in self.binding['sourceUnits'].items()}))
        (self.root / 'binding.json').write_bytes(canonical(self.binding))
        self.manifest['bindingSha256'] = digest((self.root / 'binding.json').read_bytes())
        (self.root / 'manifest.json').write_bytes(canonical(self.manifest))

    def write_compiler(self, version):
        """本地子进程夹具分别处理版本查询与标准输入，不依赖安装 solc。"""
        self.binary.write_text(
            '#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n'
            f'if sys.argv[1:] == ["--version"]:\n    print("solc fixture\\nVersion: {version}")\n'
            'elif sys.argv[1:] == ["--standard-json"]:\n'
            '    directory = Path(__file__).parent\n'
            '    data = sys.stdin.buffer.read()\n'
            '    if data != (directory / "input.json").read_bytes():\n        sys.exit(2)\n'
            '    failure = directory / "fixture-failure"\n'
            '    if failure.exists():\n        sys.exit(3)\n'
            '    sys.stdout.buffer.write((directory / "fixture-compiled-output.json").read_bytes())\n'
            '    if (directory / "fixture-mutate-compiler").exists():\n'
            '        with Path(__file__).open("ab") as binary:\n            binary.write("# 编译器已改变\\n".encode())\n'
            'else:\n    sys.exit(2)\n')
        self.binary.chmod(0o755)

    def test_重新封摘要不能把变更的产物当作真实编译结果(self):
        original = canonical(self.output)
        self.function()['name'] = 'forged'
        self.seal()
        (self.root / 'fixture-compiled-output.json').write_bytes(original)
        with self.assertRaisesRegex(CompilationBindingError, '重新编译'):
            self.load()

    def test_重新编译失败与无效输出均拒绝绑定(self):
        (self.root / 'fixture-failure').write_text('失败')
        with self.assertRaisesRegex(CompilationBindingError, '重新编译'):
            self.load()
        (self.root / 'fixture-failure').unlink()
        (self.root / 'fixture-compiled-output.json').write_text('{}')
        with self.assertRaisesRegex(CompilationBindingError, '重新编译'):
            self.load()

    def test_完整实际编译对照后才记录已验证状态(self):
        bundle = self.load()
        self.assertEqual('RECOMPILED_MATCH', bundle['verificationStatus'])

    def test_编译进程期间二进制改变拒绝真实性状态(self):
        (self.root / 'fixture-mutate-compiler').write_text('改变固定文件')
        with self.assertRaisesRegex(CompilationBindingError, '编译器'):
            self.load()

    def test_重新编译超时保持绑定失败(self):
        real_run = subprocess.run
        def run(command, **kwargs):
            if command[-1] == '--standard-json':
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return real_run(command, **kwargs)
        with patch.object(compiler_facts.subprocess, 'run', side_effect=run):
            with self.assertRaisesRegex(CompilationBindingError, '重新编译失败'):
                self.load()

    def load(self):
        return load_bound_compilation(self.manifest, self.root)

    def function(self):
        return self.output['sources']['contracts/C.sol']['ast']['nodes'][0]['nodes'][1]

    def test_loads_bound_ast_and_enumerates_function_and_getter(self):
        bundle = self.load()
        self.assertEqual(digest(self.source.encode()), bundle['sourceHash'])
        self.assertEqual(1, bundle['targetContractId'])
        self.assertEqual({'f()', 'owner()'}, {e['signature'] for e in bundle['entries']})
        self.assertEqual({'function', 'getter'}, {e['kind'] for e in bundle['entries']})
        self.assertTrue(all(e['matched'] for e in bundle['entries']))
        self.assertEqual([], bundle['entryGaps'])
        self.assertEqual('PARTIAL', bundle['status'])
        self.assertEqual(bundle['sourceHash'], load_bound_compilation(self.root / 'manifest.json', self.root)['sourceHash'])

    def test_raw_and_receipt_drift_are_rejected(self):
        for filename in ['binding.json', 'input.json', 'output.json', 'contracts/C.sol', 'fixed-solc']:
            with self.subTest(filename=filename):
                path = self.root / filename
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                with self.assertRaises(CompilationBindingError): self.load()
                path.write_bytes(original)

    def test_expected_source_compiler_settings_errors_and_closure_are_checked(self):
        cases = [lambda: self.manifest.update(expectedSourceHash='0' * 64),
                 lambda: self.binding.update(compilerVersion='Version: 0.8.14+other'),
                 lambda: self.binding.update(command=[str(self.binary), '--other']),
                 lambda: self.binding.update(settings={}),
                 lambda: self.binding.update(exitCode=1),
                 lambda: self.output.update(errors=[{'severity': 'error', 'message': '失败'}]),
                 lambda: self.input['sources']['contracts/C.sol'].update(content='changed'),
                 lambda: self.output['sources'].update({'missing.sol': {'id': 1, 'ast': {}}})]
        saved = copy.deepcopy((self.manifest, self.binding, self.input, self.output))
        for change in cases:
            with self.subTest(change=cases.index(change)):
                self.manifest, self.binding, self.input, self.output = copy.deepcopy(saved)
                change(); self.seal()
                with self.assertRaises(CompilationBindingError): self.load()
        self.manifest, self.binding, self.input, self.output = copy.deepcopy(saved)
        self.seal()
        self.binding['sourceClosureSha256'] = '0' * 64
        (self.root / 'binding.json').write_bytes(canonical(self.binding))
        self.manifest['bindingSha256'] = digest((self.root / 'binding.json').read_bytes())
        with self.assertRaises(CompilationBindingError): self.load()

    def test_duplicate_json_keys_missing_source_and_duplicate_ast_ids_fail(self):
        (self.root / 'input.json').write_bytes(b'{"language":"Solidity","language":"Other"}')
        self.binding['inputSha256'] = digest((self.root / 'input.json').read_bytes())
        (self.root / 'binding.json').write_bytes(canonical(self.binding))
        self.manifest['bindingSha256'] = digest((self.root / 'binding.json').read_bytes())
        with self.assertRaises(CompilationBindingError): self.load()
        self.seal()
        self.input['sources']['contracts/C.sol'] = {'urls': ['https://invalid.example/source.sol']}
        self.seal()
        with self.assertRaises(CompilationBindingError): self.load()
        self.input['sources']['contracts/C.sol'] = {'content': self.source}
        self.function()['body']['id'] = 4
        self.seal()
        with self.assertRaises(CompilationBindingError): self.load()

    def test_byte_spans_check_bounds_utf8_boundaries_and_unit_identity(self):
        for span in ['0:9999:0', '1:3:0', '0:1:9', '-1:1:0', 'not-a-span']:
            with self.subTest(span=span):
                self.function()['body']['src'] = span; self.seal()
                with self.assertRaises(CompilationBindingError): self.load()
        self.function()['body']['src'] = '3:6:0'; self.seal()
        bundle = self.load()
        self.assertEqual('中文', bundle['units'][0]['content'].encode()[3:9].decode())
        self.function()['src'] = '3:6:0'; self.seal()
        self.assertEqual(digest('中文'.encode()), self.load()['functions'][4]['span']['contentSha256'])

    def test_unknown_declaration_rejected_and_builtin_positive_ids_supported(self):
        require = self.function()['body']['statements'][0]['expression']['expression']
        self.write_compiler('0.5.8+fixture')
        self.binding['compilerSha256'] = digest(self.binary.read_bytes())
        self.binding['compilerVersion'] = 'solc fixture\nVersion: 0.5.8+fixture'
        require['referencedDeclaration'] = 5021
        self.seal()
        self.assertEqual('require', self.load()['builtinReferences'][5021])
        require['typeDescriptions'] = {'typeIdentifier': 't_function_internal_nonpayable$__$returns$__$'}
        self.seal()
        with self.assertRaises(CompilationBindingError): self.load()
        require['referencedDeclaration'] = -18
        with self.assertRaises(CompilationBindingError): self.load()

    def test_旧编译器sha3须按实际类型绑定而非放行悬空声明(self):
        expression = self.function()['body']['statements'][0]['expression']['expression']
        self.write_compiler('0.4.26+fixture')
        self.binding['compilerSha256'] = digest(self.binary.read_bytes())
        self.binding['compilerVersion'] = 'solc fixture\nVersion: 0.4.26+fixture'
        expression.update(name='sha3', referencedDeclaration=5021,
                          typeDescriptions={'typeIdentifier': 't_function_sha3_pure$__$returns$_t_bytes32_$'})
        self.seal()
        self.assertEqual('keccak256', self.load()['builtinReferences'][5021])
        expression['name'] = 'keccak256'
        self.seal()
        self.assertEqual('keccak256', self.load()['builtinReferences'][5021])
        expression['typeDescriptions']['typeIdentifier'] = 't_function_internal_pure$__$returns$_t_bytes32_$'
        self.seal()
        with self.assertRaises(CompilationBindingError):
            self.load()

    def test_旧suicide别名只接受编译器确认的终止调用类型(self):
        expression = self.function()['body']['statements'][0]['expression']['expression']
        self.write_compiler('0.4.26+fixture')
        self.binding['compilerSha256'] = digest(self.binary.read_bytes())
        self.binding['compilerVersion'] = 'solc fixture\nVersion: 0.4.26+fixture'
        expression.update(name='suicide', referencedDeclaration=5021,
                          typeDescriptions={'typeIdentifier': 't_function_selfdestruct_nonpayable$_t_address_$returns$__$'})
        self.seal()
        self.assertEqual('selfdestruct', self.load()['builtinReferences'][5021])
        expression['typeDescriptions']['typeIdentifier'] = 't_function_internal_nonpayable$_t_address_$returns$__$'
        self.seal()
        with self.assertRaises(CompilationBindingError):
            self.load()

    def test_ast_expressions_distinguish_check_bare_comparison_and_state_write(self):
        bundle = self.load()
        facts = extract_compiler_facts(bundle)
        self.assertEqual(1, len([f for f in facts['facts'] if f['kind'] == 'CHECK']))
        write = next(f for f in facts['facts'] if f['kind'] == 'WRITE')
        self.assertEqual(2, write['resource']['declarationId'])
        self.assertEqual('Identifier', write['expression']['leftHandSide']['nodeType'])
        statement = self.function()['body']['statements'][0]
        statement['expression'] = statement['expression']['arguments'][0]
        self.seal()
        facts = extract_compiler_facts(self.load())
        self.assertEqual([], [f for f in facts['facts'] if f['kind'] == 'CHECK'])
        self.assertTrue(any(f['kind'] == 'EXPRESSION' for f in facts['facts']))
        self.assertEqual('PARTIAL', facts['status'])

    def test_user_function_named_require_never_gets_builtin_semantics(self):
        self.function()['name'] = 'require'
        self.output['contracts']['contracts/C.sol']['C']['abi'][0]['name'] = 'require'
        call = self.function()['body']['statements'][0]['expression']['expression']
        call['referencedDeclaration'] = 4
        call['typeDescriptions'] = {'typeIdentifier': 't_function_internal_nonpayable$__$returns$__$'}
        self.seal()
        facts = extract_compiler_facts(self.load())
        self.assertEqual([], [f for f in facts['facts'] if f['kind'] == 'CHECK'])
        self.assertTrue(any(f['kind'] == 'CALL' and f['callKind'] == 'internal' for f in facts['facts']))

    def test_unmatched_abi_keeps_entry_gap_and_never_complete(self):
        self.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'function', 'name': 'unknown', 'inputs': [], 'outputs': [], 'stateMutability': 'view'})
        self.seal()
        bundle = self.load()
        self.assertEqual(3, len(bundle['entries']))
        self.assertTrue(bundle['entryGaps'])
        self.assertFalse(next(e for e in bundle['entries'] if e['signature'] == 'unknown()')['matched'])
        self.assertEqual('PARTIAL', extract_compiler_facts(bundle)['status'])

    def test_unsupported_structure_keeps_scope_limitations(self):
        self.function()['body']['statements'].append({'nodeType': 'InlineAssembly', 'id': 30,
                                                      'src': f'0:{len(self.source.encode())}:0'})
        self.seal()
        facts = extract_compiler_facts(self.load())
        self.assertEqual('PARTIAL', facts['status'])
        self.assertTrue(any('InlineAssembly' in limitation for limitation in facts['limitations']))
        self.assertFalse(any(scope['complete'] for scope in facts['scopes']))


    def test_super_and_metatype_builtins_are_type_checked(self):
        statements = self.function()['body']['statements']
        statements.extend([
            {'nodeType': 'Identifier', 'id': 40, 'src': '0:1:0', 'name': 'super',
             'referencedDeclaration': -25, 'typeDescriptions': {'typeIdentifier': 't_type$_t_super$_C_$1_$'}},
            {'nodeType': 'Identifier', 'id': 41, 'src': '0:1:0', 'name': 'type',
             'referencedDeclaration': -27, 'typeDescriptions': {'typeIdentifier': 't_function_metatype_pure$__$returns$__$'}}])
        self.seal()
        bundle = self.load()
        self.assertEqual('super', bundle['builtinReferences'][-25])
        self.assertEqual('type', bundle['builtinReferences'][-27])

    def test_inherited_override_overload_constructor_and_fallback_coverage(self):
        ast = self.output['sources']['contracts/C.sol']['ast']
        base_function = copy.deepcopy(self.function())
        base_function.update(id=50, body=None, parameters={'nodeType': 'ParameterList', 'id': 51, 'src': '0:1:0', 'parameters': []},
                             returnParameters={'nodeType': 'ParameterList', 'id': 52, 'src': '0:1:0', 'parameters': []})
        base = {'nodeType': 'ContractDefinition', 'id': 49, 'src': '0:1:0', 'name': 'Base',
                'linearizedBaseContracts': [49], 'nodes': [base_function]}
        ast['nodes'].append(base)
        ast['nodes'][0]['linearizedBaseContracts'] = [1, 49]
        self.function()['baseFunctions'] = [50]
        for identity, kind in [(60, 'constructor'), (70, 'fallback'), (80, 'receive')]:
            ast['nodes'][0]['nodes'].append({'nodeType': 'FunctionDefinition', 'id': identity, 'src': '0:1:0',
                'name': '', 'kind': kind, 'visibility': 'public', 'implemented': True,
                'parameters': {'nodeType': 'ParameterList', 'id': identity + 1, 'src': '0:1:0', 'parameters': []},
                'returnParameters': {'nodeType': 'ParameterList', 'id': identity + 2, 'src': '0:1:0', 'parameters': []},
                'body': {'nodeType': 'Block', 'id': identity + 3, 'src': '0:1:0', 'statements': []}, 'modifiers': []})
            self.output['contracts']['contracts/C.sol']['C']['abi'].append({'type': kind, 'inputs': []})
        self.seal()
        bundle = self.load()
        self.assertEqual(4, next(e for e in bundle['entries'] if e['signature'] == 'f()')['declarationId'])
        self.assertEqual({'f()', 'owner()', 'fallback()', 'receive()'}, {e['signature'] for e in bundle['entries']})
        self.assertEqual(1, len(bundle['constructors']))
        self.assertEqual([], bundle['entryGaps'])

    def test_mapping_struct_getter_uses_canonical_keys_and_field_identity(self):
        contract = self.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        state = contract['nodes'][0]
        state['typeName'] = {'nodeType': 'Mapping', 'id': 90, 'src': '0:1:0',
            'keyType': {'nodeType': 'ElementaryTypeName', 'id': 91, 'src': '0:1:0', 'name': 'uint'},
            'valueType': {'nodeType': 'UserDefinedTypeName', 'id': 92, 'src': '0:1:0', 'referencedDeclaration': 93}}
        contract['nodes'].append({'nodeType': 'StructDefinition', 'id': 93, 'src': '0:1:0', 'name': 'Flags', 'members': [
            {'nodeType': 'VariableDeclaration', 'id': 94, 'src': '0:1:0', 'name': 'closed', 'stateVariable': False,
             'typeName': {'nodeType': 'ElementaryTypeName', 'id': 95, 'src': '0:1:0', 'name': 'bool'}}]})
        self.output['contracts']['contracts/C.sol']['C']['abi'][1].update(inputs=[{'type': 'uint256'}], outputs=[{'type': 'bool'}])
        write = self.function()['body']['statements'][1]['expression']
        write['leftHandSide'] = {'nodeType': 'MemberAccess', 'id': 96, 'src': '0:1:0', 'memberName': 'closed',
             'referencedDeclaration': 94, 'expression': {'nodeType': 'IndexAccess', 'id': 97, 'src': '0:1:0',
             'baseExpression': {'nodeType': 'Identifier', 'id': 98, 'src': '0:1:0', 'name': 'owner', 'referencedDeclaration': 2},
             'indexExpression': {'nodeType': 'Literal', 'id': 99, 'src': '0:1:0', 'kind': 'number', 'value': '7'}}}
        self.seal()
        bundle = self.load()
        getter = next(e for e in bundle['entries'] if e['kind'] == 'getter')
        self.assertEqual('owner(uint256)', getter['signature'])
        resource = next(f for f in extract_compiler_facts(bundle)['facts'] if f['kind'] == 'WRITE')['resource']
        self.assertEqual(2, resource['declarationId'])
        self.assertEqual(['index', 'member'], [s['kind'] for s in resource['segments']])
        self.assertEqual(94, resource['segments'][1]['declarationId'])

    def test_distinct_source_units_with_same_basename_do_not_merge(self):
        content = '// 第二个 C.sol\n'
        (self.root / 'dependency').mkdir()
        (self.root / 'dependency/C.sol').write_bytes(content.encode())
        self.input['sources']['dependency/C.sol'] = {'content': content}
        self.binding['sourceUnits']['dependency/C.sol'] = {'path': 'dependency/C.sol', 'sha256': digest(content.encode())}
        self.output['sources']['dependency/C.sol'] = {'id': 1, 'ast': {'nodeType': 'SourceUnit', 'id': 120,
            'src': f'0:{len(content.encode())}:1', 'absolutePath': 'dependency/C.sol', 'nodes': []}}
        self.seal()
        bundle = self.load()
        self.assertEqual(2, len(bundle['units']))
        self.assertNotEqual(bundle['units'][0]['sha256'], bundle['units'][1]['sha256'])



    def test_abi_returns_and_mutability_are_not_trusted_when_ast_disagrees(self):
        abi = self.output['contracts']['contracts/C.sol']['C']['abi']
        for index, update in [(0, {'outputs': [{'type': 'bool'}]}),
                              (0, {'stateMutability': 'view'}),
                              (1, {'outputs': [{'type': 'uint256'}]})]:
            with self.subTest(index=index, update=update):
                saved = copy.deepcopy(abi[index])
                abi[index].update(update); self.seal()
                bundle = self.load()
                self.assertTrue(bundle['entryGaps'])
                self.assertFalse(bundle['entries'][index]['matched'])
                abi[index] = saved

    def test_overload_contract_parameter_and_dangling_auxiliary_references(self):
        contract = self.output['sources']['contracts/C.sol']['ast']['nodes'][0]
        overload = {'nodeType': 'FunctionDefinition', 'id': 150, 'src': '0:1:0', 'name': 'f',
            'kind': 'function', 'implemented': True, 'visibility': 'external', 'stateMutability': 'nonpayable',
            'parameters': {'nodeType': 'ParameterList', 'id': 151, 'src': '0:1:0', 'parameters': [
                {'nodeType': 'VariableDeclaration', 'id': 152, 'src': '0:1:0', 'name': 'other', 'stateVariable': False,
                 'typeName': {'nodeType': 'UserDefinedTypeName', 'id': 153, 'src': '0:1:0', 'referencedDeclaration': 1}}]},
            'returnParameters': {'nodeType': 'ParameterList', 'id': 154, 'src': '0:1:0', 'parameters': []},
            'body': {'nodeType': 'Block', 'id': 155, 'src': '0:1:0', 'statements': []}, 'modifiers': []}
        contract['nodes'].append(overload)
        self.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'function', 'name': 'f', 'inputs': [{'type': 'address', 'internalType': 'contract C'}],
             'outputs': [], 'stateMutability': 'nonpayable'})
        self.seal()
        bundle = self.load()
        self.assertEqual({'f()', 'f(address)', 'owner()'}, {e['signature'] for e in bundle['entries']})
        self.assertEqual([], bundle['entryGaps'])
        self.output['sources']['contracts/C.sol']['ast']['exportedSymbols'] = {'C': [99999]}
        self.seal()
        with self.assertRaises(CompilationBindingError): self.load()


if __name__ == '__main__':
    unittest.main()
