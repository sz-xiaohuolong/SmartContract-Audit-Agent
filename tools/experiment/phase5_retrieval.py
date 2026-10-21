"""有来源的单维对照与完整配对重排；仅决定参考顺序，不产生程序裁决。"""
import math
import time

from compiler_facts import extract_compiler_facts
from d1_consumption import candidate_context, mechanism_changed, pair_snippets
from r3_retrieval import _build_cards, bind_conditions
from reentrancy_proofs import _ReentrancyGraph, _caller_balance, _normal_reachable
from storage import fingerprint


VERSION = 'phase5-rerank-1'
CONDITIONS = ('P5_RELEVANCE', 'P5_MARGIN')
QUERY_CONFIG = {'templateVersion': 'phase5-query-1', 'maxOperations': 32,
                'maxContrasts': 3, 'dimensions': ['ACTOR', 'ORDER']}


def _json(value):
    from storage import decode, encode
    return decode(encode(value))


def _reference(fact, bundle):
    return {key: fact[key] for key in ('id', 'nodeId', 'span', 'sourceUnitHash')} | {
        'receiptDigest': bundle['receiptDigest']}


def _actor(condition):
    if condition[:2] != ('binary', '=='):
        return None
    for left, right in ((condition[2], condition[3]), (condition[3], condition[2])):
        # 仅在本模块解释已绑定 tx 内置成员；不扩充共享 D2 的证明语义。
        if left == ('member', ('builtin', 'tx'), None, 'origin'):
            left = ('builtin', 'tx.origin')
        if (left in (('builtin', 'msg.sender'), ('builtin', 'tx.origin'))
                and right[:1] == ('read',) and right[3] == 't_address'):
            return left[1], right
    return None


