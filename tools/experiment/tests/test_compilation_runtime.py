"""运行时编译接缝只用本地子进程夹具，缺闭包不得回落为安全。"""
import hashlib
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

    def test_实际标准输入输出生成可重新核验收据(self):
        from compilation_runtime import prepare_compilation
        environment = {'status': 'OK', 'compiler': {'path': str(self.fixture.binary),
            'sha256': hashlib.sha256(self.fixture.binary.read_bytes()).hexdigest()}}
        # 输出夹具校验器由此测试的输入捕获替代，仍实际执行本地编译子进程。
        self.fixture.binary.write_text('#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n'
            'if sys.argv[1:] == ["--version"]: print("solc fixture\\nVersion: 0.8.15+fixture")\n'
            'else: sys.stdin.buffer.read(); sys.stdout.buffer.write((Path(__file__).parent/"output.json").read_bytes())\n')
        environment['compiler']['sha256'] = hashlib.sha256(self.fixture.binary.read_bytes()).hexdigest()
        with patch('compilation_runtime.resolve_environment', return_value=environment):
            manifest = prepare_compilation(self.fixture.root, self.target())
        from compiler_facts import load_bound_compilation
        bundle = load_bound_compilation(manifest, self.fixture.root)
        self.assertEqual('RECOMPILED_MATCH', bundle['verificationStatus'])
        self.assertEqual('C', bundle['targetContract'])

    def test_错源码多合约与缺依赖均拒绝(self):
        from compilation_runtime import prepare_compilation
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


if __name__ == '__main__':
    unittest.main()
