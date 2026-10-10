"""公开漏洞与本机安全对照源按数据集标签分层登记。"""
import tempfile
import unittest
import hashlib
from pathlib import Path

from benchmark_targets import load_benchmark_targets, _scopes, _record


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
            self.assertTrue(all(row.get('sourceKind') == 'BENCHMARK' for row in targets))
            self.assertEqual('FULL', next(row for row in targets if row['groundTruth']['hasVulnerability'] is False)['scope'])
            self.assertEqual([], [row for row in load_benchmark_targets(root, [{'text': vulnerable,
                'project': 'https://example.test/vault'}]) if row['groundTruth']['hasVulnerability'] is True])

    def test_发现范围和函数不随真值行变化(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / 'src/main/resources/document/smartbugs_kb'
            docs.mkdir(parents=True)
            path = docs / 'reentrancy__vault.md'
            source = ('contract Vault {\n'
                      ' function first() public { msg.sender.call(""); }\n'
                      ' function second() public { msg.sender.call(""); }\n}')
            rows = []
            for line in (2, 3):
                path.write_text('---\nCategory: reentrancy\nSource: https://example.test/vault\n'
                                f'Vulnerable-Lines: {line}\n---\n```solidity\n{source}\n```\n')
                rows.append(load_benchmark_targets(root, [])[0])
            self.assertEqual(rows[0]['function'], rows[1]['function'])
            self.assertEqual(rows[0]['modelSource'], rows[1]['modelSource'])
            self.assertEqual('DISCOVERY', rows[0]['taskKind'])
            self.assertEqual([2], rows[0]['vulnerableLines'])
            self.assertEqual([3], rows[1]['vulnerableLines'])

    def test_发现范围不随阳性阴性标签变化(self):
        source = 'contract C {\n function a() public {}\n function b() public {}\n}'
        positive = _record('c', source, 'ACCESS_CONTROL', 'a', (2, 2), True, '标签', '项目')
        negative = _record('c', source, 'ACCESS_CONTROL', 'a', (2, 2), False, '标签', '项目')
        self.assertEqual(positive['modelSource'], negative['modelSource'])
        self.assertEqual(positive['scope'], negative['scope'])

    def test_答案注释不进入消费文本且原件和消费摘要各自准确(self):
        source = '// <yes> <report> REENTRANCY https://example.test/answer\ncontract C { function a() public {} }'
        target = _record('c', source, 'REENTRANCY', 'a', (2, 2), True, '标签', '项目')
        self.assertNotIn('<yes>', target['fullSource'])
        self.assertEqual(source, target['originalSource'])
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), target['originalSourceHash'])
        self.assertEqual(hashlib.sha256(target['fullSource'].encode()).hexdigest(), target['sourceHash'])
        self.assertEqual(hashlib.sha256(target['modelSource'].encode()).hexdigest(), target['modelSourceHash'])

    def test_超长发现不按标签自动缩到漏洞函数(self):
        source = 'contract C {\n' + ' uint value;\n' * 600 + ' function a() public { value = 1; }\n}'
        target = _record('c', source, 'ACCESS_CONTROL', 'a', (602, 602), True, '标签', '项目')
        self.assertFalse(target['runnable'])
        self.assertEqual(source, target['modelSource'])
        self.assertEqual('FULL', target['scope'])
        self.assertEqual('EXPLICIT_SCOPE_REQUIRED', target['inputStatus'])

    def test_旧版无名回退函数与现代构造函数名称规范化(self):
        source = 'contract A { function() public {} constructor() {} fallback() external {} receive() external payable {} }'
        self.assertEqual(['fallback', 'constructor', 'fallback', 'receive'], [row[0] for row in _scopes(source)])


if __name__ == '__main__':
    unittest.main()
