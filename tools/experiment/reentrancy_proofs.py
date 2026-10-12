"""绑定编译 AST 的有限重入保护与 CEI 防御断言；不生成攻击或利用轨迹。"""
import copy
import itertools
import re

from compiler_facts import extract_compiler_facts
from compiled_d2 import _Graph, _false_resource, _reference, _risk_matches, _walk


_OBLIGATIONS = ('actor', 'resource', 'pre_risk_guard', 'entry_coverage', 'state_version', 'bypass')
_SENDER = ('builtin', 'msg.sender')
_TRUE = ('literal', 'bool', 'true')
_FALSE = ('literal', 'bool', 'false')
_ZERO = ('literal', 'number', '0')
_MAX_PATHS = 128
_MAX_SYMBOLS = 6


def _empty():
    return {'status': 'UNKNOWN', 'proofKind': 'REENTRANCY_PROTECTION', 'candidateBound': False,
            'references': [], 'obligations': [{'name': name, 'status': 'UNKNOWN', 'references': [],
                'reason': '尚未建立完整重入保护或可满足 CEI 防御断言'} for name in _OBLIGATIONS],
            'pathEvidence': {'status': 'UNKNOWN', 'references': [], 'kind': 'FINITE_CEI_ASSERTION',
                'transactionFeasibility': 'UNVERIFIED'},
            'proofScope': {'complete': False, 'entries': [], 'gaps': [], 'callClosure': [],
                'rules': [], 'claim': '仅核验绑定运行期 AST 的重入保护与 CEI 顺序；不声称漏洞可利用性'}}


def _bare(expression):
    return (isinstance(expression, dict) and expression.get('nodeType') == 'MemberAccess'
            and expression.get('memberName') == 'call'
            and expression.get('typeDescriptions', {}).get('typeIdentifier', '').startswith('t_function_barecall_'))


def _low_spec(ast):
    """调用名字必须同时满足编译器 barecall/setvalue 类型，其他低级调用不套用规则。"""
    if not isinstance(ast, dict) or ast.get('nodeType') != 'FunctionCall' or ast.get('kind') == 'typeConversion':
        return None
    expression = ast.get('expression', {})
    if expression.get('nodeType') == 'FunctionCallOptions':
        base = expression.get('expression', {})
        if _bare(base) and expression.get('names') == ['value'] and len(expression.get('options', [])) == 1:
            return base.get('expression'), expression['options'][0]
    if expression.get('nodeType') == 'FunctionCall':
        setter = expression.get('expression', {})
        base = setter.get('expression', {})
        if (setter.get('nodeType') == 'MemberAccess' and setter.get('memberName') == 'value'
                and setter.get('typeDescriptions', {}).get('typeIdentifier', '').startswith('t_function_setvalue_')
                and _bare(base) and len(expression.get('arguments', [])) == 1):
            return base.get('expression'), expression['arguments'][0]
    return None


class _ReentrancyGraph(_Graph):
    """只补充编译类型确定的 CALL(value) 与成功返回值；不提升其他未知语法。"""

    def pure(self, ast, env):
        if (isinstance(ast, dict) and ast.get('nodeType') == 'MemberAccess' and ast.get('memberName') == 'value'
                and super().pure(ast.get('expression'), env) == ('builtin', 'msg')):
            return ('builtin', 'msg.value')
        return super().pure(ast, env)

    def expr(self, ast, tails, env, stack, context):
        if isinstance(ast, dict) and ast.get('nodeType') == 'Assignment' and ast.get('operator') in {'+=', '-='}:
            left = ast.get('leftHandSide')
            resource = self.resource(left, env)
            if resource is not None and not self.effects(left):
                old = self.pure(left, env)
                if _uint_width(old) is not None:
                    tails, right, env = self.expr(ast.get('rightHandSide'), tails, env, stack, context)
                    value = ('binary', ast['operator'][0], old, right)
                    evaluation = self.add('EVAL', ast, tails, context, env, value=value, valueType=old[3])
                    node = self.add('WRITE', ast, [evaluation], context, env, resource=resource, value=value)
                    self.record_write(resource, value, env, node)
                    return [node], value, env
        tails, value, env = super().expr(ast, tails, env, stack, context)
        if (isinstance(ast, dict) and (ast.get('nodeType') == 'BinaryOperation'
                and ast.get('operator') not in {'==', '!=', '>', '>=', '<', '<=', '&&', '||'}
                or ast.get('nodeType') == 'UnaryOperation' and ast.get('operator') not in {'!', '++', '--', 'delete'})):
            # 未使用的局部值和返回表达式也必须显式求值，不能遗漏除零或 checked 溢出。
            node = self.add('EVAL', ast, tails, context, env, value=value,
                            valueType=ast.get('typeDescriptions', {}).get('typeIdentifier', ''))
            tails = [node]
        return tails, value, env

    def call(self, ast, tails, env, stack, context):
        spec = _low_spec(ast)
        if spec is not None:
            receiver, amount = spec
            expressions = [receiver, amount] + list(ast.get('arguments', []))
            if any(self.effects(item) for item in expressions):
                self.gap('数值 CALL 的地址、数值或参数含副作用，尚未证明求值顺序')
            tails, target, env = self.expr(receiver, tails, env, stack, context)
            tails, value, env = self.expr(amount, tails, env, stack, context)
            arguments = []
            for argument in ast.get('arguments', []):
                tails, item, env = self.expr(argument, tails, env, stack, context)
                arguments.append(item)
            node = self.add('CALL', ast, tails, context, env, callKind='CALL', targetDeclarationId=None,
                            targetResource=self.resource(receiver, env), targetValue=target,
                            transferValue=value, arguments=tuple(arguments), lowLevelValueCall=True)
            env['epoch'] += 1
            env['stateValues'].clear()
            return_type = ast.get('expression', {}).get('typeDescriptions', {}).get('typeIdentifier', '')
            value = ('call-result', node)
            if 'returns$_t_bool_$_t_bytes_memory_ptr_$' in return_type:
                # 只绑定编译器确定的成功布尔量，返回数据内容仍未建模。
                value = ('tuple', value, ('unknown', 'return-data', node))
            return [node], value, env
        if ast.get('kind') == 'typeConversion' and len(ast.get('arguments', [])) == 1:
            result_type = ast.get('typeDescriptions', {}).get('typeIdentifier', '')
            if result_type in {'t_address', 't_address_payable'}:
                return self.expr(ast['arguments'][0], tails, env, stack, context)
        return super().call(ast, tails, env, stack, context)


