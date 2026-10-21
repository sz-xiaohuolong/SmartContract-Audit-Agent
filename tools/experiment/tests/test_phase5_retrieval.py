"""对照查询和同池重排的离线契约；合成事实不充当研究结论。"""
import copy
import unittest

from storage import fingerprint
import test_access_call_proofs as access
import test_reentrancy_proofs as reentry


def config():
    return {'templateVersion': 'phase5-query-1', 'maxOperations': 32, 'maxContrasts': 3,
            'dimensions': ['ACTOR', 'ORDER']}


def scoring_config():
    return {'identity': {'model': '固定向量夹具', 'revision': '1', 'dimension': 2,
                         'weightsHash': 'a' * 64},
            'queryPrefix': '', 'documentPrefix': '', 'maxInputTokens': 512}


class FixedEncoder:
    def __init__(self, vectors):
        self.vectors = vectors
        self.identity = scoring_config()['identity']

    def __call__(self, texts):
        return {'identity': self.identity, 'vectors': self.vectors,
                'tokenCounts': [10] * len(texts), 'truncated': [False] * len(texts)}


def query():
    return {'operationKey': '操作一', 'structureStatus': 'VALID', 'independentReview': 'UNREVIEWED',
            'original': '原问题', 'contrasts': [{'text': '主体对照', 'dimension': 'ACTOR'},
                                          {'text': '顺序对照', 'dimension': 'ORDER'}],
            'sourceHash': 'b' * 64, 'receiptDigest': 'c' * 64,
            'mechanism': 'REENTRANCY', 'resourceKey': 'msg.sender'}


def evidence():
    return [{'pairId': key, 'text': '改动前\n' + key + '\n改动后', 'context': key * 6,
             'beforeId': key + '-前', 'afterId': key + '-后', 'mechanism': 'REENTRANCY',
             'background': {'resourceKey': 'msg.sender'}} for key in ('a', 'b')]


