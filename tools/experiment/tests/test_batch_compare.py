"""批量对照的持久化、失败分母与付费续跑边界。"""
import tempfile
import unittest
from pathlib import Path

from batch_compare import make_plan, run_batch, replay_batch
from storage import encode


class BatchCompareTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Path(self.temp.name)
        self.targets = [{'sampleId': 'A', 'split': 'validation', 'runnable': True, 'fullSourceHash': 'a' * 64},
                        {'sampleId': 'B', 'split': 'validation', 'runnable': True, 'fullSourceHash': 'b' * 64}]
        self.state = {'ready': True, 'realReady': True, 'snapshotId': 's' * 64,
                      'collection': 's1b_' + 'a' * 32, 'endpoint': 'https://example.test', 'model': 'fixed'}

    def tearDown(self):
        self.temp.cleanup()

    def test_same_pool_and_unknown_metrics_are_persisted_per_sample(self):
        plan = make_plan(['A', 'B'], ['DENSE', 'FIELD_FILTER', 'D1'], 'offline', self.targets, self.state)
        calls = []
        def runner(sample, mode, strategy):
            calls.append((sample, strategy))
            return {'runId': str(len(calls)).zfill(32), 'status': 'COMPLETED',
                    'researchEligible': False, 'conclusion': 'UNRESOLVED',
                    'plan': {'sampleId': sample, 'mode': mode, 'strategy': strategy,
                             'snapshotId': 's' * 64, 'poolHash': sample,
                             'sourceHash': {'A': 'a', 'B': 'b'}[sample] * 64},
                    'retrieval': {'d1': {'selected': []}},
                    'model': {'status': 'COMPLETED', 'inputTokens': None, 'outputTokens': None},
                    'd2': {'verdict': 'UNKNOWN'}}
        batch_id = run_batch(self.store, plan, runner)
        report = replay_batch(self.store, batch_id)
        self.assertEqual(6, len(calls))
        self.assertEqual(6, len((self.store / batch_id / 'samples.jsonl').read_text().splitlines()))
        self.assertEqual(6, report['denominators']['planned'])
        self.assertEqual(6, report['denominators']['unknown'])
        self.assertIsNone(report['metrics']['D1']['detectionRecall'])
        self.assertIsNone(report['metrics']['D1']['retrievalRecallAtK'])
        self.assertIsNone(report['metrics']['D1']['inputTokens'])
        self.assertEqual(0, report['requestBounds']['maxRequests'])
        self.assertEqual('COMPLETED', report['status'])
        self.assertEqual(0, report['metrics']['D1']['reported'])
        self.assertEqual(2, report['metrics']['D1']['unresolved'])

    def test_按策略显示模型报告数并保留失败未知(self):
        plan = make_plan(['A', 'B'], ['DENSE', 'D1'], 'real', self.targets, self.state)
        def runner(sample, mode, strategy):
            row = self._result(sample, mode, strategy)
            if sample == 'A' and strategy == 'DENSE':
                return {**row, 'conclusion': 'VULNERABILITY_REPORTED'}
            if sample == 'B' and strategy == 'D1':
                return {**row, 'status': 'FAILED', 'conclusion': 'UNRESOLVED'}
            return row
        report = replay_batch(self.store, run_batch(self.store, plan, runner))
        self.assertEqual(1, report['metrics']['DENSE']['reported'])
        self.assertEqual(1, report['metrics']['D1']['failed'])
        self.assertEqual(2, report['metrics']['D1']['unresolved'])
        self.assertIsNone(report['metrics']['D1']['detectionRecall'])

    def test_started_real_item_is_not_recalled_after_interruption(self):
        plan = make_plan(['A'], ['DENSE', 'D1'], 'real', self.targets, self.state)
        calls = []
        def interrupted(sample, mode, strategy):
            calls.append(strategy)
            if strategy == 'DENSE':
                raise KeyboardInterrupt()
            return self._result(sample, mode, strategy)
        with self.assertRaises(KeyboardInterrupt):
            run_batch(self.store, plan, interrupted, batch_id='a' * 32)
        run_batch(self.store, plan, lambda *args: calls.append(args[2]) or self._result(*args), batch_id='a' * 32)
        report = replay_batch(self.store, 'a' * 32)
        self.assertEqual(['DENSE', 'D1'], calls)
        self.assertEqual(2, report['denominators']['unknown'])
        self.assertEqual(1, report['denominators']['failed'])
        self.assertEqual(2, report['requestBounds']['maxRequests'])

    def _result(self, sample, mode, strategy):
        return {'runId': 'b' * 32, 'status': 'COMPLETED', 'researchEligible': False,
                'conclusion': 'UNRESOLVED', 'plan': {'sampleId': sample, 'mode': mode,
                'strategy': strategy, 'snapshotId': 's' * 64, 'poolHash': sample,
                'sourceHash': {'A': 'a', 'B': 'b'}[sample] * 64},
                'retrieval': {'d1': {'selected': []}},
                'model': {'status': 'COMPLETED', 'inputTokens': 10, 'outputTokens': 2},
                'd2': {'verdict': 'UNKNOWN'}}

    def test_validation_only_and_real_request_bound(self):
        with self.assertRaises(ValueError):
            make_plan(['X'], ['D1'], 'offline', self.targets, self.state)
        with self.assertRaises(ValueError):
            make_plan(['A'], ['D1', 'D1'], 'offline', self.targets, self.state)
        with self.assertRaises(ValueError):
            make_plan(['A'], ['D1'], 'real', self.targets, {**self.state, 'realReady': False})
        plan = make_plan(['A', 'B'], ['DENSE', 'D1'], 'real', self.targets, self.state)
        self.assertEqual(4, plan['requestBounds']['maxRequests'])
        self.assertEqual(8192, plan['requestBounds']['maxOutputTokens'])
        self.assertEqual(40000, plan['requestBounds']['maxInputBytes'])

    def test_允许完整登记的多个验证目标且仍拒绝开发目标(self):
        extended = self.targets + [
            {'sampleId': f'V{i:02d}', 'split': 'validation', 'runnable': True,
             'fullSourceHash': f'{i:064x}'} for i in range(12)]
        extended += [{'sampleId': 'DEV', 'split': 'development', 'runnable': True,
                      'fullSourceHash': 'd' * 64}]
        ids = [row['sampleId'] for row in extended if row['split'] == 'validation']
        plan = make_plan(ids, ['D1'], 'offline', extended, self.state)
        self.assertEqual(14, plan['requestBounds']['samples'])
        with self.assertRaises(ValueError):
            make_plan(ids + ['DEV'], ['D1'], 'offline', extended, self.state)

    def test_changed_target_source_is_rejected_as_failed_unknown(self):
        plan = make_plan(['A'], ['D1'], 'offline', self.targets, self.state)
        batch_id = run_batch(self.store, plan,
                             lambda sample, mode, strategy: {**self._result(sample, mode, strategy),
                                                               'plan': {**self._result(sample, mode, strategy)['plan'],
                                                                        'sourceHash': 'x' * 64}})
        report = replay_batch(self.store, batch_id)
        self.assertEqual(1, report['denominators']['failed'])
        self.assertEqual(1, report['denominators']['unknown'])
        self.assertEqual('UNIT_EXECUTION_ERROR', report['samples'][0]['errorCategory'])

    def test_resume_recovers_partial_last_jsonl_line_without_repeat(self):
        plan = make_plan(['A'], ['DENSE', 'D1'], 'offline', self.targets, self.state)
        calls = []
        def interrupted(sample, mode, strategy):
            calls.append(strategy)
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            run_batch(self.store, plan, interrupted, batch_id='d' * 32)
        with (self.store / ('d' * 32) / 'samples.jsonl').open('ab') as output:
            output.write(b'{"incomplete":')
        self.assertEqual('RUNNING', replay_batch(self.store, 'd' * 32)['status'])
        run_batch(self.store, plan, lambda *args: calls.append(args[2]) or self._result(*args), batch_id='d' * 32)
        report = replay_batch(self.store, 'd' * 32)
        self.assertEqual(['DENSE', 'D1'], calls)
        self.assertEqual(1, report['denominators']['failed'])
        self.assertEqual(2, report['denominators']['planned'])

    def test_replay_rejects_duplicate_started_event(self):
        plan = make_plan(['A'], ['D1'], 'offline', self.targets, self.state)
        batch_id = run_batch(self.store, plan, self._result)
        events = self.store / batch_id / 'events.jsonl'
        with events.open('ab') as output:
            output.write(encode({'kind': 'STARTED', 'sampleId': 'A', 'strategy': 'D1'}) + b'\n')
        with self.assertRaises(ValueError):
            replay_batch(self.store, batch_id)


if __name__ == '__main__':
    unittest.main()
