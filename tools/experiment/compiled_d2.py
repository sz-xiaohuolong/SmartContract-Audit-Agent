"""绑定编译 AST 的有限控制流核验；静态可达与工具告警不等于可行漏洞。"""
import copy
from fractions import Fraction

from compiler_facts import CompilationBindingError, call_operation, extract_compiler_facts, load_bound_compilation, source_span, _walk
from risk_binding import bind_risks, binding_record, operation_matches

OBLIGATIONS = ('actor', 'resource', 'pre_risk_guard', 'entry_coverage', 'state_version', 'bypass')
_MAX_NODES = 1800
_MAX_DEPTH = 24


def _unknown(identity):
    return ('unknown', identity)


def _contains(value, tag):
    return isinstance(value, tuple) and (value[:1] == (tag,) or any(_contains(child, tag) for child in value))


def _negate(value):
    if value[:1] == ('unary',) and value[1] == '!':
        return value[2]
    if value[:1] == ('binary',) and value[1] in {'==', '!='}:
        return ('binary', '!=' if value[1] == '==' else '==', value[2], value[3])
    return ('unary', '!', value)


def _reads(value):
    result = set()
    if isinstance(value, tuple):
        if value[:1] == ('read',):
            result.add(value[1])
        for child in value:
            result.update(_reads(child))
    return result


def _authority_read(condition):
    """保留权限读取的版本；OR 的两侧必须为同一版本，否则存在旧值旁路。"""
    if condition[:2] == ('binary', '&&'):
        return _authority_read(condition[2]) or _authority_read(condition[3])
    if condition[:2] == ('binary', '||'):
        left, right = _authority_read(condition[2]), _authority_read(condition[3])
        return left if left and left == right else None
    if condition[:2] != ('binary', '=='):
        return None
    left, right = condition[2:4]
    value = right if left == ('builtin', 'msg.sender') else left if right == ('builtin', 'msg.sender') else None
    if isinstance(value, tuple) and value[:1] == ('read',) and value[3] == 't_address':
        return value
    return None


def _authority(condition):
    value = _authority_read(condition)
    return value[1] if value else None


def _current_authority(node, condition):
    value = _authority_read(condition)
    return value is not None and value[2] == (node.get('versionsBefore', {}).get(value[1], 'initial'),
                                            node.get('epochBefore'))


def _false_resource(condition):
    """识别 require(!资源) 或资源==false，字段与 key 已完成参数代入。"""
    if condition[:2] == ('binary', '&&'):
        return _false_resource(condition[2]) or _false_resource(condition[3])
    if condition[:2] == ('unary', '!') and condition[2][:1] == ('read',):
        return condition[2][1]
    if condition[:2] == ('binary', '=='):
        left, right = condition[2:4]
        if right == ('literal', 'bool', 'false') and left[:1] == ('read',):
            return left[1]
        if left == ('literal', 'bool', 'false') and right[:1] == ('read',):
            return right[1]
    return None


