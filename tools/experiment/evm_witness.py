"""本机有限业务执行见证；固定编译、真实部署和独立重放，不生成利用程序。"""
import copy
import hashlib
import json
import re
import socket
import subprocess
import time
import uuid
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from urllib.request import Request, urlopen

from compiler_facts import _walk, source_span
from storage import atomic_json, encode, fingerprint

_EVIDENCE = Path('research-artifacts/receipts/evm')
_SCHEMA = 'bound-evm-1'
_METHODS = frozenset({'eth_chainId', 'eth_accounts', 'eth_sendTransaction',
    'eth_getTransactionReceipt', 'eth_getCode', 'eth_getStorageAt', 'eth_getBalance',
    'debug_traceTransaction', 'evm_snapshot', 'evm_revert', 'evm_setNextBlockTimestamp', 'evm_mine'})
_MAX_STEPS = 48
_MAX_SECONDS = 90


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _hex(value):
    return int(str(value).removeprefix('0x') or '0', 16)


def map_program_counters(bytecode, source_map):
    """按真实指令及 PUSH 数据长度展开 Solidity 压缩源映射。"""
    code = bytes.fromhex(bytecode.removeprefix('0x'))
    positions, pc = [], 0
    while pc < len(code):
        positions.append(pc)
        opcode = code[pc]
        pc += 1 + (opcode - 0x5f if 0x60 <= opcode <= 0x7f else 0)
    current, result = [-1, -1, -1], {}
    for pc, row in zip(positions, source_map.split(';')):
        for index, value in enumerate(row.split(':')[:3]):
            if value:
                current[index] = int(value)
        result[pc] = tuple(current)
    return result


def _in_span(pc, mapping, span):
    start, length, unit = mapping.get(pc, (-1, -1, -1))
    return (unit == span['sourceUnitId'] and length > 0
            and span['start'] <= start and start + length <= span['start'] + span['length'])


def _normal_trace(trace):
    logs = trace.get('structLogs')
    if trace.get('failed') is not False or not isinstance(logs, list) or not logs:
        return False
    # 被业务代码捕获的子调用回滚也不当作辅助调用正常返回。
    if any(row.get('error') or row.get('op') in {'REVERT', 'INVALID', 'DELEGATECALL', 'CALLCODE', 'SELFDESTRUCT'} for row in logs):
        return False
    for index, row in enumerate(logs):
        if row.get('op') not in {'CALL', 'STATICCALL'}:
            continue
        continuation = next((item for item in logs[index + 1:] if item.get('depth', 0) <= row.get('depth', 0)), None)
        if (continuation is None or continuation.get('depth') != row.get('depth')
                or not continuation.get('stack') or _hex(continuation['stack'][-1]) != 1):
            return False
    return True


def check_cei_trace(trace, mapping, span, *, slot, offset, width, before, after, caller):
    """实际正常业务中，绑定数值 CALL 前余额仍有效，之后同槽扣账并持久提交。"""
    invalid = {'valid': False}
    if not _normal_trace(trace) or before <= after or after < 0 or width < 1 or width > 32:
        return invalid
    logs = trace['structLogs']
    calls = [(index, row) for index, row in enumerate(logs) if row.get('op') == 'CALL'
             and row.get('depth') == 1 and _in_span(row['pc'], mapping, span)]
    if len(calls) != 1:
        return invalid
    index, call = calls[0]
    stack = call.get('stack', [])
    if len(stack) < 7 or _hex(stack[-2]) != _hex(caller) or _hex(stack[-3]) <= 0:
        return invalid
    writes = [(i, row) for i, row in enumerate(logs) if row.get('op') == 'SSTORE'
              and row.get('depth') == 1 and len(row.get('stack', [])) >= 2
              and _hex(row['stack'][-1]) == slot]
    if not writes or any(i < index for i, _ in writes) or not any(i > index for i, _ in writes):
        return invalid
    stored = next((value for key, value in (call.get('storage') or {}).items() if _hex(key) == slot), None)
    if stored is None:
        # Anvil 的稀疏 storage 只附在 SSTORE；从同槽真实 SLOAD 后的栈顶恢复读取值。
        for i, row in enumerate(logs[:index]):
            if (row.get('op') == 'SLOAD' and row.get('depth') == 1 and row.get('stack')
                    and _hex(row['stack'][-1]) == slot and logs[i + 1].get('depth') == 1
                    and logs[i + 1].get('stack')):
                stored = logs[i + 1]['stack'][-1]
    if stored is None:
        # 仍须实际读取，禁止仅使用调用前账户快照补齐窗口。
        return invalid
    balance_at_call = (_hex(stored) >> (offset * 8)) & ((1 << (8 * width)) - 1)
    if balance_at_call != before or balance_at_call < _hex(stack[-3]):
        return invalid
    continuation = next((row for row in logs[index + 1:] if row.get('depth') == 1), None)
    if continuation is None or not continuation.get('stack') or _hex(continuation['stack'][-1]) != 1:
        return invalid
    return {'valid': True, 'callIndex': index, 'callPc': call['pc'],
            'writeIndexes': [i for i, _ in writes], 'writePcs': [row['pc'] for _, row in writes],
            'balanceAtCall': balance_at_call, 'transferValue': _hex(stack[-3]),
            'balanceBefore': before, 'balanceAfter': after, 'slot': hex(slot),
            'assertion': 'NORMAL_RETURN_CEI_ORDER'}