def _caller_balance(call, graph=None):
    """资源身份、msg.sender key、uint 类型和转账数值均来自 AST 结构。"""
    amount = call.get('transferValue')
    if not call.get('lowLevelValueCall') or call.get('targetValue') != _SENDER or not isinstance(amount, tuple):
        return None
    candidates = [amount] if amount[:1] == ('read',) else []
    if graph is not None:
        candidates.extend(read for guard, condition in graph.guards(call)
            for read in _guard_balance_reads(condition, amount) if _current_read(guard, read))
    resources = {read[1] for read in candidates if _uint_width(read) is not None
                 and read[1][2] == (('index', _SENDER),)}
    return next(iter(resources)) if len(resources) == 1 else None


def _current_read(node, value):
    return (isinstance(value, tuple) and value[:1] == ('read',)
            and value[2] == (node.get('versionsBefore', {}).get(value[1], 'initial'), node.get('epochBefore')))


def _guard_balance_reads(condition, amount):
    if condition[:2] == ('binary', '&&'):
        return _guard_balance_reads(condition[2], amount) + _guard_balance_reads(condition[3], amount)
    if condition[:1] != ('binary',):
        return []
    operator, left, right = condition[1:]
    if operator in {'<', '<='}:
        left, right = right, left
        operator = {'<': '>', '<=': '>='}[operator]
    if (isinstance(left, tuple) and left[:1] == ('read',) and _uint_width(left) is not None
            and (operator == '>' and left == amount and right == _ZERO
                 or operator in {'>=', '=='} and right == amount and left != amount)):
        return [left]
    return []


def _prebalance(graph, call):
    amount = call.get('transferValue')
    return [(guard, condition) for guard, condition in graph.guards(call)
            if any(_current_read(guard, read) for read in _guard_balance_reads(condition, amount))]


def _debit(value, balance, amount):
    return (value == _ZERO or isinstance(value, tuple) and value[:2] == ('binary', '-')
            and isinstance(value[2], tuple) and value[2][:1] == ('read',)
            and value[2][1] == balance and value[3] == amount)


def _exhaustive_debit(value, balance, amount, guards):
    if value == _ZERO:
        return True
    if not _debit(value, balance, amount):
        return False
    old = value[2]
    if old == amount:
        return True
    def equality(condition):
        if condition[:2] == ('binary', '&&'):
            return equality(condition[2]) or equality(condition[3])
        return condition == ('binary', '==', old, amount) or condition == ('binary', '==', amount, old)
    return any(equality(condition) for _, condition in guards)


def _funded_deposit(graph, balance):
    writes = [node for node in graph.nodes if node['kind'] == 'WRITE']
    function = graph.bundle['functions'][graph.entry['declarationId']]
    exits = [node for node in graph.nodes if node['kind'] == 'EXIT']
    if (graph.gaps or not writes or graph.bundle['functions'][graph.entry['declarationId']]['stateMutability'] != 'payable'
            or any(node['kind'] not in {'ENTRY', 'EXIT', 'WRITE', 'EVAL', 'RETURN'} for node in graph.nodes)
            or len(exits) != 1 or not _normal_reachable(graph, graph.start, exits[0]['id'])
            or any(not _normal_reachable(graph, write['id'], exits[0]['id']) for write in writes)
            or any(_parameter_initial_value(parameter) is None for parameter in function['parameters'])):
        return False
    for node in graph.nodes:
        if node['kind'] == 'RETURN' and graph.bundle['nodes'][node['nodeId']].get('expression') is not None:
            try:
                _literal(node['value'])
            except _Unevaluated:
                return False
    for write in writes:
        value, resource = write['value'], write['resource']
        account = resource[1] == balance[1] and len(resource[2]) == 1 and resource[2][0][0] == 'index'
        if (not account and resource[2] or value[:2] != ('binary', '+')
                or value[3] != ('builtin', 'msg.value') or value[2][:1] != ('read',)
                or _uint_width(value[2]) is None or value[2][1] != resource or not _current_read(write, value[2])):
            return False
        key = resource[2][0][1] if account else _SENDER
        if account and key != _SENDER:
            declaration = graph.bundle['declarations'].get(key[1], {}) if key[:1] == ('parameter',) else {}
            if declaration.get('typeDescriptions', {}).get('typeIdentifier') not in {'t_address', 't_address_payable'}:
                return False
    if any(node['kind'] == 'EVAL' and node['value'] not in [write['value'] for write in writes] for node in graph.nodes):
        return False
    return (sum(write['resource'][1] == balance[1] for write in writes) == 1
            and len({write['resource'] for write in writes}) == len(writes))


