"""自动标注 S1b 快照上的同池三策略与结构化模型审计适配。"""
from pathlib import Path
from time import monotonic

from audit_run import model_runner as default_model_runner
from d1_embed import DIMENSION
from formal_recall import CONTEXT_BYTES, java_retrieval, select_strategy
from program_facts import extract_facts
from recall import _recall_candidates
from snapshots import active_snapshot, vector32, verify_snapshot
from storage import decode, fingerprint


def interpret_model(model, mode):
    if mode != 'real' or model.get('status') != 'COMPLETED':
        return 'UNKNOWN'
    return {'VULNERABILITY_REPORTED': 'REPORT',
            'NO_CONFIRMED_FINDINGS': 'NO_REPORT'}.get(model.get('conclusion'), 'UNKNOWN')


def soft_without_risk(pool, mechanism):
    pairs = []
    for before in pool['candidates']:
        if before['role'] != 'VULNERABLE' or before['mechanism'] != mechanism:
            continue
        for after in pool['candidates']:
            if (after['role'] != 'DEFENSE' or after['pairId'] != before['pairId']
                    or after['mechanism'] != mechanism or after['text'] == before['text']):
                continue
            score = min(before['denseScore'], after['denseScore']) + .25 * abs(before['denseScore'] - after['denseScore'])
            pairs.append((score, before['chunkId'], before, after))
    pairs.sort(key=lambda item: (-item[0], item[1]))
    selected, context = [], ''
    for _, _, before, after in pairs:
        snippets = [(before, 'SOFT_SUPPORT'), (after, 'SOFT_CONTRAST')]
        candidate_context = ''.join(f"[{row['caseId']}/{row['chunkId']}|{row['role']}]\n{row['text']}\n"
                                    for row, _ in snippets)
        if len(candidate_context.encode()) <= CONTEXT_BYTES:
            selected = [{'candidate': row, 'use': use, 'binding': {'applicability': 'UNKNOWN'}}
                        for row, use in snippets]
            context = candidate_context
            break
    evaluations = {row['chunkId']: {'applicability': 'SUPPORTED' if row['mechanism'] == mechanism
                   and row['conditions'] else 'UNKNOWN'} for row in pool['candidates']}
    return {'status': 'COMPLETED', 'selected': selected, 'context': context,
            'gaps': ['无唯一风险事实；使用自动标注软配对，不宣称防护适用性'],
            'evaluations': evaluations}


def _risk_fact(facts, target):
    if facts['status'] == 'FAILED':
        return None
    kinds = {'CALL'} if target['mechanism'] == 'REENTRANCY' else {'CALL', 'WRITE'}
    matches = [row for row in facts['facts'] if row['kind'] in kinds
               and row['line'] in target['vulnerableLines']
               and target['function'] in row['scope']]
    return matches[0] if len(matches) == 1 else None


class BenchmarkRuntime:
    def __init__(self, root, index, encoder, model_runner=default_model_runner, java_runner=None):
        self.root = Path(root).resolve()
        self.index = index
        self.encoder = encoder
        self.model_runner = model_runner
        self.java_runner = java_runner or (lambda source, request: java_retrieval(self.root, source, request))
        self.store = self.root / '.local/d1-kb-snapshots'
        self.pointer = active_snapshot(self.store, index)
        self.snapshot = verify_snapshot(self.store, self.pointer['snapshot_id'])
        if not all(row['review_status'] == 'AUTO_LABELED' for row in self.snapshot['manifest']['samples']):
            raise ValueError('当前活动快照不是自动标注知识层')
        self.catalog = decode((self.store / 'catalogs' / (self.pointer['snapshot_id'] + '.json')).read_bytes())
        self.views = {}

    def preview(self, target):
        key = target['sampleId']
        if key in self.views:
            return self.views[key]
        if decode((self.store / 'active.json').read_bytes()) != self.pointer:
            raise ValueError('批量过程中活动知识快照已改变')
        vector = self.encoder([target['modelSource']])
        if len(vector) != 1:
            raise ValueError('查询向量数量无效')
        query = vector32([float(value) for value in vector[0]], DIMENSION)
        recalled = _recall_candidates(self.store, self.pointer['snapshot_id'], self.catalog,
            query, target['modelSource'], min(80, len(self.snapshot['rows'])),
            lambda value, limit: self.index.search(self.pointer['collection'], value, limit),
            target['sourceHash'], True)
        pool = recalled['pool']
        facts = extract_facts(target['fullSource'])
        risk = _risk_fact(facts, target)
        if risk is None:
            d1 = soft_without_risk(pool, target['mechanism'])
        else:
            resource = risk['resource'] if risk['kind'] == 'WRITE' else 'owner'
            request = {'target': {'mechanism': target['mechanism'], 'riskFactId': risk['id'],
                       'bindings': {'actor': 'msg.sender', 'resource': resource, 'authority': resource}},
                       'pool': pool, 'budget': {'maxBytes': CONTEXT_BYTES, 'maxCases': 4}}
            response = self.java_runner(target['fullSource'], request)
            results = response.get('results') if isinstance(response, dict) else None
            if (not isinstance(results, list) or len(results) != 1 or results[0].get('strategy') != 'D1'
                    or results[0].get('sourceHash') != target['sourceHash']
                    or results[0].get('snapshotId') != self.pointer['snapshot_id']):
                raise ValueError('Java D1 返回的源码或快照身份无效')
            d1 = results[0]
        view = {'pool': pool, 'd1': d1, 'snapshotId': self.pointer['snapshot_id'],
                'collection': self.pointer['collection'], 'sourceHash': target['sourceHash'],
                'targetMechanism': target['mechanism'], 'facts': facts, 'researchEligible': False}
        self.views[key] = view
        return view

    def run(self, target, strategy, mode):
        view = select_strategy(self.preview(target), strategy)
        selected = view['d1'].get('selected', [])
        started = monotonic()
        model = self.model_runner(self.root, target, view, mode)
        duration = round((monotonic() - started) * 1000)
        if not isinstance(model, dict) or model.get('status') not in ('COMPLETED', 'FAILED'):
            raise ValueError('结构化模型结果无效')
        model = {key: value for key, value in model.items() if key != '_rawResponse'}
        return {'status': model['status'], 'prediction': interpret_model(model, mode),
                'poolHash': fingerprint(view['pool']),
                'selectedIds': [row['candidate']['chunkId'] for row in selected],
                'selectedEvidence': len(selected),
                'categoryHit': (any(row['candidate']['mechanism'] == target['mechanism'] for row in selected)
                                if target['groundTruth']['hasVulnerability'] else None),
                'retrievalGaps': view['d1'].get('gaps', []),
                'errorCategory': model.get('errorCategory'),
                'inputTokens': model.get('inputTokens'), 'outputTokens': model.get('outputTokens'),
                'durationMs': duration, 'model': model}