def check_authority_trace(trace, mapping, span, *, slot, before, after, caller, offset=0, width=20):
    """原权限主体与调用者不同，实际候选写入正常提交后改变权限资源。"""
    if (not _normal_trace(trace) or width != 20 or type(offset) is not int or not 0 <= offset <= 12
            or before == 0 or before == _hex(caller)
            or before == after or after != _hex(caller)):
        return {'valid': False}
    # 未建立执行帧地址历史时，深层回调可能提前改变目标权限，不能仅凭根帧归因。
    if any(row.get('depth') != 1 for row in trace['structLogs']):
        return {'valid': False}
    all_writes = [(i, row) for i, row in enumerate(trace['structLogs']) if row.get('op') == 'SSTORE'
                  and row.get('depth') == 1 and len(row.get('stack', [])) >= 2
                  and _hex(row['stack'][-1]) == slot]
    writes = [(i, row) for i, row in all_writes if _in_span(row['pc'], mapping, span)]
    if len(writes) != 1:
        return {'valid': False}
    current, immediate_before = before, None
    for index, row in all_writes:
        value = (_hex(row['stack'][-2]) >> (8 * offset)) & ((1 << 160) - 1)
        if index == writes[0][0]:
            immediate_before = current
            if current == 0 or current == _hex(caller) or value != after:
                return {'valid': False}
        elif index > writes[0][0] and value != current:
            return {'valid': False}
        current = value
    if current != after:
        return {'valid': False}
    return {'valid': True, 'writeIndex': writes[0][0], 'writePc': writes[0][1]['pc'],
            'authorityBefore': hex(immediate_before), 'transactionAuthorityBefore': hex(before), 'authorityAfter': hex(after),
            'caller': caller, 'slot': hex(slot), 'assertion': 'PERSISTENT_UNAUTHORIZED_AUTHORITY_WRITE'}


def check_consumer_trace(trace, mapping, guard, operation, *, location, caller):
    """静态消费者还须在实际正常执行中读取同一权限并到达受保护操作。"""
    if not _normal_trace(trace):
        return {'valid': False}
    logs = trace['structLogs']
    if any(row.get('depth') != 1 for row in logs):
        return {'valid': False}
    for index, row in enumerate(logs[:-1]):
        if (row.get('op') != 'SLOAD' or row.get('depth') != 1 or not row.get('stack')
                or _hex(row['stack'][-1]) != location['slot'] or not _in_span(row['pc'], mapping, guard)):
            continue
        loaded = logs[index + 1]
        if not loaded.get('stack') or loaded.get('depth') != 1:
            continue
        value = (_hex(loaded['stack'][-1]) >> (8 * location['offset'])) & ((1 << (8 * location['width'])) - 1)
        if value != _hex(caller):
            continue
        for later, item in enumerate(logs[index + 1:], index + 1):
            if (item.get('depth') == 1 and item.get('op') == 'SSTORE'
                    and item.get('stack') and _hex(item['stack'][-1]) == location['slot']):
                break
            stack = item.get('stack', [])
            sensitive = ((item.get('op') == 'SSTORE' and len(stack) >= 2)
                         or (item.get('op') == 'CALL' and len(stack) >= 7 and _hex(stack[-3]) > 0))
            if (item.get('depth') == 1 and sensitive and _in_span(item['pc'], mapping, operation)):
                return {'valid': True, 'normalExit': True, 'authorityReadIndex': index,
                        'operationIndex': later, 'operationPc': item['pc'], 'operation': item['op']}
    return {'valid': False}


class _Rpc:
    def __init__(self, url):
        if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+', url):
            raise ValueError('执行节点必须为独立回环端口')
        self.url, self.sequence = url, 0

    def call(self, method, params):
        if method not in _METHODS:
            raise ValueError('执行方法超出正常本机业务与时间推进白名单')
        self.sequence += 1
        payload = encode({'jsonrpc': '2.0', 'id': self.sequence, 'method': method, 'params': params})
        with urlopen(Request(self.url, payload, {'Content-Type': 'application/json'}), timeout=15) as response:
            data = response.read(48 * 1024 * 1024 + 1)
        if len(data) > 48 * 1024 * 1024:
            raise ValueError('执行 trace 超出固定预算')
        value = json.loads(data)
        if value.get('id') != self.sequence or 'error' in value or 'result' not in value:
            raise ValueError('本机 EVM 返回失败或响应身份不匹配：' + method + '：' + str(value.get('error', '响应编号不匹配')))
        return value['result']


