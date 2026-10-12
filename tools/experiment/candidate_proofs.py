"""从已重编译绑定的 AST 证明权限候选；不接收人工完整性断言。"""
import copy

from compiler_facts import extract_compiler_facts, source_span
from risk_binding import bind_risks, binding_record
from compiled_d2 import _Graph, _authority, _current_authority, _reference, _walk


_OBLIGATIONS = ('actor', 'resource', 'pre_risk_guard', 'state_version', 'entry_coverage', 'bypass')
_MAX_CLOSURE = 2000
_READONLY_YUL = frozenset(('stop add sub mul div sdiv mod smod addmod mulmod exp signextend '
    'lt gt slt sgt eq iszero and or xor not byte shl shr sar keccak256 address balance origin '
    'caller callvalue calldataload calldatasize calldatacopy codesize codecopy gasprice extcodesize '
    'extcodecopy returndatasize returndatacopy extcodehash blockhash coinbase timestamp number '
    'difficulty prevrandao gaslimit chainid selfbalance basefee pop mload mstore mstore8 sload '
    'msize gas pc return revert invalid log0 log1 log2 log3 log4').split())
_YUL_SHAPES = frozenset(('YulBlock YulExpressionStatement YulFunctionCall YulIdentifier YulLiteral '
    'YulAssignment YulTypedName YulVariableDeclaration YulIf YulSwitch YulCase YulForLoop '
    'YulBreak YulContinue YulLeave').split())
_AST_SHAPES = frozenset(('Block UncheckedBlock ExpressionStatement VariableDeclarationStatement '
    'IfStatement ForStatement WhileStatement DoWhileStatement Return Break Continue RevertStatement Throw '
    'EmitStatement PlaceholderStatement TryStatement TryCatchClause InlineAssembly Assignment '
    'UnaryOperation BinaryOperation Identifier IdentifierPath Literal FunctionCall FunctionCallOptions '
    'ElementaryTypeNameExpression NewExpression MemberAccess IndexAccess IndexRangeAccess '
    'TupleExpression Conditional VariableDeclaration ElementaryTypeName UserDefinedTypeName '
    'ArrayTypeName Mapping FunctionTypeName ParameterList').split())


class _PermissionGraph(_Graph):
    """只保留权限证明需要的资源更新，不声称算术路径可满足。"""

    def statement(self, ast, tails, env, stack, context, continuation=None):
        if isinstance(ast, dict) and ast.get('nodeType') == 'UncheckedBlock':
            # 完整盘点每项存储更新；数值溢出只影响可提交路径的子集。
            # 本模块仅证明不授权路径无法到达写入，不给正反例。
            ast = dict(ast, nodeType='Block')
        return super().statement(ast, tails, env, stack, context, continuation)

    def expr(self, ast, tails, env, stack, context):
        if isinstance(ast, dict) and ast.get('nodeType') == 'Assignment' and ast.get('operator') != '=':
            left = ast.get('leftHandSide')
            if self.resource(left, env) is not None and not self.effects(left):
                # 不计算新数值，只登记确定的同一资源写入及版本失效。
                tails, _, env = super().expr(ast.get('rightHandSide'), tails, env, stack, context)
                resource = self.resource(left, env)
                value = ('unknown', 'arithmetic-result', ast['id'])
                node = self.add('WRITE', ast, tails, context, env, resource=resource, value=value)
                self.record_write(resource, value, env, node)
                return [node], value, env
        if isinstance(ast, dict) and ast.get('nodeType') == 'UnaryOperation' and ast.get('operator') in {'++', '--', 'delete'}:
            expression = ast.get('subExpression')
            resource = self.resource(expression, env)
            if resource is not None and not self.effects(expression):
                value = ('unknown', 'unary-result', ast['id'])
                node = self.add('WRITE', ast, tails, context, env, resource=resource, value=value)
                self.record_write(resource, value, env, node)
                return [node], value, env
        return super().expr(ast, tails, env, stack, context)