def build_queries(facts, binding, config):
    """只消费重验编译闭包和白名单绑定；操作与调用上下文分别登记。"""
    if (set(binding) != {'sourceHash', 'receiptDigest', 'mechanism'}
            or binding['mechanism'] not in ('ACCESS_CONTROL', 'REENTRANCY')
            or any(binding[key] != facts.get(key) for key in ('sourceHash', 'receiptDigest'))
            or facts.get('verificationStatus') != 'RECOMPILED_MATCH'):
        raise ValueError('查询绑定或编译身份无效；禁止标签、样本名称与伪造事实输入')
    if (set(config) != set(QUERY_CONFIG) or config['templateVersion'] != QUERY_CONFIG['templateVersion']
            or type(config['maxOperations']) is not int or config['maxOperations'] < 1
            or type(config['maxContrasts']) is not int or not 1 <= config['maxContrasts'] <= 3
            or not config['dimensions'] or len(config['dimensions']) != len(set(config['dimensions']))
            or not set(config['dimensions']) <= {'ACTOR', 'ORDER'}):
        raise ValueError('查询模板、维度或预算无效')
    compiled = extract_compiler_facts(facts)
    by_node = {fact['nodeId']: fact for fact in compiled['facts'] if fact['kind'] in {'CALL', 'WRITE', 'CHECK', 'BRANCH'}}
    rows, entry_gaps = [], []
    # 直接按声明排序，不依赖字典插入顺序；同一内部调用可属于多个运行期入口。
    from compiler_facts import _entry_indices, source_span
    for contract_id, contract in sorted(facts['contracts'].items()):
        span = source_span(contract['node'], facts['units'])
        artifact = facts['output'].get('contracts', {}).get(span['sourceUnit'], {}).get(contract['node']['name'], {})
        if not isinstance(artifact.get('abi'), list):
            entry_gaps.append({'contractDeclarationId': contract_id, 'reason': 'MISSING_ABI'})
            continue
        entries, _, gaps = _entry_indices(artifact['abi'], contract, facts['functions'], facts['nodes'], facts['units'])
        entry_gaps.extend({'contractDeclarationId': contract_id, 'reason': gap} for gap in gaps)
        for entry in sorted(entries, key=lambda e: e['signature']):
            if entry['kind'] == 'getter':
                continue
            if not entry['matched']:
                entry_gaps.append({'contractDeclarationId': contract_id, 'entry': entry['signature'], 'reason': 'UNBOUND_ENTRY'})
                continue
            local = {**facts, 'targetContractId': contract_id, 'targetContract': contract['node']['name']}
            graph = _ReentrancyGraph(local, entry)
            identity = {'contractDeclarationId': contract_id, 'declarationId': entry['declarationId'],
                        'signature': entry['signature']}
            entry_gaps.extend({'entry': identity, 'reason': gap} for gap in sorted(set(graph.gaps)))
            if graph.exhausted:
                entry_gaps.append({'entry': identity, 'reason': 'GRAPH_BUDGET'})
            operations = [node for node in graph.nodes if node['kind'] in {'CALL', 'WRITE'} and node.get('nodeId') in by_node]
            # 图外操作仍保留在分母；它们没有可使用的调用上下文。
            seen = {node['nodeId'] for node in operations}
            operations += [{**fact, 'context': [], 'id': None, 'structuralOnly': True}
                for fact in compiled['facts'] if fact['kind'] in {'CALL', 'WRITE'}
                and fact['functionDeclarationId'] in graph.closure and fact['nodeId'] not in seen
                and (fact['kind'] == 'WRITE' or fact.get('callKind') != 'internal' and not fact.get('builtin'))]
            for node in operations:
                fact = by_node[node['nodeId']]
                key = fingerprint({'sourceHash': facts['sourceHash'], 'entry': identity,
                    'factId': fact['id'], 'context': node['context'], 'graphNode': node['id']})
                row = {'operationKey': key, **binding, 'entry': identity, 'factId': fact['id'],
                    'context': node['context'], 'graphNode': node['id'], 'references': [_reference(fact, facts)],
                    'structureStatus': 'UNSUPPORTED', 'independentReview': 'UNREVIEWED',
                    'original': None, 'contrasts': [], 'reason': 'NO_UNIQUE_SUPPORTED_BINDING',
                    'resourceKey': None, 'limitations': sorted(set(graph.gaps))}
                if node.get('structuralOnly') or graph.exhausted:
                    rows.append(row); continue
                dimension, options = None, []
                if binding['mechanism'] == 'ACCESS_CONTROL':
                    for guard, condition in graph.guards(node):
                        actor = _actor(condition)
                        if actor and guard.get('nodeId') in by_node:
                            # 当前槽版本和未知表达式必须保持可解释；不展开角色／初始化假设。
                            read = actor[1]
                            if read[2] != (guard.get('versionsBefore', {}).get(read[1], 'initial'), guard.get('epochBefore')):
                                continue
                            options.append((actor, guard))
                    if len(options) == 1:
                        (subject, read), guard = options[0]
                        dimension = 'ACTOR'
                        slot = fingerprint(_json(read[1]))[:16]
                        # 查询文本隐藏样本名、方法分数与路径；槽和操作作为不变条件。
                        common = f'同一入口的操作 {fact["kind"]} 与权限状态槽 {slot}：'
                        original = common + f'主体 {subject} 的相等权限检查是否约束该操作？'
                        other = 'tx.origin' if subject == 'msg.sender' else 'msg.sender'
                        contrast = common + f'主体 {other} 的相等权限检查是否约束该操作？'
                        row['references'].append(_reference(by_node[guard['nodeId']], facts))
                        row['invariants'] = {'authorityResource': _json(read[1]), 'stateVersion': _json(read[2]),
                                             'operationKind': fact['kind']}
                elif node['kind'] == 'CALL':
                    resource = _caller_balance(node, graph)
                    writes = [write for write in graph.nodes if write['kind'] == 'WRITE' and resource is not None
                              and write.get('resource') == resource and write.get('nodeId') in by_node
                              and (_normal_reachable(graph, write['id'], node['id'])
                                   or _normal_reachable(graph, node['id'], write['id']))]
                    if len(writes) == 1:
                        write = writes[0]
                        before = graph.dominates(write['id'], node['id'])
                        after = graph.dominates(node['id'], write['id'])
                        if before != after:
                            dimension = 'ORDER'
                            order, other = ('之前', '之后') if before else ('之后', '之前')
                            common = f'同一入口和调用者余额资源 {fingerprint(_json(resource))[:16]}，外部回调前提未证明：'
                            original = common + f'余额写入是否在外部调用{order}？'
                            contrast = common + f'余额写入是否在外部调用{other}？'
                            row['resourceKey'] = 'msg.sender'
                            row['references'].append(_reference(by_node[write['nodeId']], facts))
                            row['invariants'] = {'resource': _json(resource), 'callback': 'UNPROVED',
                                'stateVersions': sorted((repr(k), v) for k, v in node.get('versionsBefore', {}).items())}
                if dimension in config['dimensions']:
                    row.update(structureStatus='VALID', reason=None, original=original,
                        contrasts=[{'text': contrast, 'dimension': dimension}])
                rows.append(row)
    rows.sort(key=lambda row: row['operationKey'])
    for index, row in enumerate(rows):
        if index >= config['maxOperations']:
            row.update(structureStatus='UNSUPPORTED', reason='TARGET_QUERY_BUDGET', original=None, contrasts=[])
    payload = {'schemaVersion': VERSION, **binding, 'config': config, 'queries': rows,
               'plannedOperations': len(rows), 'entryGaps': entry_gaps}
    return _json({**payload, 'querySetHash': fingerprint(payload)})


