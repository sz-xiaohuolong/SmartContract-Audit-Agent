"""离线入口、历史原件与独立审核的闭环验证。"""
import copy
import gzip
import hashlib
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from storage import atomic_json, encode, fingerprint
from test_phase5_retrieval import FixedEncoder, config, evidence, query, scoring_config


def dataset():
    from phase5_cli import seal_dataset
    q = query(); q['contrasts'] = q['contrasts'][:1]
    pool = {'evidence': evidence(), 'poolHash': fingerprint(evidence())}
    target = {'targetKey': '目标一', 'sourceHash': 'b' * 64, 'snapshotId': 'd' * 64,
        'status': 'READY', 'pool': pool, 'queries': {'queries': [q], 'entryGaps': []},
        'origin': {'path': '冻结原件', 'sha256': 'a' * 64}}
    return seal_dataset({'schemaVersion': 'phase5-dataset-1', 'targets': [target],
        'budget': {'maxPairs': 2, 'maxBytes': 4096}, 'k': 2, 'queryConfig': config(),
        'sources': [], 'requestAttempts': 0, 'researchEligible': False})


def run_fixture(data=None):
    from phase5_cli import compare_dataset
    return compare_dataset(data or dataset(), FixedEncoder([[1, 0], [0, 1], [1, 0], [0, 1]]), scoring_config())


def reviewed(data):
    from phase5_cli import review_template
    review = review_template(data)
    for target in review['targets']:
        for q in target['queries']:
            q['relevance'].update(status='REVIEWED', reviewer='独立审核甲', reviewerType='INDEPENDENT_HUMAN', rationale='逐对核对保护条件')
            q['pairGrades'] = {key: 2 if key == 'a' else 0 for key in q['pairGrades']}
            q.update(status='ACCEPTED', reviewer='独立审核乙', reviewerType='INDEPENDENT_HUMAN', rationale='单维区别与来源均可复查')
    return review


