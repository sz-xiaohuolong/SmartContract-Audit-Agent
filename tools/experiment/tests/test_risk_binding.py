"""风险容差只接受唯一实际操作，保留原行并拒绝多义绑定。"""
import unittest
from types import SimpleNamespace

from risk_binding import bind_risks


class RiskBindingTest(unittest.TestCase):
    def operation(self, identity, line, end=None):
        return {'id': identity, 'nodeId': identity, 'kind': 'CALL', 'callKind': 'CALL',
                'line': line, 'span': {'line': line, 'endLine': end or line,
                    'start': identity, 'length': 1, 'sourceUnit': 'C.sol'}}

    def bound(self, line, nodes, **fields):
        return bind_risks(SimpleNamespace(nodes=nodes), {'riskOperation': 'CALL',
            'riskLine': line, **fields}, {'nodes': {}, 'units': {}}, {'facts': []})

    def test_同操作跨度内可绑定且不改原行(self):
        node = self.operation(1, 10, 14)
        self.assertEqual([node], self.bound(13, [node]))
        self.assertEqual(10, node['line'])

    def test_正负两行接受唯一操作(self):
        node = self.operation(1, 10)
        self.assertEqual([node], self.bound(8, [node]))
        self.assertEqual([node], self.bound(12, [node]))
        self.assertEqual([], self.bound(13, [node]))

    def test_精确行优先而多义容差不猜(self):
        one, two = self.operation(1, 10), self.operation(2, 12)
        self.assertEqual([one], self.bound(10, [one, two]))
        self.assertEqual([], self.bound(11, [one, two]))

    def test_显式事实与跨度漂移拒绝(self):
        node = self.operation(1, 10)
        self.assertEqual([], self.bound(10, [node], riskFactId='forged'))
        self.assertEqual([], self.bound(10, [node], riskSpan={**node['span'], 'start': 5}))

    def test_不同操作与未知调用类型不混用(self):
        node = self.operation(1, 10)
        self.assertEqual([], self.bound(10, [dict(node, kind='WRITE')]))
        self.assertEqual([], self.bound(10, [dict(node, callKind='UNKNOWN')]))

    def test_真实UTF8语句跨度结束行由原字节计算(self):
        content = '前缀\nreceiver\n  .call\n  {value: amount}\n  (\n    ""\n  );\n'
        start = len('前缀\n'.encode())
        node = self.operation(1, 2)
        node['span'].update(start=start, length=len(content.encode()) - start - 1)
        statement = {'id': 2, 'nodeType': 'ExpressionStatement',
                     'src': f'{start}:{len(content.encode()) - start - 1}:0'}
        bundle = {'nodes': {2: statement}, 'units': {0: {'sourceUnit': 'C.sol', 'content': content}}}
        self.assertEqual([node], bind_risks(SimpleNamespace(nodes=[node]),
            {'riskOperation': 'CALL', 'riskLine': 6}, bundle, {'facts': []}))

    def test_同语句存在两个调用时即使只有一个操作跨度包含候选也不猜(self):
        content = 'x =\n first(\n  second()\n );\n'
        first, second = self.operation(1, 2), self.operation(2, 3)
        first['span'].update(start=5, length=21)
        second['span'].update(start=14, length=8)
        bundle = {'nodes': {9: {'id': 9, 'nodeType': 'ExpressionStatement', 'src': '0:26:0'}},
                  'units': {0: {'sourceUnit': 'C.sol', 'content': content}}}
        self.assertEqual([], bind_risks(SimpleNamespace(nodes=[first, second]),
            {'riskOperation': 'CALL', 'riskLine': 4}, bundle, {'facts': []}))

    def test_其他源码单元不因行号接近而绑定(self):
        node = self.operation(1, 10)
        bundle = {'nodes': {}, 'units': {}, 'targetSourceUnit': 'Target.sol'}
        self.assertEqual([], bind_risks(SimpleNamespace(nodes=[node]),
            {'riskOperation': 'CALL', 'riskLine': 10}, bundle, {'facts': []}))
