"""离线报告正确区分保护义务、漏洞裁决、未执行输入和缺失核验。"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from verirag.experiments.benchmark_batch import make_plan, replay_batch, run_batch
from verirag.evaluation.benchmark_report import render_report, summarize_d2


class BenchmarkReportTest(unittest.TestCase):
    def test_缺失核验仍计未知而保护成立不等于漏洞成立(self):
        report = {'batchId': 'a' * 32, 'plan': {'strategies': ['VANILLA']}, 'samples': [{
            'sampleId': 'a', 'strategy': 'VANILLA', 'model': {'hypotheses': [{}, {}, {}]},
            'requestAttempts': 1, 'inputTokens': 10, 'outputTokens': 2,
            'd2': {'assessments': [
                {'hypothesisIndex': 0, 'verdict': 'REFUTED', 'note': '完整保护',
                 'obligations': [{'name': 'actor', 'status': 'SUPPORTED'}]},
                {'hypothesisIndex': 1, 'verdict': 'SUPPORTED', 'note': '可行路径'}]}}]}
        detail = summarize_d2(report)
        values = detail['strategies']['VANILLA']
        self.assertEqual((3, 1, 1, 1), (values['hypotheses'], values['SUPPORTED'], values['REFUTED'], values['UNKNOWN']))
        self.assertEqual(1, values['assessmentMissing'])
        self.assertEqual(1 / 3, values['refutationRate'])
        self.assertEqual({'SUPPORTED': 1, 'REFUTED': 0, 'UNKNOWN': 2}, values['obligations']['actor'])
        self.assertEqual({'核验记录缺失': 1}, detail['unknownReasons'])

    def test_阻断输入不冒充假设或缺失收费_usage(self):
        report = {'batchId': 'a' * 32, 'plan': {'strategies': ['D1']}, 'samples': [{
            'sampleId': 'blocked', 'strategy': 'D1', 'requestAttempts': 0,
            'inputTokens': None, 'outputTokens': None, 'model': {}, 'd2': {'verdict': 'UNKNOWN'}}, {
            'sampleId': 'failed', 'strategy': 'D1', 'requestAttempts': 1,
            'inputTokens': None, 'outputTokens': None, 'model': {}}]}
        detail = summarize_d2(report)
        self.assertEqual(0, detail['strategies']['D1']['hypotheses'])
        self.assertIsNone(detail['strategies']['D1']['refutationRate'])
        self.assertEqual(1, detail['usage']['usageMissing'])
        self.assertEqual(1, detail['usage']['requestAttempts'])

    def test_非法状态不能默默进入已证明计数(self):
        report = {'batchId': 'a' * 32, 'plan': {'strategies': ['D1']}, 'samples': [{
            'sampleId': 'a', 'strategy': 'D1', 'model': {'hypotheses': [{}]},
            'd2': {'assessments': [{'hypothesisIndex': 0, 'verdict': 'SAFE'}]}}]}
        with self.assertRaises(ValueError):
            summarize_d2(report)

    def test_完整保存批次可以离线重算中文报告(self):
        targets = [{'sampleId': 'a', 'runnable': True, 'sourceHash': 'a' * 64,
                    'groundTruth': {'hasVulnerability': True, 'labelSource': '本地夹具'}}]
        plan = make_plan(['a'], ['VANILLA'], 'offline', targets, 'b' * 64)
        with TemporaryDirectory() as directory:
            batch_id = run_batch(Path(directory), plan, lambda *args: {
                'status': 'COMPLETED', 'prediction': 'UNKNOWN', 'requestAttempts': 0,
                'model': {}, 'd2': {'verdict': 'UNKNOWN'}, 'tools': []})
            report = replay_batch(Path(directory), batch_id)
            text = render_report(report, summarize_d2(report))
            self.assertIn('离线 三策略防御审计报告', text)
            self.assertIn('精确率', text)
            self.assertIn('反驳率', text)
            self.assertIn('UNKNOWN', text)