class _Graph:
    """为单个运行期入口建立结构化 CFG；所有未知结构显式进入缺口。"""
    def __init__(self, bundle, entry):
        self.bundle, self.entry = bundle, entry
        self.nodes, self.edges, self.gaps, self.closure = [], [], [], set()
        self.return_frames = []
        self.exhausted = False
        self.start = self.add('ENTRY', None, [], (), {})
        env = {'values': {}, 'versions': {}, 'stateValues': {}, 'epoch': 0}
        function = bundle['functions'][entry['declarationId']]
        arguments = [('parameter', p['id']) for p in function['parameters']]
        tails, _, _ = self.function(function['id'], arguments, [self.start], env, (), ())
        self.add('EXIT', None, tails, (), {})

    def gap(self, message):
        if message not in self.gaps:
            self.gaps.append(message)

    def add(self, kind, ast, tails, context, env, **fields):
        if len(self.nodes) >= _MAX_NODES:
            self.gap('CFG 节点预算超限')
            self.exhausted = True
            return self.nodes[-1]['id']
        identity = len(self.nodes)
        item = {'id': identity, 'kind': kind, 'context': list(context), **fields}
        if ast:
            span = source_span(ast, self.bundle['units'])
            item.update(nodeId=ast['id'], span=span, line=span['line'])
        if kind in {'CALL', 'WRITE', 'CHECK', 'BRANCH'}:
            item['stateBefore'] = copy.deepcopy(env.get('stateValues', {}))
            item['versionsBefore'] = copy.deepcopy(env.get('versions', {}))
            item['epochBefore'] = env.get('epoch', 0)
        self.nodes.append(item)
        self.edges.extend({'from': tail, 'to': identity, 'kind': 'normal'} for tail in tails)
        return identity

    def resource(self, ast, env):
        if not isinstance(ast, dict):
            return None
        kind = ast.get('nodeType')
        if kind == 'Identifier':
            identity = ast.get('referencedDeclaration')
            declaration = self.bundle['declarations'].get(identity, {})
            if declaration.get('stateVariable'):
                return ('resource', identity, ())
            # 显式静态库 storage 形参的唯一资源绑定；一般局部 storage alias 仍不支持。
            value = env['values'].get(identity)
            return value if isinstance(value, tuple) and value[:1] == ('resource',) else None
        if kind in {'IndexAccess', 'MemberAccess'}:
            base = ast.get('baseExpression') if kind == 'IndexAccess' else ast.get('expression')
            parent = self.resource(base, env)
            if parent is None:
                return None
            if kind == 'IndexAccess':
                key = self.pure(ast.get('indexExpression'), env)
                return (parent[0], parent[1], parent[2] + (('index', key),))
            identity = ast.get('referencedDeclaration')
            if identity not in self.bundle['declarations']:
                self.gap('状态成员没有唯一声明身份')
                return None
            return (parent[0], parent[1], parent[2] + (('member', identity),))
        return None

    def pure(self, ast, env):
        """无副作用的表达式结构；函数调用由 expr 展开而非在此猜测。"""
        if not isinstance(ast, dict):
            return _unknown(None)
        identity, kind = ast.get('id'), ast.get('nodeType')
        resource = self.resource(ast, env)
        if resource is not None:
            env['versions'].setdefault(resource, 'initial')
            return ('read', resource, (env['versions'][resource], env['epoch']),
                    ast.get('typeDescriptions', {}).get('typeIdentifier') or
                    self.bundle['declarations'].get(ast.get('referencedDeclaration'), {}).get(
                        'typeDescriptions', {}).get('typeIdentifier', ''))
        if kind == 'Identifier':
            reference = ast.get('referencedDeclaration')
            if reference in env['values']:
                return env['values'][reference]
            builtin = self.bundle['builtinReferences'].get(reference)
            return ('builtin', builtin) if builtin else ('variable', reference)
        if kind == 'MemberAccess':
            base = self.pure(ast.get('expression'), env)
            if base == ('builtin', 'msg') and ast.get('memberName') == 'sender':
                return ('builtin', 'msg.sender')
            return ('member', base, ast.get('referencedDeclaration'), ast.get('memberName'))
        if kind == 'Literal':
            if ast.get('kind') == 'number' and ast.get('subdenomination'):
                factors = {'wei': 1, 'gwei': 10 ** 9, 'ether': 10 ** 18, 'seconds': 1,
                           'minutes': 60, 'hours': 3600, 'days': 86400, 'weeks': 604800}
                try:
                    scaled = Fraction(ast['value']) * factors[ast['subdenomination']]
                    return ('literal', 'number', str(scaled.numerator)) if scaled.denominator == 1 else _unknown(identity)
                except (KeyError, ValueError, ZeroDivisionError):
                    return _unknown(identity)
            return ('literal', ast.get('kind'), ast.get('value', ast.get('hexValue')))
        if kind == 'BinaryOperation':
            return ('binary', ast.get('operator'), self.pure(ast.get('leftExpression'), env),
                    self.pure(ast.get('rightExpression'), env))
        if kind == 'UnaryOperation' and ast.get('operator') not in {'++', '--', 'delete'}:
            return ('unary', ast.get('operator'), self.pure(ast.get('subExpression'), env))
        if kind == 'TupleExpression' and len(ast.get('components', [])) == 1:
            return self.pure(ast['components'][0], env)
        return _unknown(identity)

    def effects(self, ast):
        """编译器保证的 pure/view 内部调用不写状态；未知或外部调用保守计入。"""
        result = []
        for node in _walk(ast):
            kind = node.get('nodeType')
            if kind in {'Assignment', 'NewExpression'} or kind == 'UnaryOperation' and node.get('operator') in {'++', '--', 'delete'}:
                result.append(node)
            if kind != 'FunctionCall' or node.get('kind') == 'typeConversion':
                continue
            expression = node.get('expression', {})
            type_id = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
            reference = expression.get('referencedDeclaration')
            builtin = self.bundle['builtinReferences'].get(reference)
            target = self.bundle['functions'].get(reference, {})
            pure_builtin = builtin in {'sha256', 'keccak256', 'ripemd160', 'ecrecover', 'addmod', 'mulmod'}
            pure_encoding = type_id.startswith(('t_function_abiencode', 't_function_bytesconcat', 't_function_stringconcat'))
            readonly_internal = type_id.startswith('t_function_internal') and target.get('stateMutability') in {'view', 'pure'}
            if not (pure_builtin or pure_encoding or readonly_internal):
                result.append(node)
        return result

    def observes_state(self, ast):
        for node in _walk(ast):
            if node.get('nodeType') == 'Identifier' and self.bundle['declarations'].get(
                    node.get('referencedDeclaration'), {}).get('stateVariable'):
                return True
            if node.get('nodeType') == 'FunctionCall' and node.get('kind') != 'typeConversion':
                expression = node.get('expression', {})
                builtin = self.bundle['builtinReferences'].get(expression.get('referencedDeclaration'))
                type_id = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
                if builtin not in {'sha256', 'keccak256', 'ripemd160', 'ecrecover', 'addmod', 'mulmod'} and not type_id.startswith('t_function_abiencode'):
                    return True
        return False

    def conditional_calls(self, ast):
        return [node for node in _walk(ast) if node.get('nodeType') == 'FunctionCall'
                and node.get('kind') != 'typeConversion'
                and not self.bundle['builtinReferences'].get(node.get('expression', {}).get('referencedDeclaration'))
                in {'sha256', 'keccak256', 'ripemd160', 'ecrecover', 'addmod', 'mulmod'}
                and not node.get('expression', {}).get('typeDescriptions', {}).get('typeIdentifier', '').startswith('t_function_abiencode')]

    def record_write(self, resource, value, env, node):
        # 不同符号 key 在运行时可能相等；同根旧事实一律失效，不能缓存为仍锁定。
        for observed in set(env['versions']) | set(env['stateValues']):
            if observed != resource and observed[1] == resource[1]:
                env['versions'][observed] = ('unknown', 'possible-alias', node)
                env['stateValues'].pop(observed, None)
        env['versions'][resource] = node
        env['stateValues'][resource] = value

    def expr(self, ast, tails, env, stack, context):
        if not isinstance(ast, dict) or self.exhausted:
            return tails, _unknown(None), env
        kind = ast['nodeType']
        if kind == 'FunctionCall':
            return self.call(ast, tails, env, stack, context)
        if kind == 'Assignment':
            left, right = ast.get('leftHandSide'), ast.get('rightHandSide')
            if self.effects(left):
                self.gap('赋值左侧 key 含副作用，求值顺序未证明')
            tails, value, env = self.expr(right, tails, env, stack, context)
            resource = self.resource(left, env)
            if resource is not None:
                if ast.get('operator') != '=':
                    self.gap('复合状态赋值语义尚未证明')
                    value = _unknown(ast['id'])
                node = self.add('WRITE', ast, tails, context, env, resource=resource, value=value)
                self.record_write(resource, value, env, node)
                return [node], value, env
            reference = left.get('referencedDeclaration') if isinstance(left, dict) else None
            declaration = self.bundle['declarations'].get(reference, {})
            if declaration.get('nodeType') == 'VariableDeclaration' and not declaration.get('stateVariable'):
                if declaration.get('storageLocation') == 'storage' or ast.get('operator') != '=':
                    self.gap('存储别名或复合局部赋值尚未支持')
                    value = _unknown(ast['id'])
                env['values'][reference] = value
                return tails, value, env
            self.gap('无法解析赋值资源')
            node = self.add('UNKNOWN', ast, tails, context, env)
            return [node], _unknown(ast['id']), env
        if kind == 'BinaryOperation':
            left, right = ast.get('leftExpression'), ast.get('rightExpression')
            le, re = self.effects(left), self.effects(right)
            unordered = bool(le and (re or self.observes_state(right)) or re and self.observes_state(left))
            uncertain_short_circuit = ast.get('operator') in {'&&', '||'} and (
                self.conditional_calls(left) or self.conditional_calls(right))
            if unordered or uncertain_short_circuit:
                self.gap('含副作用或状态观察的二元/短路表达式求值顺序尚未证明')
                tails = [self.add('UNKNOWN', ast, tails, context, env)]
            tails, lv, env = self.expr(left, tails, env, stack, context)
            tails, rv, env = self.expr(right, tails, env, stack, context)
            if unordered or uncertain_short_circuit:
                env['epoch'] += 1
                env['stateValues'].clear()
            return tails, ('binary', ast.get('operator'), lv, rv), env
        if kind == 'UnaryOperation':
            operator = ast.get('operator')
            if operator in {'++', '--', 'delete'}:
                resource = self.resource(ast.get('subExpression'), env)
                self.gap('自增、自减或delete的状态更新语义尚未证明')
                if resource:
                    node = self.add('WRITE', ast, tails, context, env, resource=resource, value=_unknown(ast['id']))
                    self.record_write(resource, _unknown(ast['id']), env, node)
                    return [node], _unknown(ast['id']), env
            tails, value, env = self.expr(ast.get('subExpression'), tails, env, stack, context)
            return tails, ('unary', operator, value), env
        if kind in {'Identifier', 'MemberAccess', 'IndexAccess', 'Literal'}:
            if self.effects(ast):
                self.gap('资源寻址表达式中的副作用尚未支持')
            return tails, self.pure(ast, env), env
        if kind == 'TupleExpression' and len(ast.get('components', [])) == 1:
            return self.expr(ast['components'][0], tails, env, stack, context)
        self.gap(f'表达式 {kind} 尚未支持')
        return tails, _unknown(ast['id']), env

    def call(self, ast, tails, env, stack, context):
        expression, args = ast.get('expression', {}), ast.get('arguments', [])
        operation = call_operation(ast, self.bundle)
        if operation is not None and operation.get('native'):
            # 先统一位置身份；未知外部效果仍阻止完整保护证明。
            for argument in [operation['receiver']] + operation['options'] + list(args):
                tails, _, env = self.expr(argument, tails, env, stack, context)
            self.gap('原生调用结构已绑定，外部效果与正常提交尚未证明')
            node = self.add('CALL', ast, tails, context, env, callKind=operation['callKind'],
                semanticTags=operation['semanticTags'], targetDeclarationId=None,
                targetResource=self.resource(operation['receiver'], env), arguments=())
            env['epoch'] += 1
            env['stateValues'].clear()
            return [node], _unknown(ast['id']), env
        receiver = expression.get('expression', {}) if expression.get('nodeType') == 'MemberAccess' else expression
        if self.effects(receiver):
            self.gap('调用 receiver 含副作用或未知调用，求值顺序和状态效果尚未证明')
            tails = [self.add('UNKNOWN', expression, tails, context, env)]
            env['epoch'] += 1
            env['stateValues'].clear()
        if expression.get('nodeType') == 'FunctionCallOptions':
            self.gap('调用选项与低级调用尚未支持')
            expression = expression.get('expression', {})
        if sum(bool(self.effects(arg)) for arg in args) > 1:
            self.gap('多个带副作用实参的求值顺序尚未证明')
        values = []
        for arg in args:
            tails, value, env = self.expr(arg, tails, env, stack, context)
            values.append(value)
        reference = expression.get('referencedDeclaration')
        builtin = self.bundle['builtinReferences'].get(reference)
        if builtin in {'require', 'assert'}:
            condition = values[0] if values else _unknown(ast['id'])
            check = self.add('CHECK', ast, tails, context, env, condition=condition, builtin=builtin)
            abort = self.add('ABORT', None, [], context, env)
            self.edges.append({'from': check, 'to': abort, 'kind': 'abort'})
            return [check], ('void',), env
        if builtin == 'revert':
            abort = self.add('ABORT', ast, tails, context, env)
            return [], ('void',), env
        if ast.get('kind') == 'typeConversion':
            return tails, ('cast', expression.get('typeDescriptions', {}).get('typeIdentifier'), tuple(values)), env
        if builtin in {'sha256', 'keccak256', 'ripemd160', 'ecrecover', 'addmod', 'mulmod'}:
            return tails, ('pure-call', builtin, tuple(values)), env
        type_id = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
        if type_id.startswith('t_function_internal') and reference in self.bundle['functions']:
            if ast.get('names'):
                self.gap('内部调用命名实参尚未按声明名称代入，不能按位置证明权限')
            target = self.bundle['functions'][reference]
            # 普通虚调用按目标合约有效 override，super 和 private 保留显式声明。
            base = expression.get('expression', {})
            is_super = self.bundle['builtinReferences'].get(base.get('referencedDeclaration')) == 'super'
            qualified = expression.get('nodeType') == 'MemberAccess' and self.bundle['declarations'].get(
                base.get('referencedDeclaration'), {}).get('nodeType') == 'ContractDefinition'
            target_lineage = self.bundle['contracts'][self.bundle['targetContractId']]['linearizedBaseContracts']
            if not is_super and not qualified and target['visibility'] != 'private' and target['contractId'] in target_lineage:
                effective = [fid for fid in self.bundle['contracts'][self.bundle['targetContractId']]['effectiveFunctions']
                             if self.bundle['functions'][fid]['signature'] == target['signature']]
                if len(effective) != 1:
                    self.gap('虚内部调用无法唯一解析 override')
                else:
                    reference = effective[0]
                    target = self.bundle['functions'][reference]
            if expression.get('nodeType') == 'MemberAccess' and 'bound_to' in type_id:
                receiver = self.resource(base, env)
                if receiver is None:
                    self.gap('内部库 receiver 不能唯一绑定资源')
                    receiver = _unknown(expression['id'])
                values = [receiver] + values
            return self.function(reference, values, tails, env, stack, context + (ast['id'],))
        if type_id.startswith('t_function_external'):
            mutability = self.bundle['functions'].get(reference, {}).get('stateMutability')
            static = mutability in {'view', 'pure'} or '_view' in type_id or '_pure' in type_id
            target_resource = self.resource(expression.get('expression'), env)
            node = self.add('CALL', ast, tails, context, env, callKind='STATICCALL' if static else 'CALL',
                            targetDeclarationId=reference, targetResource=target_resource, arguments=tuple(values))
            if not static:
                env['epoch'] += 1
                env['stateValues'].clear()
            return [node], _unknown(ast['id']), env
        # abi.encodePacked 等编译器纯 builtin 可以留表达式；未知调用不能冒充纯函数。
        if type_id.startswith(('t_function_abiencode', 't_function_bytesconcat', 't_function_stringconcat')):
            return tails, ('pure-call', type_id, tuple(values)), env
        self.gap('动态、低级或未解析调用尚未证明')
        node = self.add('CALL', ast, tails, context, env, callKind='UNKNOWN', targetDeclarationId=reference,
                        targetResource=None, arguments=tuple(values))
        env['epoch'] += 1
        env['stateValues'].clear()
        return [node], _unknown(ast['id']), env

    def merge(self, environments):
        if not environments:
            return {'values': {}, 'versions': {}, 'stateValues': {}, 'epoch': 0}
        result = copy.deepcopy(environments[0])
        for key in {'values', 'versions', 'stateValues'}:
            all_keys = set().union(*(env[key] for env in environments))
            result[key] = {identity: environments[0][key][identity] for identity in all_keys
                           if identity in environments[0][key] and all(
                               env[key].get(identity) == environments[0][key][identity] for env in environments)}
            if key == 'values':
                for identity in all_keys - result[key].keys():
                    result[key][identity] = ('unknown', 'branch', identity)
            if key == 'versions':
                for identity in all_keys - result[key].keys():
                    result[key][identity] = ('unknown', 'branch')
        epochs = {env['epoch'] for env in environments}
        result['epoch'] = next(iter(epochs)) if len(epochs) == 1 else max(epochs) + 1
        return result

    def statement(self, ast, tails, env, stack, context, continuation=None):
        if not isinstance(ast, dict) or not tails or self.exhausted:
            return tails, env
        kind = ast['nodeType']
        if kind in {'Block', 'UncheckedBlock'}:
            if kind == 'UncheckedBlock':
                self.gap('UncheckedBlock 算术与存储更新语义尚未证明')
            for statement in ast.get('statements', []):
                tails, env = self.statement(statement, tails, env, stack, context, continuation)
            return tails, env
        if kind == 'ExpressionStatement':
            tails, value, env = self.expr(ast.get('expression'), tails, env, stack, context)
            if ast.get('expression', {}).get('nodeType') == 'BinaryOperation':
                node = self.add('EXPRESSION', ast, tails, context, env, value=value)
                tails = [node]
            return tails, env
        if kind == 'VariableDeclarationStatement':
            declarations = ast.get('declarations', [])
            tails, value, env = self.expr(ast.get('initialValue'), tails, env, stack, context)
            values = (list(value[1:]) if isinstance(value, tuple) and value[:1] == ('tuple',)
                      else [value])
            if len(declarations) != len(values) or not declarations:
                self.gap('多变量声明或解构赋值尚未支持')
                # 未识别的返回形状不能让后续引用继承已有局部值。
                values = [_unknown(ast['id'])] * len(declarations)
            for declaration, item in zip(declarations, values):
                if declaration is None:
                    continue
                if declaration.get('storageLocation') == 'storage':
                    self.gap('局部 storage 引用别名尚未支持')
                    item = _unknown(declaration['id'])
                    tails = [self.add('UNKNOWN', ast, tails, context, env)]
                env['values'][declaration['id']] = item
            return tails, env
        if kind == 'IfStatement':
            tails, condition, env = self.expr(ast.get('condition'), tails, env, stack, context)
            branch = self.add('BRANCH', ast, tails, context, env, condition=condition)
            paths, environments = [], []
            for edge_kind, body in [('true', ast.get('trueBody')), ('false', ast.get('falseBody'))]:
                edge = self.add('BRANCH_ARM', None, [], context, env)
                self.edges.append({'from': branch, 'to': edge, 'kind': edge_kind})
                bt, be = self.statement(body, [edge], copy.deepcopy(env), stack, context, continuation)
                paths.extend(bt)
                if bt:
                    environments.append(be)
            return paths, self.merge(environments)
        if kind == 'Return':
            tails, value, env = self.expr(ast.get('expression'), tails, env, stack, context)
            node = self.add('RETURN', ast, tails, context, env, value=value)
            self.return_frames[-1].append(([node], value, copy.deepcopy(env)))
            return [], env
        if kind in {'RevertStatement', 'Throw'}:
            self.add('ABORT', ast, tails, context, env)
            return [], env
        if kind == 'EmitStatement':
            # 日志参数仍可能有副作用；不执行事件名为普通函数调用。
            for argument in ast.get('eventCall', {}).get('arguments', []):
                tails, _, env = self.expr(argument, tails, env, stack, context)
            return tails, env
        if kind == 'PlaceholderStatement' and continuation:
            return continuation(tails, env)
        self.gap(f'语句 {kind} 尚未支持')
        node = self.add('UNKNOWN', ast, tails, context, env)
        env['epoch'] += 1
        env['stateValues'].clear()
        return [node], env

    def function(self, identity, arguments, tails, env, stack, context):
        if identity in stack or len(stack) >= _MAX_DEPTH:
            self.gap('递归或内部调用深度超限')
            node = self.add('UNKNOWN', self.bundle['functions'][identity]['node'], tails, context, env)
            env['epoch'] += 1
            env['stateValues'].clear()
            return [node], _unknown(identity), env
        function = self.bundle['functions'][identity]
        self.closure.add(identity)
        if not function['body'] or len(arguments) != len(function['parameters']):
            self.gap('内部函数体或实参绑定不完整')
            node = self.add('UNKNOWN', function['node'], tails, context, env)
            env['epoch'] += 1
            env['stateValues'].clear()
            return [node], _unknown(identity), env
        caller_values = env['values'].copy()
        env = copy.deepcopy(env)
        for parameter, argument in zip(function['parameters'], arguments):
            env['values'][parameter['id']] = argument
        stack = stack + (identity,)
        context = context + (identity,)
        self.return_frames.append([])

        def body(bt, be):
            return self.statement(function['body'], bt, be, stack, context)

        continuation = body
        for invocation in reversed(function['modifiers']):
            modifier_id = invocation.get('modifierName', {}).get('referencedDeclaration')
            modifier = self.bundle['functions'].get(modifier_id)
            if not modifier or modifier['node']['nodeType'] != 'ModifierDefinition':
                self.gap('修饰器声明无法解析')
                continue
            if modifier_id not in self.bundle['contracts'][self.bundle['targetContractId']]['effectiveModifiers']:
                self.gap('修饰器覆盖后的实际实现尚未解析，不能沿用父合约保护')
            self.closure.add(modifier_id)
            placeholders = [n for n in _walk(modifier['body']) if n['nodeType'] == 'PlaceholderStatement']
            if len(placeholders) != 1:
                self.gap('修饰器必须只有一个占位符')
            if any(n['nodeType'] == 'Return' for n in _walk(function['body'])):
                self.gap('带修饰器的函数 return 续接尚未证明')
            inner = continuation

            def wrapped(bt, be, invocation=invocation, modifier=modifier, inner=inner):
                actuals = []
                # 旧 compact AST 将无括号修饰器的实参表示为 null。
                for argument in invocation.get('arguments') or []:
                    bt, value, be = self.expr(argument, bt, be, stack, context)
                    actuals.append(value)
                if len(actuals) != len(modifier['parameters']):
                    self.gap('修饰器形参与实参无法一一绑定')
                for parameter, actual in zip(modifier['parameters'], actuals):
                    be['values'][parameter['id']] = actual
                return self.statement(modifier['body'], bt, be, stack, context + (modifier['id'],), inner)
            continuation = wrapped
        tails, env = continuation(tails, env)
        returns = self.return_frames.pop()
        if tails:
            parameters = function['returnParameters']
            if not parameters:
                fallthrough = ('void',)
            elif len(parameters) == 1 and parameters[0].get('name'):
                fallthrough = env['values'].get(parameters[0]['id'], _unknown(parameters[0]['id']))
            else:
                fallthrough = _unknown(identity)
                self.gap('隐式或多返回值语义尚未证明')
            returns.append((tails, fallthrough, env))
        all_tails = [tail for rt, _, _ in returns for tail in rt]
        values = [value for _, value, _ in returns]
        result_value = values[0] if values and all(v == values[0] for v in values) else _unknown(identity)
        result_env = self.merge([re for _, _, re in returns]) if returns else env
        result_env['values'] = caller_values
        return all_tails, result_value, result_env

    def reachable(self, start, end, avoid=None):
        pending, seen = [start], set()
        while pending:
            current = pending.pop()
            if current == end:
                return True
            if current in seen or current == avoid:
                continue
            seen.add(current)
            pending.extend(e['to'] for e in self.edges if e['from'] == current)
        return False

    def dominates(self, guard, risk):
        return guard == risk or self.reachable(self.start, risk) and not self.reachable(self.start, risk, avoid=guard)

    def guards(self, risk):
        result = []
        for node in self.nodes:
            if node['id'] == risk['id'] or not self.dominates(node['id'], risk['id']):
                continue
            if node['kind'] == 'CHECK':
                result.append((node, node['condition']))
            if node['kind'] == 'BRANCH':
                arms = {e['kind']: self.reachable(e['to'], risk['id']) for e in self.edges if e['from'] == node['id']}
                if arms.get('true') and not arms.get('false'):
                    result.append((node, node['condition']))
                elif arms.get('false') and not arms.get('true'):
                    result.append((node, _negate(node['condition'])))
        return result

    def intervening(self, guard, risk, resource):
        return [node for node in self.nodes if node['id'] not in {guard['id'], risk['id']}
                and self.reachable(guard['id'], node['id']) and self.reachable(node['id'], risk['id'])
                and (node['kind'] == 'CALL' and node.get('callKind') != 'STATICCALL'
                     or node['kind'] == 'UNKNOWN'
                     or node['kind'] == 'WRITE' and node.get('resource', (None, None))[1] == resource[1])]

    def public(self):
        def safe(value):
            if isinstance(value, dict):
                return {str(key): safe(child) for key, child in value.items()}
            if isinstance(value, (tuple, list)):
                return [safe(child) for child in value]
            return value
        return {'nodes': [safe({k: v for k, v in node.items() if k != 'stateBefore'}) for node in self.nodes],
                'edges': self.edges, 'gaps': self.gaps}


