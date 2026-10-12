"""真实工具双收据的来源、重放和漂移拒绝；合成后端不依赖真实工具。"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import bound_slither


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class BoundSlitherTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = {'schemaVersion': '1', 'provider': 'solc-standard-json', 'bindingPath': 'binding.json',
                         'bindingSha256': 'b' * 64, 'inputPath': 'input.json', 'outputPath': 'output.json',
                         'targetSourceUnit': 'contracts/C.sol', 'targetContract': 'C', 'expectedSourceHash': 'a' * 64}
        self.bundle = {'sourceHash': 'a' * 64, 'targetSourceUnit': 'contracts/C.sol', 'manifest': self.manifest,
                       'manifestDigest': digest(canonical(self.manifest)), 'receiptDigest': 'b' * 64,
                       'environmentHash': 'c' * 64, 'verificationStatus': 'RECOMPILED_MATCH'}
        self.issue = {'check': 'reentrancy-no-eth', 'id': 'original-id', 'elements': [
            {'type': 'node', 'source_mapping': {'start': 5, 'length': 9, 'filename_relative': 'contracts/C.sol'}}]}
        self.worker_runs = 0
        self.replay_change = None

    def fake_worker(self, manifest_path, *, root, python_executable, directory):
        """用独立生成的原件模拟子进程；验证阶段必须实际调用第二次。"""
        self.worker_runs += 1
        directory.mkdir(parents=True, exist_ok=True)
        issue = copy.deepcopy(self.issue)
        if self.worker_runs > 1 and self.replay_change == 'issue': issue['check'] = 'unrelated'
        raw = {'success': True, 'error': None, 'results': {'detectors': [issue]}}
        identity = {'schemaVersion': 'bound-slither-1', 'producerCodeSha256': 'd' * 64,
                    'manifestDigest': self.bundle['manifestDigest'], 'compilerReceiptDigest': 'b' * 64,
                    'sourceHash': 'a' * 64, 'sourceFile': 'contracts/C.sol',
                    'pythonExecutable': str(Path(sys.executable).resolve()), 'toolIdentity': {'version': 'fixture'},
                    'compilerExecution': {'binarySha256Before': 'e' * 64, 'binarySha256After': 'e' * 64,
                                          'settings': {'optimizer': {'enabled': False}}},
                    'parsedCompilation': {'sourceUnits': {'contracts/C.sol': {'sha256': 'a' * 64}}},
                    'detectorsRun': ['reentrancy-no-eth'], 'effectSummaries': []}
        if self.worker_runs > 1 and self.replay_change == 'settings':
            identity['compilerExecution']['settings']['optimizer']['enabled'] = True
        raw_path = directory / 'slither-detectors.json'; raw_path.write_bytes(canonical(raw))
        receipt = {'identity': identity, 'status': 'MATCH', 'elapsedSeconds': float(self.worker_runs),
                   'rawResultCanonicalSha256': digest(canonical(raw))}
        receipt_path = directory / 'receipt.json'; receipt_path.write_bytes(canonical(receipt))
        return {'engine': 'SLITHER', 'status': 'OK', 'sourceHash': self.bundle['sourceHash'],
                'sourceFile': self.bundle['targetSourceUnit'], 'issues': [issue], 'version': 'fixture',
                'rawResultPath': str(raw_path.relative_to(root)), 'rawResultSha256': digest(raw_path.read_bytes()),
                'compilationReceipt': {'schemaVersion': 'bound-slither-1', 'path': str(receipt_path.relative_to(root)),
                                       'sha256': digest(receipt_path.read_bytes())}, 'paidModelRequests': 0}

    def analyze(self):
        with patch.object(bound_slither, '_invoke_worker', side_effect=self.fake_worker), patch.object(
                bound_slither, '_resolve_python', return_value=Path(sys.executable).resolve()):
            return bound_slither.analyze_bound(self.manifest, root=self.root)

    def verify(self, tool):
        with patch.object(bound_slither, '_invoke_worker', side_effect=self.fake_worker), patch.object(
                bound_slither, '_resolve_python', return_value=Path(sys.executable).resolve()):
            return bound_slither.verify_bound_tool(tool, self.bundle, root=self.root)

    def test_analyze_returns_standard_tool_and_original_element_spans(self):
        tool = self.analyze()
        self.assertEqual('OK', tool['status'])
        self.assertEqual(self.issue, tool['issues'][0])
        self.assertTrue((self.root / tool['rawResultPath']).is_file())
        self.assertEqual(0, tool['paidModelRequests'])

    def test_verification_replays_backend_instead_of_trusting_ok_and_hashes(self):
        tool = self.analyze()
        result = self.verify(tool)
        self.assertEqual('MATCH', result['status'])
        self.assertEqual(2, self.worker_runs)
        self.assertNotEqual(1, self.worker_runs)

    def test_matching_environment_hash_without_receipts_remains_unknown(self):
        tool = {'engine': 'SLITHER', 'status': 'OK', 'sourceHash': 'a' * 64,
                'environmentHash': 'c' * 64, 'issues': []}
        self.assertEqual('UNKNOWN', self.verify(tool)['status'])
        self.assertEqual(0, self.worker_runs)

    def test_caller_modified_issue_is_not_bound_by_real_receipt(self):
        tool = self.analyze(); tool['issues'][0]['check'] = 'forged-label'
        self.assertEqual('UNKNOWN', self.verify(tool)['status'])

    def test_数值同等但类型不同的告警不是原始告警(self):
        tool = self.analyze()
        tool['issues'][0]['elements'][0]['source_mapping']['start'] = 5.0
        self.assertEqual('UNKNOWN', self.verify(tool)['status'])

    def test_重封收据不能把布尔设置替换为等值整数(self):
        tool = self.analyze()
        path = self.root / tool['compilationReceipt']['path']
        receipt = json.loads(path.read_text())
        receipt['identity']['compilerExecution']['settings']['optimizer']['enabled'] = 0
        path.write_bytes(canonical(receipt))
        tool['compilationReceipt']['sha256'] = digest(path.read_bytes())
        self.assertEqual('UNKNOWN', self.verify(tool)['status'])

    def test_resealed_raw_and_receipt_cannot_override_actual_detector(self):
        tool = self.analyze()
        raw_path = self.root / tool['rawResultPath']
        raw = json.loads(raw_path.read_text()); raw['results']['detectors'][0]['check'] = 'forged-label'
        raw_path.write_bytes(canonical(raw)); tool['issues'] = raw['results']['detectors']
        tool['rawResultSha256'] = digest(raw_path.read_bytes())
        receipt_path = self.root / tool['compilationReceipt']['path']
        receipt = json.loads(receipt_path.read_text()); receipt['rawResultCanonicalSha256'] = digest(canonical(raw))
        receipt_path.write_bytes(canonical(receipt)); tool['compilationReceipt']['sha256'] = digest(receipt_path.read_bytes())
        self.assertEqual('UNKNOWN', self.verify(tool)['status'])
        self.assertEqual(2, self.worker_runs)

    def test_changed_effective_settings_or_detector_during_replay_are_unknown(self):
        for changed in ['settings', 'issue']:
            with self.subTest(changed=changed):
                self.worker_runs = 0; self.replay_change = changed
                self.assertEqual('UNKNOWN', self.verify(self.analyze())['status'])

    def test_manifest_and_source_identity_must_match_the_compilation_bundle(self):
        tool = self.analyze(); changed = copy.deepcopy(self.bundle)
        changed['sourceHash'] = '0' * 64
        with patch.object(bound_slither, '_resolve_python', return_value=Path(sys.executable).resolve()):
            self.assertEqual('UNKNOWN', bound_slither.verify_bound_tool(tool, changed, root=self.root)['status'])
        self.assertEqual(1, self.worker_runs)

    def test_artifacts_outside_evidence_directory_are_rejected_before_read(self):
        tool = self.analyze(); tool['rawResultPath'] = 'config/providers.local.properties'
        self.assertEqual('UNKNOWN', self.verify(tool)['status'])

    def test_missing_dependency_has_explicit_failure_without_fallback(self):
        with patch.object(bound_slither, '_resolve_python', side_effect=ValueError('工具解释器不可用')):
            result = bound_slither.analyze_bound(self.manifest, root=self.root)
        self.assertNotEqual('OK', result['status'])
        self.assertEqual('DEPENDENCY_UNAVAILABLE', result['errorCategory'])
        self.assertEqual([], result['issues'])
        self.assertEqual(0, self.worker_runs)

    def test_invalid_or_failed_worker_never_becomes_success(self):
        with patch.object(bound_slither, '_resolve_python', return_value=Path(sys.executable).resolve()), patch.object(
                bound_slither, '_invoke_worker', side_effect=TimeoutError('真实工具超时')):
            result = bound_slither.analyze_bound(self.manifest, root=self.root)
        self.assertNotEqual('OK', result['status'])
        self.assertEqual([], result['issues'])

    def test_成功标记缺真实原件收据仍是失败(self):
        with patch.object(bound_slither, '_resolve_python', return_value=Path(sys.executable).resolve()), patch.object(
                bound_slither, '_invoke_worker', return_value={'engine': 'SLITHER', 'status': 'OK', 'issues': []}):
            result = bound_slither.analyze_bound(self.manifest, root=self.root)
        self.assertNotEqual('OK', result['status'])
        self.assertEqual([], result['issues'])

    def test_非法告警元素不能通过原件与重放同等比较(self):
        self.issue = 'invalid-detector-object'
        result = self.analyze()
        self.assertNotEqual('OK', result['status'])

    def test_重放顶层源码身份也必须匹配收据(self):
        tool = self.analyze()
        original_worker = self.fake_worker

        def changed_worker(*args, **kwargs):
            replay = original_worker(*args, **kwargs)
            replay['sourceHash'] = '0' * 64
            return replay

        with patch.object(bound_slither, '_invoke_worker', side_effect=changed_worker), patch.object(
                bound_slither, '_resolve_python', return_value=Path(sys.executable).resolve()):
            result = bound_slither.verify_bound_tool(tool, self.bundle, root=self.root)
        self.assertEqual('UNKNOWN', result['status'])

    def test_virtual_environment_interpreter_entry_is_preserved(self):
        environment = self.root / 'tool-venv' / 'bin'
        environment.mkdir(parents=True)
        entry = environment / 'python'
        entry.symlink_to(Path(sys.executable).resolve())
        self.assertEqual(entry, bound_slither._resolve_python(self.root, str(entry)))
        self.assertNotEqual(entry.resolve(), bound_slither._resolve_python(self.root, str(entry)))


class _Record:
    def __init__(self, **values):
        self.__dict__.update(values)


class SlithIREffectTest(unittest.TestCase):
    """合成 IR 仅验证提取边界，不借函数修饰标记伪造完整存储证明。"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'contracts/C.sol'
        self.bundle = {'binding': {'environment': str(self.root)},
                       'units': {0: {'sourceUnit': 'contracts/C.sol', 'path': str(self.source)}},
                       'declarations': {11: {'nodeType': 'VariableDeclaration', 'stateVariable': True, 'src': '10:3:0'}},
                       'functions': {7: {'sourceUnit': 'contracts/C.sol', 'canonicalName': 'C.f()', 'body': {},
                                         'parameters': [], 'span': {'start': 0, 'length': 90}}}}
        self.variable = _Record(source_mapping=self.location(10, 3))
        self.operations = []
        self.internal = []
        self.function = _Record(id=7, source_mapping=self.location(0, 90), contains_assembly=False,
                                internal_calls=self.internal, library_calls=[], modifiers=[],
                                state_variables_read=[], state_variables_written=[self.variable],
                                all_state_variables_read=lambda: [], all_state_variables_written=lambda: [self.variable],
                                all_internal_calls=lambda: self.internal, all_slithir_operations=lambda: self.operations,
                                all_high_level_calls=lambda: [], all_low_level_calls=lambda: [])
        self.slither = _Record(contracts=[_Record(functions_declared=[self.function], modifiers_declared=[])])

    def location(self, start, length):
        return _Record(filename=_Record(absolute=str(self.source)), start=start, length=length)

    def result(self):
        return bound_slither._effects(self.slither, self.bundle)[0]

    def test_state_effect_is_bound_to_exact_declaration_even_when_marked_view(self):
        self.function.view = True
        self.assertEqual([11], self.result()['transitiveStateWrites'])
        self.assertEqual(7, self.result()['declarationId'])

    def test_unbound_generated_variable_is_a_gap_not_a_named_resource_guess(self):
        self.function.state_variables_written.append(_Record(source_mapping=None))
        result = self.result()
        self.assertFalse(result['complete'])
        self.assertIn('SlithIR 状态变量未绑定 AST 声明', result['gaps'])

    def test_real_call_semantics_keep_non_static_call_incomplete(self):
        for static in [True, False]:
            with self.subTest(static=static):
                operation = type('HighLevelCall', (), {})()
                operation.function = None
                operation.node = _Record(source_mapping=self.location(25, 8))
                operation.is_static_call = lambda: static
                self.operations[:] = [operation]
                result = self.result()
                self.assertEqual('STATICCALL' if static else 'CALL', result['calls'][0]['semantics'])
                self.assertEqual(static, result['complete'])

    def test_storage_receiver_root_is_recorded_without_claiming_alias_effect_completion(self):
        self.bundle['functions'][8] = {'parameters': [{'id': 81, 'storageLocation': 'storage'}]}
        operation = type('InternalCall', (), {})()
        operation.function = _Record(id=8, contains_assembly=False)
        operation.arguments = [_Record(points_to_origin=self.variable)]
        operation.node = _Record(source_mapping=self.location(30, 9))
        self.operations.append(operation)
        self.internal.append(operation)
        result = self.result()
        self.assertFalse(result['complete'])
        self.assertEqual(11, result['calls'][0]['storageArguments'][0]['passedStorageRootDeclarationId'])
        self.assertEqual(81, result['calls'][0]['storageArguments'][0]['targetParameterDeclarationId'])

    def test_assembly_in_transitive_modifier_keeps_coverage_incomplete(self):
        modifier = _Record(id=9, contains_assembly=True, internal_calls=[], library_calls=[], modifiers=[])
        self.function.modifiers.append(modifier)
        result = self.result()
        self.assertFalse(result['complete'])
        self.assertIn('存在汇编语义', result['gaps'])


