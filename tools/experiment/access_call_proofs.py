"""编译器确认的终止调用访问义务；仅给有限防御断言，不生成利用轨迹。"""
import copy
import itertools
import re

from candidate_proofs import _PermissionGraph
from compiler_facts import extract_compiler_facts, source_span
from risk_binding import bind_risks, binding_record
from compiled_d2 import _reference, _risk_matches


_OBLIGATIONS = ('actor', 'resource', 'pre_risk_guard', 'entry_coverage', 'state_version', 'bypass')
_CALLER = '运行调用主体 A'
_DEPLOYER = '部署主体 D'
_MAX_PATHS = 128
_MAX_ASSIGNMENTS = 1024


class _CannotEvaluate(ValueError):
    """未进入有限语义的值或不可满足的防御断言。"""


def _empty():
    return {'status': 'UNKNOWN', 'proofKind': 'ACCESS_CONTROL_TERMINATION', 'candidateBound': False,
        'references': [], 'obligations': [{'name': name, 'status': 'UNKNOWN', 'references': [],
            'reason': '尚无绑定运行初态的终止调用访问义务反例'} for name in _OBLIGATIONS],
        'pathEvidence': {'status': 'UNKNOWN', 'references': [], 'kind': 'FINITE_ACCESS_ASSERTION',
            'transactionFeasibility': 'UNVERIFIED'},
        'proofScope': {'complete': False, 'counterexampleComplete': False, 'universalProtection': False,
            'entries': [], 'gaps': [], 'callClosure': [],
            'claim': '仅证明限定运行初态下可满足的静态访问义务反例，不证明漏洞可利用性或链上代码删除'}}


def _terminal_builtin(ast, bundle):
    if not isinstance(ast, dict) or ast.get('nodeType') != 'FunctionCall' or ast.get('kind') != 'functionCall':
        return None
    expression = ast.get('expression', {})
    reference = expression.get('referencedDeclaration')
    builtin = bundle['builtinReferences'].get(reference)
    if (expression.get('nodeType') == 'Identifier' and reference not in bundle['declarations']
            and builtin in {'selfdestruct', 'suicide'}
            and expression.get('typeDescriptions', {}).get('typeIdentifier', '').startswith(f't_function_{builtin}_')):
        return builtin
    return None


class _AccessCallGraph(_PermissionGraph):
    """终止调用直接连接总退出，内部调用者与修饰器后缀不再执行。"""

    def __init__(self, bundle, entry):
        self.terminal_nodes = []
        super().__init__(bundle, entry)
        exits = [node for node in self.nodes if node['kind'] == 'EXIT']
        if len(exits) == 1:
            self.edges.extend({'from': node, 'to': exits[0]['id'], 'kind': 'normal'}
                              for node in self.terminal_nodes)
        else:
            self.gap('终止调用没有唯一总退出')

    def expr(self, ast, tails, env, stack, context):
        if not tails:
            return [], ('void',), env
        tails, value, env = super().expr(ast, tails, env, stack, context)
        if tails and isinstance(ast, dict) and value != ('void',):
            # 未使用的局部表达式也须求值；未知算术结果不能被忽略成正常执行。
            evaluation = self.add('EVAL', ast, tails, context, env, value=value,
                                  valueType=ast.get('typeDescriptions', {}).get('typeIdentifier', ''))
            tails = [evaluation]
        return tails, value, env

    def statement(self, ast, tails, env, stack, context, continuation=None):
        if isinstance(ast, dict) and ast.get('nodeType') == 'Return' and tails:
            tails, value, env = self.expr(ast.get('expression'), tails, env, stack, context)
            if tails:
                node = self.add('RETURN', ast, tails, context, env, value=value)
                self.return_frames[-1].append(([node], value, copy.deepcopy(env)))
            # 返回表达式中的内部终止已经结束当前执行，不能产生断开的 RETURN 续接。
            return [], env
        return super().statement(ast, tails, env, stack, context, continuation)

    def call(self, ast, tails, env, stack, context):
        builtin = _terminal_builtin(ast, self.bundle)
        if builtin is not None:
            arguments = ast.get('arguments', [])
            if len(arguments) != 1:
                self.gap('终止调用地址实参没有唯一绑定')
                return super().call(ast, tails, env, stack, context)
            tails, value, env = self.expr(arguments[0], tails, env, stack, context)
            if not tails:
                return [], ('void',), env
            node = self.add('CALL', ast, tails, context, env, callKind='CALL', builtin=builtin,
                terminalBuiltin=True, targetDeclarationId=ast['expression']['referencedDeclaration'],
                targetValue=value, targetResource=self.resource(arguments[0], env), arguments=(value,))
            self.terminal_nodes.append(node)
            return [], ('void',), env
        expression = ast.get('expression', {})
        builtin = self.bundle['builtinReferences'].get(expression.get('referencedDeclaration'))
        if builtin in {'require', 'assert', 'revert'}:
            values = []
            for argument in ast.get('arguments', []):
                tails, value, env = self.expr(argument, tails, env, stack, context)
                values.append(value)
                if not tails:
                    return [], ('void',), env
            if builtin == 'revert':
                self.add('ABORT', ast, tails, context, env)
                return [], ('void',), env
            condition = values[0] if values else ('unknown', ast['id'])
            node = self.add('CHECK', ast, tails, context, env, condition=condition, builtin=builtin)
            abort = self.add('ABORT', None, [], context, env)
            self.edges.append({'from': node, 'to': abort, 'kind': 'abort'})
            return [node], ('void',), env
        if ast.get('kind') == 'typeConversion' and len(ast.get('arguments', [])) == 1:
            tails, value, env = self.expr(ast['arguments'][0], tails, env, stack, context)
            return tails, ('cast', ast.get('typeDescriptions', {}).get('typeIdentifier', ''), value), env
        return super().call(ast, tails, env, stack, context)


