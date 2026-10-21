"""运行时编译接缝只用本地子进程夹具，缺闭包不得回落为安全。"""
import hashlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_compiler_facts as fixtures


class CompilationRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompilerFactsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def target(self):
        source = self.fixture.source
        return {'fullSource': source, 'sourceHash': hashlib.sha256(source.encode()).hexdigest(),
                'candidateContracts': ['C']}

    def compiler_environment(self, output=None, error=None):
        if output is not None:
            (self.fixture.root / 'output.json').write_text(json.dumps(output))
        body = ('sys.stderr.write(' + repr(error) + '); sys.exit(1)' if error else
                'sys.stdout.buffer.write((Path(__file__).parent/"output.json").read_bytes())')
        self.fixture.binary.write_text('#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n'
            'if sys.argv[1:] == ["--version"]: print("solc fixture\\nVersion: 0.8.15+fixture")\n'
            'else:\n    sys.stdin.buffer.read()\n    ' + body + '\n')
        return {'status': 'OK', 'compiler': {'path': str(self.fixture.binary),
            'sha256': hashlib.sha256(self.fixture.binary.read_bytes()).hexdigest()}}

    def test_发现预编译不消费候选合约或真值(self):
        from verirag.analysis.compilation_runtime import prepare_discovery_compilation
        target = {**self.target(), 'candidateContracts': ['不存在'], 'contract': '不存在',
                  'groundTruth': {'contract': '不存在'}, 'vulnerableLines': [999]}
        before = copy.deepcopy(target)
        with patch('verirag.analysis.compilation_runtime.resolve_environment', return_value=self.compiler_environment()):
            manifest = prepare_discovery_compilation(self.fixture.root, target)
        self.assertEqual('C', manifest['targetContract'])
        self.assertEqual(before, target)
        from verirag.analysis.compiler_facts import load_bound_compilation
        self.assertEqual('RECOMPILED_MATCH', load_bound_compilation(manifest, self.fixture.root)['verificationStatus'])

    def test_发现预编译缺可绑定主源码合约不能返回空成功(self):
        from verirag.analysis.compilation_runtime import prepare_discovery_compilation
        output = copy.deepcopy(self.fixture.output)
        output['contracts']['contracts/C.sol'] = {}
        with patch('verirag.analysis.compilation_runtime.resolve_environment', return_value=self.compiler_environment(output)):
            with self.assertRaisesRegex(ValueError, '主源码.*合约'):
                prepare_discovery_compilation(self.fixture.root, self.target())

    def test_旧编译器不支持协议须明确诊断并保留原输出(self):
        from verirag.analysis.compilation_runtime import prepare_compilation
        message = 'unrecognised option --standard-json\n'
        with patch('verirag.analysis.compilation_runtime.resolve_environment', return_value=self.compiler_environment(error=message)):
            with self.assertRaisesRegex(ValueError, '不支持.*standard-json'):
                prepare_compilation(self.fixture.root, self.target())
        logs = list((self.fixture.root / 'research-artifacts/receipts/compilations').glob('*/compiler-stderr.log'))
        self.assertEqual(1, len(logs))
        self.assertEqual(message, logs[0].read_text())

    def test_错误编译输出须保留明确失败而非JSON解析异常(self):
        from verirag.analysis.compilation_runtime import prepare_compilation
        with patch('verirag.analysis.compilation_runtime.resolve_environment', return_value=self.compiler_environment(error='compiler crashed')):
            with self.assertRaisesRegex(ValueError, '固定编译器执行失败'):
                prepare_compilation(self.fixture.root, self.target())

    def test_实际标准输入输出生成可重新核验收据(self):
        from verirag.analysis.compilation_runtime import prepare_compilation
        environment = {'status': 'OK', 'compiler': {'path': str(self.fixture.binary),
            'sha256': hashlib.sha256(self.fixture.binary.read_bytes()).hexdigest()}}
        # 输出夹具校验器由此测试的输入捕获替代，仍实际执行本地编译子进程。
        self.fixture.binary.write_text('#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n'
            'if sys.argv[1:] == ["--version"]: print("solc fixture\\nVersion: 0.8.15+fixture")\n'
            'else: sys.stdin.buffer.read(); sys.stdout.buffer.write((Path(__file__).parent/"output.json").read_bytes())\n')
        environment['compiler']['sha256'] = hashlib.sha256(self.fixture.binary.read_bytes()).hexdigest()
        with patch('verirag.analysis.compilation_runtime.resolve_environment', return_value=environment):
            manifest = prepare_compilation(self.fixture.root, self.target())
        from verirag.analysis.compiler_facts import load_bound_compilation
        bundle = load_bound_compilation(manifest, self.fixture.root)
        self.assertEqual('RECOMPILED_MATCH', bundle['verificationStatus'])
        self.assertEqual('C', bundle['targetContract'])
        selection = bundle['input']['settings']['outputSelection']['*']['*']
        self.assertTrue({'evm.bytecode.sourceMap', 'evm.deployedBytecode.sourceMap',
                         'evm.methodIdentifiers'}.issubset(selection), '真实 Slither 必须消费原编译收据中的源码映射')

    def test_错源码多合约与缺依赖均拒绝(self):
        from verirag.analysis.compilation_runtime import prepare_compilation
        target = self.target()
        target['sourceHash'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '源码'):
            prepare_compilation(self.fixture.root, target)
        target = self.target()
        target['candidateContracts'] = ['C', 'D']
        with self.assertRaisesRegex(ValueError, '合约'):
            prepare_compilation(self.fixture.root, target)
        target = self.target()
        target['fullSource'] = 'import "missing.sol"; ' + target['fullSource']
        target.pop('sourceHash')
        with self.assertRaisesRegex(ValueError, '依赖'):
            prepare_compilation(self.fixture.root, target)

    def test_候选复用发现收据且事实身份不漂移(self):
        from verirag.analysis.compilation_runtime import prepare_candidate_compilations
        from verirag.analysis.compiler_facts import load_bound_compilation, extract_compiler_facts
        original = load_bound_compilation(self.fixture.manifest, self.fixture.root)
        target = {**self.target(), 'discoveryCompilation': self.fixture.manifest,
                  'compilerTemplate': self.fixture.manifest}
        before = copy.deepcopy(target)
        manifest = prepare_candidate_compilations(self.fixture.root, target)
        bundle = load_bound_compilation(manifest, self.fixture.root)
        self.assertEqual(original['receiptDigest'], bundle['receiptDigest'])
        self.assertEqual(original['environmentHash'], bundle['environmentHash'])
        self.assertEqual(extract_compiler_facts(original), extract_compiler_facts(bundle))
        self.assertEqual(before, target)

    def test_多合约投影逐项拒绝错合约而保留合法收据(self):
        from verirag.analysis.compilation_runtime import prepare_candidate_compilations
        target = {**self.target(), 'candidateContracts': ['C', '不存在'],
                  'discoveryCompilation': self.fixture.manifest, 'compilerTemplate': self.fixture.manifest}
        result = prepare_candidate_compilations(self.fixture.root, target)
        self.assertEqual(self.fixture.manifest['bindingSha256'], result['manifests']['C']['bindingSha256'])
        self.assertNotIn('不存在', result['manifests'])
        self.assertIn('不存在', result['errors'])

    def test_发现收据丢失不能重新编译掩盖身份失败(self):
        from verirag.analysis.compilation_runtime import prepare_candidate_compilations
        manifest = {**self.fixture.manifest, 'bindingPath': 'missing.json'}
        with self.assertRaises(ValueError):
            prepare_candidate_compilations(self.fixture.root,
                {**self.target(), 'discoveryCompilation': manifest,
                 'compilerTemplate': self.fixture.manifest})


if __name__ == '__main__':
    unittest.main()