def _reference(node, bundle):
    if 'span' not in node:
        return None
    return {'nodeId': node['nodeId'], 'line': node['line'], 'span': node['span'],
            'sourceHash': bundle['sourceHash'], 'environmentHash': bundle['environmentHash'],
            'sourceUnitHash': bundle['units'][node['span']['sourceUnitId']]['sha256'], 'context': node['context']}


def _set(result, name, status, nodes, bundle, reason):
    item = next(o for o in result['obligations'] if o['name'] == name)
    refs = [_reference(n, bundle) for n in nodes]
    item.update(status=status, references=[r for r in refs if r], reason=reason)


def _path(status, nodes, bundle, reason):
    refs = [_reference(n, bundle) for n in nodes]
    return {'status': status, 'references': [r for r in refs if r], 'reason': reason,
            'kind': 'STATIC_CONTROL_FLOW', 'transactionFeasibility': 'UNVERIFIED'}


def _tool_binding(tools, bundle, root):
    """编译与工具分别实际执行并重放；不把环境摘要相等当作第二收据。"""
    from bound_slither import verify_bound_tool
    indexes = [index for index, tool in enumerate(tools) if tool.get('engine') == 'SLITHER'
                and tool.get('targetContract', bundle['targetContract']) == bundle['targetContract']
                and tool.get('sourceFile', bundle['targetSourceUnit']) == bundle['targetSourceUnit']
                and (tool.get('compilationReceipt') is None or
                     tool.get('sourceHash') == bundle['sourceHash'])]
    bindings = [verify_bound_tool(tools[index], bundle, root=root) for index in indexes]
    if bindings and all(binding['status'] == 'MATCH' for binding in bindings):
        return {'status': 'MATCH', 'reason': '实际编译第一收据与独立 Slither 第二收据重放匹配',
                'receipts': bindings, 'matchedToolIndexes': indexes, 'paidModelRequests': 0}
    if not tools:
        reason = '没有原工具运行收据；静态路径仍保留'
    elif any(tool.get('sourceHash') != bundle['sourceHash'] for tool in tools):
        reason = '原工具源码摘要没有绑定同一原件'
    elif any(tool.get('status') != 'OK' for tool in tools):
        reason = '原工具失败、超时或未执行'
    else:
        reason = '工具 configHash/executionConfigHash 与编译 environmentHash 含义不同；尚未核验固定编译器、依赖与设置的双收据桥'
    return {'status': 'UNKNOWN', 'errorCategory': 'TOOL_ENVIRONMENT_BINDING', 'reason': reason,
            'receipts': bindings,
            'requirements': ['同源码', '固定编译器版本与二进制', '完整依赖闭包', '有效编译设置', '原工具运行收据']}