def _type_value(value, identifier):
    if identifier == 't_bool':
        valid = type(value) is bool
    elif identifier in {'t_address', 't_address_payable'}:
        valid = value in {_CALLER, _DEPLOYER} or type(value) is int and 0 <= value < 2 ** 160
    else:
        width = re.fullmatch(r't_uint(\d+)', identifier)
        valid = bool(width and type(value) is int and 0 <= value < 2 ** int(width.group(1)))
    if not valid:
        raise _CannotEvaluate('值与编译器声明类型不一致或类型超出范围')
    return value


def _root(resource):
    if not isinstance(resource, tuple) or len(resource) != 3 or resource[0] != 'resource' or resource[2]:
        raise _CannotEvaluate('只支持唯一声明绑定的标量状态槽')
    return resource[1]


def _value(term, parameters, initial, versions, caller):
    if not isinstance(term, tuple) or not term:
        raise _CannotEvaluate('表达式缺少有限 AST 语义')
    kind = term[0]
    if kind == 'literal':
        if term[1] == 'bool' and term[2] in {'true', 'false'}:
            return term[2] == 'true'
        if term[1] == 'number' and re.fullmatch(r'(?:\d+|0x[0-9a-fA-F]+)', str(term[2])):
            return int(term[2], 16 if str(term[2]).startswith('0x') else 10)
    if term == ('builtin', 'msg.sender'):
        return caller
    if kind == 'parameter' and term[1] in parameters:
        return parameters[term[1]]
    if kind == 'read':
        root, version = _root(term[1]), term[2][0]
        if version == 'initial' and root in initial:
            return initial[root]
        if type(version) is int and (root, version) in versions:
            return versions[(root, version)]
        raise _CannotEvaluate('状态读取未绑定默认、构造或路径写入版本')
    if kind == 'cast':
        value = _value(term[2], parameters, initial, versions, caller)
        return _type_value(value, term[1])
    if kind == 'unary' and term[1] == '!':
        value = _value(term[2], parameters, initial, versions, caller)
        if type(value) is bool:
            return not value
    if kind == 'binary':
        left = _value(term[2], parameters, initial, versions, caller)
        right = _value(term[3], parameters, initial, versions, caller)
        operator = term[1]
        if operator in {'==', '!='}:
            if type(left) is not type(right) and {left, right} - {_CALLER, _DEPLOYER, 0}:
                raise _CannotEvaluate('比较值的编译类型未证明兼容')
            return left == right if operator == '==' else left != right
        if operator in {'&&', '||'} and type(left) is bool and type(right) is bool:
            return left and right if operator == '&&' else left or right
        if operator in {'>', '>=', '<', '<='} and type(left) is int and type(right) is int:
            return {'>': left > right, '>=': left >= right, '<': left < right, '<=': left <= right}[operator]
    raise _CannotEvaluate('调用结果、算术或表达式语义尚未证明')


def _default(identifier):
    if identifier == 't_bool':
        return False
    if identifier in {'t_address', 't_address_payable'} or re.fullmatch(r't_uint\d+', identifier):
        return 0
    raise _CannotEvaluate('状态或形参类型尚未进入默认初态语义')


