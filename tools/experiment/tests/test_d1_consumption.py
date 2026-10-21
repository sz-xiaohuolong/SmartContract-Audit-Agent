"""自动标注消费层只识别可见改动，不把片段改动当作适用性证明。"""
import unittest

from verirag.retrieval.d1_consumption import NO_CHANGE, candidate_context, mechanism_changed, pair_snippets, risk_bindings, soft_pairs
from verirag.analysis.program_facts import extract_facts


class D1ConsumptionTest(unittest.TestCase):
    def pair(self, identity, before, after, score=.9, mechanism='ACCESS_CONTROL'):
        base = {'pairId': identity, 'mechanism': mechanism,
                'riskKind': 'WRITE' if mechanism == 'ACCESS_CONTROL' else 'CALL',
                'conditions': [], 'reviewed': False, 'denseScore': score}
        return [{**base, 'caseId': identity + '-before', 'chunkId': identity + '-before',
                 'role': 'VULNERABLE', 'text': before},
                {**base, 'caseId': identity + '-after', 'chunkId': identity + '-after',
                 'role': 'DEFENSE', 'text': after}]

    def test_文字标签和标识符改名不构成机制变化(self):
        self.assertFalse(mechanism_changed('旧代码', '新代码', 'REENTRANCY'))
        self.assertFalse(mechanism_changed('require(msg.sender == owner);',
                                          'require(msg.sender == admin);', 'ACCESS_CONTROL'))
        self.assertFalse(mechanism_changed('delete balances[msg.sender]; receiver.call("");',
                                          'delete credits[msg.sender]; payee.call("");', 'REENTRANCY'))

    def test_注释和字符串中的权限文本不能生成机制事件(self):
        before = 'value = next;'
        after = before + '\n// require(msg.sender == admin);\n'
        after += 'string s = "onlyOwner require(msg.sender == admin);";\n/* nonReentrant */'
        self.assertFalse(mechanism_changed(before, after, 'ACCESS_CONTROL'))
        self.assertFalse(mechanism_changed(before, after, 'REENTRANCY'))

    def test_不完整权限条件不能冒充完整条件(self):
        self.assertFalse(mechanism_changed('value = next;',
                                          'require(msg.sender == admin', 'ACCESS_CONTROL'))

    def test_重入消费识别调用与索引写入的先后变化(self):
        self.assertTrue(mechanism_changed('msg.sender.call("");\ncredit[msg.sender] = 0;',
                                         'credit[msg.sender] = 0;\nmsg.sender.call("");', 'REENTRANCY'))

    def test_摘要从700字符以后的真实权限改动定位窗口(self):
        prefix = '// 普通说明\n' * 100
        before = prefix + 'value = next;\n'
        after = prefix + 'require(msg.sender == admin);\nvalue = next;\n'
        left, right = pair_snippets(before, after, 'ACCESS_CONTROL')
        self.assertIn('require(msg.sender == admin)', right)
        self.assertIn('原片段第', right)
        self.assertTrue(mechanism_changed(left, right, 'ACCESS_CONTROL'))
        self.assertLessEqual(max(len(left), len(right)), 900)

    def test_摘要预算不足不能留下似乎完整的软配对(self):
        before = 'value = next;'
        after = 'require(msg.sender == admin && ' + 'allowed[msg.sender] && ' * 100 + 'true);'
        left, right = pair_snippets(before, after, 'ACCESS_CONTROL', limit=160)
        self.assertTrue(left.startswith(NO_CHANGE))
        self.assertTrue(right.startswith(NO_CHANGE))
        self.assertLessEqual(max(len(left), len(right)), 160)
        self.assertFalse(mechanism_changed(left, right, 'ACCESS_CONTROL'))

    def test_两对去重且实际中文上下文字节参与预算(self):
        rows = self.pair('一', 'value1 = next;', 'require(msg.sender == admin); value1 = next;')
        rows += self.pair('二', 'value2 = next;', 'require(msg.sender == admin); value2 = next;', .8)
        rows += self.pair('三', rows[0]['text'], rows[1]['text'], .7)
        result = soft_pairs({'candidates': rows}, 'ACCESS_CONTROL')
        self.assertEqual(4, len(result['selected']))
        self.assertEqual(len(result['context'].encode()), result['usedBytes'])
        self.assertLessEqual(result['usedBytes'], 4096)
        self.assertEqual({'UNKNOWN'}, {row['applicability'] for row in result['evaluations'].values()})
        self.assertNotIn('|DEFENSE]', result['context'])
        first_cost = sum(len(candidate_context(row, True).encode()) for row in rows[:2])
        exact = soft_pairs({'candidates': rows[:2]}, 'ACCESS_CONTROL', max_bytes=first_cost)
        self.assertEqual(2, len(exact['selected']))
        under = soft_pairs({'candidates': rows[:2]}, 'ACCESS_CONTROL', max_bytes=first_cost - 1)
        self.assertEqual([], under['selected'])

    def test_不同机制不同风险类型或者相同案例不能配对(self):
        for field, value in [('mechanism', 'REENTRANCY'), ('riskKind', 'CALL'), ('caseId', 'p-before')]:
            with self.subTest(field=field):
                rows = self.pair('p', 'value = next;', 'require(msg.sender == admin); value = next;')
                rows[1][field] = value
                self.assertEqual([], soft_pairs({'candidates': rows}, 'ACCESS_CONTROL')['selected'])

    def test_两个改动前与一个改动后不能按分数猜配对(self):
        rows = self.pair('p', 'value = next;', 'require(msg.sender == admin); value = next;')
        rows.insert(1, {**rows[0], 'caseId': 'other-before', 'chunkId': 'other-before',
                        'text': 'otherValue = next;', 'denseScore': .99})
        self.assertEqual([], soft_pairs({'candidates': rows}, 'ACCESS_CONTROL')['selected'])

    def test_登记多义标识不能被仅剩两条的池重新配对(self):
        marker = '【配对关系不唯一，禁止软配对】\n'
        rows = self.pair('p', marker + 'value = next;', marker + 'require(msg.sender == admin); value = next;')
        self.assertEqual([], soft_pairs({'candidates': rows}, 'ACCESS_CONTROL')['selected'])

    def test_CALL有多个主体资源或者主体不一致时不猜测资源(self):
        source = ('contract C { mapping(address => uint) a; mapping(address => uint) b;\n'
                  'function f() public { msg.sender.call(""); a[msg.sender] = 0; b[msg.sender] = 0; } }')
        facts = extract_facts(source)
        risk = next(row for row in facts['facts'] if row['kind'] == 'CALL')
        self.assertEqual({'actor': 'msg.sender'}, risk_bindings(facts, risk))
        source = source.replace('msg.sender.call', 'receiver.call').replace('b[msg.sender] = 0;', '')
        facts = extract_facts(source)
        risk = next(row for row in facts['facts'] if row['kind'] == 'CALL')
        self.assertEqual({'actor': 'msg.sender'}, risk_bindings(facts, risk))

    def test_权限标的仅来自风险前的唯一真实状态检查(self):
        source = ('contract C { address admin; uint value;\n'
                  'function f() public { require(msg.sender == admin); value = 1; } }')
        facts = extract_facts(source)
        risk = next(row for row in facts['facts'] if row['kind'] == 'WRITE')
        self.assertEqual({'actor': 'msg.sender', 'resource': 'value', 'authority': 'admin'}, risk_bindings(facts, risk))
        source = source.replace('address admin;', 'address admin; address manager;').replace('value = 1;',
                  'require(msg.sender == manager); value = 1;')
        facts = extract_facts(source)
        risk = next(row for row in facts['facts'] if row['kind'] == 'WRITE')
        self.assertNotIn('authority', risk_bindings(facts, risk))


if __name__ == '__main__':
    unittest.main()
