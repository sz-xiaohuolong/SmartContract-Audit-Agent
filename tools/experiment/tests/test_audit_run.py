"""单样本运行必须先持久化计划，重放不重新调用模型。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from audit_run import RunDependencies, run_once, replay, selected_ids
from storage import decode


class AuditRunTest(unittest.TestCase):
    def test_d1_selection_ids_follow_java_result_shape(self):
        self.assertEqual(['chunk-1'], selected_ids([{'candidate': {'chunkId': 'chunk-1'}, 'use': 'SUPPORT'}]))
        with self.assertRaises(ValueError): selected_ids([{'chunkId': 'wrong-level'}])

    def test_once_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = {'sampleId': 'fixture', 'fullSource': 'contract C {}', 'modelSource': 'contract C {}',
                      'fullSourceHash': 'a' * 64, 'modelSourceHash': 'b' * 64, 'assignmentHash': 'c' * 64,
                      'formalLedgerHash': 'd' * 64, 'scope': 'FULL', 'lineStart': 1, 'lineEnd': 1,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f', 'groupId': 'g', 'researchEligible': False}
            calls = []
            preview = {'snapshotId': 's' * 64, 'collection': 's1b_'+'f'*32, 'sourceHash': 'a'*64,
                       'modelSourceHash': 'b'*64, 'pool': {}, 'facts': {'facts': []},
                       'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': ''}}
            def model(*args):
                calls.append('model')
                return {'status': 'COMPLETED', 'conclusion': 'NO_CONFIRMED_FINDINGS',
                        'hypotheses': [], 'inputTokens': None, 'outputTokens': None}
            deps = RunDependencies(None, None, None, model, lambda *args: [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}])
            with patch('audit_run.load_target', return_value=target), patch('audit_run.preview', return_value=preview):
                result = run_once(root, 'fixture', 'offline', deps)
            self.assertEqual('COMPLETED', result['status'])
            self.assertEqual(['model'], calls)
            self.assertIsNone(result['model']['inputTokens'])
            self.assertEqual(result, replay(root, result['runId']))
            self.assertEqual(['model'], calls)
            run_dir = root / '.local/audit-runs' / result['runId']
            self.assertEqual(1, len((run_dir / 'sample.jsonl').read_text().splitlines()))
            self.assertGreater(len((run_dir / 'events.jsonl').read_text().splitlines()), 2)
            (run_dir / 'plan.json').write_text('{}')
            with self.assertRaises(ValueError): replay(root, result['runId'])

    def test_failure_never_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            target = {'sampleId': 'fixture', 'fullSource': 'contract C {}', 'modelSource': 'contract C {}',
                      'fullSourceHash': 'a'*64, 'modelSourceHash': 'b'*64, 'assignmentHash': 'c'*64,
                      'formalLedgerHash': 'd'*64, 'scope': 'FULL', 'lineStart': 1, 'lineEnd': 1,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f', 'groupId': 'g', 'researchEligible': False}
            deps = RunDependencies(None, None, None, lambda *args: (_ for _ in ()).throw(RuntimeError('secret')),
                                   lambda *args: [])
            view = {'snapshotId': 's'*64, 'collection': 's1b_'+'f'*32, 'sourceHash': 'a'*64,
                    'modelSourceHash': 'b'*64, 'pool': {}, 'facts': {'facts': []},
                    'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': ''}}
            with patch('audit_run.load_target', return_value=target), patch('audit_run.preview', return_value=view):
                result = run_once(Path(directory), 'fixture', 'offline', deps)
            self.assertEqual('FAILED', result['status'])
            self.assertEqual('UNRESOLVED', result['conclusion'])
            self.assertNotIn('secret', str(result))

    def test_source_change_before_model_rejects_without_request(self):
        with tempfile.TemporaryDirectory() as directory:
            target = {'sampleId': 'fixture', 'fullSource': 'contract C {}', 'modelSource': 'contract C {}',
                      'fullSourceHash': 'a'*64, 'modelSourceHash': 'b'*64, 'assignmentHash': 'c'*64,
                      'formalLedgerHash': 'd'*64, 'scope': 'FULL', 'lineStart': 1, 'lineEnd': 1,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f', 'groupId': 'g', 'researchEligible': False}
            changed = {**target, 'fullSourceHash': 'e'*64}
            view = {'snapshotId': 's'*64, 'collection': 's1b_'+'f'*32, 'sourceHash': 'a'*64,
                    'modelSourceHash': 'b'*64, 'pool': {}, 'facts': {'facts': []},
                    'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': ''}}
            calls = []
            deps = RunDependencies(None, None, None, lambda *args: calls.append(1), lambda *args: [])
            with patch('audit_run.load_target', side_effect=[target, changed]), patch('audit_run.preview', return_value=view):
                with self.assertRaises(ValueError): run_once(Path(directory), 'fixture', 'offline', deps)
            self.assertEqual([], calls)

    def test_prompt_over_limit_rejects_without_request(self):
        with tempfile.TemporaryDirectory() as directory:
            target = {'sampleId': 'fixture', 'fullSource': 'contract C {}', 'modelSource': 'x'*9900,
                      'fullSourceHash': 'a'*64, 'modelSourceHash': 'b'*64, 'assignmentHash': 'c'*64,
                      'formalLedgerHash': 'd'*64, 'scope': 'FUNCTION', 'lineStart': 1, 'lineEnd': 1,
                      'mechanism': 'ACCESS_CONTROL', 'function': 'f', 'groupId': 'g', 'researchEligible': False}
            view = {'snapshotId': 's'*64, 'collection': 's1b_'+'f'*32, 'sourceHash': 'a'*64,
                    'modelSourceHash': 'b'*64, 'pool': {}, 'facts': {'facts': []},
                    'd1': {'status': 'NO_RISK_FACT', 'selected': [], 'context': 'y'*2048}}
            calls = []
            deps = RunDependencies(None, None, None, lambda *args: calls.append(1), lambda *args: [])
            with patch('audit_run.load_target', return_value=target), patch('audit_run.preview', return_value=view):
                with self.assertRaises(ValueError): run_once(Path(directory), 'fixture', 'offline', deps)
            self.assertEqual([], calls)


if __name__ == '__main__': unittest.main()