def _initial_term(ast, graph):
    if isinstance(ast, dict) and ast.get('nodeType') == 'FunctionCall' and ast.get('kind') == 'typeConversion':
        if len(ast.get('arguments', [])) != 1:
            raise _CannotEvaluate('初值类型转换实参不完整')
        return ('cast', ast.get('typeDescriptions', {}).get('typeIdentifier', ''),
                _initial_term(ast['arguments'][0], graph))
    if not isinstance(ast, dict) or graph.effects(ast):
        raise _CannotEvaluate('声明初值包含未验证副作用')
    return graph.pure(ast, {'values': {}, 'versions': {}, 'stateValues': {}, 'epoch': 0})


def _run_nodes(graph, nodes, edges, parameters, initial, caller, terminal=None):
    versions, conditions, selected = {}, [], {edge['from']: edge['kind'] for edge in edges}
    for node in nodes:
        kind = node['kind']
        if kind in {'ENTRY', 'EXIT', 'BRANCH_ARM'}:
            continue
        if kind in {'EVAL', 'EXPRESSION', 'RETURN'}:
            if kind == 'RETURN' and graph.bundle['nodes'][node['nodeId']].get('expression') is None:
                continue
            value = _value(node['value'], parameters, initial, versions, caller)
            identifier = node.get('valueType', '')
            if identifier in {'t_bool', 't_address', 't_address_payable'} or re.fullmatch(r't_uint\d+', identifier):
                _type_value(value, identifier)
        elif kind in {'CHECK', 'BRANCH'}:
            value = _value(node['condition'], parameters, initial, versions, caller)
            required = selected.get(node['id']) != 'false'
            if type(value) is not bool or value != required:
                raise _CannotEvaluate('防御断言或分支约束不可满足')
            conditions.append({'nodeId': node['nodeId'], 'conditionValue': value, 'requiredValue': required})
        elif kind == 'WRITE':
            root = _root(node['resource'])
            identifier = graph.bundle['declarations'][root].get('typeDescriptions', {}).get('typeIdentifier', '')
            value = _type_value(_value(node['value'], parameters, initial, versions, caller), identifier)
            versions[(root, node['id'])] = value
        elif kind == 'CALL' and terminal is not None and node['id'] == terminal['id'] and node.get('terminalBuiltin'):
            _type_value(_value(node['targetValue'], parameters, initial, versions, caller), 't_address')
        else:
            raise _CannotEvaluate('路径有动态调用、未知副作用或非成功终止')
    return versions, conditions


def _initialize(bundle, runtime_graph):
    """实际重放单一合约的声明初值和简单构造写入，不枚举存储初态。"""
    contract = bundle['contracts'][bundle['targetContractId']]
    if contract['linearizedBaseContracts'] != [bundle['targetContractId']]:
        raise _CannotEvaluate('继承构造的实际初始化顺序尚未验证')
    if contract['node'].get('baseContracts'):
        raise _CannotEvaluate('基类构造绑定尚未验证')
    state, references, constructors = {}, [], []
    for identity in contract['effectiveStateVariables']:
        declaration = bundle['declarations'][identity]
        identifier = declaration.get('typeDescriptions', {}).get('typeIdentifier', '')
        state[identity] = _default(identifier)
        initial = declaration.get('value')
        if initial is not None:
            state[identity] = _type_value(_value(_initial_term(initial, runtime_graph), {}, state, {}, _DEPLOYER), identifier)
            references.append({'nodeId': declaration['id'], 'span': source_span(declaration, bundle['units'])})
    functions = [function for function in bundle['functions'].values()
                 if function['contractId'] == bundle['targetContractId'] and function['kind'] == 'constructor']
    if len(functions) > 1:
        raise _CannotEvaluate('构造函数没有唯一绑定')
    for function in functions:
        if function['modifiers']:
            raise _CannotEvaluate('构造修饰器或基类调用尚未验证')
        graph = _AccessCallGraph(bundle, {'declarationId': function['id'], 'signature': function['signature']})
        if graph.gaps or graph.terminal_nodes or any(node['kind'] not in {'ENTRY', 'EXIT', 'EVAL', 'WRITE', 'RETURN', 'EXPRESSION'}
                                                  for node in graph.nodes):
            raise _CannotEvaluate('构造程序超出简单初始化语义')
        paths = list(_paths(graph, None))
        if len(paths) != 1:
            raise _CannotEvaluate('构造初始化缺少唯一正常退出')
        parameters = {}
        for parameter in function['parameters']:
            identifier = parameter.get('typeDescriptions', {}).get('typeIdentifier', '')
            parameters[parameter['id']] = _DEPLOYER if identifier in {'t_address', 't_address_payable'} else _default(identifier)
        nodes, edges = paths[0]
        versions, _ = _run_nodes(graph, nodes, edges, parameters, state, _DEPLOYER)
        for node in nodes:
            if node['kind'] == 'WRITE':
                root = _root(node['resource'])
                state[root] = versions[(root, node['id'])]
                reference = _reference(node, bundle)
                if reference is not None:
                    references.append(reference)
        constructors.append({'declarationId': function['id'],
            'parameters': [{'declarationId': identity, 'value': value} for identity, value in parameters.items()]})
    return state, {'status': 'REPLAYED', 'runtimeInitialized': True, 'constructors': constructors,
        'references': references, 'reason': '状态初值来自编译声明默认值或实际简单构造 AST 重放；未任意枚举存储槽'}