def _configuration(root):
    from tool_environment import _configuration as read_configuration
    path = root / 'config/tools.local.properties'
    values = read_configuration(path) if path.is_file() else {}
    if values.get('tools.evm.enabled') != 'true':
        raise ValueError('本机有限执行提供器尚未显式配置')
    result = {'hardfork': 'istanbul', 'timestamp': 1600000000, 'chainId': 31337,
              'maxSteps': _MAX_STEPS, 'maxSeconds': _MAX_SECONDS}
    for tool in ('anvil', 'cast'):
        path = Path(values.get('tools.evm.' + tool, '')).expanduser().resolve()
        expected = values.get('tools.evm.' + tool + '-sha256')
        if not path.is_file() or _sha(path.read_bytes()) != expected:
            raise ValueError('本机执行二进制未绑定固定摘要：' + tool)
        probe = subprocess.run([str(path), '--version'], capture_output=True, timeout=5, check=True)
        result[tool] = {'path': str(path), 'sha256': expected, 'version': probe.stdout.decode().strip()}
    return result


@contextmanager
def _node(configuration, directory):
    # 独立非 fork 节点，不读取外部链，不使用或归档私钥。
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    command = [configuration['anvil']['path'], '--host', '127.0.0.1', '--port', str(port),
               '--hardfork', configuration['hardfork'], '--timestamp', str(configuration['timestamp']),
               '--chain-id', str(configuration['chainId']), '--steps-tracing', '--silent']
    with (directory / 'node-stdout.log').open('wb') as stdout, (directory / 'node-stderr.log').open('wb') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        rpc = _Rpc('http://127.0.0.1:' + str(port))
        try:
            started = time.monotonic()
            while True:
                if process.poll() is not None or time.monotonic() - started > 10:
                    raise ValueError('独立 Anvil 节点启动失败')
                try:
                    if _hex(rpc.call('eth_chainId', [])) == configuration['chainId']:
                        break
                except (OSError, ValueError):
                    time.sleep(.05)
            yield rpc
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


class _Session:
    def __init__(self, rpc, configuration, directory):
        self.rpc, self.configuration, self.directory = rpc, configuration, directory
        self.accounts = rpc.call('eth_accounts', [])
        self.records, self.deployments = [], []
        self.started, self.timestamp = time.monotonic(), configuration['timestamp']

    def cast(self, command, *args):
        result = subprocess.run([self.configuration['cast']['path'], command, *map(str, args)],
                                capture_output=True, timeout=10, check=True)
        return result.stdout.decode().strip()

    def calldata(self, abi, arguments):
        signature = abi.get('name', '') + '(' + ','.join(item['type'] for item in abi.get('inputs', [])) + ')'
        return self.cast('calldata', signature, *arguments) if abi.get('type') == 'function' else '0x'

    def advance(self, seconds):
        self.timestamp += seconds
        self.rpc.call('evm_setNextBlockTimestamp', [self.timestamp])
        self.rpc.call('evm_mine', [])

    def transact(self, *, sender, data, address=None, value=0):
        if len(self.records) >= _MAX_STEPS or time.monotonic() - self.started > _MAX_SECONDS:
            raise ValueError('有限业务序列预算耗尽')
        # 指定时间直接由本次交易消耗；先挖空块会让业务块重新取墙上时间并漂移。
        self.timestamp += 1
        self.rpc.call('evm_setNextBlockTimestamp', [self.timestamp])
        transaction = {'from': sender, 'data': data, 'value': hex(value), 'gas': hex(8_000_000),
                       'type': '0x0', 'gasPrice': hex(10 ** 9)}
        if address is not None:
            transaction['to'] = address
        tx_hash = self.rpc.call('eth_sendTransaction', [transaction])
        receipt = self.rpc.call('eth_getTransactionReceipt', [tx_hash])
        deadline = time.monotonic() + 5
        while receipt is None and time.monotonic() < deadline:
            time.sleep(.02)
            receipt = self.rpc.call('eth_getTransactionReceipt', [tx_hash])
        if not isinstance(receipt, dict):
            raise ValueError('正常业务调用缺成功或失败回执原件')
        trace = self.rpc.call('debug_traceTransaction', [tx_hash,
            {'disableMemory': True, 'disableStack': False, 'disableStorage': False}])
        index = len(self.records)
        record = {'transaction': transaction, 'receipt': receipt, 'trace': trace, 'timestamp': self.timestamp}
        atomic_json(self.directory / f'transaction-{index}.json', record)
        self.records.append(record)
        return record

    def storage(self, address, location):
        word = _hex(self.rpc.call('eth_getStorageAt', [address, hex(location['slot']), 'latest']))
        return (word >> (8 * location['offset'])) & ((1 << (8 * location['width'])) - 1)

    def deploy(self, artifact, constructor_args, identity):
        bytecode = artifact['evm']['bytecode']['object']
        constructor = next((item for item in artifact['abi'] if item['type'] == 'constructor'), {'inputs': []})
        encoded = ''
        if constructor['inputs']:
            signature = 'f(' + ','.join(item['type'] for item in constructor['inputs']) + ')'
            encoded = self.cast('abi-encode', signature, *constructor_args).removeprefix('0x')
        record = self.transact(sender=self.accounts[0], data='0x' + bytecode + encoded)
        address = record['receipt'].get('contractAddress')
        if _hex(record['receipt']['status']) != 1 or not address or not _normal_trace(record['trace']):
            raise ValueError('原合约构造程序没有正常部署')
        code = self.rpc.call('eth_getCode', [address, 'latest']).removeprefix('0x')
        if code != artifact['evm']['deployedBytecode']['object']:
            raise ValueError('实际部署字节码与固定编译原件不一致')
        self.deployments.append({'identity': identity, 'address': address,
            'constructorArguments': constructor_args, 'runtimeSha256': _sha(bytes.fromhex(code)),
            'codeHash': self.cast('keccak', '0x' + code)})
        return address


