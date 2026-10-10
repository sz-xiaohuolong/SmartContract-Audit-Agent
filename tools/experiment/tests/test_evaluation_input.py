"""评测源码清理的词法与原始位置约束。"""
import unittest

from benchmark_targets import _record


class EvaluationInputTest(unittest.TestCase):
    def target(self, source):
        return _record('fixture', source, 'ACCESS_CONTROL', 'a', None, True, '标签', '项目')

    def test_字符串内标签网址和注释符号必须保留(self):
        source = ('// <yes> <report> ACCESS_CONTROL\ncontract C {\n'
                  ' string s = "<yes> https://example.test/answer /* marker */ // end";\n'
                  ' string q = \'<report> \\\' quote\';\n'
                  ' function a() public {}\n}')
        clean = self.target(source)['fullSource']
        self.assertEqual(' ' * len('// <yes> <report> ACCESS_CONTROL'), clean.splitlines()[0])
        self.assertEqual(source.splitlines()[2:], clean.splitlines()[2:])

    def test_块注释清理保持每一行以及语句原始列(self):
        source = ('/* @vulnerable_at_lines 5\r\n * Source: https://example.test/answer\r\n */\r\n'
                  'contract C {\r\n function a() public { /* <yes> */ owner = msg.sender; }\r\n}')
        clean = self.target(source)['fullSource']
        self.assertNotIn('@vulnerable_at_lines', clean)
        self.assertEqual(len(source), len(clean))
        self.assertEqual(source.count('\r\n'), clean.count('\r\n'))
        self.assertEqual(source.index('owner ='), clean.index('owner ='))

    def test_未闭合字符串与注释拒绝生成清理输入(self):
        for source in ('contract C { string s = "<yes>;', 'contract C { /* <yes>'):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    self.target(source)

    def test_清理回执只记录位置和摘要而不回填答案(self):
        target = self.target('// <yes>\ncontract C { function a() public {} }')
        self.assertNotIn('<yes>', target['fullSource'])
        receipt = target['inputGovernanceReceipt']
        self.assertEqual(target['originalSourceHash'], receipt['originalSourceHash'])
        self.assertEqual(target['fullSourceHash'], receipt['fullSourceHash'])
        self.assertEqual([{'kind': 'LINE_COMMENT', 'lineStart': 1, 'lineEnd': 1}], receipt['removedComments'])
        self.assertTrue(receipt['lineNumbersPreserved'])
        self.assertNotIn('<yes>', str(receipt))


if __name__ == '__main__':
    unittest.main()