def _paths(graph, risk):
    adjacent = {}
    for edge in graph.edges:
        if edge['kind'] != 'abort':
            adjacent.setdefault(edge['from'], []).append(edge)
    pending, inspected = [(graph.start, [], [])], 0
    while pending and inspected < _MAX_PATHS:
        current, path, edges = pending.pop()
        if current in path:
            continue
        path = path + [current]
        if graph.nodes[current]['kind'] == 'EXIT':
            inspected += 1
            if risk is None or risk['id'] in path:
                yield [graph.nodes[identity] for identity in path], edges
        else:
            pending.extend((edge['to'], path, edges + [edge]) for edge in adjacent.get(current, []))


def _assignments(bundle, entry):
    parameters = bundle['functions'][entry['declarationId']]['parameters']
    domains = []
    for parameter in parameters:
        identifier = parameter.get('typeDescriptions', {}).get('typeIdentifier', '')
        if identifier in {'t_address', 't_address_payable'}:
            domains.append((_CALLER, _DEPLOYER, 0))
        elif identifier == 't_bool':
            domains.append((False, True))
        elif re.fullmatch(r't_uint\d+', identifier):
            domains.append((0, 1, 2))
        else:
            raise _CannotEvaluate('运行入口实参类型尚未进入有限求值')
    for values in itertools.islice(itertools.product(*domains), _MAX_ASSIGNMENTS):
        yield {parameter['id']: value for parameter, value in zip(parameters, values)}


