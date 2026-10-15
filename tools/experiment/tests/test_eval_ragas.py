"""检索评估的身份、分母与标注隔离回归。"""
import copy
import hashlib
import math
import gzip
import tempfile
import unittest
from pathlib import Path

from storage import fingerprint
from eval_ragas import normalize_row, rank_metrics, evaluate_offline, qrels_template, seal, validate_dataset, prepare_dataset


def sample(strategy='D1'):
    source = 'contract C { function withdraw() public {} }'
    sha = hashlib.sha256(source.encode()).hexdigest()
    candidates = [{'chunkId': key, 'caseId': key, 'text': text, 'pairId': 'pair',
                   'mechanism': 'REENTRANCY', 'role': 'VULNERABLE'}
                  for key, text in [('a', '付款后扣余额'), ('b', '先扣余额再付款'), ('c', '无关函数')]]
    pool = {'candidates': candidates}
    selected = [] if strategy == 'VANILLA' else [{'candidate': c} for c in candidates[:2]]
    context = '' if not selected else '[a/a|改动前·未审核]\n付款后扣余额\n[b/b|改动后·未审核]\n先扣余额再付款\n'
    return {'sampleId': 'target', 'strategy': strategy, 'source': source, 'sourceHash': sha,
            'snapshotId': 'f' * 64, 'poolHash': fingerprint(pool), 'status': 'COMPLETED',
            'retrieval': {'pool': pool, 'modelSourceHash': sha, 'targetMechanism': 'REENTRANCY',
                          'd1': {'selected': selected, 'context': context}},
            'model': {'status': 'COMPLETED', 'conclusion': 'VULNERABILITY_REPORTED',
                      'hypotheses': [{'function': 'withdraw', 'riskLine': 1, 'riskOperation': 'CALL',
                                      'reason': '付款后扣余额'}],
                      'requestConsumptionReceipt': {'schemaVersion': 'request-consumption-1', 'sourceHash': sha, 'modelSourceHash': sha,
                          'contextSha256': hashlib.sha256(context.encode()).hexdigest(),
                          'evidenceIds': [x['candidate']['chunkId'] for x in selected]}}}


def dataset(rows=None):
    return seal({'schemaVersion': 'rag-evaluation-1', 'rows': rows or [normalize_row(sample())],
                 'origin': {'batchId': 'e' * 32, 'mode': 'real'}})


