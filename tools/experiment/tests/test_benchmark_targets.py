"""公开漏洞与本机安全对照源按数据集标签分层登记。"""
import tempfile
import unittest
from pathlib import Path

from benchmark_targets import load_benchmark_targets


class BenchmarkTargetsTest(unittest.TestCase):
    def test_源码和标签分别保存且不把知识侧近克隆当测试(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / 'src/main/resources/document/smartbugs_kb'
            safe = root / 'src/main/resources/testset/safe_contracts'
            docs.mkdir(parents=True); safe.mkdir(parents=True)
            vulnerable = 'contract Vault { function take() public { msg.sender.call(""); } }'
            (docs / 'reentrancy__vault.md').write_text(
                '---\nCategory: reentrancy\nSource: https://example.test/vault\nVulnerable-Lines: 1\n---\n'
                + '```solidity\n' + vulnerable + '\n```\n')
            (safe / 'safe_23_Ownable.sol').write_text(
                'contract Ownable { function transferOwnership(address next) public onlyOwner { owner = next; } }')
            targets = load_benchmark_targets(root, [])
            self.assertEqual({True, False}, {row['groundTruth']['hasVulnerability'] for row in targets})
            self.assertTrue(all(row['runnable'] for row in targets))
            self.assertEqual('FUNCTION', next(row for row in targets if row['groundTruth']['hasVulnerability'] is False)['scope'])
            self.assertEqual([], [row for row in load_benchmark_targets(root, [{'text': vulnerable,
                'project': 'https://example.test/vault'}]) if row['groundTruth']['hasVulnerability'] is True])


if __name__ == '__main__':
    unittest.main()