def _corroboration(hypothesis, tools, bundle, risk_span, root, matched_tool_indexes, required_check=None):
    """同检测类别、真实函数和源码跨度佐证；相同文件名不构成绑定。"""
    from d2_verify import ISSUE_TYPES
    from pathlib import Path
    references = []
    function_name = hypothesis.get('functionSignature', hypothesis.get('function', '')).split('(', 1)[0]
    for tool_index in matched_tool_indexes:
        tool = tools[tool_index]
        if tool.get('engine') != 'SLITHER' or tool.get('status') != 'OK' or tool.get('sourceHash') != bundle['sourceHash']:
            continue
        for index, issue in enumerate(tool.get('issues', [])):
            if required_check is not None and issue.get('check') != required_check:
                continue
            if ISSUE_TYPES.get(issue.get('check')) != (hypothesis['vulnerabilityType'], hypothesis['riskOperation']):
                continue
            elements = issue.get('elements', [])
            for element in elements:
                if element.get('type') != 'function' or element.get('name') != function_name:
                    continue
                parent = element.get('type_specific_fields', {}).get('parent', {})
                mapping = element.get('source_mapping', {})
                if parent.get('name') != hypothesis['contract'] or risk_span['line'] not in mapping.get('lines', []):
                    continue
                unit = next((unit for unit in bundle['units'].values()
                             if unit['sourceUnit'] == risk_span['sourceUnit']), None)
                paths = [mapping.get(key) for key in ('filename_absolute', 'filename_relative') if mapping.get(key)]
                cwd = Path(root).resolve()
                # 实际映射须解析到已绑定源码原件，禁止 basename 匹配。
                if unit is None or not paths or not all((Path(path) if Path(path).is_absolute() else cwd / path).resolve()
                        == Path(unit['path']).resolve() for path in paths):
                    continue
                start, length = mapping.get('start'), mapping.get('length')
                if type(start) is not int or type(length) is not int or not (
                        start <= risk_span['start'] and risk_span['start'] + risk_span['length'] <= start + length):
                    continue
                references.append({'engine': 'SLITHER', 'toolIndex': tool_index, 'issueIndex': index, 'check': issue['check'],
                    'line': hypothesis['riskLine'], 'sourceHash': bundle['sourceHash'], 'sourceFile': unit['sourceUnit'],
                    'span': {'start': start, 'length': length}, 'scope': hypothesis['contract'] + '.' + function_name})
    return references