def _parameter_initial_value(parameter):
    """资金建态实参必须匹配实际编译类型，无关数值参数采用零值。"""
    identity = parameter.get('typeDescriptions', {}).get('typeIdentifier', '')
    if identity in {'t_address', 't_address_payable'}:
        return '调用主体 A'
    if re.fullmatch(r't_uint\d+', identity):
        return 0
    if identity == 't_bool':
        return False
    return None


def _initialization_gaps(bundle):
    """未建模构造程序时只允许编译声明明确的默认初值，不能枚举不可达的槽值。"""
    lineage = set(bundle['contracts'][bundle['targetContractId']]['linearizedBaseContracts'])
    gaps = []
    for identity in lineage:
        contract = bundle['contracts'][identity]['node']
        if any(base.get('arguments') for base in contract.get('baseContracts', [])):
            gaps.append(f'合约 {identity} 的基类构造实参语义尚未核验')
        for declaration in contract.get('nodes', []):
            if declaration.get('nodeType') != 'VariableDeclaration' or not declaration.get('stateVariable'):
                continue
            initial = declaration.get('value')
            if initial is None:
                continue
            default = (initial.get('nodeType') == 'Literal'
                       and (initial.get('kind') == 'bool' and initial.get('value') == 'false'
                            or initial.get('kind') == 'number' and initial.get('value') == '0'))
            if not default:
                gaps.append(f'状态槽 {declaration["id"]} 的非默认初值尚未核验，不能假设零或 False')
    for function in bundle['functions'].values():
        if function['contractId'] not in lineage or function['kind'] != 'constructor':
            continue
        body = function['body']
        if function['modifiers'] or body is None or body.get('statements'):
            gaps.append(f'构造声明 {function["id"]} 的初始化语义尚未核验')
    return gaps


def _entries(bundle):
    entries = copy.deepcopy(bundle['entries'])
    listed = {entry['declarationId'] for entry in entries}
    for identity in bundle['contracts'][bundle['targetContractId']]['effectiveFunctions']:
        function = bundle['functions'][identity]
        if function['kind'] in {'fallback', 'receive'} and identity not in listed:
            entries.append({'signature': function['signature'], 'kind': function['kind'],
                            'declarationId': identity, 'matched': True})
    return entries


def _references(result, bundle, nodes):
    refs = []
    for node in nodes:
        reference = _reference(node, bundle)
        if reference is not None and reference not in refs:
            refs.append(reference)
    for reference in refs:
        if reference not in result['references']:
            result['references'].append(reference)
    return refs


def _normal_reachable(graph, start, end, avoid=None):
    pending, seen = [start], set()
    while pending:
        current = pending.pop()
        if current == end:
            return True
        if current in seen or current == avoid:
            continue
        seen.add(current)
        pending.extend(edge['to'] for edge in graph.edges if edge['from'] == current and edge['kind'] != 'abort')
    return False


def _mutex_for(graph, call):
    choices = []
    for guard, condition in graph.guards(call):
        resource = _false_resource(condition)
        if resource is None or resource[2]:
            continue
        reads = [value for value in _read_terms(condition) if value[1] == resource]
        if not reads or not all(_current_read(guard, value) for value in reads):
            continue
        acquired = [node for node in graph.nodes if node['kind'] == 'WRITE'
                    and node.get('resource') == resource and node.get('value') == _TRUE
                    and graph.dominates(guard['id'], node['id']) and graph.dominates(node['id'], call['id'])
                    and not graph.intervening(guard, node, resource)]
        if acquired and _lock_held(graph, call, resource, acquired[-1]):
            choices.append((resource, guard, acquired[-1]))
    return choices


def _lock_held(graph, node, resource, acquired=None):
    """CALL 清空局部值缓存后仍盘点本函数锁写；全入口阻断是单独核验的归纳前提。"""
    acquisitions = [acquired] if acquired is not None else [item for item in graph.nodes
        if item['kind'] == 'WRITE' and item['resource'] == resource and item['value'] == _TRUE
        and graph.dominates(item['id'], node['id'])]
    for acquire in acquisitions:
        invalidating = [item for item in graph.nodes if item['kind'] == 'WRITE'
            and item['id'] not in {acquire['id'], node['id']} and item['resource'][1] == resource[1]
            and _normal_reachable(graph, acquire['id'], item['id'])
            and _normal_reachable(graph, item['id'], node['id'])
            and (item['resource'] != resource or item['value'] != _TRUE)]
        if not invalidating:
            return True
    return False


def _read_terms(value):
    if isinstance(value, tuple):
        if value[:1] == ('read',):
            yield value
        for child in value:
            yield from _read_terms(child)