class RagasEvaluationTest(unittest.TestCase):
    def test_保留真正消费的片段顺序且不从标签合成答案(self):
        raw = sample()
        raw['groundTruth'] = {'reason': '不得泄漏的真值'}
        row = normalize_row(raw)
        self.assertEqual(['a', 'b'], row['retrieved_context_ids'])
        self.assertEqual('[a/a|改动前·未审核]\n付款后扣余额\n', row['retrieved_contexts'][0])
        self.assertNotIn('不得泄漏的真值', str(row))
        self.assertNotIn('reference', row)

    def test_源码或上下文或候选池被修改时阻止评分(self):
        for change in ('source', 'context', 'pool', 'ids'):
            with self.subTest(change=change):
                raw = sample()
                if change == 'source': raw['source'] += '// 改动'
                if change == 'context': raw['retrieval']['d1']['context'] += '伪造'
                if change == 'pool': raw['retrieval']['pool']['candidates'].pop()
                if change == 'ids': raw['model']['requestConsumptionReceipt']['evidenceIds'] = ['a']
                self.assertEqual('INVALID_INPUT', normalize_row(raw)['inputStatus'])

    def test_无检索不是检索失败且模型失败不生成安全回答(self):
        row = normalize_row(sample('VANILLA'))
        self.assertEqual('READY', row['inputStatus'])
        self.assertEqual([], row['retrieved_contexts'])
        raw = sample(); raw['model']['status'] = 'FAILED'; raw['status'] = 'FAILED'
        self.assertIsNone(normalize_row(raw)['response'])
        raw = {'sampleId': 'missing', 'strategy': 'D1', 'status': 'FAILED'}
        self.assertEqual('MISSING_INPUT', normalize_row(raw)['inputStatus'])

    def test_相同片段ID不能借用另一份正文的人工等级(self):
        raw = sample()
        choice = raw['retrieval']['d1']
        choice['context'] = choice['context'].replace('付款后扣余额', '完全不相关的广告')
        raw['model']['requestConsumptionReceipt']['contextSha256'] = hashlib.sha256(choice['context'].encode()).hexdigest()
        self.assertEqual('INVALID_INPUT', normalize_row(raw)['inputStatus'])
        raw = sample()
        raw['retrieval']['d1']['selected'][0]['candidate'] = dict(raw['retrieval']['d1']['selected'][0]['candidate'], text='另一份正文')
        self.assertEqual('INVALID_INPUT', normalize_row(raw)['inputStatus'])

    def test_内外层快照或源码身份冲突时拒绝(self):
        for container, key in [('retrieval', 'sourceHash'), ('pool', 'snapshotId'), ('d1', 'snapshotId')]:
            with self.subTest(container=container):
                raw = sample(); view = raw['retrieval']
                (view if container == 'retrieval' else view[container])[key] = '0' * 64
                raw['poolHash'] = fingerprint(view['pool'])
                self.assertEqual('INVALID_INPUT', normalize_row(raw)['inputStatus'])

    def test_损坏模型结构和未知收据版本保留单元失败(self):
        for key in ('model', 'retrieval'):
            raw = sample(); raw[key] = ['损坏记录']
            self.assertEqual('INVALID_INPUT', normalize_row(raw)['inputStatus'])
        raw = sample(); raw['model']['requestConsumptionReceipt']['schemaVersion'] = 'unknown-9'
        self.assertEqual('INVALID_INPUT', normalize_row(raw)['inputStatus'])

    def test_排序指标使用人工相关等级和固定k分母(self):
        scores = rank_metrics(['b', 'c'], {'a': 2, 'b': 1, 'c': 0}, 4)
        self.assertEqual(0.25, scores['precisionAtK'])
        self.assertEqual(0.5, scores['poolRecallAtK'])
        self.assertEqual(1.0, scores['mrrAtK'])
        self.assertAlmostEqual(1 / (3 + 1 / math.log2(3)), scores['ndcgAtK'])
        self.assertEqual(0, rank_metrics([], {'a': 1}, 4)['poolRecallAtK'])
        self.assertIsNone(rank_metrics(['c'], {'c': 0}, 4)['poolRecallAtK'])
        with self.assertRaises(ValueError): rank_metrics(['a', 'a'], {'a': 1}, 4)

    def test_未审核模板不计分且同类标签不冒充相关性(self):
        data = dataset(); qrels = qrels_template(data)
        report = evaluate_offline(data, qrels, 4)
        self.assertEqual(0, report['strategies']['D1']['precisionAtK']['count'])
        self.assertIsNone(report['strategies']['D1']['precisionAtK']['mean'])
        self.assertEqual('UNREVIEWED', report['rows'][0]['status'])

    def test_审核身份失配与不完整标注均拒绝(self):
        data = dataset(); qrels = qrels_template(data)
        q = qrels['queries'][0]
        q.update(reviewStatus='REVIEWED', reviewer='独立审核人', rationale='逐项核查',
                 grades={'a': 2, 'b': 1, 'c': 0})
        report = evaluate_offline(data, qrels, 2)
        self.assertEqual(1.0, report['strategies']['D1']['precisionAtK']['mean'])
        for field, value in [('sourceHash', '0' * 64), ('grades', {'a': 1}), ('poolHash', '0' * 64)]:
            changed = copy.deepcopy(qrels); changed['queries'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluate_offline(data, changed, 2)

    def test_共同目标比较不混入无检索或缺失样本(self):
        rows = [normalize_row(sample(s)) for s in ['D1', 'DENSE', 'VANILLA']]
        extra = copy.deepcopy(rows[0]); extra['sampleId'] = 'extra'; rows.append(extra)
        data = dataset(rows); qrels = qrels_template(data)
        for q in qrels['queries']:
            q.update(reviewStatus='REVIEWED', reviewer='审核人', rationale='逐项核查', grades={'a': 1, 'b': 0, 'c': 0})
        report = evaluate_offline(data, qrels, 2)
        self.assertEqual(['target'], report['paired']['sampleIds'])
        self.assertEqual(['D1', 'DENSE'], report['paired']['strategies'])
        self.assertEqual(2, report['strategies']['D1']['precisionAtK']['count'])

    def test_导出文件修改必须更新身份且重复单元拒绝(self):
        data = dataset(); data['rows'][0]['response'] = '被改写'
        with self.assertRaises(ValueError): validate_dataset(data)
        rows = [normalize_row(sample()), normalize_row(sample())]
        with self.assertRaises(ValueError): validate_dataset(dataset(rows))

    def test_真实批次入口读取gzip原件且保留未完成单元(self):
        from benchmark_batch import make_plan, prepare_batch, run_batch
        raw = sample()
        with tempfile.TemporaryDirectory() as temp:
            targets = [{'sampleId': 'target', 'sourceHash': raw['sourceHash'], 'runnable': True,
                        'groundTruth': {'hasVulnerability': True}}]
            plan = make_plan(['target'], ['D1'], 'real', targets, raw['snapshotId'])
            pending = prepare_batch(temp, plan, 'a' * 32)
            self.assertEqual('MISSING_INPUT', prepare_dataset(pending)['rows'][0]['inputStatus'])
            run_batch(temp, plan, lambda *args: dict(raw, prediction='REPORT'), 'a' * 32)
            original = (pending / 'samples.jsonl').read_bytes()
            (pending / 'samples.jsonl.gz').write_bytes(gzip.compress(original))
            (pending / 'samples.jsonl').unlink()
            result = prepare_dataset(pending)
            self.assertEqual('READY', result['rows'][0]['inputStatus'])
            self.assertEqual(1, len(prepare_dataset(pending, ['target'])['rows']))
            with self.assertRaises(ValueError): prepare_dataset(pending, ['不存在的样本'])
            self.assertEqual(hashlib.sha256(original).hexdigest(), result['origin']['samplesSha256'])
            self.assertEqual(original, gzip.decompress((pending / 'samples.jsonl.gz').read_bytes()))


if __name__ == '__main__':
    unittest.main()