def _execution_artifacts(bundle, directory):
    """扩展输出选择取得源映射，原编译输入及第一收据不改写。"""
    compiler_input = copy.deepcopy(bundle['input'])
    selection = compiler_input['settings'].setdefault('outputSelection', {})
    selection.setdefault('*', {}).setdefault('', [])
    selection['*'][''] = sorted(set(selection['*']['']) | {'ast'})
    selection['*']['*'] = sorted(set(selection['*'].get('*', [])) | {'abi',
        'evm.bytecode.object', 'evm.bytecode.sourceMap', 'evm.deployedBytecode.object',
        'evm.deployedBytecode.sourceMap', 'evm.methodIdentifiers'})
    compiler = Path(bundle['binding']['compiler'])
    if _sha(compiler.read_bytes()) != bundle['binding']['compilerSha256']:
        raise ValueError('执行编译器发生漂移')
    result = subprocess.run([str(compiler), '--standard-json'], input=encode(compiler_input),
                            capture_output=True, timeout=120, check=True)
    output = json.loads(result.stdout)
    if _sha(compiler.read_bytes()) != bundle['binding']['compilerSha256'] or any(
            item.get('severity') == 'error' for item in output.get('errors', [])):
        raise ValueError('扩展源映射编译失败')
    for unit, contracts in bundle['output']['contracts'].items():
        for name, original in contracts.items():
            actual = output['contracts'][unit][name]
            if original['abi'] != actual['abi'] or any(original['evm'][key]['object'] != actual['evm'][key]['object']
                    for key in ('bytecode', 'deployedBytecode')):
                raise ValueError('扩展源映射改变原字节码或 ABI')
    if any(source['ast'] != output['sources'][unit]['ast'] for unit, source in bundle['output']['sources'].items()):
        raise ValueError('扩展源映射改变原 AST 声明身份')
    atomic_json(directory / 'execution-input.json', compiler_input)
    atomic_json(directory / 'execution-output.json', output)
    return output, fingerprint({'input': compiler_input, 'output': output})


def _type_target(declaration):
    node = declaration.get('typeName', {})
    return node.get('referencedDeclaration') if node.get('nodeType') == 'UserDefinedTypeName' else None


def _argument_values(abi, actor, number=0, address=None):
    result = []
    for item in abi.get('inputs', []):
        identity = item['type']
        if re.fullmatch(r'uint(?:[0-9]+)?', identity):
            result.append(str(number))
        elif identity == 'address':
            result.append(address or actor)
        elif identity == 'bool':
            result.append('false')
        else:
            raise ValueError('有限执行尚未支持 ABI 形参：' + identity)
    return result


def _dependencies(bundle, graph):
    targets = set()
    for node in graph.nodes:
        if node['kind'] != 'CALL' or node.get('lowLevelValueCall'):
            continue
        target = bundle['functions'].get(node.get('targetDeclarationId'))
        if target is None or target['contractId'] == bundle['targetContractId']:
            raise ValueError('辅助外部调用的实现声明没有唯一绑定')
        targets.add(target['contractId'])
    return targets