class _Effects:
    """全语法递归盘点存储写入；未知别名、动态调用和汇编不当作无效果。"""

    def __init__(self, bundle):
        self.bundle = bundle
        self.writes, self.gaps, self.calls, self.closure = [], [], [], set()
        self.visits = 0

    def gap(self, message):
        if message not in self.gaps:
            self.gaps.append(message)

    def roots(self, ast, aliases):
        if not isinstance(ast, dict):
            return set()
        kind = ast.get('nodeType')
        if kind == 'Identifier':
            identity = ast.get('referencedDeclaration')
            declaration = self.bundle['declarations'].get(identity, {})
            if declaration.get('stateVariable'):
                return {identity}
            if declaration.get('storageLocation') == 'storage':
                result = aliases.get(identity)
                if result is None:
                    self.gap(f'存储别名 {identity} 未唯一绑定')
                    return set()
                return set(result)
            return set()
        if kind in {'MemberAccess', 'IndexAccess', 'IndexRangeAccess'}:
            return self.roots(ast.get('expression', ast.get('baseExpression')), aliases)
        if kind == 'TupleExpression':
            return set().union(*(self.roots(item, aliases) for item in ast.get('components', [])))
        self.gap(f'写入资源形状 {kind} 未证明')
        return set()

    def target(self, expression):
        identity = expression.get('referencedDeclaration')
        function = self.bundle['functions'].get(identity)
        if function is None:
            return None
        base = expression.get('expression', {})
        is_super = self.bundle['builtinReferences'].get(base.get('referencedDeclaration')) == 'super'
        qualified = self.bundle['declarations'].get(base.get('referencedDeclaration'), {}).get('nodeType') == 'ContractDefinition'
        lineage = self.bundle['contracts'][self.bundle['targetContractId']]['linearizedBaseContracts']
        if not is_super and not qualified and function['visibility'] != 'private' and function['contractId'] in lineage:
            matches = [self.bundle['functions'][fid] for fid in self.bundle['contracts'][self.bundle['targetContractId']]['effectiveFunctions']
                       if self.bundle['functions'][fid]['signature'] == function['signature']]
            if len(matches) != 1:
                self.gap(f'虚内部调用 {identity} 未唯一绑定')
                return None
            return matches[0]
        return function

    def visit(self, value, aliases, stack):
        if not isinstance(value, (dict, list)):
            return
        if isinstance(value, list):
            for item in value:
                self.visit(item, aliases, stack)
            return
        kind = value.get('nodeType')
        if kind is not None and kind not in _AST_SHAPES:
            self.gap(f'AST 形状 {kind} 的存储效果未证明')
        if kind == 'InlineAssembly':
            yul = value.get('AST')
            operations = [node.get('functionName', {}).get('name') for node in _walk(yul)
                          if node.get('nodeType') == 'YulFunctionCall']
            unknown_shapes = [node for node in _walk(yul) if node.get('nodeType') not in _YUL_SHAPES]
            if not isinstance(yul, dict) or unknown_shapes or any(operation not in _READONLY_YUL for operation in operations):
                self.gap(f'汇编 {value.get("id")} 的存储效果未证明')
        if kind == 'NewExpression' and value.get('typeName', {}).get('nodeType') != 'ArrayTypeName':
            self.gap(f'创建表达式 {value.get("id")} 的回调闭包未证明')
        if kind == 'VariableDeclarationStatement':
            for declaration in value.get('declarations', []):
                if declaration is not None and declaration.get('storageLocation') == 'storage':
                    aliases[declaration['id']] = self.roots(value.get('initialValue'), aliases)
        if kind == 'Assignment' or kind == 'UnaryOperation' and value.get('operator') in {'++', '--', 'delete'}:
            left = value.get('leftHandSide', value.get('subExpression'))
            for root in self.roots(left, aliases):
                self.writes.append({'nodeId': value['id'], 'root': root, 'span': source_span(value, self.bundle['units'])})
            if isinstance(left, dict) and left.get('nodeType') == 'Identifier':
                declaration = self.bundle['declarations'].get(left.get('referencedDeclaration'), {})
                if declaration.get('storageLocation') == 'storage' and not declaration.get('stateVariable'):
                    self.gap(f'存储引用重绑定 {value["id"]} 未证明')
        if kind == 'FunctionCall' and value.get('kind') != 'typeConversion':
            expression = value.get('expression', {})
            type_id = expression.get('typeDescriptions', {}).get('typeIdentifier', '')
            reference = expression.get('referencedDeclaration')
            builtin = self.bundle['builtinReferences'].get(reference)
            declaration = self.bundle['declarations'].get(reference, {})
            if builtin in {'require', 'assert', 'revert', 'sha256', 'keccak256', 'ripemd160', 'ecrecover', 'addmod', 'mulmod', 'type', 'blockhash', 'gasleft'}:
                pass
            elif declaration.get('nodeType') in {'EventDefinition', 'ErrorDefinition'}:
                pass
            elif expression.get('nodeType') == 'NewExpression' and expression.get('typeName', {}).get('nodeType') == 'ArrayTypeName':
                pass
            elif type_id.startswith(('t_function_arraypush', 't_function_arraypop')):
                for root in self.roots(expression.get('expression'), aliases):
                    self.writes.append({'nodeId': value['id'], 'root': root,
                                        'span': source_span(value, self.bundle['units'])})
            elif type_id.startswith(('t_function_abiencode', 't_function_bytesconcat', 't_function_stringconcat')):
                pass
            elif type_id.startswith('t_function_internal'):
                target = self.target(expression)
                if target is None:
                    self.gap(f'内部调用 {value["id"]} 缺少实际声明')
                else:
                    actuals = list(value.get('arguments', []))
                    if expression.get('nodeType') == 'MemberAccess' and 'bound_to' in type_id:
                        actuals.insert(0, expression.get('expression'))
                    bound = {}
                    if len(actuals) != len(target['parameters']):
                        self.gap(f'内部调用 {value["id"]} 实参未完全代入')
                    for parameter, actual in zip(target['parameters'], actuals):
                        if parameter.get('storageLocation') == 'storage':
                            bound[parameter['id']] = self.roots(actual, aliases)
                    self.function(target['id'], bound, stack)
            elif type_id.startswith('t_function_external'):
                # 普通外部调用只可通过本合约入口写本合约存储；这些入口逐项核验。
                self.calls.append({'nodeId': value['id'], 'kind': 'EXTERNAL', 'reference': reference,
                                   'span': source_span(value, self.bundle['units'])})
            else:
                self.gap(f'动态、低级或未解析调用 {value["id"]} 的存储效果未证明')
        for key, child in value.items():
            if key != 'AST':
                self.visit(child, aliases, stack)

    def function(self, identity, aliases=None, stack=()):
        self.visits += 1
        if self.visits > _MAX_CLOSURE or identity in stack or len(stack) >= 24:
            self.gap('候选效果闭包递归或预算超限')
            return
        self.closure.add(identity)
        function = self.bundle['functions'].get(identity)
        if function is None or function['body'] is None:
            self.gap(f'调用声明 {identity} 缺少实现')
            return
        aliases = dict(aliases or {})
        for invocation in function['modifiers']:
            modifier_id = invocation.get('modifierName', {}).get('referencedDeclaration')
            modifier = self.bundle['functions'].get(modifier_id)
            # 旧 compact AST 将无括号修饰器的实参表示为 null。
            actuals = invocation.get('arguments') or []
            # 修饰器实参在入口执行，可独立写权限；不能只盘点修饰器函数体。
            self.visit(actuals, aliases, stack + (identity,))
            bound = {}
            if modifier is not None:
                if len(actuals) != len(modifier['parameters']):
                    self.gap(f'修饰器 {modifier_id} 实参未完全代入')
                for parameter, actual in zip(modifier['parameters'], actuals):
                    if parameter.get('storageLocation') == 'storage':
                        bound[parameter['id']] = self.roots(actual, aliases)
            self.function(modifier_id, bound, stack + (identity,))
        self.visit(function['body'], aliases, stack + (identity,))