def freeze_pool(view, snapshot, catalog):
    """从冻结原件重建配对窗口；保留所有候选，拒绝半对或身份漂移。"""
    snapshot_id = fingerprint(snapshot)
    pool = view['pool']
    if (view['snapshotId'] != snapshot_id or pool['snapshotId'] != snapshot_id
            or pool['sourceHash'] != view['sourceHash'] or view.get('poolHash') != fingerprint(pool)):
        raise ValueError('候选池快照、源码或摘要不符')
    registry = _build_cards(snapshot, catalog, snapshot_id)
    cards = {card['pairId']: card for card in registry['cards']}
    docs = {doc['id']: doc for doc in snapshot['documents']}
    pairs, seen = {}, set()
    for candidate in pool['candidates']:
        key = candidate['chunkId']
        metadata = catalog['cases'].get(key)
        if key in seen or metadata is None or any(candidate[k] != metadata[k] for k in ('pairId', 'role', 'mechanism')):
            raise ValueError('重复候选或配对来源不符')
        seen.add(key)
        roles = pairs.setdefault(candidate['pairId'], {})
        if candidate['role'] in roles:
            raise ValueError('重复配对角色')
        roles[candidate['role']] = candidate
    materials = []
    for pair, roles in sorted(pairs.items()):
        if set(roles) != {'VULNERABLE', 'DEFENSE'} or pair not in cards:
            raise ValueError('缺少完整配对或机制窗口')
        before, after = (roles[role] for role in ('VULNERABLE', 'DEFENSE'))
        left, right = pair_snippets(docs[before['chunkId']]['text'], docs[after['chunkId']]['text'], before['mechanism'])
        if before['text'] != left or after['text'] != right or not mechanism_changed(left, right, before['mechanism']):
            raise ValueError('配对文本与快照机制窗口不符')
        text = '改动前（未审核，省略其他上下文）\n' + left + '\n改动后（未审核，省略其他上下文）\n' + right
        materials.append({'pairId': pair, 'beforeId': before['chunkId'], 'afterId': after['chunkId'],
            'mechanism': before['mechanism'], 'background': cards[pair]['background'],
            'text': text, 'context': candidate_context(before, True) + candidate_context(after, True),
            'materialHash': fingerprint(text), 'lineage': cards[pair]['lineage'],
            'sources': cards[pair]['sources']})
    return {'snapshotId': snapshot_id, 'sourceHash': view['sourceHash'], 'poolHash': fingerprint(pool),
            'evidence': materials, 'evidenceHash': fingerprint(materials), 'routes': pool.get('routes'),
            'originSchema': pool['schemaVersion']}


def _validate_materials(evidence):
    ids, side_ids = set(), set()
    for row in evidence:
        if (row['pairId'] in ids or not row['text'] or not row['context']
                or row['beforeId'] == row['afterId'] or {row['beforeId'], row['afterId']} & side_ids):
            raise ValueError('配对重复、缺少一侧或材料为空')
        ids.add(row['pairId']); side_ids.update((row['beforeId'], row['afterId']))