def prove_access_call(bundle, hypothesis):
    """只证明编译绑定的 selfdestruct/suicide 访问义务；最终双收据裁决由调用方负责。"""
    result = _empty()
    gaps = result['proofScope']['gaps']
    required = ('entries', 'functions', 'declarations', 'builtinReferences', 'contracts', 'nodes', 'units',
                'targetContractId', 'targetContract', 'targetSourceUnit', 'sourceHash', 'environmentHash')
    if (not isinstance(bundle, dict) or bundle.get('verificationStatus') != 'RECOMPILED_MATCH'
            or any(key not in bundle for key in required)):
        result['status'] = 'FAILED'
        gaps.append('编译 bundle 缺少实际重编译绑定或结构索引')
        return result
    if (not isinstance(hypothesis, dict) or type(hypothesis.get('riskLine')) is not int or hypothesis['riskLine'] < 1
            or 'riskFactId' in hypothesis and not isinstance(hypothesis['riskFactId'], str)
            or 'riskSpan' in hypothesis and (not isinstance(hypothesis['riskSpan'], dict)
                or type(hypothesis['riskSpan'].get('start')) is not int
                or type(hypothesis['riskSpan'].get('length')) is not int
                or hypothesis['riskSpan']['start'] < 0 or hypothesis['riskSpan']['length'] < 1)):
        result['status'] = 'FAILED'
        gaps.append('候选风险位置或结构无效')
        return result
    if hypothesis.get('vulnerabilityType') != 'ACCESS_CONTROL' or hypothesis.get('riskOperation') != 'CALL':
        gaps.append('有限终止调用证明器仅支持访问控制 CALL 候选')
        return result
    if (hypothesis.get('contract') != bundle['targetContract']
            or hypothesis.get('sourceHash', bundle['sourceHash']) != bundle['sourceHash']
            or hypothesis.get('sourceFile', bundle['targetSourceUnit']) != bundle['targetSourceUnit']
            or hypothesis.get('mechanism', 'ACCESS_CONTROL') != 'ACCESS_CONTROL'
            or hypothesis.get('riskKind', 'CALL') != 'CALL'):
        result['status'] = 'FAILED'
        gaps.append('候选合约、源码或机制与编译目标不一致')
        return result
    signature = hypothesis.get('functionSignature', hypothesis.get('function'))
    name = hypothesis.get('function')
    if (not isinstance(signature, str) or hypothesis.get('functionSignature') is not None and name is not None
            and (not isinstance(name, str) or (name != signature if '(' in name else name != signature.split('(', 1)[0]))):
        result['status'] = 'FAILED'
        gaps.append('候选短函数名与完整签名不一致')
        return result
    entries = [entry for entry in bundle['entries'] if entry['kind'] in {'function', 'fallback', 'receive'} and entry['matched']
               and (entry['signature'] == signature or '(' not in signature and signature == entry['signature'].split('(', 1)[0])]
    if len(entries) != 1:
        result['status'] = 'UNKNOWN' if '(' not in signature and len(entries) > 1 else 'FAILED'
        gaps.append('候选运行期入口未唯一绑定')
        return result
    entry = entries[0]
    graph = _AccessCallGraph(bundle, entry)
    result['cfg'] = graph.public()
    facts = extract_compiler_facts(bundle)
    risks = bind_risks(graph, hypothesis, bundle, facts)
    if len(risks) != 1:
        unsupported = [node for node in graph.nodes if node['kind'] == 'CALL'
                       and _risk_matches(dict(node, callKind='CALL'), hypothesis, bundle, facts)]
        if len(unsupported) == 1 and not unsupported[0].get('terminalBuiltin'):
            gaps.append('该调用的类型或动态语义超出终止内置证明范围')
            return result
        result['status'] = 'FAILED'
        gaps.append('候选风险 CALL 未唯一绑定，不能修正模型给出的风险行')
        return result
    risk = risks[0]
    result['candidateBound'] = True
    result['riskBinding'] = binding_record(risk, hypothesis)
    result['proofScope'].update(riskSpan=copy.deepcopy(risk['span']), callClosure=sorted(graph.closure))
    if not risk.get('terminalBuiltin'):
        gaps.append('调用没有编译器确认的终止内置语义，超出有限证明范围')
        return result
    result['proofScope'].update(riskSpan=copy.deepcopy(risk['span']), callClosure=sorted(graph.closure),
        entries=[{'signature': entry['signature'], 'declarationId': entry['declarationId'], 'matched': True,
                  'complete': not graph.gaps}], rules=['实际入口与风险跨度绑定', '编译器终止内置类型',
        '默认与简单构造初始化重放', '逐项表达式与状态版本求值', '成功终止不续接调用者'])
    gaps.extend(graph.gaps)
    if gaps:
        return result
    try:
        initial, initialization = _initialize(bundle, graph)
        assignments = list(_assignments(bundle, entry))
    except (KeyError, TypeError, _CannotEvaluate) as error:
        gaps.append(str(error))
        return result
    for nodes, edges in _paths(graph, risk):
        for parameters in assignments:
            try:
                _, conditions = _run_nodes(graph, nodes, edges, parameters, initial, _CALLER, terminal=risk)
            except (KeyError, TypeError, _CannotEvaluate):
                continue
            references = []
            for node in nodes:
                reference = _reference(node, bundle)
                if reference is not None and reference not in references:
                    references.append(reference)
            witness = {'normalExit': True, 'initialization': initialization,
                'cfgNodeIds': [node['id'] for node in nodes], 'conditions': conditions,
                'initialStorage': [{'root': identity, 'value': value} for identity, value in initial.items()],
                'parameters': [{'declarationId': identity, 'value': value} for identity, value in parameters.items()],
                'environment': {'caller': _CALLER, 'deploymentCaller': _DEPLOYER},
                'termination': {'nodeId': risk['nodeId'], 'builtin': risk['builtin'], 'normalExit': True},
                'scope': '绑定初态的静态访问义务反例；无需资金断言，不包含利用交易或攻击载荷'}
            result.update(status='COUNTEREXAMPLE', references=references)
            result['proofScope']['counterexampleComplete'] = True
            result['pathEvidence'].update(status='FEASIBLE', normalExit=True, references=references, witness=witness,
                transactionFeasibility='FINITE_AST_ASSERTION', reason='独立于部署主体的调用主体满足全部路径约束并正常终止')
            for item in result['obligations']:
                if item['name'] in {'actor', 'entry_coverage', 'bypass'}:
                    item.update(status='REFUTED', references=references,
                        reason='已绑定的运行初态与正常终止路径构成主体权限覆盖反例；未声称资源标的、非权限前置条件或状态顺序缺失')
            return result
    gaps.append('有限默认或构造初态下未得到可满足的无授权正常终止路径；不据此推断安全')
    return result