def _related(graph, root):
    """仅有余额读取与数值 CALL 的入口同样能够打开窗口，不能只盘点 WRITE。"""
    if any(node.get('nodeType') == 'Identifier' and node.get('referencedDeclaration') == root
           for identity in graph.closure for node in _walk(graph.bundle['functions'][identity]['body'])):
        return True
    for node in graph.nodes:
        if node['kind'] == 'WRITE' and node['resource'][1] == root:
            return True
        values = [node.get(field) for field in ('condition', 'value', 'transferValue', 'targetValue', 'arguments')]
        if any(read[1][1] == root for value in values for read in _read_terms(value)):
            return True
        if node['kind'] == 'CALL':
            balance = _caller_balance(node, graph)
            if balance is not None and balance[1] == root:
                return True
    return False


def _mutex_complete(graphs, entries, resource, balance):
    evidence, gaps = [], []
    roots = {resource[1], balance[1]}
    for entry in entries:
        graph = graphs.get(entry['declarationId'])
        if graph is None:
            continue
        writes = [node for node in graph.nodes if node['kind'] == 'WRITE' and node['resource'][1] in roots]
        if not writes and not _related(graph, balance[1]):
            continue
        guards = [(node, condition) for node in graph.nodes if node['kind'] == 'CHECK'
                  for condition in [node['condition']] if _false_resource(condition) == resource
                  and all(_current_read(node, value) for value in _read_terms(condition))]
        for write in writes:
            candidates = [(guard, condition) for guard, condition in guards
                          if graph.dominates(guard['id'], write['id'])]
            acquiring = write['resource'] == resource and write['value'] == _TRUE
            if acquiring:
                candidates = [(guard, condition) for guard, condition in candidates
                              if not graph.intervening(guard, write, resource)]
            elif not _lock_held(graph, write, resource):
                candidates = []
            if not candidates:
                gaps.append(f'{entry["signature"]}：相关资源写入未被同一全局互斥锁覆盖')
            else:
                evidence.extend([candidates[0][0], write])
        for call in graph.nodes:
            if call['kind'] != 'CALL' or call.get('callKind') == 'STATICCALL':
                continue
            if not any(choice[0] == resource for choice in _mutex_for(graph, call)):
                gaps.append(f'{entry["signature"]}：更早或其他 CALL 窗口未保持同一全局锁')
            evidence.append(call)
    return evidence, gaps


def _cei_local(graph, call, balance):
    guards = _prebalance(graph, call)
    writes = [node for node in graph.nodes if node['kind'] == 'WRITE' and node['resource'] == balance
              and _debit(node['value'], balance, call.get('transferValue')) and graph.dominates(node['id'], call['id'])]
    if not guards or not writes:
        return None
    guard = guards[0][0]
    eligible = [write for write in writes if graph.dominates(guard['id'], write['id'])
                and not graph.intervening(guard, write, balance)
                and _exhaustive_debit(write['value'], balance, call.get('transferValue'), guards)]
    if not eligible or call.get('stateBefore', {}).get(balance) != eligible[-1]['value']:
        return None
    write = eligible[-1]
    if any(node['kind'] == 'CALL' and node.get('callKind') != 'STATICCALL'
           and _normal_reachable(graph, graph.start, node['id'])
           and _normal_reachable(graph, node['id'], write['id']) for node in graph.nodes):
        return None
    if any(node['kind'] == 'WRITE' and node['resource'][1] == balance[1]
           and _normal_reachable(graph, call['id'], node['id']) for node in graph.nodes):
        return None
    return [guard, write, call]


def _cei_complete(graphs, entries, balance):
    evidence, gaps = [], []
    for entry in entries:
        graph = graphs.get(entry['declarationId'])
        if graph is None:
            continue
        writes = [node for node in graph.nodes if node['kind'] == 'WRITE' and node['resource'][1] == balance[1]]
        if not writes and not _related(graph, balance[1]):
            continue
        calls = [node for node in graph.nodes if node['kind'] == 'CALL' and node.get('callKind') != 'STATICCALL']
        if not calls and writes:
            if _funded_deposit(graph, balance):
                evidence.extend(writes)
                continue
            gaps.append(f'{entry["signature"]}：仅写入相关余额的入口缺少经济来源或互斥锁证明')
        for call in calls:
            other_balance = _caller_balance(call, graph)
            local = _cei_local(graph, call, other_balance) if other_balance and other_balance[1] == balance[1] else None
            if local is None:
                gaps.append(f'{entry["signature"]}：数值调用未保持同主体、同资源的严格 CEI')
            else:
                evidence.extend(local)
        if any(write['resource'][2] != (('index', _SENDER),)
               or not any(_debit(write['value'], write['resource'], call.get('transferValue')) for call in calls)
               for write in writes):
            gaps.append(f'{entry["signature"]}：余额写入 key 或新值不属于已证明的归零规则')
    return evidence, gaps


def _path_candidates(graph, risk, write):
    """只枚举到正常 EXIT 的无环路径，ABORT 与超限路径不产生满足性断言。"""
    adjacent = {}
    for edge in graph.edges:
        if edge['kind'] != 'abort':
            adjacent.setdefault(edge['from'], []).append(edge)
    pending = [(graph.start, [], [])]
    visited_paths = 0
    while pending and visited_paths < _MAX_PATHS:
        current, nodes, edges = pending.pop()
        if current in nodes:
            continue
        nodes = nodes + [current]
        if graph.nodes[current]['kind'] == 'EXIT':
            visited_paths += 1
            if risk['id'] in nodes and write['id'] in nodes and nodes.index(risk['id']) < nodes.index(write['id']):
                yield nodes, edges
            continue
        pending.extend((edge['to'], nodes, edges + [edge]) for edge in adjacent.get(current, []))