def score_pool(query_set, evidence, encode, config):
    """同一完整配对分别与原查询和每条对照计算余弦；异常使整单元失败。"""
    _validate_materials(evidence)
    result = {'schemaVersion': VERSION, 'operationKey': query_set['operationKey'],
        'mechanism': query_set['mechanism'], 'resourceKey': query_set.get('resourceKey'),
        'queryHash': fingerprint(query_set), 'evidenceHash': fingerprint(evidence), 'config': config,
        'configHash': fingerprint(config), 'status': 'NOT_SCORABLE', 'margin': None, 'scores': [],
        'errors': [], 'encodingCalls': 0, 'encodingTexts': 0, 'durationMs': 0}
    if query_set['structureStatus'] != 'VALID' or not query_set['contrasts'] or not evidence:
        result['errors'] = ['无有效结构对照或完整材料']; return result
    texts = [config['queryPrefix'] + text for text in
             [query_set['original']] + [q['text'] for q in query_set['contrasts']]]
    texts += [config['documentPrefix'] + row['text'] for row in evidence]
    started = time.monotonic()
    try:
        if type(config['maxInputTokens']) is not int or config['maxInputTokens'] < 1:
            raise ValueError('编码输入上限无效')
        result['encodingCalls'], result['encodingTexts'] = 1, len(texts)
        encoded = encode(texts)
        if encoded['identity'] != config['identity']:
            raise ValueError('评分器模型身份漂移')
        if any(len(encoded[field]) != len(texts) for field in ('vectors', 'truncated', 'tokenCounts')):
            raise ValueError('编码数量不完整')
        if any(flag is not False for flag in encoded['truncated']) or any(
                type(count) is not int or count < 1 or count > config['maxInputTokens'] for count in encoded['tokenCounts']):
            raise ValueError('编码发生截断或超过输入上限')
        vectors = []
        for vector in encoded['vectors']:
            if len(vector) != config['identity']['dimension'] or any(
                    type(v) not in (float, int) or not math.isfinite(v) for v in vector):
                raise ValueError('向量维度或有限数值无效')
            norm = math.hypot(*vector)
            if not norm or not math.isfinite(norm):
                raise ValueError('零向量或范数溢出')
            vectors.append([v / norm for v in vector])
        query_count = 1 + len(query_set['contrasts'])
        scores = []
        for row, vector in zip(evidence, vectors[query_count:]):
            similarities = [sum(a * b for a, b in zip(q, vector)) for q in vectors[:query_count]]
            scores.append({'pairId': row['pairId'], 'originalScore': similarities[0],
                'contrastScores': similarities[1:], 'margin': similarities[0] - max(similarities[1:])})
        result.update(status='SCORED', scores=scores, vectors=vectors, inputHashes=[fingerprint(t) for t in texts],
                      tokenCounts=encoded['tokenCounts'], errors=[])
    except (ValueError, TypeError, KeyError, OverflowError, RuntimeError, OSError) as error:
        result.update(status='FAILED', errors=[str(error)], scores=[])
    result['durationMs'] = round((time.monotonic() - started) * 1000)
    return result


def rank_pool(frozen_pool, scores, condition, budget):
    """共享过滤、配对预算与渲染；仅替换排序键，负差值不触发拒绝。"""
    evidence = frozen_pool['evidence']
    _validate_materials(evidence)
    if (condition not in CONDITIONS or scores['evidenceHash'] != fingerprint(evidence)
            or any(type(budget.get(k)) is not int or budget[k] < 1 for k in ('maxPairs', 'maxBytes'))):
        raise ValueError('条件、预算或同池身份不符')
    result = {'schemaVersion': VERSION, 'condition': condition, 'poolHash': frozen_pool['poolHash'],
        'operationKey': scores['operationKey'], 'evidenceHash': scores['evidenceHash'], 'budget': budget,
        'ranking': [], 'selectedPairs': [], 'selectedEvidenceIds': [], 'context': '', 'contextBytes': 0,
        'rejected': [], 'status': scores['status']}
    if scores['status'] != 'SCORED':
        return {**result, 'reason': scores['errors'], 'fallback': '原检索可单独运行；本单元未参与新方法比较'}
    by_id = {row['pairId']: row for row in scores['scores']}
    if len(by_id) != len(scores['scores']) or set(by_id) != {row['pairId'] for row in evidence}:
        raise ValueError('评分未完整覆盖同一候选池')
    key = 'originalScore' if condition == 'P5_RELEVANCE' else 'margin'
    if any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k])
           for row in by_id.values() for k in ('originalScore', 'margin')):
        raise ValueError('排序分数不是有限数值')
    ordered = sorted(evidence, key=lambda row: (-by_id[row['pairId']][key], row['pairId']))
    result['ranking'] = [row['pairId'] for row in ordered]
    used = set()
    for row in ordered:
        pair, reason = row['pairId'], None
        if row['mechanism'] != scores.get('mechanism', row['mechanism']):
            reason = 'MECHANISM_CONFLICT'
        elif bind_conditions(row['background'], {'resourceKey': scores.get('resourceKey')})['applicability'] == 'CONTRADICTED':
            reason = 'RESOURCE_CONFLICT'
        elif fingerprint(row['text']) in used:
            reason = 'DUPLICATE_MATERIAL'
        elif len(result['selectedPairs']) >= budget['maxPairs']:
            reason = 'PAIR_BUDGET'
        elif result['contextBytes'] + len(row['context'].encode()) > budget['maxBytes']:
            reason = 'BYTE_BUDGET'
        if reason:
            result['rejected'].append({'pairId': pair, 'reason': reason}); continue
        result['selectedPairs'].append(pair)
        result['selectedEvidenceIds'].extend((row['beforeId'], row['afterId']))
        result['context'] += row['context']
        result['contextBytes'] += len(row['context'].encode())
        used.add(fingerprint(row['text']))
    result.update(status='COMPLETED', contextHash=fingerprint(result['context']))
    return result