class SlithIRReferenceTest(unittest.TestCase):
    """引用定义与实际操作分别绑定，歧义或内存副本不能转成状态写入。"""

    def setUp(self):
        SlithIREffectTest.setUp(self)
        self.variable.name = 'Acc'
        self.field = _Record(name='balance', source_mapping=self.location(15, 4), type='uint256')
        self.bundle['declarations'].update({
            12: {'nodeType': 'VariableDeclaration', 'stateVariable': False, 'src': '15:4:0'},
            13: {'nodeType': 'VariableDeclaration', 'stateVariable': False, 'src': '20:4:0',
                 'storageLocation': 'default', 'typeDescriptions': {'typeIdentifier': 't_struct$_Holder_$1_storage_ptr'}}})
        self.bundle['nodes'] = dict(self.bundle['declarations'])
        self.bundle['nodes'].update({
            21: {'id': 21, 'nodeType': 'IndexAccess', 'src': '30:15:0'},
            22: {'id': 22, 'nodeType': 'MemberAccess', 'src': '34:10:0', 'memberName': 'sender',
                 'expression': {'nodeType': 'Identifier', 'name': 'msg'}},
            23: {'id': 23, 'nodeType': 'MemberAccess', 'src': '50:11:0', 'referencedDeclaration': 12},
            24: {'id': 24, 'nodeType': 'Assignment', 'src': '50:16:0'}})
        struct_type = _Record(type=_Record(elems={'balance': self.field}))
        self.reference = _Record(name='REF_0', type=struct_type, points_to_origin=self.variable)
        self.alias = type('LocalVariable', (), {})()
        self.alias.name = 'acc'; self.alias.is_storage = True
        self.alias.source_mapping = self.location(20, 4)
        self.alias.type = struct_type
        self.member = _Record(name='REF_1', type='uint256', points_to_origin=self.alias)
        key = type('SolidityVariableComposed', (), {})(); key.name = 'msg.sender'
        index = type('Index', (), {})()
        index.variable_left = self.variable; index.variable_right = key; index.lvalue = self.reference
        index.expression = _Record(source_mapping=self.location(30, 15),
                                   expression_right=_Record(source_mapping=self.location(34, 10)))
        index.node = _Record(source_mapping=self.location(25, 21)); index.read = [self.variable, key]
        alias = type('Assignment', (), {})()
        alias.lvalue = self.alias; alias.rvalue = self.reference; alias.read = [self.reference]
        alias.expression = _Record(source_mapping=self.location(30, 15)); alias.node = index.node
        member = type('Member', (), {})()
        member.variable_left = self.alias; member.variable_right = _Record(value='balance'); member.lvalue = self.member
        member.expression = _Record(source_mapping=self.location(50, 11))
        member.node = _Record(source_mapping=self.location(50, 16)); member.read = [self.alias]
        write = type('Binary', (), {})()
        write.lvalue = self.member; write.read = [self.member]
        write.expression = _Record(source_mapping=self.location(50, 16)); write.node = member.node
        self.operations[:] = [index, alias, member, write]
        self.function.slithir_operations = self.operations

    location = SlithIREffectTest.location
    result = SlithIREffectTest.result

    def test_状态引用绑定真实key字段与写入跨度且不把别名初始化当作写入(self):
        result = self.result()
        alias = next(item for item in result['referenceBindings'] if item['irVariable'] == 'acc')
        self.assertEqual('BOUND', alias['bindingStatus'])
        self.assertEqual(11, alias['rootDeclarationId'])
        self.assertEqual({'kind': 'BUILTIN', 'name': 'msg.sender'}, alias['path'][0]['key']['value'])
        writes = [item for item in result['stateAccesses'] if item['mode'] == 'WRITE']
        self.assertEqual(1, len(writes))
        self.assertEqual(12, writes[0]['path'][1]['memberDeclarationId'])
        self.assertEqual(24, writes[0]['astNodeId'])
        self.assertEqual({'sourceUnit': 'contracts/C.sol', 'start': 50, 'length': 16}, writes[0]['expressionSpan'])

    def test_一个storage别名出现多个定义时保留未知(self):
        self.operations.insert(2, copy.copy(self.operations[1]))
        result = self.result()
        alias = next(item for item in result['referenceBindings'] if item['irVariable'] == 'acc')
        self.assertEqual('UNRESOLVED', alias['bindingStatus'])
        writes = [item for item in result['stateAccesses'] if item['mode'] == 'WRITE']
        self.assertEqual('UNRESOLVED', writes[0]['bindingStatus'])
        self.assertIsNone(writes[0]['rootDeclarationId'])

    def test_旧版Slither局部变量跨度覆盖整个声明语句时绑定唯一子声明(self):
        child = dict(self.bundle['declarations'][13], id=13)
        self.bundle['nodes'][26] = {'id': 26, 'nodeType': 'VariableDeclarationStatement', 'src': '20:26:0',
                                    'declarations': [child], 'assignments': [13]}
        self.alias.source_mapping = self.location(20, 26)
        alias = next(item for item in self.result()['referenceBindings'] if item['irVariable'] == 'acc')
        self.assertEqual((13, 11, 'BOUND'), (alias['declarationId'], alias['rootDeclarationId'], alias['bindingStatus']))

    def test_声明语句含多个局部变量时不按名字选择别名(self):
        child = dict(self.bundle['declarations'][13], id=13)
        self.bundle['nodes'][26] = {'id': 26, 'nodeType': 'VariableDeclarationStatement', 'src': '20:26:0',
                                    'declarations': [child, dict(child, id=14)], 'assignments': [13, 14]}
        self.alias.source_mapping = self.location(20, 26)
        self.assertFalse(any(item['irVariable'] == 'acc' and item['bindingStatus'] == 'BOUND'
                             for item in self.result()['referenceBindings']))

    def test_内存结构副本不绑定到原状态字段(self):
        self.alias.is_storage = False
        self.bundle['declarations'][13]['typeDescriptions']['typeIdentifier'] = 't_struct$_Holder_$1_memory_ptr'
        result = self.result()
        writes = [item for item in result['stateAccesses'] if item['mode'] == 'WRITE']
        self.assertFalse(any(item['bindingStatus'] == 'BOUND' and item['rootDeclarationId'] == 11 for item in writes))

    def test_字段AST与SlithIR声明冲突必须拒绝绑定(self):
        self.bundle['nodes'][23]['referencedDeclaration'] = 99
        write = next(item for item in self.result()['stateAccesses'] if item['mode'] == 'WRITE')
        self.assertEqual('UNRESOLVED', write['bindingStatus'])
        self.assertIsNone(write['path'][1]['memberDeclarationId'])

    def test_索引key的AST与实际IR主体冲突必须拒绝绑定(self):
        self.bundle['nodes'][22]['expression']['name'] = 'tx'
        write = next(item for item in self.result()['stateAccesses'] if item['mode'] == 'WRITE')
        self.assertEqual('UNRESOLVED', write['bindingStatus'])
        self.assertEqual('UNRESOLVED', write['path'][0]['key']['bindingStatus'])


if __name__ == '__main__':
    unittest.main()