class _Unevaluated(ValueError):
    pass


def _symbols(value):
    if isinstance(value, tuple):
        if value[:1] in {('read',), ('parameter',)}:
            yield value
        for child in value:
            yield from _symbols(child)


def _uint_width(value):
    identity = value[3] if value[:1] == ('read',) else ''
    match = re.fullmatch(r't_uint(\d+)', identity)
    return int(match.group(1)) if match else None


def _literal(value):
    if value == _TRUE:
        return True
    if value == _FALSE:
        return False
    if value[:2] == ('literal', 'number') and re.fullmatch(r'\d+', str(value[2])):
        return int(value[2])
    raise _Unevaluated('字面值未进入有限数值语法')


def _slot(resource, assignments):
    segments = []
    for kind, value in resource[2]:
        if kind != 'index':
            raise _Unevaluated('结构字段资源不进入有限数值反例')
        segments.append(_value(value, assignments, {}, {}, {}))
    return resource[1], tuple(segments)


def _value(term, assignments, initial, versions, calls):
    if not isinstance(term, tuple) or not term:
        raise _Unevaluated('表达式不属于有限 AST 抽象')
    kind = term[0]
    if kind == 'literal':
        return _literal(term)
    if term == _SENDER:
        return '调用主体 A'
    if term == ('builtin', 'msg.value') and term in assignments:
        return assignments[term]
    if kind == 'parameter':
        if term not in assignments:
            raise _Unevaluated('形参类型或数值未绑定')
        return assignments[term]
    if kind == 'read':
        slot = _slot(term[1], assignments)
        version = term[2][0]
        if version == 'initial':
            if slot not in initial:
                initial[slot] = assignments[term]
            value = initial[slot]
        elif type(version) is int and (slot, version) in versions:
            value = versions[(slot, version)]
        else:
            raise _Unevaluated('读到未证明的合流或存储版本')
        width = _uint_width(term)
        if width is not None and (type(value) is not int or value < 0 or value >= 2 ** width):
            raise _Unevaluated('读值越过编译整数类型范围')
        return value
    if kind == 'call-result' and term[1] in calls:
        return calls[term[1]]
    if kind == 'unary' and term[1] == '!':
        value = _value(term[2], assignments, initial, versions, calls)
        if type(value) is not bool:
            raise _Unevaluated('逻辑非的操作数未证明为布尔')
        return not value
    if kind == 'binary':
        operator = term[1]
        left = _value(term[2], assignments, initial, versions, calls)
        right = _value(term[3], assignments, initial, versions, calls)
        if operator in {'&&', '||'}:
            if type(left) is not bool or type(right) is not bool:
                raise _Unevaluated('布尔连接包含未知类型')
            return left and right if operator == '&&' else left or right
        if operator in {'==', '!='}:
            return left == right if operator == '==' else left != right
        if type(left) is not int or type(right) is not int:
            raise _Unevaluated('数值表达式包含未知类型')
        if operator in {'>', '>=', '<', '<='}:
            return {'>': left > right, '>=': left >= right, '<': left < right, '<=': left <= right}[operator]
        if operator in {'+', '-'}:
            result = left + right if operator == '+' else left - right
            # 选择无溢出的数值见证，同时适用于旧版回绕与新版 checked 语义。
            if result < 0 or result >= 2 ** 256:
                raise _Unevaluated('算术结果可能下溢或上溢')
            return result
    raise _Unevaluated('未知 AST 表达式、调用结果或算术语义')


def _funding_state(graph, amount):
    """从默认初值执行已限定的线性入账 AST；辅助总账不能独立猜值。"""
    function = graph.bundle['functions'][graph.entry['declarationId']]
    assignments = {('builtin', 'msg.value'): amount}
    assignments.update({('parameter', p['id']): _parameter_initial_value(p) for p in function['parameters']})
    for node in graph.nodes:
        for symbol in _symbols(node.get('value')):
            if symbol[:1] == ('read',):
                assignments[symbol] = 0 if _uint_width(symbol) is not None else False
    initial, versions, state = {}, {}, {}
    try:
        for node in graph.nodes:
            if node['kind'] in {'WRITE', 'EVAL'}:
                value = _value(node['value'], assignments, initial, versions, {})
                type_id = node.get('valueType') or node['value'][2][3]
                width = re.fullmatch(r't_uint(\d+)', type_id)
                if not width or type(value) is not int or not 0 <= value < 2 ** int(width.group(1)):
                    return None
                if node['kind'] == 'WRITE':
                    slot = _slot(node['resource'], assignments)
                    versions[(slot, node['id'])] = value
                    state[slot] = value
        return state
    except (KeyError, IndexError, TypeError, _Unevaluated):
        return None