def _execution_proof(proof, hypothesis, bundle, graph, risk, tool_binding, root):
    """仅为已绑定候选补正常业务见证；失败不改变静态证明的未知结论。"""
    if (proof.get('status') != 'UNKNOWN' or not proof.get('candidateBound')
            or tool_binding.get('status') != 'MATCH'):
        return proof
    scope = proof.get('proofScope', {})
    authority = (hypothesis['vulnerabilityType'] == 'ACCESS_CONTROL'
                 and proof.get('proofKind') == 'ACCESS_CONTROL_AUTHORITY_WRITE_CANDIDATE')
    resource = scope.get('authorityResource') if authority else (
        scope.get('balanceResource') if hypothesis['vulnerabilityType'] == 'REENTRANCY' else None)
    if resource is None or scope.get('riskSpan') != risk['span']:
        return proof
    from evm_witness import execute_bound_witness
    execution = execute_bound_witness(bundle, hypothesis, graph, risk, resource, tool_binding, root=root)
    proof['executionBinding'] = execution
    witness = execution.get('witness', {})
    initialization = witness.get('initialization', {})
    expected_kind = 'ACCESS_CONTROL_AUTHORITY_WRITE' if authority else 'CEI_COUNTEREXAMPLE'
    expected_assertion = 'PERSISTENT_UNAUTHORIZED_AUTHORITY_WRITE' if authority else 'NORMAL_RETURN_CEI_ORDER'
    receipts = execution.get('receipts', [])
    if (execution.get('status') != 'MATCH' or execution.get('provider') != 'bound-evm-1'
            or len(receipts) != 2 or receipts[0].get('path') == receipts[1].get('path')
            or any(not item.get('path') or len(item.get('sha256', '')) != 64 for item in receipts)
            or witness.get('kind') != expected_kind or witness.get('normalExit') is not True
            or witness.get('location', {}).get('resource') != resource
            or witness.get('assertion', {}).get('valid') is not True
            or witness.get('assertion', {}).get('assertion') != expected_assertion
            or initialization.get('runtimeInitialized' if authority else 'funded') is not True
            or authority and (not witness.get('effectReferences') or not witness.get('authorityConsumers')
                or witness.get('consumerExecution', {}).get('valid') is not True
                or witness.get('consumerExecution', {}).get('normalExit') is not True)):
        scope.setdefault('gaps', []).append('本机执行见证未通过独立正常提交、初态与资源绑定：'
                                           + execution.get('reason', '收据或断言不完整'))
        return proof
    references = [{'engine': 'LOCAL_EVM', 'provider': execution['provider'], **item} for item in receipts]
    references.extend(witness.get('effectReferences', []))
    proof.update(status='COUNTEREXAMPLE', proofKind=expected_kind)
    scope.update(counterexampleComplete=True, conditionedOnInitialState=False,
                 conditionedOnExternalCalls=False, executionScope='BOUND_NORMAL_BUSINESS_TRACE')
    # 静态全入口缺口仍保留；存在性见证不声称完整保护或整合约安全。
    proof['references'].extend(references)
    proof['pathEvidence'] = {'status': 'FEASIBLE', 'normalExit': True, 'witness': witness,
        'references': references, 'transactionFeasibility': 'INDEPENDENT_EVM_REPLAY',
        'reason': '原字节码正常业务在两个独立本机节点提交相同的有限属性反例'}
    for obligation in proof['obligations']:
        if not authority and obligation['name'] == 'pre_risk_guard':
            from reentrancy_proofs import _prebalance
            obligation.update(status='SUPPORTED' if _prebalance(graph, risk) else 'UNKNOWN',
                references=references, reason='余额检查单独按编译控制关系判断，CEI反例不否定所有前置检查')
            continue
        obligation.update(status='SUPPORTED' if obligation['name'] in {'actor', 'resource'} else 'REFUTED',
            references=references, reason='同主体及资源已绑定；正常提交见证否定该候选的完整保护')
    return proof


