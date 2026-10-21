"""D1 来源、上下文消费与预算准入的失败边界。"""
import copy
import hashlib
import unittest

from verirag.retrieval.d1_consumption import candidate_context, pair_snippets
from verirag.evaluation.d1_research_check import inspect_consumption, inspect_bindings, inspect_pair_sources, build_protocol


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def fixture():
    before = 'contract C { function f() public { owner = msg.sender; } }'
    after = 'contract C { function f() public { require(msg.sender == owner); owner = msg.sender; } }'
    source = {'id': 'k', 'source_hash': sha(before), 'origin': 'https://example.test/commit/123@revision',
              'project_group': 'project', 'review_status': 'AUTO_LABELED', 'split': 'knowledge'}
    docs, cases, selected = [], {}, []
    for (role, text), window in zip((('VULNERABLE', before), ('DEFENSE', after)),
                                   pair_snippets(before, after, 'ACCESS_CONTROL')):
        key = 'k_' + role
        docs.append({'id': key, 'sample_id': 'k', 'text': text})
        meta = {'caseId': key, 'pairId': 'k', 'role': role, 'mechanism': 'ACCESS_CONTROL',
                'riskKind': 'WRITE', 'conditions': [], 'reviewed': False}
        cases[key] = meta
        candidate = {**meta, 'chunkId': key, 'text': window, 'denseScore': .8,
                     'provenance': source['origin'] + '@' + source['source_hash']}
        selected.append({'candidate': candidate, 'use': 'SOFT_SUPPORT' if role == 'VULNERABLE' else 'SOFT_CONTRAST',
                         'binding': {'applicability': 'UNKNOWN', 'conditions': []}})
    context = ''.join(candidate_context(x['candidate']) for x in selected)
    choice = {'selected': selected, 'context': context, 'usedBytes': len(context.encode()),
              'evaluations': {x['candidate']['chunkId']: x['binding'] for x in selected}}
    row = {'sampleId': 'target', 'strategy': 'D1', 'sourceHash': sha('target'), 'source': 'target',
           'selectedIds': [x['candidate']['chunkId'] for x in selected], 'model': {},
           'retrieval': {'pool': {'schemaVersion': 'auto-1', 'candidates': [x['candidate'] for x in selected]},
                         'd1': choice, 'modelSourceHash': sha('target')}}
    snapshot = {'manifest': {'samples': [source]}, 'documents': docs}
    return row, snapshot, {'cases': cases}


