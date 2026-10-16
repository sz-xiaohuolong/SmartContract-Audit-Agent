"""有来源的机制卡片、独立多路召回与保守条件绑定；不产生安全证明。"""
import math
import re
from collections import Counter

from d1_consumption import _code, candidate_context, mechanism_changed, mechanism_events, pair_snippets
from recall import _recall_candidates
from snapshots import verify_snapshot
from storage import fingerprint


STRATEGIES = frozenset({'R3_CODE', 'R3_CARD', 'R3_DENSE', 'R3_FUSION'})
VERSION = 'r3-mechanism-1'


def _terms(text):
    return re.findall(r'[a-z_$][a-z0-9_$]*|\d+', re.sub(r'([a-z])([A-Z])', r'\1 \2', text).lower())


def bm25(documents, query, limit):
    """各路独立搜索完整知识侧；无匹配词的项不补成召回结果。"""
    counts = {key: Counter(_terms(text)) for key, text in documents.items()}
    average = sum(sum(row.values()) for row in counts.values()) / max(1, len(counts)) or 1
    scores = {}
    for term in set(_terms(query)):
        frequency = sum(term in row for row in counts.values())
        weight = math.log(1 + (len(counts) - frequency + 0.5) / (frequency + 0.5))
        for key, row in counts.items():
            tf = row[term]
            if tf:
                scores[key] = scores.get(key, 0) + weight * tf * 2.2 / (
                    tf + 1.2 * (0.25 + 0.75 * sum(row.values()) / average))
    return sorted(scores, key=lambda key: (-scores[key], key))[:limit]


def reciprocal_fusion(routes):
    scores = {}
    for ranking in routes.values():
        if len(ranking) != len(set(ranking)):
            raise ValueError('召回路内案例重复')
        for rank, key in enumerate(ranking, 1):
            scores[key] = scores.get(key, 0) + 1 / rank
    return scores


def _resource_key(text):
    # 只读取显式写入的索引键，不把权限保护条件误作需要相同的背景。
    keys = {re.sub(r'\s+', '', match) for match in re.findall(
        r'\[\s*([^\]\n]+)\s*\]\s*(?:=|\+=|-=|\+\+|--)', _code(text))}
    return next(iter(keys)) if len(keys) == 1 and keys <= {'msg.sender', 'tx.origin'} else None


def bind_conditions(background, target):
    left, right = background.get('resourceKey'), target.get('resourceKey')
    contradicted = left is not None and right is not None and left != right
    return {'applicability': 'CONTRADICTED' if contradicted else 'UNKNOWN',
            'resourceKey': right, 'historicalResourceKey': left,
            'actor': 'msg.sender' if right == 'msg.sender' else None,
            'stateVersion': None, 'path': None,
            'reason': '资源归属键冲突' if contradicted else '可见资源键已对齐；路径和状态版本仍需当前程序证据' if left == right and left else '背景条件尚未绑定'}


def complementary_order(rows):
    """固定权重的贪心选择；差异覆盖只用于参考选择，不提升适用性等级。"""
    remaining, result, coverage = list(rows), [], set()
    while remaining:
        def marginal(row):
            features = set(row['features'])
            return row['score'] + 0.2 * len(features - coverage) - 0.2 * len(features & coverage)
        chosen = min(remaining, key=lambda row: (-marginal(row), row['pairId']))
        result.append({**chosen, 'marginalScore': marginal(chosen),
                       'newCoverage': sorted(set(chosen['features']) - coverage)})
        coverage.update(chosen['features'])
        remaining.remove(chosen)
    return result


def _features(before, after, mechanism):
    left = [event[2] for event in mechanism_events(before, mechanism)]
    right = [event[2] for event in mechanism_events(after, mechanism)]
    result = []
    if [e for e in left if e.startswith('GUARD')] != [e for e in right if e.startswith('GUARD')]:
        result.append('GUARD_CHANGE')
    if [e for e in left if e.startswith('MODIFIER')] != [e for e in right if e.startswith('MODIFIER')]:
        result.append('MODIFIER_CHANGE')
    if mechanism == 'REENTRANCY' and [e.split(':')[0] for e in left] != [e.split(':')[0] for e in right]:
        result.append('OPERATION_ORDER_CHANGE')
    return result or ['VISIBLE_MECHANISM_CHANGE']