def _apply_proof(result, proof, hypothesis, tools, bundle, root):
    result['candidateProof'] = proof
    if (proof.get('status') not in {'PROVED', 'COUNTEREXAMPLE'}
            and not (proof.get('candidateBound') and proof.get('pathEvidence', {}).get('status') == 'CONDITIONAL')):
        return
    result['status'] = 'PARTIAL'
    result.pop('errorCategory', None)
    result['proofScope'] = copy.deepcopy(proof['proofScope'])
    result['proofScope']['candidate'] = copy.deepcopy(hypothesis)
    result['pathEvidence'] = copy.deepcopy(proof['pathEvidence'])
    result['obligations'] = copy.deepcopy(proof['obligations'])
    result['references'] = copy.deepcopy(proof.get('references', []))
    if 'cfg' in proof:
        result['cfg'] = copy.deepcopy(proof['cfg'])
    if proof.get('status') not in {'PROVED', 'COUNTEREXAMPLE'}:
        return
    if result['toolBinding']['status'] != 'MATCH':
        return
    if proof.get('proofKind') == 'ACCESS_CONTROL_GUARDED_CALL':
        declared = hypothesis.get('claimProperty')
        matched = declared == 'UNAUTHORIZED_CALL_REACHABILITY'
        result['claimBinding'] = {'status': 'MATCH' if matched else 'UNVERIFIED',
            'declaredProperty': declared, 'provedProperty': proof['proofScope'].get('property'),
            'reason': '候选须明确主张未授权调用可达；调用前保护不能反驳资金锁死等其他属性'}
        if not matched:
            return
    if (proof['status'] == 'PROVED' and proof['proofScope']['complete']
            and proof['pathEvidence']['status'] == 'BLOCKED'
            and len(proof['obligations']) == len(OBLIGATIONS)
            and {item['name'] for item in proof['obligations']} == set(OBLIGATIONS)
            and all(item['status'] == 'SUPPORTED' for item in proof['obligations'])):
        result.update(verdict='REFUTED', protectionVerdict='SUPPORTED', status='COMPLETED')
    elif (proof['status'] == 'COUNTEREXAMPLE' and proof['pathEvidence']['status'] == 'FEASIBLE'
          and proof['pathEvidence'].get('normalExit') is True
          and (hypothesis['vulnerabilityType'] == 'REENTRANCY'
               and proof['pathEvidence'].get('witness', {}).get('initialization', {}).get('funded') is True
               or hypothesis['vulnerabilityType'] == 'ACCESS_CONTROL'
               and proof.get('proofKind') in {'ACCESS_CONTROL_TERMINATION', 'ACCESS_CONTROL_AUTHORITY_WRITE'}
               and proof['pathEvidence'].get('witness', {}).get('initialization', {}).get('runtimeInitialized') is True)):
        if (proof.get('proofKind') == 'ACCESS_CONTROL_AUTHORITY_WRITE'
                and proof.get('executionBinding', {}).get('status') == 'MATCH'
                and proof['pathEvidence'].get('transactionFeasibility') == 'INDEPENDENT_EVM_REPLAY'
                and proof['pathEvidence']['witness'].get('effectReferences')):
            result['corroboration'] = copy.deepcopy(proof['pathEvidence']['witness']['effectReferences'])
            result.update(verdict='SUPPORTED', protectionVerdict='REFUTED', status='COMPLETED')
            return
        risk_span = proof['proofScope'].get('riskSpan')
        if isinstance(risk_span, dict):
            corroboration = _corroboration(hypothesis, tools, bundle, risk_span, root,
                result['toolBinding'].get('matchedToolIndexes', []),
                required_check='suicidal' if proof.get('proofKind') == 'ACCESS_CONTROL_TERMINATION' else None)
            result['corroboration'] = corroboration
            if corroboration:
                result.update(verdict='SUPPORTED', protectionVerdict='REFUTED', status='COMPLETED')
                result['references'].extend(corroboration)


def _risk_matches(node, hypothesis, bundle, facts):
    # 兼容旧调用接缝；整图唯一性由 bind_risks 核验。
    return (operation_matches(node, hypothesis, bundle, facts)
            and node['span']['line'] <= hypothesis['riskLine'] <= node['span'].get('endLine', node['line']))