def _setup(session, bundle, output, graph):
    dependencies = {}
    for identity in sorted(_dependencies(bundle, graph)):
        contract = bundle['contracts'][identity]['node']
        unit = source_span(contract, bundle['units'])['sourceUnit']
        artifact = output['contracts'][unit][contract['name']]
        constructor = next((item for item in artifact['abi'] if item['type'] == 'constructor'), {'inputs': []})
        if constructor['inputs']:
            raise ValueError('辅助实现构造参数未建立合法绑定')
        dependencies[identity] = session.deploy(artifact, [], contract['name'])
    artifact = output['contracts'][bundle['targetSourceUnit']][bundle['targetContract']]
    constructor = next((item for item in artifact['abi'] if item['type'] == 'constructor'), {'inputs': []})
    if len(dependencies) > 1 and any(item['type'] == 'address' for item in constructor['inputs']):
        raise ValueError('构造地址实参有多个辅助实现，不猜测绑定')
    log_address = next(iter(dependencies.values()), None)
    args = _argument_values(constructor, session.accounts[0], address=log_address)
    address = session.deploy(artifact, args, bundle['targetContract'])
    # 仅选择 AST 明确将地址形参转为相应合约资源的真实配置入口。
    for entry in bundle['entries']:
        if not entry['matched'] or entry['kind'] == 'getter':
            continue
        function = bundle['functions'][entry['declarationId']]
        if len(function['parameters']) != 1 or function['parameters'][0].get('typeDescriptions', {}).get('typeIdentifier') not in {'t_address', 't_address_payable'}:
            continue
        assignments = [node for node in _walk(function['body']) if node.get('nodeType') == 'Assignment'
                       and node.get('operator') == '=' and node.get('leftHandSide', {}).get('nodeType') == 'Identifier']
        for assignment in assignments:
            root = bundle['declarations'].get(assignment['leftHandSide'].get('referencedDeclaration'), {})
            target = _type_target(root)
            right = assignment.get('rightHandSide', {})
            if (target in dependencies and right.get('kind') == 'typeConversion'
                    and len(right.get('arguments', [])) == 1 and right['arguments'][0].get('referencedDeclaration') == function['parameters'][0]['id']):
                abi = next((item for item in artifact['abi'] if item.get('name') == function['node']['name']
                            and item.get('type') == 'function' and len(item['inputs']) == 1), None)
                if abi is None:
                    raise ValueError('合法配置入口 ABI 未唯一绑定')
                result = session.transact(sender=session.accounts[0], address=address,
                    data=session.calldata(abi, [dependencies[target]]))
                if _hex(result['receipt']['status']) != 1 or not _normal_trace(result['trace']):
                    raise ValueError('辅助地址合法配置未正常提交')
    return address, artifact, dependencies


def _layout(tool_binding, root):
    layouts = [row for receipt in tool_binding.get('receipts', [])
               for row in receipt.get('storageLayout', []) if row.get('declarationId') == root]
    if not layouts:
        raise ValueError('独立 Slither 未提供唯一权限／余额存储布局')
    if len({fingerprint(row) for row in layouts}) != 1 or layouts[0].get('bindingStatus') != 'BOUND':
        raise ValueError('独立存储布局不唯一或声明未绑定')
    return layouts[0]