def _build_cards(snapshot, catalog, snapshot_id):
    if catalog.get('snapshotId') != snapshot_id or set(catalog['cases']) != {d['id'] for d in snapshot['documents']}:
        raise ValueError('卡片目录与快照身份不符')
    docs = {d['id']: d for d in snapshot['documents']}
    origins = {s['id']: s for s in snapshot['manifest']['samples']}
    groups = {}
    for key, metadata in catalog['cases'].items():
        groups.setdefault(metadata['pairId'], []).append(key)
    cards, excluded = [], []
    for pair, keys in sorted(groups.items()):
        roles = {catalog['cases'][key]['role']: key for key in keys}
        if len(keys) != 2 or set(roles) != {'VULNERABLE', 'DEFENSE'}:
            excluded.append({'pairId': pair, 'reason': '配对不唯一'})
            continue
        ordered = [roles['VULNERABLE'], roles['DEFENSE']]
        metadata = catalog['cases'][ordered[0]]
        mechanism = metadata['mechanism']
        if mechanism not in ('REENTRANCY', 'ACCESS_CONTROL'):
            raise ValueError('卡片机制未登记')
        before, after = (docs[key]['text'] for key in ordered)
        sources = []
        for key in ordered:
            document = docs[key]
            origin = origins[document['sample_id']]
            if origin['split'] != 'knowledge' or catalog['cases'][key]['mechanism'] != mechanism:
                raise ValueError('卡片来源必须属于同机制知识划分')
            sources.append({'documentId': key, 'sampleId': origin['id'], 'origin': origin['origin'],
                            'sourceHash': origin['source_hash'], 'textHash': __import__('hashlib').sha256(document['text'].encode()).hexdigest(),
                            'events': [list(event) for event in mechanism_events(document['text'], mechanism)]})
        first, second = pair_snippets(before, after, mechanism)
        if not mechanism_changed(first, second, mechanism):
            excluded.append({'pairId': pair, 'reason': '未取得完整机制变化窗口'})
            continue
        cards.append({'schemaVersion': VERSION, 'cardId': pair + '@' + VERSION, 'pairId': pair,
            'mechanism': mechanism, 'sources': sources, 'sourceReview': 'SNAPSHOT_IDENTITY_CHECKED',
            'semanticReview': 'UNREVIEWED', 'generation': '确定性可见事件抽取；无模型调用',
            'reportHash': None, 'patchRevision': None, 'license': None, 'lineage': origins[docs[ordered[0]]['sample_id']]['project_group'],
            'background': {'resourceKey': _resource_key(before)},
            'purposeProxy': ' '.join(re.findall(r'\bfunction\s+([A-Za-z_$][\w$]*)', before)),
            'behavior': ' '.join(event[2] for event in mechanism_events(before, mechanism)),
            'afterBehavior': ' '.join(event[2] for event in mechanism_events(after, mechanism)),
            'features': _features(before, after, mechanism),
            'obligation': '检查同资源状态更新、所有回调入口及完整互斥范围' if mechanism == 'REENTRANCY' else '检查调用主体、权限来源、初始化与敏感入口的绕过路径',
            'alternatives': '同资源先更新或完整互斥锁须由当前程序证据核验' if mechanism == 'REENTRANCY' else '有效角色检查或等效权限委派须由当前程序证据核验',
            'limitations': '自动改动对不证明漏洞或修复有效；缺报告、补丁提交、许可和独立语义审核，不能正式研究准入'})
    payload = {'schemaVersion': VERSION, 'snapshotId': snapshot_id, 'catalogHash': fingerprint(catalog),
               'cards': cards, 'excluded': excluded, 'researchEligible': False}
    return {**payload, 'registryHash': fingerprint(payload)}


