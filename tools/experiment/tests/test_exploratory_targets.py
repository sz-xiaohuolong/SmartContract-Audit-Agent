"""公开目标源码只作探索性测试，不能自动得到安全负例。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from exploratory_targets import load_targets
from dataset_fixture import smartbugs_fixture


class ExploratoryTargetsTest(unittest.TestCase):
    def test_提取源码并排除与知识侧同组或近克隆目标(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = 'pragma solidity ^0.5.0;\ncontract Vault {\n uint balance;\n function take() public { msg.sender.call(""); balance = 0; }\n}'
            smartbugs_fixture(root, source, lines=(4,))
            targets = load_targets(root, [])
            self.assertEqual(1, len(targets))
            self.assertEqual('REENTRANCY', targets[0]['mechanism'])
            self.assertEqual([4], targets[0]['vulnerableLines'])
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), targets[0]['sourceHash'])
            self.assertEqual([], load_targets(root, [{'text': source, 'project': 'other'}]))
            self.assertEqual([], load_targets(root, [{'text': source.split('function')[1], 'project': 'other'}]))
            self.assertEqual([], load_targets(root, [{'text': 'different', 'project': 'https://example.test/vault'}]))

    def test_缺少可核标签时拒绝充作验证目标(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            smartbugs_fixture(root, 'contract A {}', category='access_control', lines=())
            with self.assertRaises(ValueError):
                load_targets(root, [])

    def test_原始字节和空白行保留且历史样本编号稳定(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = '\npragma solidity ^0.5.0;\r\ncontract Vault { function take() public {} }\r\n\r\n'
            path = smartbugs_fixture(root, source, lines=(3,))
            row = load_targets(root, [])[0]
            relative = path.relative_to(root).as_posix()
            suffix = hashlib.sha1(relative.encode()).hexdigest()[:10]
            self.assertEqual('reentrancy__dataset_reentrancy_vault__' + suffix, row['sampleId'])
            self.assertEqual(source, row['source'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row['sourceHash'])
            self.assertEqual([3], row['vulnerableLines'])
            self.assertEqual(relative, row['sourcePath'])
            self.assertEqual('vulnerabilities.json', row['metadataPath'])
            self.assertEqual(hashlib.sha256((root / 'vulnerabilities.json').read_bytes()).hexdigest(), row['metadataHash'])
            self.assertFalse(row['researchEligible'])

    def test_缺少原始数据集时显式报错(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'vulnerabilities.json'):
                load_targets(directory, [])

    def test_标注不能越界读取源码或重复登记(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            smartbugs_fixture(root, 'contract A {}')
            path = root / 'vulnerabilities.json'
            entry = json.loads(path.read_text())[0]
            for entries in ([entry, entry], [{**entry, 'path': '../outside.sol'}]):
                path.write_text(json.dumps(entries))
                with self.assertRaises(ValueError):
                    load_targets(root, [])


if __name__ == '__main__':
    unittest.main()