def _location(session, bundle, resource, tool_binding, actor):
    layout = _layout(tool_binding, resource[1])
    slot, offset = layout['slot'], layout['offset']
    declaration = bundle['declarations'][resource[1]]
    type_node = declaration.get('typeName', {})
    for segment in resource[2]:
        if segment[0] == 'index':
            if type_node.get('nodeType') != 'Mapping' or tuple(segment[1]) != ('builtin', 'msg.sender'):
                raise ValueError('执行资源 key 不是实际调用主体的地址映射')
            slot = _hex(session.cast('keccak', '0x' + _hex(actor).to_bytes(32, 'big').hex() + slot.to_bytes(32, 'big').hex()))
            offset, type_node = 0, type_node['valueType']
        elif segment[0] == 'member':
            members = [row for row in layout.get('members', []) if row.get('memberDeclarationId') == segment[1]]
            if len(members) != 1 or members[0].get('bindingStatus') != 'BOUND':
                raise ValueError('结构字段缺少独立布局映射')
            slot, offset = slot + members[0]['relativeSlot'], members[0]['offset']
            type_node = bundle['declarations'][segment[1]].get('typeName', {})
        else:
            raise ValueError('未支持存储路径段')
    name = type_node.get('name', '')
    width = 20 if name in {'address', 'address payable'} else 1 if name == 'bool' else (
        int(name[4:] or '256') // 8 if re.fullmatch(r'uint[0-9]*', name) else None)
    if width is None:
        raise ValueError('资源不是已绑定的地址、布尔或无符号整数字段')
    return {'slot': slot, 'offset': offset, 'width': width, 'resource': resource, 'layout': layout}


def _access_fact(tool_binding, risk, root, access):
    refs = []
    for receipt in tool_binding.get('receipts', []):
        for effect in receipt.get('effectSummaries', []):
            for item in effect.get('stateAccesses', []):
                span = item.get('statementSpan') or item.get('span', {})
                if (item.get('bindingStatus') == 'BOUND' and item.get('mode') == access
                        and item.get('rootDeclarationId') == root and span.get('sourceUnit') == risk['span']['sourceUnit']
                        and type(span.get('start')) is int and type(span.get('length')) is int
                        and span['start'] <= risk['span']['start']
                        and risk['span']['start'] + risk['span']['length'] <= span['start'] + span['length']):
                    refs.append({'engine': 'SLITHIR', 'effect': effect.get('signature'), 'stateAccess': item})
    return refs


def _numeric_domain(bundle):
    factors = {'ether': 10 ** 18, 'gwei': 10 ** 9, 'wei': 1, 'weeks': 604800,
               'days': 86400, 'hours': 3600, 'minutes': 60, 'seconds': 1}
    amounts, times = {1, 10 ** 18, 2 * 10 ** 18, 3 * 10 ** 18}, {604801}
    for node in bundle['nodes'].values():
        if node.get('nodeType') != 'Literal' or node.get('kind') != 'number':
            continue
        try:
            value = Fraction(node['value']) * factors.get(node.get('subdenomination'), 1)
            if value.denominator != 1 or value <= 0:
                continue
            value = int(value)
            if node.get('subdenomination') in {'weeks', 'days', 'hours', 'minutes', 'seconds'}:
                times.add(value + 1)
            elif value <= 10 ** 20:
                amounts.update({value, value + 1})
        except (ValueError, KeyError, ZeroDivisionError):
            continue
    # 固定有限候选集合，搜索无结果永远不构成反驳。
    return sorted(amounts)[:12], max(times)


def _runtime_abi(artifact, entry):
    matches = [item for item in artifact['abi'] if item['type'] == 'function'
               and item.get('name') + '(' + ','.join(arg['type'] for arg in item['inputs']) + ')' == entry['signature']]
    if len(matches) != 1:
        raise ValueError('执行入口 ABI 未唯一绑定')
    return matches[0]


def check_auxiliary_calls(trace, mapping, risk_pc, graph, bundle, dependencies):
    """每个辅助调用都绑定其编译声明的具体部署，不按名称或地址集合放行。"""
    for row in trace['structLogs']:
        if row.get('op') not in {'CALL', 'STATICCALL'}:
            continue
        if row.get('depth') != 1 or len(row.get('stack', [])) < 2:
            raise ValueError('辅助实现包含尚未绑定的深层外部调用')
        if row['pc'] == risk_pc:
            continue
        nodes = [node for node in graph.nodes if node['kind'] == 'CALL'
                 and _in_span(row['pc'], mapping, node['span'])]
        if len(nodes) != 1:
            raise ValueError('辅助 CALL 的源码跨度没有唯一编译节点')
        declaration = bundle['functions'].get(nodes[0].get('targetDeclarationId'), {})
        address = dependencies.get(declaration.get('contractId'))
        if address is None or _hex(row['stack'][-2]) != _hex(address):
            raise ValueError('辅助 CALL 没有访问其编译声明对应的实际部署')


def _run_cei(session, bundle, output, graph, risk, resource, tool_binding):
    from reentrancy_proofs import _mutex_for
    if list(_mutex_for(graph, risk)):
        raise ValueError('存在实际互斥保护，有限 CEI 顺序运行不足以证明重入保护失效')
    if not risk.get('lowLevelValueCall') or risk.get('targetValue') != ('builtin', 'msg.sender'):
        raise ValueError('该执行断言尚未支持非调用主体数值 CALL')
    if any(node['kind'] == 'UNKNOWN' for node in graph.nodes):
        raise ValueError('候选入口包含未核验保护语义')
    address, artifact, dependencies = _setup(session, bundle, output, graph)
    actor = session.accounts[1]
    location = _location(session, bundle, resource, tool_binding, actor)
    abi = _runtime_abi(artifact, graph.entry)
    amount_domain, elapsed = _numeric_domain(bundle)
    deposits = [item for item in artifact['abi'] if item['type'] in {'function', 'fallback', 'receive'}
                and (item.get('stateMutability') == 'payable' or item.get('payable') is True)
                and item != abi]
    if not deposits:
        raise ValueError('没有实际 payable 入账入口，不能构造余额')
    # 先尝试能越过源码阈值的合法入账；每个失败也保留回执。
    funding = sorted(set([2 * 10 ** 18, 3 * 10 ** 18] + amount_domain), reverse=True)[:6]
    for deposit in deposits:
        for value in funding:
            try:
                args = _argument_values(deposit, actor, number=0)
                result = session.transact(sender=actor, address=address, data=session.calldata(deposit, args), value=value)
            except ValueError:
                continue
            credited = session.storage(address, location)
            if _hex(result['receipt']['status']) != 1 or not _normal_trace(result['trace']) or credited <= 0:
                continue
            # 入账必须有独立 SlithIR 写入同声明根，不能靠给定余额见证。
            function_name = deposit.get('name')
            entry = next((entry for entry in bundle['entries'] if entry['matched']
                          and (entry['signature'].split('(', 1)[0] == function_name or deposit['type'] in {'fallback', 'receive'}
                               and entry['signature'].split('(', 1)[0] == deposit['type'])), None)
            if entry is None:
                raise ValueError('实际入账入口没有编译声明')
            effects = [effect for receipt in tool_binding.get('receipts', []) for effect in receipt.get('effectSummaries', [])
                       if effect.get('declarationId') == entry['declarationId']]
            if not any(item.get('mode') == 'WRITE' and item.get('rootDeclarationId') == resource[1]
                       and item.get('bindingStatus') == 'BOUND' for effect in effects for item in effect.get('stateAccesses', [])):
                raise ValueError('入账缺同资源 SlithIR 写入佐证')
            initial = {'funded': True, 'entry': entry['signature'], 'msgValue': value,
                       'creditedValue': credited, 'receiptIndex': len(session.records) - 1,
                       'contractBalance': _hex(session.rpc.call('eth_getBalance', [address, 'latest']))}
            session.advance(elapsed)
            for amount in sorted(set(amount_domain + [credited]), reverse=True):
                if amount > credited:
                    continue
                before = session.storage(address, location)
                result = session.transact(sender=actor, address=address,
                    data=session.calldata(abi, _argument_values(abi, actor, number=amount)))
                after = session.storage(address, location)
                if _hex(result['receipt']['status']) != 1:
                    continue
                mapping = map_program_counters(artifact['evm']['deployedBytecode']['object'],
                                               artifact['evm']['deployedBytecode']['sourceMap'])
                assertion = check_cei_trace(result['trace'], mapping, risk['span'],
                    slot=location['slot'], offset=location['offset'], width=location['width'],
                    before=before, after=after, caller=actor)
                if assertion['valid']:
                    check_auxiliary_calls(result['trace'], mapping, assertion['callPc'], graph, bundle, dependencies)
                    return {'kind': 'CEI_COUNTEREXAMPLE', 'assertion': assertion, 'location': location,
                            'initialization': initial, 'caller': actor, 'target': address,
                            'transactionIndex': len(session.records) - 1, 'normalExit': True}
                if after != before:
                    # 一次不匹配的成功业务改变状态后，停止沿该状态继续猜测。
                    break
            break
    raise ValueError('固定正常业务搜索未找到完整 CEI 断言见证')


def _run_authority(session, bundle, output, graph, risk, resource, tool_binding):
    from candidate_proofs import authority_consumers
    if resource[2] or bundle['declarations'][resource[1]].get('typeDescriptions', {}).get('typeIdentifier') != 't_address':
        raise ValueError('权限执行断言只接受实际标量地址权限资源')
    refs = _access_fact(tool_binding, risk, resource[1], 'WRITE')
    if not refs:
        raise ValueError('权限写入缺独立 SlithIR 同操作资源证据')
    consumers = authority_consumers(bundle, resource)
    consumption_refs = [reference for consumer in consumers
                        for reference in _access_fact(tool_binding,
                            {'span': consumer['guard']['span']}, resource[1], 'READ')]
    if not consumers or not consumption_refs:
        raise ValueError('权限资源缺实际敏感入口与同一 SlithIR 权限读取佐证')
    address, artifact, _ = _setup(session, bundle, output, graph)
    location = _location(session, bundle, resource, tool_binding, session.accounts[0])
    abi = _runtime_abi(artifact, graph.entry)
    funding_index = None
    deposits = [item for item in artifact['abi'] if item['type'] in {'fallback', 'receive'}
                and (item.get('payable') or item.get('stateMutability') == 'payable')]
    if len(deposits) == 1:
        # 由原合约正常收款入口建立消费者资金，零额 CALL 不能充当敏感转账。
        funded = session.transact(sender=session.accounts[0], address=address, data='0x', value=10**18)
        if _hex(funded['receipt']['status']) != 1 or not _normal_trace(funded['trace']):
            raise ValueError('权限消费者的原合约正常收款入口未提交')
        funding_index = len(session.records) - 1
    before = session.storage(address, location)
    if before == 0:
        # 只由真实公开初始化入口形成权限主体，不能直接修改状态。
        result = session.transact(sender=session.accounts[0], address=address,
            data=session.calldata(abi, _argument_values(abi, session.accounts[0])))
        if _hex(result['receipt']['status']) != 1 or not _normal_trace(result['trace']):
            raise ValueError('公开初始化没有正常提交')
        before = session.storage(address, location)
    actor = session.accounts[1]
    result = session.transact(sender=actor, address=address,
        data=session.calldata(abi, _argument_values(abi, actor)))
    after = session.storage(address, location)
    mapping = map_program_counters(artifact['evm']['deployedBytecode']['object'],
                                  artifact['evm']['deployedBytecode']['sourceMap'])
    assertion = check_authority_trace(result['trace'], mapping, risk['span'],
        slot=location['slot'], offset=location['offset'], width=location['width'], before=before, after=after, caller=actor)
    if _hex(result['receipt']['status']) != 1 or not assertion['valid']:
        raise ValueError('未授权主体未正常持久改变同一权限资源')
    transaction_index = len(session.records) - 1
    consumer_execution = None
    for consumer in consumers:
        entry = next(item for item in bundle['entries'] if item['declarationId'] == consumer['declarationId'])
        consumer_abi = _runtime_abi(artifact, entry)
        try:
            arguments = _argument_values(consumer_abi, actor, number=1)
        except ValueError:
            continue
        observed = session.transact(sender=actor, address=address, data=session.calldata(consumer_abi, arguments))
        check = check_consumer_trace(observed['trace'], mapping, consumer['guard']['span'],
            consumer['operation']['span'], location=location, caller=actor)
        if _hex(observed['receipt']['status']) == 1 and check['valid']:
            consumer_execution = {**check, 'entry': entry['signature'],
                                  'transactionIndex': len(session.records) - 1}
            break
        if _hex(observed['receipt']['status']) == 1:
            break  # 状态已变化，不能继续在新初态上拼接不同消费者。
    if consumer_execution is None:
        raise ValueError('权限消费者未在同一初态实际正常读取权限并执行敏感操作')
    return {'kind': 'ACCESS_CONTROL_AUTHORITY_WRITE', 'assertion': assertion,
            'location': location, 'initialization': {'runtimeInitialized': True, 'authorityBefore': hex(before),
                                                    'consumerFundingReceiptIndex': funding_index},
            'caller': actor, 'target': address, 'transactionIndex': transaction_index,
            'normalExit': True, 'authorityConsumers': consumers,
            'consumerExecution': consumer_execution,
            'effectReferences': refs + consumption_refs}


def _normalized(records):
    # 回执的区块哈希包含节点生成细节；交易内容、状态、事件和完整指令执行均独立对账。
    return [{'transaction': item['transaction'], 'timestamp': item['timestamp'],
             'receipt': {key: item['receipt'].get(key) for key in ('status', 'from', 'to', 'contractAddress',
                          'gasUsed', 'logs', 'transactionIndex')}, 'trace': item['trace']} for item in records]


def execute_bound_witness(bundle, hypothesis, graph, risk, resource, tool_binding, *, root):
    """提供器实际执行两次；调用方填写的成功字段不参与准入。"""
    directory = None
    try:
        root = Path(root).resolve()
        if bundle.get('verificationStatus') != 'RECOMPILED_MATCH' or tool_binding.get('status') != 'MATCH':
            raise ValueError('有限执行缺实际编译与独立 Slither 双收据')
        configuration = _configuration(root)
        directory = root / _EVIDENCE / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        identities, witnesses = [], []
        for index in range(2):
            run_directory = directory / str(index)
            run_directory.mkdir()
            output, compilation_hash = _execution_artifacts(bundle, run_directory)
            with _node(configuration, run_directory) as rpc:
                session = _Session(rpc, configuration, run_directory)
                run = _run_cei if hypothesis['vulnerabilityType'] == 'REENTRANCY' else _run_authority
                witness = run(session, bundle, output, graph, risk, resource, tool_binding)
                identity = {'schemaVersion': _SCHEMA, 'configuration': configuration,
                    'sourceHash': bundle['sourceHash'], 'manifestDigest': bundle['manifestDigest'],
                    'compilerReceiptDigest': bundle['receiptDigest'], 'executionCompilationHash': compilation_hash,
                    'providerSha256': _sha(Path(__file__).read_bytes()), 'candidate': hypothesis,
                    'deployments': session.deployments, 'witness': witness,
                    'executionDigest': fingerprint(_normalized(session.records))}
                atomic_json(run_directory / 'receipt.json', identity)
                identities.append(identity)
                witnesses.append(witness)
        if encode(identities[0]) != encode(identities[1]):
            raise ValueError('独立 EVM 重放的部署、实际路径或持久状态发生漂移')
        for tool in ('anvil', 'cast'):
            if _sha(Path(configuration[tool]['path']).read_bytes()) != configuration[tool]['sha256']:
                raise ValueError('本机执行工具在重放期间发生漂移')
        receipt_paths = [str((directory / str(index) / 'receipt.json').relative_to(root)) for index in range(2)]
        return {'status': 'MATCH', 'provider': _SCHEMA, 'witness': witnesses[0],
                'receipts': [{'path': path, 'sha256': _sha((root / path).read_bytes())} for path in receipt_paths],
                'reason': '固定原字节码的正常业务执行、源映射、实际状态和独立节点重放匹配',
                'paidModelRequests': 0}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        return {'status': 'UNKNOWN', 'provider': _SCHEMA, 'reason': str(error),
                'errorCategory': 'EVM_WITNESS_UNVERIFIED', 'paidModelRequests': 0,
                'artifactDirectory': str(directory.relative_to(root)) if directory is not None else None}
    finally:
        if directory is not None:
            from organize_storage import archive_file
            records = []
            for path in sorted(directory.glob('*/*.json')):
                if path.name != 'receipt.json':
                    records.append(archive_file(path))
            atomic_json(directory / 'artifact-index.json', {'artifacts': records,
                'readPolicy': 'storage.read_artifact()还原原始字节；失败与成功原件均保留'})