def verify_cards(registry, snapshot, catalog):
    expected = _build_cards(snapshot, catalog, fingerprint(snapshot))
    if registry != expected:
        raise ValueError('卡片内容、原件指针或身份不符；不得伪造语义审核')


def _render(card, binding):
    sources = ' / '.join(source['documentId'] for source in card['sources'])
    return (f"[机制卡片 {card['pairId']}｜未审核｜来源 {sources}]\n"
            f"可见差异：{','.join(card['features'])}；前侧事件节选：{card['behavior'][:220]}；后侧事件节选：{card['afterBehavior'][:220]}\n"
            f"保护义务：{card['obligation']}。替代保护：{card['alternatives']}。\n"
            f"绑定：{binding['reason']}；状态版本、路径：未知。\n"
            '局限：仅作取证线索，自动改动不证明修复有效；需在待审源码重新核对。\n')


class R3Retrieval:
    def __init__(self, store, snapshot_id, catalog):
        self.store, self.snapshot_id, self.catalog = store, snapshot_id, catalog
        self.snapshot = verify_snapshot(store, snapshot_id)
        self.registry = _build_cards(self.snapshot, catalog, snapshot_id)

    def select(self, view, strategy, *, allow_unreviewed=False, max_bytes=4096, max_pairs=2):
        if strategy not in STRATEGIES:
            raise ValueError('R3 策略未登记')
        verify_cards(self.registry, self.snapshot, self.catalog)
        if not allow_unreviewed:
            raise ValueError('卡片缺少独立语义审核；须显式选择工程探索模式')
        if view['snapshotId'] != self.snapshot_id:
            raise ValueError('卡片与查询快照不符')
        cards = {c['pairId']: c for c in self.registry['cards']}
        source_text = view['r3QueryText']
        background = {'resourceKey': _resource_key(source_text)}
        routes, scores, rejected, incremental = {}, {}, [], []
        if strategy in ('R3_CODE', 'R3_CARD'):
            candidates = view['pool']['candidates']
            order = list(dict.fromkeys(row['candidate']['pairId'] for row in view['d1']['selected']))
            pool = {**view['pool'], 'schemaVersion': 'r3-expression-1', 'registryHash': self.registry['registryHash']}
            selection = [{'pairId': pair, 'features': cards[pair]['features'] if pair in cards else [],
                          'score': 1 / (rank + 1)} for rank, pair in enumerate(order)]
        else:
            full = _recall_candidates(self.store, self.snapshot_id, self.catalog,
                view['r3QueryVector'], source_text, len(self.snapshot['rows']), None, view['sourceHash'], True)['pool']
            all_candidates = full['candidates']
            docs = {d['id']: d['text'] for d in self.snapshot['documents']}
            fulltexts = {pair: '\n'.join(docs[s['documentId']] for s in card['sources']) for pair, card in cards.items()}
            dense_documents = sorted(all_candidates, key=lambda c: (-c['denseScore'], c['chunkId']))[:80]
            routes['dense'] = list(dict.fromkeys(c['pairId'] for c in dense_documents if c['pairId'] in cards))
            routes['code'] = bm25(fulltexts, source_text, 10)
            routes['purpose'] = bm25({p: c['purposeProxy'] for p, c in cards.items()},
                ' '.join(re.findall(r'\bfunction\s+([A-Za-z_$][\w$]*)', source_text)), 10)
            routes['behavior'] = bm25({p: c['behavior'] for p, c in cards.items()},
                ' '.join(e[2] for e in mechanism_events(source_text, view['targetMechanism'])), 10)
            scores = reciprocal_fusion(routes)
            union = sorted(scores)
            incremental = sorted(set(union) - set(routes['dense']))
            candidates = [c for c in all_candidates if c['pairId'] in union]
            pool = {'schemaVersion': 'r3-union-1', 'snapshotId': self.snapshot_id,
                    'sourceHash': view['sourceHash'], 'registryHash': self.registry['registryHash'],
                    'queryHash': fingerprint({'text': source_text, 'vector': view['r3QueryVector']}),
                    'routes': routes, 'candidates': candidates}
            dense = {pair: max(c['denseScore'] for c in candidates if c['pairId'] == pair) for pair in union}
            ranking = sorted(union, key=lambda pair: (-(dense[pair] if strategy == 'R3_DENSE' else scores[pair]), pair))
            selection = []
            for rank, pair in enumerate(ranking):
                binding = bind_conditions(cards[pair]['background'], background)
                if cards[pair]['mechanism'] != view['targetMechanism'] or binding['applicability'] == 'CONTRADICTED':
                    rejected.append({'pairId': pair, 'reason': '机制或资源背景冲突'})
                else:
                    selection.append({'pairId': pair, 'features': cards[pair]['features'], 'score': 1 / (rank + 1)})
            selection = complementary_order(selection)
        by_pair = {}
        for candidate in candidates:
            by_pair.setdefault(candidate['pairId'], {})[candidate['role']] = candidate
        selected, parts, accepted, bindings, decisions = [], [], [], {}, []
        for item in selection:
            pair = item['pairId']
            card, roles = cards.get(pair), by_pair.get(pair, {})
            if card is None:
                rejected.append({'pairId': pair, 'reason': '缺失卡片；代码与卡片共同拒绝'})
                continue
            if set(roles) != {'VULNERABLE', 'DEFENSE'}:
                raise ValueError('消费时缺少完整原代码对')
            binding = bind_conditions(card['background'], background)
            code = ''.join(candidate_context(roles[role], True) for role in ('VULNERABLE', 'DEFENSE'))
            rendered = _render(card, binding)
            # 表达实验共同准入；超限整体拒绝，绝不裁剪语义或偷偷退回代码。
            material = code if strategy == 'R3_CODE' else rendered
            if len(accepted) >= max_pairs or len((''.join(parts) + material).encode()) > max_bytes:
                rejected.append({'pairId': pair, 'reason': '案例数或参考字节预算不足'})
                continue
            if strategy in ('R3_CODE', 'R3_CARD'):
                common = sum(max(len(entry['code'].encode()), len(entry['card'].encode())) for entry in decisions)
                if common + max(len(code.encode()), len(rendered.encode())) > max_bytes:
                    rejected.append({'pairId': pair, 'reason': '共同表达预算不足'})
                    continue
            accepted.append(pair)
            bindings[pair] = binding
            decisions.append({**item, 'code': code, 'card': rendered})
            selected.extend({'candidate': roles[role], 'use': 'SOFT_SUPPORT' if role == 'VULNERABLE' else 'SOFT_CONTRAST',
                             'binding': binding} for role in ('VULNERABLE', 'DEFENSE'))
            parts.append(material)
        context = ''.join(parts)
        receipt = {'version': VERSION, 'registryHash': self.registry['registryHash'],
            'representation': 'CODE' if strategy == 'R3_CODE' else 'CARD', 'selectedPairs': accepted,
            'cardCount': len(accepted), 'snippetCount': len(selected), 'bindings': bindings,
            'selection': [{k: v for k, v in d.items() if k not in ('code', 'card')} for d in decisions],
            'routes': routes, 'fusionScores': scores, 'independentAddedPairs': incremental,
            'rejected': rejected, 'contextHash': __import__('hashlib').sha256(context.encode()).hexdigest(),
            'contextBytes': len(context.encode()), 'referenceTokens': None,
            'exactTokenFairness': 'UNVERIFIED', 'allowUnreviewed': True, 'researchEligible': False}
        choice = {'status': 'COMPLETED', 'strategy': strategy, 'selected': selected, 'context': context,
                  'gaps': ['工程探索：卡片未独立审核；绑定不能替代 D2 证据'], 'evaluations': {},
                  'budgetKind': 'UTF8_BYTES', 'maxBytes': max_bytes}
        return {**view, 'pool': pool, 'poolHash': fingerprint(pool), 'd1': choice,
                'strategy': strategy, 'r3Receipt': receipt}