def _evaluate_compiled(hypothesis, manifest, tools, *, root):
    """重新核验原编译产物，计算局部路径与六义务；不接受人工证明或攻击回执。"""
    result = {'schemaVersion': '2', 'provider': 'solc-standard-json', 'status': 'PARTIAL',
              'verdict': 'UNKNOWN', 'protectionVerdict': 'UNKNOWN', 'references': [],
              'obligations': [{'name': name, 'status': 'UNKNOWN', 'references': [], 'reason': '尚无完整编译路径证据'}
                              for name in OBLIGATIONS],
              'pathEvidence': {'status': 'UNKNOWN', 'references': [], 'reason': '尚无完整候选路径证明'},
              'localPathEvidence': {'status': 'UNKNOWN', 'references': [], 'reason': '尚无唯一绑定的局部路径'},
              'proofScope': {'complete': False, 'entries': [], 'gaps': [], 'callClosure': []},
              'cfg': {'nodes': [], 'edges': [], 'gaps': []},
              'note': '静态可达不证明交易可行或最终提交；工具告警不能代替反例'}
    try:
        bundle = load_bound_compilation(manifest, root)
    except CompilationBindingError as error:
        result.update(status='FAILED', errorCategory='COMPILATION_BINDING_FAILED', note='编译绑定失败：' + str(error))
        result['proofScope']['gaps'].append(str(error))
        return result
    result['binding'] = {key: bundle.get(key) for key in
                         ('manifestDigest', 'receiptDigest', 'environmentHash', 'sourceHash', 'verificationStatus')}
    if (not isinstance(hypothesis, dict) or not isinstance(tools, list)
            or type(hypothesis.get('riskLine')) is not int or hypothesis['riskLine'] < 1
            or hypothesis.get('riskOperation') not in {'WRITE', 'CALL'}):
        result.update(status='FAILED', errorCategory='INVALID_HYPOTHESIS', note='假设或工具输入结构无效')
        return result
    mechanism = hypothesis.get('vulnerabilityType', hypothesis.get('mechanism'))
    if (mechanism not in {'ACCESS_CONTROL', 'REENTRANCY'}
            or hypothesis.get('mechanism', mechanism) != mechanism
            or mechanism == 'REENTRANCY' and hypothesis['riskOperation'] != 'CALL'
            or hypothesis.get('contract') != bundle['targetContract']
            or hypothesis.get('sourceHash', bundle['sourceHash']) != bundle['sourceHash']
            or hypothesis.get('sourceFile', bundle['targetSourceUnit']) != bundle['targetSourceUnit']):
        category = ('SOURCE_HASH_MISMATCH' if hypothesis.get('sourceHash', bundle['sourceHash']) != bundle['sourceHash']
                    else 'HYPOTHESIS_BINDING_MISMATCH')
        result.update(status='FAILED', errorCategory=category, note='机制、合约或源码身份没有绑定目标')
        return result
    if (not isinstance(hypothesis.get('functionSignature', hypothesis.get('function')), str)
            or hypothesis.get('riskKind', hypothesis['riskOperation']) != hypothesis['riskOperation']
            or 'riskFactId' in hypothesis and not isinstance(hypothesis['riskFactId'], str)
            or 'riskSpan' in hypothesis and (not isinstance(hypothesis['riskSpan'], dict)
                or not isinstance(hypothesis['riskSpan'].get('sourceUnit'), str)
                or type(hypothesis['riskSpan'].get('start')) is not int
                or type(hypothesis['riskSpan'].get('length')) is not int
                or hypothesis['riskSpan']['start'] < 0 or hypothesis['riskSpan']['length'] < 1)
            or any(not isinstance(tool, dict) for tool in tools)):
        result.update(status='FAILED', errorCategory='INVALID_HYPOTHESIS', note='签名、风险跨度或工具结构无效')
        return result
    if 'functionSignature' in hypothesis and 'function' in hypothesis:
        name, signature = hypothesis['function'], hypothesis['functionSignature']
        if not isinstance(name, str) or not isinstance(signature, str) or (name != signature if '(' in name else name != signature.split('(', 1)[0]):
            result.update(status='FAILED', errorCategory='HYPOTHESIS_BINDING_MISMATCH', note='函数名与完整签名不一致')
            return result
    result['toolBinding'] = _tool_binding(tools, bundle, root)
    graph_options = {}
    if mechanism == 'ACCESS_CONTROL':
        if hypothesis['riskOperation'] == 'CALL':
            from access_call_proofs import _AccessCallGraph, prove_access_call
            from candidate_proofs import _GuardedCallGraph, prove_guarded_call
            proof = prove_guarded_call(bundle, hypothesis)
            if proof.get('applicable'):
                graph_type = _GuardedCallGraph
            else:
                proof = prove_access_call(bundle, hypothesis)
                graph_type = _AccessCallGraph
        else:
            from candidate_proofs import _PermissionGraph, prove_candidate
            proof = prove_candidate(bundle, hypothesis)
            graph_type = _PermissionGraph
    else:
        from reentrancy_proofs import _ReentrancyGraph, prove_reentrancy
        effects = [summary for receipt in result['toolBinding'].get('receipts', [])
                   for summary in receipt.get('effectSummaries', [])] if result['toolBinding']['status'] == 'MATCH' else []
        graph_options = {'effect_summaries': effects or None}
        proof = prove_reentrancy(bundle, hypothesis, **graph_options)
        graph_type = _ReentrancyGraph
    function_name = hypothesis.get('functionSignature', hypothesis.get('function'))
    candidates = [e for e in bundle['entries'] if e['matched'] and e['kind'] != 'getter' and
                  (e['signature'] == function_name or '(' not in str(function_name)
                   and e['signature'].split('(', 1)[0] == function_name)]
    if len(candidates) != 1:
        result['note'] = '运行期函数签名不唯一；重载必须显式绑定完整签名'
        return result
    # 展示、绑定与专用证明共享同一编译语义，避免低级 CALL 再次退化为 UNKNOWN。
    graph = graph_type(bundle, candidates[0], **graph_options)
    facts = extract_compiler_facts(bundle)
    risks = bind_risks(graph, hypothesis, bundle, facts)
    if len(risks) != 1:
        result['note'] = '风险操作、字节跨度与调用上下文无法唯一绑定'
        if hypothesis.get('riskFactId') or hypothesis.get('riskSpan'):
            result.update(status='FAILED', errorCategory='RISK_BINDING_MISMATCH')
        result['cfg'] = graph.public()
        result['proofScope']['gaps'] = graph.gaps + [result['note']]
        _apply_proof(result, proof, hypothesis, tools, bundle, root)
        if result['verdict'] != 'UNKNOWN':
            result['note'] = '结论仅针对绑定候选与有限静态防御属性，不代表整合约安全或可利用性'
        return result
    risk = risks[0]
    proof = _execution_proof(proof, hypothesis, bundle, graph, risk, result['toolBinding'], root)
    result['riskBinding'] = {**_reference(risk, bundle), **binding_record(risk, hypothesis)}
    result['cfg'] = graph.public()
    if proof.get('proofKind') in {'ACCESS_CONTROL_TERMINATION', 'ACCESS_CONTROL_GUARDED_CALL'}:
        # 调用使用各自专用证明；通用局部检查不能把未覆盖语义升级为完整保护。
        for name in ('proofScope', 'pathEvidence', 'obligations', 'references'):
            result[name] = copy.deepcopy(proof[name])
        result['proofScope']['candidate'] = copy.deepcopy(hypothesis)
        _apply_proof(result, proof, hypothesis, tools, bundle, root)
        result['note'] = ('已核验调用主体保护；范围仅为绑定操作的可达性，不代表整合约或外部效果安全'
                          if result['verdict'] == 'REFUTED' else
                          '已核验有限访问义务反例与终止调用工具证据；不代表攻击可利用性'
                          if result['verdict'] == 'SUPPORTED' else
                          '调用仅保留有限访问义务证据；证明不完整或缺双收据时保持未知')
        if result.get('claimBinding', {}).get('status') == 'UNVERIFIED':
            result['note'] = '已证明调用前保护子属性，但候选所主张属性未匹配，不能据此反驳候选'
        return result
    guards = graph.guards(risk)
    local_gaps = list(graph.gaps)
    authority = None
    if mechanism == 'ACCESS_CONTROL':
        auth_guards = [(g, _authority(c)) for g, c in guards if _authority(c)]
        authority = auth_guards[0][1] if auth_guards else None
        conditions = {g['id']: c for g, c in guards}
        stable = [(g, a) for g, a in auth_guards if _current_authority(g, conditions[g['id']])
                  and not graph.intervening(g, risk, a)]
        _set(result, 'actor', 'SUPPORTED' if auth_guards else 'REFUTED' if not local_gaps else 'UNKNOWN',
             [risk] + [g for g, _ in auth_guards], bundle, '真实主体来自 msg.sender；只认可地址权限等值条件')
        resource = risk.get('resource') or risk.get('targetResource')
        known = bool(resource) and not _contains(resource, 'unknown')
        _set(result, 'resource', 'SUPPORTED' if known else 'UNKNOWN', [risk], bundle,
             '风险资源使用状态声明、索引表达式和成员声明身份；未知 key 不放行')
        _set(result, 'pre_risk_guard', 'SUPPORTED' if auth_guards else 'REFUTED' if not local_gaps else 'UNKNOWN',
             [risk] + [g for g, _ in auth_guards], bundle, '仅实际支配风险正常路径的 CHECK 或退出分支提供保护')
        changes = [n for g, a in auth_guards for n in graph.intervening(g, risk, a)]
        for g, a in auth_guards:
            if not _current_authority(g, conditions[g['id']]):
                changes.extend(n for n in graph.nodes if n['kind'] in {'WRITE', 'CALL', 'UNKNOWN'}
                               and graph.reachable(n['id'], g['id']))
        _set(result, 'state_version', 'SUPPORTED' if stable else 'REFUTED' if any(n['kind'] == 'WRITE' for n in changes)
             else 'UNKNOWN', [risk] + changes, bundle, '检查与风险之间的同根写入或可回调 CALL 使旧权限状态失效')
        blocked = bool(stable) and known and not any('占位符' in gap or 'return 续接' in gap for gap in local_gaps)
        result['localPathEvidence'] = _path('BLOCKED' if blocked else 'UNKNOWN' if any(n['kind'] == 'UNKNOWN' and graph.reachable(n['id'], risk['id']) for n in graph.nodes) else 'REACHABLE',
                                            [risk] + [g for g, _ in stable], bundle,
                                            '未授权主体在风险前被失败退出边阻断' if blocked else
                                            '仅保留图上路径；未证明建态、约束可满足或最终交易提交')
    else:
        locks = [(g, _false_resource(c)) for g, c in guards if _false_resource(c)]
        lock = locks[0][1] if locks else None
        writes = [n for n in graph.nodes if n['kind'] == 'WRITE' and n.get('resource') == lock
                  and n.get('value') == ('literal', 'bool', 'true') and graph.dominates(n['id'], risk['id'])]
        locked = lock is not None and risk['stateBefore'].get(lock) == ('literal', 'bool', 'true')
        _set(result, 'resource', 'SUPPORTED' if lock and not _contains(lock, 'unknown') else 'UNKNOWN',
             [risk] + [g for g, _ in locks] + writes, bundle, '回调入口检查与锁定写入须绑定同声明、同 key、同字段')
        _set(result, 'pre_risk_guard', 'SUPPORTED' if locks else 'UNKNOWN',
             [risk] + [g for g, _ in locks], bundle, '已展开内部 getter 的入口状态条件，不能凭函数名推断锁')
        _set(result, 'state_version', 'SUPPORTED' if locked else 'UNKNOWN', [risk] + writes, bundle,
             '仅此风险 CALL 前的同 key 状态版本；更早 CALL 的窗口另行保留')
        result['localPathEvidence'] = _path('BLOCKED' if locked and not any(n['kind'] == 'UNKNOWN' and graph.reachable(n['id'], risk['id']) for n in graph.nodes) else 'UNKNOWN' if any(n['kind'] == 'UNKNOWN' and graph.reachable(n['id'], risk['id']) for n in graph.nodes) else 'REACHABLE',
                                            [risk] + writes + [g for g, _ in locks], bundle,
                                            '该 CALL 发起的同入口同 key 回调遇到已置位状态；不覆盖其他 CALL或入口' if locked else
                                            '风险前未证明锁定；静态控制流不构成可行反例')
    result['localPathEvidence']['conditional'] = bool(local_gaps)
    result['localPathEvidence']['scope'] = {'entry': candidates[0]['signature'], 'riskSpan': risk['span'],
        'meaning': '只对绑定风险操作的编译控制关系作局部命题，不声称完整交易或全部入口安全',
        'remainingSemanticGaps': local_gaps}
    result['localPathEvidence']['premises'] = (['实际调用者不等于绑定的地址权限状态'] if mechanism == 'ACCESS_CONTROL' else
        ['回调使用相同运行入口和参数 key', '未覆盖别名、动态实现和其他入口的效果不在此局部命题内'])
    windows = []
    if mechanism == 'REENTRANCY' and lock:
        windows = [_reference(n, bundle) for n in graph.nodes if n['kind'] == 'CALL' and n.get('callKind') != 'STATICCALL'
                   and n.get('stateBefore', {}).get(lock) != ('literal', 'bool', 'true')]
    # 全量运行入口保守展开；只排除已证明没有状态效果与外部调用的入口。
    entries, all_gaps, closure = [], list(bundle['entryGaps']) + local_gaps, set(graph.closure)
    entry_complete = mechanism == 'ACCESS_CONTROL' and authority is not None
    sensitive_roots = {r[1] for r in [risk.get('resource'), risk.get('targetResource'), authority] if r}
    for entry in bundle['entries']:
        item = {'signature': entry['signature'], 'kind': entry['kind'], 'declarationId': entry['declarationId'],
                'matched': entry['matched'], 'related': True, 'complete': False, 'reason': ''}
        if not entry['matched']:
            item['reason'] = '入口未唯一绑定编译声明'
            entry_complete = False
        elif entry['kind'] == 'getter':
            item.update(complete=True, related=False, reason='ABI 与声明对账的自动 getter 只有读取，无调用或写入')
        else:
            other = graph if entry['declarationId'] == candidates[0]['declarationId'] else graph_type(bundle, entry)
            closure.update(other.closure)
            all_gaps.extend(entry['signature'] + '：' + gap for gap in other.gaps)
            effects = [n for n in other.nodes if n['kind'] in {'WRITE', 'CALL'}]
            sensitive = [n for n in effects if n['kind'] == 'CALL'
                         or n.get('resource', (None, None))[1] in sensitive_roots]
            item['complete'] = not other.gaps
            if not effects and not other.gaps:
                item.update(related=False, reason='完整展开无状态写入和外部调用，无法改变绑定风险资源')
            elif not sensitive and not other.gaps:
                # 首轮只排除无效果入口；复杂状态依赖的传递相关性不从名称猜测。
                item.update(reason='其他状态效果暂未证明与候选无关，保守计入相关入口')
                entry_complete = False
            else:
                item['reason'] = '包含相关资源写入、外部调用或未覆盖语义'
            if other.gaps:
                entry_complete = False
            if mechanism == 'ACCESS_CONTROL':
                for operation in sensitive:
                    covered = [(g, a) for g, c in other.guards(operation) if (a := _authority(c)) is not None
                               and a == authority and _current_authority(g, c)]
                    if not any(not other.intervening(g, operation, a) for g, a in covered):
                        entry_complete = False
            else:
                entry_complete = False
        entries.append(item)
    all_gaps = sorted(set(all_gaps))
    if not entry_complete:
        all_gaps.append('全量相关运行期入口的候选保护尚未取得穷尽证明')
    result['proofScope'] = {'complete': not all_gaps, 'candidate': copy.deepcopy(hypothesis),
                            'riskSpan': risk['span'], 'entries': entries, 'gaps': all_gaps,
                            'callClosure': sorted(closure), 'unlockedCallWindows': windows, 'rules': ['AST身份', '参数代入', 'CFG支配', '资源字段与key', '状态版本']}
    _set(result, 'entry_coverage', 'SUPPORTED' if entry_complete and not all_gaps else 'UNKNOWN', [risk], bundle,
         'ABI、继承与自动 getter 全量枚举；相关语义缺口不能从候选范围移除')
    if mechanism == 'ACCESS_CONTROL' and result['localPathEvidence']['status'] == 'BLOCKED' and not all_gaps:
        _set(result, 'bypass', 'SUPPORTED', [risk], bundle, '所有相关入口的风险与权限写入均由稳定的实际主体保护阻断')
        result['pathEvidence'] = copy.deepcopy(result['localPathEvidence'])
    _apply_proof(result, proof, hypothesis, tools, bundle, root)
    for item in result['obligations'] + [result['pathEvidence'], result['localPathEvidence']]:
        for reference in item['references']:
            if reference not in result['references']:
                result['references'].append(reference)
    result['note'] = ('结论仅针对绑定候选与完整编译证明范围' if result['verdict'] == 'REFUTED' else
                      '已核验有限静态反例与同类工具证据；不代表攻击可利用性' if result['verdict'] == 'SUPPORTED' else
                      '局部静态证据保留；路径可满足性、入口覆盖或工具绑定不足，最终未知')
    return result


def evaluate_compiled(hypothesis, manifest, tools, *, root):
    """最终裁决与独立引用复核分开；复核不改变现行证明门槛。"""
    result = _evaluate_compiled(hypothesis, manifest, tools, root=root)
    from evidence_review import review_evidence
    try:
        bundle = load_bound_compilation(manifest, root)
        result['evidenceReview'] = review_evidence(hypothesis, result, bundle)
    except (ValueError, OSError, KeyError, TypeError):
        result['evidenceReview'] = {'schemaVersion': 'evidence-review-1', 'status': 'UNRESOLVED',
            'checks': [], 'gateApplied': False, 'newModelRequests': 0,
            'reason': '原件或编译身份不可重验，复核保持未决'}
    return result