def _empty():
    return {'status': 'UNKNOWN', 'proofKind': 'REFUTATION', 'candidateBound': False,
            'authorityClosure': [], 'initialization': {'status': 'UNVERIFIED', 'references': []},
            'references': [], 'obligations': [{'name': name, 'status': 'UNKNOWN', 'references': [],
                'reason': '尚未建立完整权限候选证明'} for name in _OBLIGATIONS],
            'pathEvidence': {'status': 'UNKNOWN', 'references': [], 'kind': 'CANDIDATE_PERMISSION_CLOSURE'},
            'proofScope': {'complete': False, 'entries': [], 'gaps': [], 'callClosure': []}}


def _append_references(result, nodes, bundle):
    references = [reference for node in nodes if (reference := _reference(node, bundle)) is not None]
    for reference in references:
        if reference not in result['references']:
            result['references'].append(reference)
    return references


def prove_candidate(bundle, hypothesis):
    """输入为 load_bound_compilation 的 bundle；输出不包含最终工具裁决。"""
    result = _empty()
    gaps = result['proofScope']['gaps']
    if not isinstance(bundle, dict) or bundle.get('verificationStatus') != 'RECOMPILED_MATCH':
        result['status'] = 'FAILED'
        gaps.append('编译 bundle 尚未实际重编译绑定')
        return result
    if (not isinstance(hypothesis, dict) or type(hypothesis.get('riskLine')) is not int
            or hypothesis['riskLine'] < 1
            or 'riskFactId' in hypothesis and not isinstance(hypothesis['riskFactId'], str)
            or 'riskSpan' in hypothesis and (not isinstance(hypothesis['riskSpan'], dict)
                or type(hypothesis['riskSpan'].get('start')) is not int
                or type(hypothesis['riskSpan'].get('length')) is not int
                or hypothesis['riskSpan']['start'] < 0 or hypothesis['riskSpan']['length'] < 1)):
        result['status'] = 'FAILED'
        gaps.append('候选位置或数据结构无效')
        return result
    if hypothesis.get('vulnerabilityType') != 'ACCESS_CONTROL' or hypothesis.get('riskOperation') != 'WRITE':
        gaps.append('该有限证明器只处理权限写入候选')
        return result
    if (hypothesis.get('contract') != bundle['targetContract']
            or hypothesis.get('sourceHash', bundle['sourceHash']) != bundle['sourceHash']
            or hypothesis.get('sourceFile', bundle['targetSourceUnit']) != bundle['targetSourceUnit']
            or hypothesis.get('mechanism', 'ACCESS_CONTROL') != 'ACCESS_CONTROL'
            or hypothesis.get('riskKind', 'WRITE') != 'WRITE'):
        result['status'] = 'FAILED'
        gaps.append('候选合约、源码或机制与实际编译目标不一致')
        return result
    signature = hypothesis.get('functionSignature', hypothesis.get('function'))
    name = hypothesis.get('function')
    if (not isinstance(signature, str) or hypothesis.get('functionSignature') is not None
            and name is not None and (not isinstance(name, str)
                or (name != signature if '(' in name else name != signature.split('(', 1)[0]))):
        result['status'] = 'FAILED'
        gaps.append('候选函数名称与完整签名不一致')
        return result
    candidates = [entry for entry in bundle['entries'] if entry['kind'] == 'function' and entry['matched']
        and (entry['signature'] == signature or '(' not in signature
            and bundle['functions'][entry['declarationId']]['node'].get('name') == signature)]
    if len(candidates) != 1:
        result['status'] = 'UNKNOWN' if '(' not in signature and len(candidates) > 1 else 'FAILED'
        gaps.append('候选运行入口未唯一绑定')
        return result
    entry = candidates[0]
    graph = _PermissionGraph(bundle, entry)
    gaps.extend(f'{entry["signature"]}：{gap}' for gap in graph.gaps)
    facts = extract_compiler_facts(bundle)
    risks = bind_risks(graph, hypothesis, bundle, facts)
    if len(risks) != 1 or risks[0].get('resource') is None:
        result['status'] = 'FAILED'
        gaps.append('候选风险写入未唯一绑定')
        return result
    risk = risks[0]
    result['candidateBound'] = True
    result['riskBinding'] = binding_record(risk, hypothesis)
    result['proofScope']['riskSpan'] = copy.deepcopy(risk['span'])
    primary_guards = [(guard, authority) for guard, condition in graph.guards(risk)
                      if (authority := _authority(condition)) is not None and _current_authority(guard, condition)
                      and not graph.intervening(guard, risk, authority)]
    primary_guards = [(guard, authority) for guard, authority in primary_guards if not authority[2]]
    authorities = {authority for _, authority in primary_guards}
    if len(authorities) != 1:
        gaps.append('未证明同主体、同版本的唯一实际权限槽支配风险写入')
        return result
    authority = next(iter(authorities))
    risk_root = risk['resource'][1]
    protected = {risk_root, authority[1]}
    graphs = {entry['declarationId']: graph}
    summaries = {}
    entries = list(bundle['entries'])
    listed = {item['declarationId'] for item in entries}
    for identity in bundle['contracts'][bundle['targetContractId']]['effectiveFunctions']:
        function = bundle['functions'][identity]
        if function['kind'] in {'fallback', 'receive'} and identity not in listed:
            entries.append({'signature': function['signature'], 'kind': 'function', 'declarationId': identity, 'matched': True})
    if bundle['entryGaps']:
        gaps.extend(bundle['entryGaps'])
    closure = set()
    for other in entries:
        if not other['matched']:
            gaps.append(f'运行入口 {other["signature"]} 未唯一绑定')
            continue
        if other['kind'] == 'getter':
            continue
        effects = _Effects(bundle)
        effects.function(other['declarationId'])
        summaries[other['declarationId']] = effects
        closure.update(effects.closure)
        gaps.extend(f'{other["signature"]}：{gap}' for gap in effects.gaps)
    dependencies = []
    inspected = set()
    changed = True
    while changed:
        changed = False
        for other in entries:
            effects = summaries.get(other['declarationId'])
            if effects is None:
                continue
            sensitive = [write for write in effects.writes if write['root'] in protected]
            if not sensitive:
                continue
            if other['declarationId'] not in graphs:
                graphs[other['declarationId']] = _PermissionGraph(bundle, other)
                gaps.extend(f'{other["signature"]}：{gap}' for gap in graphs[other['declarationId']].gaps)
            other_graph = graphs[other['declarationId']]
            expected = {(write['nodeId'], write['root']) for write in sensitive}
            observed = {(node.get('nodeId'), node.get('resource', (None, None))[1]) for node in other_graph.nodes if node['kind'] == 'WRITE'}
            for missing in expected - observed:
                gaps.append(f'{other["signature"]}：相关写入 {missing} 未完整展开')
            for write in [node for node in other_graph.nodes if node['kind'] == 'WRITE' and node.get('resource', (None, None))[1] in protected]:
                key = (other['declarationId'], write['id'])
                if key in inspected:
                    continue
                inspected.add(key)
                choices = [(guard, role) for guard, condition in other_graph.guards(write)
                    if (role := _authority(condition)) is not None and not role[2]
                    and _current_authority(guard, condition) and not other_graph.intervening(guard, write, role)]
                if write['resource'][1] == risk_root and risk_root != authority[1]:
                    choices = [(guard, role) for guard, role in choices if role == authority]
                roles = {role for _, role in choices}
                if len(roles) != 1:
                    gaps.append(f'{other["signature"]}：资源 {write["resource"][1]} 写入未获唯一稳定主体保护')
                    continue
                role = next(iter(roles))
                new_root = role[1]
                if new_root not in protected:
                    protected.add(new_root)
                    changed = True
                guard = next(guard for guard, item in choices if item == role)
                refs = _append_references(result, [guard, write], bundle)
                dependencies.append({'entry': other['signature'], 'writtenRoot': write['resource'][1],
                    'authorityRoot': new_root, 'guardNodeId': guard['nodeId'], 'writeNodeId': write['nodeId'],
                    'references': refs})
    for other in entries:
        effects = summaries.get(other['declarationId'])
        related = bool(effects and (effects.gaps or effects.calls or any(write['root'] in protected for write in effects.writes)))
        related_graph = graphs.get(other['declarationId'])
        result['proofScope']['entries'].append({'signature': other['signature'], 'kind': other['kind'],
            'declarationId': other['declarationId'], 'matched': other['matched'], 'related': related,
            'complete': other['matched'] and (effects is None or not effects.gaps)
                and (related_graph is None or not related_graph.gaps),
            'reason': '实际 AST 与内部调用闭包完整盘点；其他入口的回调继续经过已核权限写入入口'})
    result['authorityClosure'] = dependencies
    result['proofScope']['callClosure'] = sorted(closure)
    result['proofScope']['protectedRoots'] = sorted(protected)
    result['proofScope']['rules'] = ['编译声明身份', '完整存储效果盘点', '内部参数与storage receiver代入',
        'CHECK支配', '同权限槽版本', '权限委派闭包', '完整ABI与fallback入口']
    result['initialization'] = {'status': 'NO_UNPROTECTED_RUNTIME_AUTHORITY_WRITE' if not gaps else 'UNVERIFIED',
        'context': 'FIXED_COMPILED_RUNTIME', 'constructors': copy.deepcopy(bundle['constructors']),
        'reason': '构造阶段建立初始配置；所有可调用权限写入另行核验，未保护公开初始化不得免除',
        'references': []}
    gaps[:] = sorted(set(gaps))
    refs = _append_references(result, [risk] + [guard for guard, _ in primary_guards], bundle)
    for item in result['obligations']:
        if item['name'] in {'actor', 'resource', 'pre_risk_guard', 'state_version'} or not gaps:
            item.update(status='SUPPORTED', references=refs, reason='真实主体权限检查支配绑定写入；存储版本和所有权限写入口按实际闭包核验')
    if not gaps:
        result['status'] = 'PROVED'
        result['proofScope']['complete'] = True
        result['pathEvidence'].update(status='BLOCKED', references=result['references'],
            reason='未授权主体无法通过任何相关写入入口改变风险资源或取得委派权限')
    return result
