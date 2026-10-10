"""检查恢复、依赖、摘要漂移和越界验收的真实风险。"""
import json
from pathlib import Path
import tempfile
import unittest
from workflow import Workflow, DEPENDENCIES, digest, atomic_json, bib_entries, check_metric_claims


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'workflow/runs/run01'
        self.run.mkdir(parents=True)
        self.source = self.root / 'source.md'; self.source.write_text('证据')
        atomic_json(self.run / '输入清单.json', {'资料': [{'来源': 'source.md', '摘要': digest(self.source)}]})
        atomic_json(self.root / 'workflow/运行状态.json', {'轮次': 'run01', '派发次数': 0,
                    '任务': {key: {'状态': '待执行'} for key in DEPENDENCIES}})
        self.flow = Workflow(self.root, self.run)

    def test_dependencies_and_duplicate_dispatch(self):
        with self.assertRaisesRegex(ValueError, '前置'): self.flow.start('T02', 'L')
        self.flow.start('T00')
        with self.assertRaisesRegex(ValueError, '重复'): self.flow.start('T00')

    def test_accept_requires_actual_inside_output(self):
        self.flow.start('T00')
        with self.assertRaises(ValueError): self.flow.accept('T00', [], '测试')
        outside = self.root / 'outside.md'; outside.write_text('越界')
        with self.assertRaises(ValueError): self.flow.accept('T00', [outside], '测试')
        link = self.run / 'linked.md'; link.symlink_to(outside)
        with self.assertRaises(ValueError): self.flow.accept('T00', [link], '测试')

    def test_input_drift_does_not_dispatch(self):
        self.source.write_text('新证据')
        with self.assertRaisesRegex(ValueError, '漂移'): self.flow.start('T00')
        self.assertEqual(self.flow.status()['状态']['任务']['T00']['状态'], '待执行')

    def test_resume_detects_changed_accepted_output(self):
        self.flow.start('T00')
        output = self.run / 'result.md'; output.write_text('初稿')
        self.flow.accept('T00', [output], '已核对')
        self.assertEqual(Workflow(self.root, self.run).status()['需重验任务'], [])
        output.write_text('后来修改')
        self.assertEqual(self.flow.status()['需重验任务'], ['T00'])

    def test_atomic_write_preserves_valid_json(self):
        p = self.root / 'record.json'
        atomic_json(p, {'说明': '中文'}); atomic_json(p, {'说明': '更新'})
        self.assertEqual(json.loads(p.read_text())['说明'], '更新')
        self.assertEqual(list(self.root.glob('.proposal-*')), [])

    def test_bib_nested_braces_and_duplicate_keys(self):
        b = '@article{a,title={带{嵌套}标题},year={2026}}'
        self.assertEqual(bib_entries(b)['a']['fields']['title'], '带{嵌套}标题')
        with self.assertRaisesRegex(ValueError, '重复'): bib_entries(b + b)

    def test_wrong_parent_batch_and_numeric_claim(self):
        summary = {'batchId': 'a', 'metrics': {'D1': {'f1': 0.934782}}}
        claim = {'batchId': 'b', 'values': []}
        with self.assertRaisesRegex(ValueError, '不同批次'): check_metric_claims(claim, summary)
        claim = {'batchId': 'a', 'values': [{'path': 'metrics.D1.f1', 'value': 0.99}]}
        self.assertEqual(check_metric_claims(claim, summary)['错误路径'], ['metrics.D1.f1'])

    def test_assemble_rejects_unaccepted_or_drifted_sources(self):
        source = self.run / 'chapter.md'; source.write_text('章节')
        target = self.run / 'combined.md'
        with self.assertRaisesRegex(ValueError, '未验收'): self.flow.assemble([source], target)
        self.flow.start('T00'); self.flow.accept('T00', [source], '测试')
        self.flow.assemble([source], target)
        self.assertEqual(target.read_text(), '章节\n')
        source.write_text('改变')
        with self.assertRaisesRegex(ValueError, '漂移'): self.flow.assemble([source], target)


if __name__ == '__main__': unittest.main()