class D1ResearchCheckTest(unittest.TestCase):
    def test_展示文本可回算也不能代替最终API请求回执(self):
        row, _, _ = fixture()
        result = inspect_consumption(row)
        self.assertEqual('VERIFIED', result['contextStatus'])
        self.assertEqual('UNVERIFIED', result['requestStatus'])
        self.assertFalse(result['actualRequestVerified'])

    def test_上下文丢片段或伪造字节数均失败(self):
        row, _, _ = fixture()
        for field, value in (('context', '仅一侧'), ('usedBytes', 1)):
            changed = copy.deepcopy(row)
            changed['retrieval']['d1'][field] = value
            self.assertEqual('FAILED', inspect_consumption(changed)['contextStatus'])

    def test_最终消费回执绑定有序证据与源码及上下文(self):
        row, _, _ = fixture()
        receipt = {'schemaVersion': 'request-consumption-1', 'sourceHash': row['sourceHash'],
                   'modelSourceHash': row['retrieval']['modelSourceHash'],
                   'contextSha256': sha(row['retrieval']['d1']['context']), 'evidenceIds': row['selectedIds'],
                   'systemPromptSha256': sha('system'), 'userPromptSha256': sha('user'),
                   'systemPromptBytes': 6, 'userPromptBytes': 4, 'promptTemplateVersion': 'fixture-v1',
                   'messageOrder': ['system', 'user'], 'tokenizer': None,
                   'inputTokens': None, 'outputTokens': None}
        row['model']['requestConsumptionReceipt'] = receipt
        self.assertTrue(inspect_consumption(row)['actualRequestVerified'])
        receipt['evidenceIds'] = list(reversed(receipt['evidenceIds']))
        self.assertEqual('FAILED', inspect_consumption(row)['requestStatus'])

    def test_自动池的支持或条件伪装会阻断准入(self):
        row, _, _ = fixture()
        view = row['retrieval']
        self.assertTrue(inspect_bindings(view)['passed'])
        view['d1']['selected'][0]['binding']['applicability'] = 'SUPPORTED'
        result = inspect_bindings(view)
        self.assertFalse(result['passed'])
        self.assertIn('AUTO_BINDING_NOT_UNKNOWN', [x['kind'] for x in result['issues']])

    def test_正式路径引用不存在或过晚事实不能支持条件(self):
        row, _, _ = fixture()
        view = row['retrieval']
        view['pool']['schemaVersion'] = '1'
        view['facts'] = {'scopes': [{'id': 'f', 'complete': True}], 'facts': [
            {'id': 'risk', 'scope': 'f', 'kind': 'WRITE', 'order': 3},
            {'id': 'late', 'scope': 'f', 'kind': 'CHECK', 'order': 4}]}
        view['d1']['target'] = {'riskFactId': 'risk'}
        condition = {'predicate': 'CHECK_BEFORE', 'subject': '$actor', 'resource': '$authority', 'expected': True}
        selection = view['d1']['selected'][0]
        selection['candidate']['conditions'] = [condition]
        selection['binding'] = {'applicability': 'SUPPORTED', 'conditions': [
            {'condition': condition, 'subject': 'msg.sender', 'resource': 'owner', 'state': 'SUPPORTED',
             'evidence': ['late'], 'reason': '错误的过晚条件'}]}
        view['d1']['evaluations'][selection['candidate']['chunkId']] = selection['binding']
        result = inspect_bindings(view)
        self.assertFalse(result['passed'])
        self.assertIn('CONDITION_EVIDENCE_OUTSIDE_PRECONDITION', [x['kind'] for x in result['issues']])

    def test_源全文与窗口摘要可核但自动来源仍不是人工真值(self):
        row, snapshot, catalog = fixture()
        result = inspect_pair_sources(snapshot, catalog, [row])
        self.assertTrue(result['passed'])
        self.assertEqual(1, result['selectedPairs'])
        self.assertEqual('PENDING', result['pairs'][0]['humanReview']['status'])
        row['retrieval']['pool']['candidates'][0]['provenance'] = '伪造来源'
        self.assertFalse(inspect_pair_sources(snapshot, catalog, [row])['passed'])

    def test_形式绑定引用主体资源错配与伪造前置证据均拒绝(self):
        row, _, _ = fixture()
        view = row['retrieval']
        view['pool']['schemaVersion'] = '1'
        condition = {'predicate': 'CHECK_BEFORE', 'subject': '$actor', 'resource': '$authority', 'expected': True}
        selected = view['d1']['selected'][0]
        selected['candidate']['conditions'] = [condition]
        selected['binding'] = {'applicability': 'SUPPORTED', 'conditions': [
            {'condition': condition, 'subject': 'msg.sender', 'resource': 'owner', 'state': 'SUPPORTED',
             'evidence': ['guard'], 'reason': '夹具'}]}
        view['d1']['evaluations'][selected['candidate']['chunkId']] = selected['binding']
        view['facts'] = {'scopes': [{'id': 'f', 'complete': True}], 'facts': [
            {'id': 'risk', 'scope': 'f', 'kind': 'WRITE', 'order': 3},
            {'id': 'guard', 'scope': 'f', 'kind': 'CHECK', 'order': 2, 'subject': 'other', 'resource': 'owner'}]}
        view['d1']['target'] = {'riskFactId': 'risk'}
        result = inspect_bindings(view)
        self.assertIn('CONDITION_EVIDENCE_BINDING_MISMATCH', [x['kind'] for x in result['issues']])
        selected['binding']['conditions'][0]['evidence'] = []
        result = inspect_bindings(view)
        self.assertIn('OBSERVED_CONDITION_WITHOUT_EVIDENCE', [x['kind'] for x in result['issues']])

    def test_预算包括完整组件未知token及价格保持空值(self):
        plan = {'snapshotId': 'a' * 64, 'sampleIds': ['s1', 's2'],
                'provider': {'model': 'fixture', 'endpoint': 'https://example.test/v1'}}
        protocol = build_protocol(plan)
        self.assertEqual(['VANILLA', 'DENSE', 'D1', 'PAIRED_ONLY', 'D1_NO_CONDITIONS', 'D1_NO_REPAIR'],
                         [row['id'] for row in protocol['arms']])
        budget = protocol['budget']
        self.assertEqual({'system', 'source', 'context', 'messageOverhead', 'output'}, set(budget['components']))
        self.assertIsNone(budget['tokenizer'])
        self.assertIsNone(budget['fullPromptInputTokenCap'])
        self.assertIsNone(budget['maxInputTokens'])
        self.assertIsNone(budget['estimatedAmount'])
        self.assertFalse(protocol['formalAdmission']['passed'])
        self.assertEqual(36, budget['maxRequests'])

    def test_假token计数和隐藏重试不可混入正式预算(self):
        plan = {'snapshotId': 'a' * 64, 'sampleIds': ['s1'], 'provider': {}}
        with self.assertRaisesRegex(ValueError, 'tokenizer'):
            build_protocol(plan, tokenizer={'name': 'codepoint', 'revision': '1', 'source': '字符数量'},
                           input_token_cap=100)
        with self.assertRaisesRegex(ValueError, '重试'):
            build_protocol(plan, retries=-1)


if __name__ == '__main__':
    unittest.main()