class Phase5CliTest(unittest.TestCase):
    def historical_fixture(self):
        from test_phase5_retrieval import Phase5RetrievalTest
        from test_r3_retrieval import R3RetrievalTest
        from benchmark_batch import make_plan
        helper = Phase5RetrievalTest()
        access_helper, bundle = helper.access_bundle()
        self.addCleanup(helper.doCleanups)
        root = access_helper.fixture.root
        runtime, target = R3RetrievalTest().setup_runtime(str(root))
        view = runtime.r3.select(runtime.preview(target), 'R3_FUSION', allow_unreviewed=True)
        for item in (view, view['pool']): item['sourceHash'] = bundle['sourceHash']
        view['poolHash'] = fingerprint(view['pool'])
        view['targetMechanism'] = 'ACCESS_CONTROL'
        view['discoveryCompilation'] = access_helper.fixture.manifest
        sample = {'sampleId': '目标', 'runnable': True, 'sourceHash': bundle['sourceHash'],
                  'groundTruth': {'hasVulnerability': True}}
        plan = make_plan(['目标'], ['R3_FUSION'], 'offline', [sample], view['snapshotId'])
        batch = root / 'research-artifacts/runs/benchmarks' / ('1' * 32)
        batch.mkdir(parents=True)
        atomic_json(batch / 'plan.json', plan)
        row = {'sampleId': '目标', 'strategy': 'R3_FUSION', 'sourceHash': bundle['sourceHash'],
            'source': access_helper.fixture.source, 'retrieval': view, 'status': 'COMPLETED',
            'model': {'hypotheses': [], 'requestConsumptionReceipt': {
                'sourceHash': bundle['sourceHash'], 'contextSha256': hashlib.sha256(view['d1']['context'].encode()).hexdigest()}}}
        (batch / 'samples.jsonl.gz').write_bytes(gzip.compress(encode(row) + b'\n'))
        return root, batch, row

    def test_压缩历史原件可生成查询和盲审材料且保持字节不变(self):
        from phase5_cli import prepare_batch, inventory, review_template, verify_sources
        root, batch, _ = self.historical_fixture()
        before = (batch / 'samples.jsonl.gz').read_bytes()
        data = prepare_batch(root, batch.name)
        self.assertEqual('READY', data['targets'][0]['status'])
        self.assertTrue(review_template(data)['targets'])
        verify_sources(root, data)
        self.assertEqual(before, (batch / 'samples.jsonl.gz').read_bytes())
        manifest = inventory(root, [batch.name])
        self.assertEqual(1, manifest['batches'][0]['plannedTargets'])
        changed = copy.deepcopy(data); changed['targets'][0]['queries']['queries'][0]['original'] = '伪造查询'
        from phase5_cli import seal_dataset
        with self.assertRaises(ValueError): verify_sources(root, seal_dataset(changed))

    def test_来源错绑和缺失目标明确保留(self):
        from phase5_cli import prepare_batch
        root, batch, row = self.historical_fixture()
        row['retrieval']['snapshotId'] = '0' * 64
        (batch / 'samples.jsonl.gz').write_bytes(gzip.compress(encode(row) + b'\n'))
        data = prepare_batch(root, batch.name)
        self.assertEqual('INPUT_FAILED', data['targets'][0]['status'])
        self.assertIn('快照', data['targets'][0]['reason'])

    def test_历史叶子原件符号链接不得绕过根目录(self):
        from phase5_cli import inventory
        root, batch, _ = self.historical_fixture()
        with TemporaryDirectory() as directory:
            outside = Path(directory) / 'plan.json'
            outside.write_bytes((batch / 'plan.json').read_bytes())
            (batch / 'plan.json').unlink(); (batch / 'plan.json').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, '路径|链接'):
                inventory(root, [batch.name])

    def test_有效单元索引按原件行核对而不合并历史候选(self):
        from phase5_cli import inventory
        root, batch, _ = self.historical_fixture()
        from storage import decode, read_artifact
        plan = decode(read_artifact(batch / 'plan.json'))
        index = {'batchId': batch.name, 'planHash': plan['planHash'], 'units': [
            {'artifact': 'samples.jsonl', 'batchId': batch.name, 'rowIndex': 0, 'sampleId': '目标', 'strategy': 'R3_FUSION'}]}
        atomic_json(root / 'index.json', index)
        result = inventory(root, [batch.name], unit_indexes={batch.name: 'index.json'})
        self.assertEqual(1, result['batches'][0]['effectiveUnits'])
        self.assertEqual(1, len(result['batches'][0]['segments']))
        index['units'][0]['rowIndex'] = 10; atomic_json(root / 'index.json', index)
        with self.assertRaises(ValueError): inventory(root, [batch.name], unit_indexes={batch.name: 'index.json'})

    def test_跨划分同项目事件或补丁必须拒绝且缺登记保留未知(self):
        from phase5_cli import check_lineage
        records = [{'id': '知识', 'split': 'knowledge', 'sourceHash': 'a' * 64,
            'project': '项目甲', 'event': '事件甲', 'patch': '补丁甲'},
            {'id': '目标', 'split': 'development', 'sourceHash': 'b' * 64,
             'project': '项目乙', 'event': None, 'patch': None}]
        self.assertEqual('REVIEW_REQUIRED', check_lineage(records)['status'])
        for field in ('sourceHash', 'project', 'event', 'patch'):
            changed = copy.deepcopy(records); changed[1][field] = changed[0][field]
            with self.subTest(field=field), self.assertRaises(ValueError): check_lineage(changed)

    def test_命令行无付费入口且帮助可执行(self):
        completed = subprocess.run([sys.executable, 'tools/experiment/phase5_cli.py', '--help'], capture_output=True, text=True)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn('prepare', completed.stdout)
        self.assertNotIn('--execute', completed.stdout)

    def test_回执回读可复算且篡改分数或排名拒绝(self):
        from phase5_cli import validate_run, write_output
        from storage import decode, read_artifact
        result = run_fixture()
        with TemporaryDirectory() as directory:
            path = Path(directory) / '结果'
            write_output(path, {'run.json': result})
            restored = decode(read_artifact(path / 'run.json'))
            validate_run(restored)
            with self.assertRaises(ValueError):
                write_output(path, {'run.json': result})
        for field in ('scores', 'rankings'):
            changed = copy.deepcopy(result)
            if field == 'scores': changed['comparisons'][0]['scores']['scores'][0]['margin'] = 123
            else: changed['comparisons'][0]['rankings']['P5_MARGIN']['selectedPairs'] = []
            changed['runHash'] = fingerprint({k: v for k, v in changed.items() if k != 'runHash'})
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_run(changed)

    def test_审核表隐藏方法分数排序且缺标签真实成绩为空(self):
        from phase5_cli import review_template
        from eval_ragas import evaluate_phase5
        data = dataset(); review = review_template(data)
        self.assertNotIn('margin', str(review))
        self.assertNotIn('P5_MARGIN', str(review))
        self.assertTrue(all(v is None for v in review['targets'][0]['queries'][0]['pairGrades'].values()))
        report = evaluate_phase5(run_fixture(data), review)
        self.assertEqual(0, report['coverage']['independentlyAcceptedQueries'])
        self.assertIsNone(report['strategies']['P5_MARGIN']['ndcgAtK']['mean'])
        self.assertEqual(1, report['coverage']['plannedTargets'])

    def test_独立审核必须覆盖完整配对池与查询身份(self):
        from eval_ragas import evaluate_phase5
        data = dataset(); result = run_fixture(data)
        report = evaluate_phase5(result, reviewed(data))
        self.assertEqual('CASE_PAIR', report['rankingUnit'])
        self.assertEqual(['目标一'], report['paired']['targetKeys'])
        self.assertEqual(1, report['strategies']['P5_MARGIN']['ndcgAtK']['mean'])
        for kind in ('missing', 'identity', 'ai', 'rejected'):
            review = reviewed(data)
            if kind == 'missing': review['targets'][0]['queries'][0]['pairGrades'].pop('b')
            elif kind == 'identity': review['targets'][0]['queries'][0]['queryHash'] = '错身份'
            elif kind == 'ai': review['targets'][0]['queries'][0]['relevance']['reviewerType'] = 'AI'
            else:
                review['targets'][0]['queries'][0]['status'] = 'REJECTED'
                rejected = evaluate_phase5(result, review)
                self.assertEqual(0, rejected['coverage']['independentlyAcceptedQueries'])
                continue
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                evaluate_phase5(result, review)

    def test_全零等级和缺失目标保持原分母(self):
        from phase5_cli import seal_dataset
        from eval_ragas import evaluate_phase5
        data = dataset(); data['targets'].append({'targetKey': '缺失目标', 'status': 'INPUT_MISSING', 'reason': '无保存结果'})
        data = seal_dataset(data); review = reviewed(data)
        review['targets'][0]['queries'][0]['pairGrades'] = {'a': 0, 'b': 0}
        report = evaluate_phase5(run_fixture(data), review)
        self.assertEqual(2, report['coverage']['plannedTargets'])
        self.assertEqual(1, report['coverage']['completeScoredTargets'])
        self.assertEqual(0, report['strategies']['P5_MARGIN']['precisionAtK']['mean'])
        self.assertIsNone(report['strategies']['P5_MARGIN']['ndcgAtK']['mean'])

    def test_零操作目标和入口缺口在报告中逐目标展示(self):
        from phase5_cli import seal_dataset
        from eval_ragas import evaluate_phase5
        data = dataset()
        empty = copy.deepcopy(data['targets'][0]); empty['targetKey'] = '汇编入口目标'
        empty['queries'] = {'queries': [], 'entryGaps': [{'entry': 'execute()', 'reason': 'INLINE_ASSEMBLY'}]}
        data['targets'].append(empty); data = seal_dataset(data)
        report = evaluate_phase5(run_fixture(data))
        self.assertEqual(2, len(report['targetCoverage']))
        target = next(t for t in report['targetCoverage'] if t['targetKey'] == '汇编入口目标')
        self.assertEqual(0, target['plannedQueries'])
        self.assertEqual(empty['queries']['entryGaps'], target['entryGaps'])
        self.assertEqual('UNSCORED', target['evaluationStatus'])
        self.assertEqual(2, report['coverage']['unscoredTargets'])

    def test_按目标先平均避免多操作支配指标(self):
        from phase5_cli import seal_dataset
        from eval_ragas import evaluate_phase5
        data = dataset()
        second = copy.deepcopy(data['targets'][0]); second['targetKey'] = '目标二'
        for index in range(2):
            q = copy.deepcopy(second['queries']['queries'][0]); q['operationKey'] = f'第二目标操作{index}'
            if index == 0: second['queries']['queries'] = []
            second['queries']['queries'].append(q)
        data['targets'].append(second); data = seal_dataset(data)
        review = reviewed(data)
        for q in review['targets'][1]['queries']: q['pairGrades'] = {'a': 0, 'b': 2}
        result = run_fixture(data); report = evaluate_phase5(result, review)
        expected = (1 + 1 / __import__('math').log2(3)) / 2
        self.assertAlmostEqual(expected, report['strategies']['P5_MARGIN']['ndcgAtK']['mean'])
        self.assertEqual(2, report['strategies']['P5_MARGIN']['ndcgAtK']['count'])

    def test_原件路径越界压缩回读和来源变化(self):
        from phase5_cli import read_pointer
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = encode({'内容': '冻结原件'})
            (root / 'a.json.gz').write_bytes(gzip.compress(raw))
            pointer = {'path': 'a.json', 'sha256': hashlib.sha256(raw).hexdigest()}
            self.assertEqual(raw, read_pointer(root, pointer))
            for change in ({'path': '../越界'}, {'sha256': '0' * 64}):
                with self.assertRaises(ValueError): read_pointer(root, {**pointer, **change})
            (root / 'link.json').symlink_to(root / 'a.json.gz')
            with self.assertRaises(ValueError): read_pointer(root, {'path': 'link.json', 'sha256': pointer['sha256']})

    def test_原子发布失败不留下完成目录(self):
        from phase5_cli import write_output
        with TemporaryDirectory() as directory:
            path = Path(directory) / '结果'
            with self.assertRaises(ValueError):
                write_output(path, {'a.json': {'坏值': float('nan')}})
            self.assertFalse(path.exists())
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_本机编码先查完整token再编码且不自动连接服务(self):
        from phase5_cli import local_encoder
        from unittest.mock import patch
        class Model:
            max_seq_length = 512
            def tokenizer(self, texts, **kwargs):
                self.options = kwargs
                return {'input_ids': [[1] * len(text) for text in texts]}
            def encode(self, texts, **kwargs):
                raise AssertionError('超限输入不能进入编码')
        model = Model()
        with patch('d1_embed.verify_model_dir'), TemporaryDirectory() as directory:
            calls = []
            def factory(path, **kwargs): calls.append(kwargs); return model
            encoder, _ = local_encoder(directory, factory=factory)
            self.assertTrue(calls[0]['local_files_only'])
            self.assertFalse(calls[0]['trust_remote_code'])
            with self.assertRaisesRegex(ValueError, '禁止截断'): encoder(['字' * 513])
            self.assertFalse(model.options['truncation'])

    def test_重封摘要不能把有效查询伪装成不可评分(self):
        from phase5_cli import validate_run
        from phase5_retrieval import rank_pool, CONDITIONS
        result = run_fixture(); scores = result['comparisons'][0]['scores']
        scores.update(status='NOT_SCORABLE', scores=[], errors=['伪造跳过'])
        result['comparisons'][0]['rankings'] = {condition: rank_pool(result['dataset']['targets'][0]['pool'], scores, condition,
            result['dataset']['budget']) for condition in CONDITIONS}
        result['runHash'] = fingerprint({k: v for k, v in result.items() if k != 'runHash'})
        with self.assertRaises(ValueError): validate_run(result)

    def test_人工看到的查询和材料必须与冻结原件一致(self):
        from eval_ragas import evaluate_phase5
        data = dataset(); result = run_fixture(data)
        for field in ('original', 'contrasts', 'material', 'source'):
            review = reviewed(data)
            if field in ('original', 'contrasts'): review['targets'][0]['queries'][0][field] = '另一份查询'
            elif field == 'material': review['targets'][0]['materials'][0]['text'] = '另一份材料'
            else: review['targets'][0]['sourceText'] = '另一份目标'
            with self.subTest(field=field), self.assertRaises(ValueError): evaluate_phase5(result, review)


if __name__ == '__main__':
    unittest.main()