def _funding_matches(witness, graph, balance):
    credited = next((item['value'] for item in witness['initialStorage']
                     if item['root'] == balance[1] and item['keys'] == ['调用主体 A']), None)
    if type(credited) is not int or credited < witness['environment']['contractBalanceAtLeast']:
        return False
    state = _funding_state(graph, credited)
    return state is not None and all(
        type(item['value']) is type(state.get((item['root'], tuple(item['keys'])),
            False if type(item['value']) is bool else 0))
        and item['value'] == state.get((item['root'], tuple(item['keys'])),
            False if type(item['value']) is bool else 0)
        for item in witness['initialStorage'])


def _witness(graph, path, edges, bundle, risk, funding_graphs=(), balance=None):
    nodes = [graph.nodes[identity] for identity in path]
    terms = [node.get(field) for node in nodes for field in ('condition', 'value', 'transferValue', 'targetValue')]
    symbols = list(dict.fromkeys(symbol for term in terms for symbol in _symbols(term)))
    if len(symbols) > _MAX_SYMBOLS:
        return None
    domains = []
    for symbol in symbols:
        if symbol[:1] == ('read',):
            if _uint_width(symbol) is not None:
                domains.append((0, 1, 2))
            elif symbol[3] == 't_bool':
                domains.append((False, True))
            else:
                return None
        else:
            declaration = bundle['declarations'].get(symbol[1], {})
            if not re.fullmatch(r't_uint\d+', declaration.get('typeDescriptions', {}).get('typeIdentifier', '')):
                return None
            domains.append((0, 1, 2))
    selected = {edge['from']: edge['kind'] for edge in edges if edge['kind'] in {'true', 'false'}}
    conditional = None
    for values in itertools.product(*domains):
        assignments = dict(zip(symbols, values))
        initial, versions, calls, call_data, checked = {}, {}, {}, [], []
        try:
            for node in nodes:
                kind = node['kind']
                if kind in {'UNKNOWN', 'EXPRESSION'}:
                    raise _Unevaluated('路径包含未证明的语义节点')
                if kind in {'CHECK', 'BRANCH'}:
                    value = _value(node['condition'], assignments, initial, versions, calls)
                    expected = selected.get(node['id']) != 'false'
                    if type(value) is not bool or value != expected:
                        raise _Unevaluated('断言或分支约束未满足')
                    checked.append({'nodeId': node['nodeId'], 'conditionValue': value, 'requiredValue': expected})
                if kind == 'CALL':
                    if not node.get('lowLevelValueCall'):
                        raise _Unevaluated('未知外部合约的正常返回条件未证明')
                    target = _value(node['targetValue'], assignments, initial, versions, calls)
                    amount = _value(node['transferValue'], assignments, initial, versions, calls)
                    if target != '调用主体 A' or type(amount) is not int or amount <= 0:
                        raise _Unevaluated('调用对象或非零数值未绑定')
                    calls[node['id']] = True
                    call_data.append({'nodeId': node['nodeId'], 'success': True, 'value': amount,
                        'recipient': target, 'normalReturn': True,
                        'assumption': '目标接受正常调用且本次不改变本合约存储；仅为 CEI 顺序的有限满足性见证'})
                if kind == 'WRITE':
                    value = _value(node['value'], assignments, initial, versions, calls)
                    slot = _slot(node['resource'], assignments)
                    versions[(slot, node['id'])] = value
                if kind in {'EVAL', 'RETURN'}:
                    if kind == 'RETURN' and graph.bundle['nodes'].get(node['nodeId'], {}).get('expression') is None:
                        continue
                    value = _value(node['value'], assignments, initial, versions, calls)
                    type_id = node.get('valueType', '')
                    match = re.fullmatch(r't_uint(\d+)', type_id)
                    if match and (type(value) is not int or value < 0 or value >= 2 ** int(match.group(1))):
                        raise _Unevaluated('表达式结果越过编译整数类型范围')
            if not any(call['nodeId'] == risk['nodeId'] and call['success'] for call in call_data):
                continue
            witness = {'normalExit': True, 'cfgNodeIds': path, 'conditions': checked, 'calls': call_data,
                'initialStorage': [{'root': slot[0], 'keys': list(slot[1]), 'value': value} for slot, value in initial.items()],
                'parameters': [{'declarationId': symbol[1], 'value': assignments[symbol]} for symbol in symbols if symbol[:1] == ('parameter',)],
                'environment': {'caller': '调用主体 A', 'contractBalanceAtLeast': sum(call['value'] for call in call_data)},
                'scope': '有限 AST 数值与布尔约束；正常 EXIT 的 CEI 顺序反例，不表示攻击交易或漏洞利用证明'}
            if not funding_graphs or any(_funding_matches(witness, funding, balance) for funding in funding_graphs):
                return witness
            if conditional is None:
                conditional = witness
        except (KeyError, TypeError, _Unevaluated):
            continue
    return conditional


def _counterexample(graph, risk, balance, bundle, funding_graphs=()):
    if graph.gaps or _mutex_for(graph, risk):
        return None
    writes = [node for node in graph.nodes if node['kind'] == 'WRITE' and node['resource'] == balance
              and _debit(node['value'], balance, risk.get('transferValue'))
              and _normal_reachable(graph, risk['id'], node['id'])]
    if any(node['kind'] == 'WRITE' and node['resource'][1] == balance[1]
           and _normal_reachable(graph, node['id'], risk['id']) for node in graph.nodes):
        return None
    for write in writes:
        for path, edges in _path_candidates(graph, risk, write):
            witness = _witness(graph, path, edges, bundle, risk, funding_graphs, balance)
            if witness is not None:
                return [graph.nodes[identity] for identity in path], witness
    return None


