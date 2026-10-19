"""本机执行提供器的准入、源映射与持久状态断言，全部使用离线数据。"""
import unittest
import tempfile
from pathlib import Path

from evm_witness import map_program_counters, check_cei_trace, check_authority_trace, _Rpc, _normal_trace, _access_fact, _Session
import evm_witness


class EvmWitnessTest(unittest.TestCase):
    def test_执行失败类别明确且始终返回未知(self):
        from unittest.mock import patch
        bundle = {'verificationStatus': 'RECOMPILED_MATCH'}
        for category in ('SEARCH_NO_WITNESS', 'TRANSACTION_REVERTED', 'BUDGET_EXHAUSTED',
                         'UNSUPPORTED_SEMANTICS', 'REPLAY_MISMATCH'):
            with self.subTest(category=category), tempfile.TemporaryDirectory() as directory:
                with patch('evm_witness._configuration', return_value={}), \
                     patch('evm_witness._execution_artifacts', side_effect=evm_witness._WitnessFailure(category, '本地失败夹具')):
                    result = evm_witness.execute_bound_witness(bundle, {}, None, None, None,
                        {'status': 'MATCH'}, root=directory)
                self.assertEqual('UNKNOWN', result['status'])
                self.assertEqual(category, result['failureKind'])
                self.assertEqual(0, result['paidModelRequests'])
                self.assertEqual(0, result['executionSummary']['transactions'])

    def test_缺执行环境与缺双收据分别登记(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            with patch('evm_witness._configuration', side_effect=FileNotFoundError('缺本机配置')):
                result = evm_witness.execute_bound_witness({'verificationStatus': 'RECOMPILED_MATCH'},
                    {}, None, None, None, {'status': 'MATCH'}, root=directory)
            self.assertEqual(('UNKNOWN', 'ENVIRONMENT_UNAVAILABLE'), (result['status'], result['failureKind']))
            result = evm_witness.execute_bound_witness({}, {}, None, None, None, {}, root=directory)
            self.assertEqual(('UNKNOWN', 'BINDING_MISSING'), (result['status'], result['failureKind']))

    def test_构造回滚与等待回执超时按实际原因分类(self):
        from unittest.mock import Mock, patch
        session = object.__new__(_Session)
        session.accounts = ['0xaa']; session.records = []; session.deployments = []
        record = {'receipt': {'status': '0x0'}, 'trace': {'failed': True, 'structLogs': []}}
        artifact = {'abi': [], 'evm': {'bytecode': {'object': '00'}}}
        with patch.object(session, 'transact', return_value=record), self.assertRaises(ValueError) as failure:
            session.deploy(artifact, [], 'fixture')
        self.assertEqual('TRANSACTION_REVERTED', evm_witness._failure_kind(failure.exception))
        session.timestamp = 1; session.started = 0; session.rpc = Mock()
        session.rpc.call.side_effect = [None, '0xabc', None]
        with patch('evm_witness.time.monotonic', side_effect=[0, 0, 6]), self.assertRaises(ValueError) as failure:
            session.transact(sender='0xaa', data='0x')
        self.assertEqual('TIMEOUT', evm_witness._failure_kind(failure.exception))

    def trace(self, logs, failed=False):
        return {'failed': failed, 'structLogs': logs}

    def call(self):
        # EVM 栈从末端取 gas、目标、数值；仅使用普通业务转账。
        return {'pc': 4, 'op': 'CALL', 'depth': 1,
                'stack': ['0', '0', '0', '0', '1', 'aa', 'ffff'], 'storage': {'01': '02'}}

    def write(self):
        return {'pc': 5, 'op': 'SSTORE', 'depth': 1, 'stack': ['1', '1']}

    def test_源映射按PUSH步长展开并继承省略字段(self):
        self.assertEqual({0: (0, 1, 0), 3: (0, 1, 0), 4: (10, 2, 0)},
            map_program_counters('61ffff5b00', '0:1:0;;10:2:0'))

    def test_正常提交且CALL先于同槽扣账可给CEI断言(self):
        result = check_cei_trace(self.trace([self.call(), self.write()]),
            {4: (10, 2, 0)}, {'start': 10, 'length': 2, 'sourceUnitId': 0},
            slot=1, offset=0, width=32, before=2, after=1, caller='0xaa')
        self.assertTrue(result['valid'])
        self.assertEqual(0, result['callIndex'])

    def test_稀疏trace从实际SLOAD结果恢复调用时余额(self):
        call = self.call()
        call.pop('storage')
        logs = [{'pc': 1, 'op': 'SLOAD', 'depth': 1, 'stack': ['1']},
                {'pc': 2, 'op': 'PUSH1', 'depth': 1, 'stack': ['2']}, call, self.write()]
        self.assertTrue(check_cei_trace(self.trace(logs), {4: (10, 2, 0)},
            {'start': 10, 'length': 2, 'sourceUnitId': 0},
            slot=1, offset=0, width=32, before=2, after=1, caller='0xaa')['valid'])
        logs[1]['stack'] = ['1']
        self.assertFalse(check_cei_trace(self.trace(logs), {4: (10, 2, 0)},
            {'start': 10, 'length': 2, 'sourceUnitId': 0},
            slot=1, offset=0, width=32, before=2, after=1, caller='0xaa')['valid'])

    def test_回滚错主体错槽或前置扣账不准入(self):
        arguments = ({4: (10, 2, 0)}, {'start': 10, 'length': 2, 'sourceUnitId': 0})
        for trace in [self.trace([self.call(), self.write()], True),
                      self.trace([self.write(), self.call()]),
                      self.trace([self.call()]),
                      self.trace([dict(self.call(), depth=2), self.write()])]:
            self.assertFalse(check_cei_trace(trace, *arguments, slot=1, offset=0,
                width=32, before=2, after=1, caller='0xaa')['valid'])
        self.assertFalse(check_cei_trace(self.trace([self.call(), self.write()]),
            *arguments, slot=2, offset=0, width=32, before=2, after=1, caller='0xbb')['valid'])

    def test_权限写入要求原主体与运行主体不同及持久改值(self):
        span = {'start': 10, 'length': 2, 'sourceUnitId': 0}
        trace = self.trace([{'pc': 5, 'op': 'SSTORE', 'depth': 1, 'stack': ['bb', '1']}])
        self.assertTrue(check_authority_trace(trace, {5: (10, 2, 0)}, span,
            slot=1, before=0xaa, after=0xbb, caller='0xbb')['valid'])
        self.assertFalse(check_authority_trace(trace, {5: (10, 2, 0)}, span,
            slot=1, before=0xbb, after=0xbb, caller='0xbb')['valid'])
        self.assertFalse(check_authority_trace(trace, {5: (20, 2, 0)}, span,
            slot=1, before=0xaa, after=0xbb, caller='0xbb')['valid'])

    def test_RPC仅允许回环及固定正常业务方法(self):
        for url in ['https://example.com', 'http://localhost:8545', 'http://127.0.0.1:8545/other']:
            with self.assertRaises(ValueError):
                _Rpc(url)
        rpc = _Rpc('http://127.0.0.1:8545')
        for method in ['anvil_setStorageAt', 'anvil_setBalance', 'anvil_setCode', 'anvil_impersonateAccount']:
            with self.assertRaises(ValueError):
                rpc.call(method, [])

    def test_被父调用捕获的子调用耗尽gas仍不是正常返回(self):
        self.assertFalse(_normal_trace(self.trace([
            self.call(), {'pc': 3, 'depth': 2, 'op': 'ADD', 'error': 'out of gas'},
            {'pc': 5, 'depth': 1, 'op': 'POP', 'stack': ['0']} ])))
        self.assertFalse(_normal_trace(self.trace([
            self.call(), {'pc': 5, 'depth': 1, 'op': 'POP', 'stack': ['0']} ])))

    def test_候选写旧权限但其他语句写新权限不能归因到候选(self):
        logs = [{'pc': 5, 'op': 'SSTORE', 'depth': 1, 'stack': ['aa', '1']},
                {'pc': 6, 'op': 'SSTORE', 'depth': 1, 'stack': ['bb', '1']}]
        self.assertFalse(check_authority_trace(self.trace(logs),
            {5: (10, 2, 0), 6: (20, 2, 0)}, {'start': 10, 'length': 2, 'sourceUnitId': 0},
            slot=1, before=0xaa, after=0xbb, caller='0xbb')['valid'])

    def test_紧凑权限字段按真实偏移绑定而非整槽(self):
        span = {'start': 10, 'length': 2, 'sourceUnitId': 0}
        trace = self.trace([{'pc': 5, 'op': 'SSTORE', 'depth': 1, 'stack': ['bb01', '1']}])
        self.assertTrue(check_authority_trace(trace, {5: (10, 2, 0)}, span,
            slot=1, offset=1, width=20, before=0xaa, after=0xbb, caller='0xbb')['valid'])
        trace['structLogs'][0]['stack'] = ['aa01', '1']
        self.assertFalse(check_authority_trace(trace, {5: (10, 2, 0)}, span,
            slot=1, offset=1, width=20, before=0xaa, after=0xbb, caller='0xbb')['valid'])

    def test_候选必须改变紧前权限且后续不能覆盖拼接(self):
        span = {'start': 10, 'length': 2, 'sourceUnitId': 0}
        for offset in (0, 1):
            def write(pc, value):
                return {'pc': pc, 'op': 'SSTORE', 'depth': 1,
                        'stack': [hex((value << (8 * offset)) | (1 if offset else 0)), '1']}
            for logs in ([write(1, 0xbb), write(5, 0xbb)],
                         [write(5, 0xbb), write(6, 0xcc), write(7, 0xbb)]):
                self.assertFalse(check_authority_trace(self.trace(logs), {5: (10, 2, 0)}, span,
                    slot=1, offset=offset, before=0xaa, after=0xbb, caller='0xbb')['valid'])

    def test_权限候选和消费者拒绝未建模深层回调写入(self):
        guard = {'sourceUnitId': 0, 'start': 10, 'length': 3}
        operation = {'sourceUnitId': 0, 'start': 20, 'length': 3}
        callback = [self.call(),
                    {'pc': 5, 'depth': 2, 'op': 'CALL', 'stack': ['0', '0', '0', '0', '0', 'cc', 'ffff']},
                    {'pc': 6, 'depth': 3, 'op': 'SSTORE', 'stack': ['bb', '1']},
                    {'pc': 7, 'depth': 2, 'op': 'STOP', 'stack': ['1']},
                    {'pc': 8, 'depth': 1, 'op': 'POP', 'stack': ['1']}]
        self.assertTrue(_normal_trace(self.trace(callback)))
        logs = callback + [{'pc': 9, 'depth': 1, 'op': 'SSTORE', 'stack': ['bb', '1']}]
        self.assertFalse(check_authority_trace(self.trace(logs), {9: (20, 1, 0)}, operation,
            slot=1, before=0xaa, after=0xbb, caller='0xbb')['valid'])
        logs = [{'pc': 1, 'depth': 1, 'op': 'SLOAD', 'stack': ['1']},
                {'pc': 2, 'depth': 1, 'op': 'PUSH1', 'stack': ['bb']}] + callback + [
                {'pc': 9, 'depth': 1, 'op': 'SSTORE', 'stack': ['1', '2']}]
        self.assertFalse(evm_witness.check_consumer_trace(self.trace(logs), {1: (10, 1, 0), 9: (20, 1, 0)},
            guard, operation, location={'slot': 1, 'offset': 0, 'width': 20}, caller='0xbb')['valid'])

    def test_真实SlithIR模式字段与操作跨度可回读(self):
        span = {'sourceUnit': 'C.sol', 'start': 10, 'length': 3}
        fact = {'bindingStatus': 'BOUND', 'mode': 'WRITE', 'rootDeclarationId': 9, 'statementSpan': span}
        binding = {'receipts': [{'effectSummaries': [{'signature': 'set()', 'stateAccesses': [fact]}]}]}
        self.assertEqual(1, len(_access_fact(binding, {'span': span}, 9, 'WRITE')))
        self.assertEqual([], _access_fact(binding, {'span': span}, 9, 'READ'))

    def test_旧硬分叉正常交易显式采用传统费用字段(self):
        class LocalRpc:
            receipts = 0
            def call(self, method, params):
                if method == 'eth_accounts': return ['0xaa']
                if method == 'eth_sendTransaction':
                    if params[0].get('gasPrice') is None or params[0].get('type') != '0x0':
                        raise ValueError('旧硬分叉拒绝默认EIP1559交易')
                    return '0x01'
                if method == 'eth_getTransactionReceipt':
                    self.receipts += 1
                    return {'status': '0x1'} if self.receipts > 1 else None
                if method == 'debug_traceTransaction': return {'failed': False, 'structLogs': [{'op': 'STOP'}]}
                return True
        with tempfile.TemporaryDirectory() as directory:
            session = _Session(LocalRpc(), {'timestamp': 1600000000}, Path(directory))
            self.assertEqual('0x1', session.transact(sender='0xaa', data='0x')['receipt']['status'])

    def test_指定时间必须用于业务交易而非提前消耗在空块(self):
        class LocalRpc:
            pending_timestamp = None
            transaction_timestamp = None

            def call(self, method, params):
                if method == 'eth_accounts': return ['0xaa']
                if method == 'evm_setNextBlockTimestamp': self.pending_timestamp = params[0]
                if method == 'evm_mine': self.pending_timestamp = None
                if method == 'eth_sendTransaction':
                    self.transaction_timestamp = self.pending_timestamp
                    self.pending_timestamp = None
                    return '0x01'
                if method == 'eth_getTransactionReceipt': return {'status': '0x1'}
                if method == 'debug_traceTransaction': return {'failed': False, 'structLogs': [{'op': 'STOP'}]}
                return True

        with tempfile.TemporaryDirectory() as directory:
            rpc = LocalRpc()
            session = _Session(rpc, {'timestamp': 1600000000}, Path(directory))
            session.advance(100)
            for expected in (1600000101, 1600000102):
                record = session.transact(sender='0xaa', data='0x')
                self.assertEqual(expected, rpc.transaction_timestamp)
                self.assertEqual(expected, record['timestamp'])

    def test_消费者必须实际读取权限并正常到达同跨度操作(self):
        guard = {'sourceUnitId': 0, 'start': 10, 'length': 3}
        operation = {'sourceUnitId': 0, 'start': 20, 'length': 3}
        mapping = {1: (10, 1, 0), 3: (20, 1, 0)}
        logs = [{'pc': 1, 'depth': 1, 'op': 'SLOAD', 'stack': ['1']},
                {'pc': 2, 'depth': 1, 'op': 'PUSH1', 'stack': ['bb']},
                {'pc': 3, 'depth': 1, 'op': 'SSTORE', 'stack': ['2', '4']}]
        location = {'slot': 1, 'offset': 0, 'width': 20}
        for ending, expected in [([], True), ([{'op': 'REVERT', 'depth': 1}], False)]:
            result = evm_witness.check_consumer_trace(self.trace(logs + ending), mapping,
                guard, operation, location=location, caller='0xbb')
            self.assertEqual(expected, result['valid'])
        logs[1]['stack'] = ['aa']
        self.assertFalse(evm_witness.check_consumer_trace(self.trace(logs), mapping,
            guard, operation, location=location, caller='0xbb')['valid'])

    def test_辅助调用不能串用另一个已部署实现(self):
        from types import SimpleNamespace
        graph = SimpleNamespace(nodes=[{'kind': 'CALL', 'targetDeclarationId': 7,
            'span': {'sourceUnitId': 0, 'start': 10, 'length': 3}}])
        bundle = {'functions': {7: {'contractId': 8}}}
        row = {'op': 'CALL', 'pc': 3, 'depth': 1, 'stack': ['aa', 'ffff']}
        mapping = {3: (10, 2, 0)}
        dependencies = {8: '0xaa', 9: '0xbb'}
        evm_witness.check_auxiliary_calls({'structLogs': [row]}, mapping, 99, graph, bundle, dependencies)
        row['stack'] = ['bb', 'ffff']
        with self.assertRaisesRegex(ValueError, '辅助'):
            evm_witness.check_auxiliary_calls({'structLogs': [row]}, mapping, 99, graph, bundle, dependencies)

    def test_只读及零额调用不能充当敏感权限消费者(self):
        guard = {'sourceUnitId': 0, 'start': 10, 'length': 3}
        operation = {'sourceUnitId': 0, 'start': 20, 'length': 3}
        for opcode, value, expected in [('STATICCALL', '1', False), ('CALL', '0', False), ('CALL', '1', True)]:
            logs = [{'pc': 1, 'depth': 1, 'op': 'SLOAD', 'stack': ['1']},
                    {'pc': 2, 'depth': 1, 'op': 'PUSH1', 'stack': ['bb']},
                    {'pc': 3, 'depth': 1, 'op': opcode, 'stack': ['0', '0', '0', '0', value, 'bb', 'ffff']},
                    {'pc': 4, 'depth': 1, 'op': 'STOP', 'stack': ['1']}]
            result = evm_witness.check_consumer_trace(self.trace(logs), {1: (10, 1, 0), 3: (20, 1, 0)},
                guard, operation, location={'slot': 1, 'offset': 0, 'width': 20}, caller='0xbb')
            self.assertEqual(expected, result['valid'])
