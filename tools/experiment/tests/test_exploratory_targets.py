"""公开目标源码只作探索性测试，不能自动得到安全负例。"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from exploratory_targets import load_targets


class ExploratoryTargetsTest(unittest.TestCase):
    def test_提取源码并排除与知识侧同组或近克隆目标(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = 'pragma solidity ^0.5.0;\ncontract Vault {\n uint balance;\n function take() public { msg.sender.call(""); balance = 0; }\n}'
            header = '---\nDataset: smartbugs-curated\nCategory: reentrancy\nSource: https://example.test/vault\nVulnerable-Lines: 4\n---\n'
            file = root / 'reentrancy__vault.md'
            file.write_text(header + '# 案例\n```solidity\n' + source + '\n```\n')
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
            (root / 'access_control__bad.md').write_text('---\nCategory: access_control\n---\n```solidity\ncontract A {}\n```')
            with self.assertRaises(ValueError):
                load_targets(root, [])


if __name__ == '__main__':
    unittest.main()