def prove_reentrancy(bundle, hypothesis):
    """输入真实重新编译匹配的 bundle；Slither 双收据和最终裁决由调用方核验。"""
    result = _empty()
    scope, gaps = result['proofScope'], result['proofScope']['gaps']
    if not isinstance(bundle, dict) or bundle.get('verificationStatus') != 'RECOMPILED_MATCH':
        result['status'] = 'FAILED'
        gaps.append('编译 bundle 尚未实际重编译绑定')
        return result
    if (not isinstance(hypothesis, dict) or type(hypothesis.get('riskLine')) is not int or hypothesis['riskLine'] < 1
            or 'riskFactId' in hypothesis and not isinstance(hypothesis['riskFactId'], str)
            or 'riskSpan' in hypothesis and (not isinstance(hypothesis['riskSpan'], dict)
                or type(hypothesis['riskSpan'].get('start')) is not int
                or type(hypothesis['riskSpan'].get('length')) is not int
                or hypothesis['riskSpan']['start'] < 0 or hypothesis['riskSpan']['length'] < 1)):
        result['status'] = 'FAILED'
        gaps.append('候选位置或数据结构无效')
        return result
    if hypothesis.get('vulnerabilityType') != 'REENTRANCY' or hypothesis.get('riskOperation') != 'CALL':
        gaps.append('该有限证明器只处理重入 CALL 候选')
        return result
    if (hypothesis.get('contract') != bundle['targetContract']
            or hypothesis.get('sourceHash', bundle['sourceHash']) != bundle['sourceHash']
            or hypothesis.get('sourceFile', bundle['targetSourceUnit']) != bundle['targetSourceUnit']
            or hypothesis.get('mechanism', 'REENTRANCY') != 'REENTRANCY'
            or hypothesis.get('riskKind', 'CALL') != 'CALL'):
        result['status'] = 'FAILED'
        gaps.append('候选合约、源码或机制与实际编译目标不一致')
        return result
    signature = hypothesis.get('functionSignature', hypothesis.get('function'))
    name = hypothesis.get('function')
    if (not isinstance(signature, str) or hypothesis.get('functionSignature') is not None and name is not None
            and (not isinstance(name, str) or (name != signature if '(' in name else name != signature.split('(', 1)[0]))):
        result['status'] = 'FAILED'
        gaps.append('候选函数名称与完整签名不一致')
        return result
    entries = _entries(bundle)
    candidates = [entry for entry in entries if entry['kind'] != 'getter' and entry['matched']
                  and (entry['signature'] == signature if '(' in signature else entry['signature'].split('(', 1)[0] == signature)]
    if len(candidates) != 1:
        result['status'] = 'UNKNOWN' if len(candidates) > 1 else 'FAILED'
        gaps.append('候选运行入口未唯一绑定')
        return result
    entry = candidates[0]
    graph = _ReentrancyGraph(bundle, entry)
    facts = extract_compiler_facts(bundle)
    risks = [node for node in graph.nodes if _risk_matches(node, hypothesis, bundle, facts)]
    if len(risks) != 1:
        unsupported = [node for node in graph.nodes if node['kind'] == 'CALL' and node.get('callKind') == 'UNKNOWN'
            and _risk_matches(dict(node, callKind='CALL'), hypothesis, bundle, facts)]
        result['status'] = 'UNKNOWN' if unsupported else 'FAILED'
        gaps.append('候选风险 CALL 未唯一绑定或尚未支持该调用类型')
        return result
    risk = risks[0]
    scope['riskSpan'] = copy.deepcopy(risk['span'])
    scope['functionSignature'] = entry['signature']
    result['candidateBound'] = True
    refs = _references(result, bundle, [risk])
    balance = _caller_balance(risk, graph)
    if balance is None:
        gaps.extend(graph.gaps)
        gaps.append('未绑定同主体 msg.sender 映射余额与编译 uint 转账数值')
        return result
    graphs = {entry['declarationId']: graph}
    gaps.extend(bundle['entryGaps'])
    closure = set()
    for other in entries:
        if not other['matched']:
            gaps.append(f'运行入口 {other["signature"]} 未唯一绑定')
            continue
        if other['kind'] == 'getter':
            scope['entries'].append({'signature': other['signature'], 'kind': other['kind'],
                'declarationId': other['declarationId'], 'matched': True, 'related': False, 'complete': True})
            continue
        other_graph = graphs.setdefault(other['declarationId'], _ReentrancyGraph(bundle, other))
        closure.update(other_graph.closure)
        gaps.extend(f'{other["signature"]}：{gap}' for gap in other_graph.gaps)
        related = _related(other_graph, balance[1])
        scope['entries'].append({'signature': other['signature'], 'kind': other['kind'],
            'declarationId': other['declarationId'], 'matched': True, 'related': related, 'complete': not other_graph.gaps})
    scope['callClosure'] = sorted(closure)
    scope['protectedRoots'] = [balance[1]]
    scope['rules'] = ['编译声明与字节跨度绑定', '同主体映射 key', '正常 EXIT 路径', '有限布尔与整数约束']
    protection_evidence, protection_rule, protection_gaps = None, None, []
    for mutex, guard, acquire in _mutex_for(graph, risk):
        evidence, mutex_gaps = _mutex_complete(graphs, entries, mutex, balance)
        if not mutex_gaps and _prebalance(graph, risk):
            protection_evidence, protection_rule = [guard, acquire, risk] + evidence, 'GLOBAL_MUTEX'
            scope['protectedRoots'].append(mutex[1])
            break
        protection_gaps.extend(mutex_gaps)
    if protection_evidence is None and _cei_local(graph, risk, balance):
        evidence, cei_gaps = _cei_complete(graphs, entries, balance)
        if not cei_gaps:
            protection_evidence, protection_rule = evidence, 'STRICT_CEI'
        protection_gaps.extend(cei_gaps)
    if protection_evidence is not None and not gaps:
        refs = _references(result, bundle, protection_evidence)
        result['status'] = 'PROVED'
        scope['complete'] = True
        scope['rules'].append(protection_rule)
        for obligation in result['obligations']:
            obligation.update(status='SUPPORTED', references=refs,
                reason='同主体资源与前置余额检查已绑定；所有相关入口及早期调用窗口满足统一互斥锁或严格 CEI')
        result['pathEvidence'].update(status='BLOCKED', references=refs,
            reason='所有相关运行入口均受相同全局互斥锁或前置余额归零规则覆盖',
            transactionFeasibility='NOT_REQUIRED_FOR_UNIVERSAL_PROTECTION')
        return result
    deposits = [(other, graphs[other['declarationId']]) for other in entries if other['declarationId'] in graphs
                and _funded_deposit(graphs[other['declarationId']], balance)]
    counterexample = _counterexample(graph, risk, balance, bundle, [item[1] for item in deposits])
    if counterexample is not None:
        nodes, witness = counterexample
        initialization_gaps = _initialization_gaps(bundle)
        gaps.extend(initialization_gaps)
        deposits.sort(key=lambda item: not _funding_matches(witness, item[1], balance))
        if deposits:
            deposit, deposit_graph = deposits[0]
            amount = next(item['value'] for item in witness['initialStorage'] if item['root'] == balance[1])
            function = bundle['functions'][deposit['declarationId']]
            funded = not initialization_gaps and _funding_matches(witness, deposit_graph, balance)
            witness['initialization'] = {'funded': funded, 'entry': deposit['signature'], 'msgValue': amount,
                'parameters': [{'declarationId': parameter['id'], 'value': _parameter_initial_value(parameter)}
                               for parameter in function['parameters']],
                'creditedValue': amount, 'normalExit': True,
                'storageAfter': [{'root': slot[0], 'keys': list(slot[1]), 'value': value}
                    for slot, value in (_funding_state(deposit_graph, amount) or {}).items()],
                'cfgNodeIds': [node['id'] for node in deposit_graph.nodes],
                'reason': '编译 AST 证明 payable 入账以同一 msg.value 增加余额与合约资金；小额数值不溢出',
                'references': _references(result, bundle, [node for node in deposit_graph.nodes if node['kind'] == 'WRITE'])}
        else:
            witness['initialization'] = {'funded': False, 'status': 'ADMISSIBLE_INITIAL_STATE',
                'reason': '有限顺序断言以给定余额与资金为前提；当前 AST 未证明该初始状态的建态历史'}
        if not witness['initialization']['funded']:
            scope['conditionedOnInitialState'] = True
            scope['counterexampleComplete'] = False
            gaps.append('只有条件初始状态见证，未证明余额与资金的可调用建态历史')
            result['pathEvidence'].update(status='CONDITIONAL', references=_references(result, bundle, nodes),
                witness=witness, normalExit=True, transactionFeasibility='CONDITIONAL_INITIAL_STATE',
                reason='给定初始状态下存在正常 EXIT 的 CEI 顺序反例；初始状态可达性尚未证明，最终保持未知')
            return result
        refs = _references(result, bundle, nodes)
        result['status'] = 'COUNTEREXAMPLE'
        result['proofKind'] = 'CEI_COUNTEREXAMPLE'
        scope['counterexampleComplete'] = True
        scope['conditionedOnInitialState'] = False
        scope['rules'].append('NORMAL_EXIT_SATISFIABLE_CEI_ORDER')
        for obligation in result['obligations']:
            protected = (obligation['name'] in {'actor', 'resource'}
                         or obligation['name'] == 'pre_risk_guard' and bool(_prebalance(graph, risk)))
            obligation.update(status='SUPPORTED' if protected else 'REFUTED', references=refs,
                reason='同主体数值 CALL 的非零余额与路径约束已满足；后置归零有正常 EXIT 的有限防御断言反例')
        result['pathEvidence'].update(status='FEASIBLE', references=refs, witness=witness, normalExit=True,
            reason='已给出可调用资金建态、满足受支持路径约束且正常提交的 CEI 顺序反例；不声称攻击可利用性',
            transactionFeasibility='SATISFIABLE_ABSTRACTION')
        return result
    gaps.extend(protection_gaps)
    gaps.append('未建立完整入口保护或正常 EXIT 的可满足 CEI 顺序反例')
    gaps[:] = sorted(set(gaps))
    return result