class Phase5RetrievalTest(unittest.TestCase):
    def access_bundle(self):
        helper = access.AccessCallProofTest(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        owner = next(n for n in helper.contract['nodes'] if n.get('id') == 2)
        condition = helper.node('BinaryOperation', operator='==', leftExpression=helper.sender(),
                                rightExpression=helper.state_read(owner))
        helper.function['body']['statements'] = [helper.require(condition), helper.statement(helper.call)]
        helper.fixture.seal()
        return helper, helper.fixture.load()

    def build(self, bundle, mechanism='ACCESS_CONTROL', **options):
        from phase5_retrieval import build_queries
        return build_queries(bundle, {'sourceHash': bundle['sourceHash'],
            'receiptDigest': bundle['receiptDigest'], 'mechanism': mechanism}, {**config(), **options})

    def test_主体对照仅改变一个维度且保留事实与入口(self):
        _, bundle = self.access_bundle()
        result = self.build(bundle)
        valid = [q for q in result['queries'] if q['structureStatus'] == 'VALID']
        self.assertEqual(1, len(valid))
        row = valid[0]
        self.assertEqual('UNREVIEWED', row['independentReview'])
        self.assertEqual(row['original'].replace('msg.sender', 'tx.origin'), row['contrasts'][0]['text'])
        self.assertEqual('ACTOR', row['contrasts'][0]['dimension'])
        self.assertTrue(row['references'])
        self.assertEqual(bundle['receiptDigest'], row['receiptDigest'])
        self.assertIn('entry', row)

    def test_错编译身份伪造绑定和标签输入均拒绝(self):
        from phase5_retrieval import build_queries
        _, bundle = self.access_bundle()
        binding = {'sourceHash': bundle['sourceHash'], 'receiptDigest': bundle['receiptDigest'], 'mechanism': 'ACCESS_CONTROL'}
        for extra in ({'groundTruth': True}, {'sampleId': 'safe'}, {'riskFactId': '伪造'}, {'receiptDigest': '错收据'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                build_queries(bundle, {**binding, **extra}, config())
        bundle['verificationStatus'] = 'UNVERIFIED'
        with self.assertRaises(ValueError):
            self.build(bundle)

    def test_无主体绑定不生成看似有效查询(self):
        helper, _ = self.access_bundle()
        helper.function['body']['statements'] = [helper.statement(helper.call)]
        helper.fixture.seal()
        result = self.build(helper.fixture.load())
        self.assertTrue(result['queries'])
        self.assertTrue(all(q['structureStatus'] == 'UNSUPPORTED' for q in result['queries']))
        self.assertTrue(all(q['reason'] for q in result['queries']))

    def test_tx_origin检查也能生成对称主体对照(self):
        helper, _ = self.access_bundle()
        condition = helper.function['body']['statements'][0]['expression']['arguments'][0]
        condition['leftExpression'] = helper.node('MemberAccess', memberName='origin',
            typeDescriptions={'typeIdentifier': 't_address'}, expression=helper.node('Identifier', name='tx',
            referencedDeclaration=-26, typeDescriptions={'typeIdentifier': 't_magic_transaction'}))
        helper.fixture.seal()
        rows = self.build(helper.fixture.load())['queries']
        self.assertEqual(1, sum(q['structureStatus'] == 'VALID' for q in rows))
        self.assertIn('tx.origin', rows[0]['original'])
        self.assertIn('msg.sender', rows[0]['contrasts'][0]['text'])

    def test_所有同行操作均登记且目标总预算不静默丢弃(self):
        helper, _ = self.access_bundle()
        helper.function['body']['statements'] += [helper.statement(helper.terminal())]
        helper.fixture.seal(); bundle = helper.fixture.load()
        result = self.build(bundle, maxOperations=1)
        self.assertEqual(2, result['plannedOperations'])
        self.assertEqual(2, len(result['queries']))
        self.assertEqual(1, sum(q.get('reason') == 'TARGET_QUERY_BUDGET' for q in result['queries']))
        self.assertEqual(2, len({q['operationKey'] for q in result['queries']}))
        reordered = dict(bundle, functions=dict(reversed(list(bundle['functions'].items()))))
        self.assertEqual(result, self.build(reordered, maxOperations=1))

    def test_重入同一余额写入前后可分别构造对照(self):
        helper = reentry.ReentrancyProofTest(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        for statements, word in (([helper.guard, helper.statement(helper.call), helper.write], '之后'),
                                 ([helper.guard, helper.write, helper.statement(helper.call)], '之前')):
            helper.fixture.function()['body']['statements'] = statements
            helper.fixture.seal()
            result = self.build(helper.fixture.load(), 'REENTRANCY')
            valid = [q for q in result['queries'] if q['structureStatus'] == 'VALID']
            self.assertEqual(1, len(valid))
            self.assertIn(word, valid[0]['original'])
            self.assertEqual('ORDER', valid[0]['contrasts'][0]['dimension'])

    def test_共享内部操作按每次调用上下文分别登记(self):
        helper, _ = self.access_bundle()
        internal = helper.node('FunctionDefinition', name='work', kind='function', implemented=True,
            visibility='internal', stateMutability='nonpayable', modifiers=[],
            parameters=helper.node('ParameterList', parameters=[]), returnParameters=helper.node('ParameterList', parameters=[]),
            body=helper.node('Block', statements=[helper.statement(helper.call)]))
        helper.contract['nodes'].append(internal)
        def invocation():
            return helper.statement(helper.node('FunctionCall', kind='functionCall', arguments=[], expression=helper.node(
                'Identifier', name='work', referencedDeclaration=internal['id'],
                typeDescriptions={'typeIdentifier': 't_function_internal_nonpayable$__$returns$__$'})))
        guard = helper.function['body']['statements'][0]
        helper.function['body']['statements'] = [guard, invocation(), invocation()]
        helper.fixture.seal()
        result = self.build(helper.fixture.load())
        valid = [q for q in result['queries'] if q['structureStatus'] == 'VALID']
        self.assertEqual(2, len(valid))
        self.assertEqual(1, len({q['factId'] for q in valid}))
        self.assertEqual(2, len({q['operationKey'] for q in valid}))
        self.assertNotEqual(valid[0]['context'], valid[1]['context'])

    def test_查询写盘回读保持相同JSON字段类型(self):
        from storage import decode, encode
        helper = reentry.ReentrancyProofTest(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        helper.fixture.seal()
        result = self.build(helper.fixture.load(), 'REENTRANCY')
        self.assertEqual(result, decode(encode(result)))

    def test_仅有汇编的其他入口不能从覆盖分母消失(self):
        helper, _ = self.access_bundle()
        other = helper.syntax.fresh(helper.function)
        other['name'] = 'unparsed'; other['body']['statements'] = [helper.node('InlineAssembly')]
        helper.contract['nodes'].append(other)
        helper.fixture.output['contracts']['contracts/C.sol']['C']['abi'].append(
            {'type': 'function', 'name': 'unparsed', 'inputs': [], 'outputs': [], 'stateMutability': 'nonpayable'})
        helper.fixture.seal()
        result = self.build(helper.fixture.load())
        self.assertTrue(any(gap.get('entry', {}).get('signature') == 'unparsed()' for gap in result['entryGaps']))

    def test_固定干扰档位能分别重算两种排序(self):
        from phase5_retrieval import score_pool, rank_pool
        q = query(); q['contrasts'] = q['contrasts'][:1]
        for level in (0, 1, 2, 4):
            rows = [evidence()[0]]
            for index in range(level):
                rows.append({**evidence()[1], 'pairId': f'd{index}', 'beforeId': f'd{index}-前',
                    'afterId': f'd{index}-后', 'text': f'另一来源的表面相似材料{index}', 'context': f'干扰材料{index}'})
            scored = score_pool(q, rows, FixedEncoder([[1, 0], [0.8, 0.6], [0.8, -0.6]] + [[1, 0]] * level), scoring_config())
            pool = {'evidence': rows, 'poolHash': fingerprint(rows)}
            margin = rank_pool(pool, scored, 'P5_MARGIN', {'maxPairs': 1, 'maxBytes': 4096})
            relevance = rank_pool(pool, scored, 'P5_RELEVANCE', {'maxPairs': 1, 'maxBytes': 4096})
            self.assertEqual(['a'], margin['selectedPairs'])
            self.assertEqual(['d0'] if level else ['a'], relevance['selectedPairs'])
            self.assertEqual(level + 1, len(margin['ranking']))

    def test_逐材料最大差值保留负值且不先求均值(self):
        from phase5_retrieval import score_pool
        # 原查询与两条对照分别沿 x、y、负 y 轴，两份材料分别沿 x、y。
        result = score_pool(query(), evidence(), FixedEncoder([[1, 0], [0, 1], [0, -1], [1, 0], [0, 1]]), scoring_config())
        self.assertEqual('SCORED', result['status'])
        self.assertAlmostEqual(1, result['scores'][0]['margin'])
        self.assertAlmostEqual(-1, result['scores'][1]['margin'])
        self.assertEqual([1, -1], result['scores'][1]['contrastScores'])
        self.assertIn('vectors', result)

    def test_异常向量和截断使整个比较单元失败(self):
        from phase5_retrieval import score_pool
        for vector in ([0, 0], [float('nan'), 0], [1], [True, 0]):
            encoder = FixedEncoder([[1, 0], [0, 1], [0, -1], [1, 0], vector])
            result = score_pool(query(), evidence(), encoder, scoring_config())
            self.assertEqual('FAILED', result['status'])
            self.assertEqual([], result['scores'])
            self.assertTrue(result['errors'])
        def truncated(texts):
            value = FixedEncoder([[1, 0]] * len(texts))(texts)
            value['truncated'][-1] = True
            return value
        self.assertEqual('FAILED', score_pool(query(), evidence(), truncated, scoring_config())['status'])

    def test_评分器身份漂移拒绝且无对照差值为空(self):
        from phase5_retrieval import score_pool
        encoder = FixedEncoder([[1, 0]] * 5)
        encoder.identity = {**encoder.identity, 'revision': '漂移'}
        self.assertEqual('FAILED', score_pool(query(), evidence(), encoder, scoring_config())['status'])
        q = query(); q['contrasts'] = []
        result = score_pool(q, evidence(), lambda texts: self.fail('无对照不能调用编码'), scoring_config())
        self.assertEqual('NOT_SCORABLE', result['status'])
        self.assertIsNone(result['margin'])

    def scores(self):
        from phase5_retrieval import score_pool
        return score_pool(query(), evidence(), FixedEncoder([[1, 0], [0, 1], [0, -1], [1, 0], [0, 1]]), scoring_config())

    def test_同池只换排序键且预算拒绝整对(self):
        from phase5_retrieval import rank_pool
        pool = {'evidence': evidence(), 'poolHash': fingerprint(evidence())}
        scores = self.scores()
        scores['scores'][0].update(originalScore=0.9, margin=-0.9)
        scores['scores'][1].update(originalScore=0.8, margin=-0.2)
        for condition, expected in (('P5_RELEVANCE', ['a']), ('P5_MARGIN', ['b'])):
            result = rank_pool(pool, scores, condition, {'maxPairs': 1, 'maxBytes': 6})
            self.assertEqual(expected, result['selectedPairs'])
            self.assertEqual(1, len(result['rejected']))
            self.assertEqual(6, result['contextBytes'])
            self.assertEqual(2, len(result['ranking']))
            self.assertEqual(2, len(result['selectedEvidenceIds']))
        self.assertEqual([], rank_pool(pool, scores, 'P5_MARGIN', {'maxPairs': 1, 'maxBytes': 1})['selectedPairs'])

    def test_同分按ID稳定且重复完整材料不挤占预算(self):
        from phase5_retrieval import rank_pool
        rows = evidence(); rows[1]['text'] = rows[0]['text']
        scores = self.scores(); scores['evidenceHash'] = fingerprint(rows)
        for row in scores['scores']:
            row.update(originalScore=0, margin=0)
        result = rank_pool({'evidence': rows, 'poolHash': fingerprint(rows)}, scores, 'P5_MARGIN', {'maxPairs': 2, 'maxBytes': 100})
        self.assertEqual(['a'], result['selectedPairs'])
        self.assertEqual('DUPLICATE_MATERIAL', result['rejected'][0]['reason'])

    def test_错池和不完整评分不能继续排名(self):
        from phase5_retrieval import rank_pool
        for change in ('hash', 'missing'):
            scores = self.scores()
            if change == 'hash': scores['evidenceHash'] = '错池'
            else: scores['scores'].pop()
            with self.assertRaises(ValueError):
                rank_pool({'evidence': evidence(), 'poolHash': fingerprint(evidence())}, scores,
                          'P5_MARGIN', {'maxPairs': 2, 'maxBytes': 4096})

    def test_机制和资源冲突在两种排序共同过滤(self):
        from phase5_retrieval import score_pool, rank_pool
        rows = evidence(); rows[0]['mechanism'] = 'ACCESS_CONTROL'
        rows[1]['background']['resourceKey'] = 'tx.origin'
        scores = score_pool(query(), rows, FixedEncoder([[1, 0]] * 5), scoring_config())
        for condition in ('P5_RELEVANCE', 'P5_MARGIN'):
            result = rank_pool({'evidence': rows, 'poolHash': fingerprint(rows)}, scores, condition,
                               {'maxPairs': 2, 'maxBytes': 4096})
            self.assertEqual([], result['selectedPairs'])
            self.assertEqual({'MECHANISM_CONFLICT', 'RESOURCE_CONFLICT'}, {r['reason'] for r in result['rejected']})

    def test_冻结池核对快照文本且拒绝半对与重复候选(self):
        from tempfile import TemporaryDirectory
        from test_r3_retrieval import R3RetrievalTest
        from phase5_retrieval import freeze_pool
        with TemporaryDirectory() as directory:
            runtime, target = R3RetrievalTest().setup_runtime(directory)
            view = runtime.r3.select(runtime.preview(target), 'R3_FUSION', allow_unreviewed=True)
            pool = freeze_pool(view, runtime.snapshot, runtime.catalog)
            self.assertTrue(pool['evidence'])
            self.assertIn('改动前', pool['evidence'][0]['text'])
            for kind in ('half', 'repeat', 'text', 'snapshot'):
                changed = copy.deepcopy(view)
                if kind == 'half': changed['pool']['candidates'].pop()
                elif kind == 'repeat': changed['pool']['candidates'].append(changed['pool']['candidates'][0])
                elif kind == 'text': changed['pool']['candidates'][0]['text'] += '伪造'
                else: changed['snapshotId'] = '0' * 64
                changed['poolHash'] = fingerprint(changed['pool'])
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    freeze_pool(changed, runtime.snapshot, runtime.catalog)


if __name__ == '__main__':
    unittest.main()
