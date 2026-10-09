"""失败原文重放保留原费用、历史状态与失败分母。"""
import tempfile
import unittest
from pathlib import Path
from reparse_benchmark import reparse_rows


class ReparseBenchmarkTest(unittest.TestCase):
    def test_只重放有原文的解析失败而不重新计费(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagnostic = root / '.local/auto-benchmark-diagnostics/a.txt'
            diagnostic.parent.mkdir(parents=True)
            diagnostic.write_text('{"schemaVersion":"2","hypotheses":[]}')
            original = {'status': 'FAILED', 'prediction': 'UNKNOWN', 'sampleId': 'a', 'strategy': 'D1',
                'sourceHash': 'h', 'errorCategory': 'MODEL_OUTPUT_INVALID',
                'diagnosticPath': str(diagnostic.relative_to(root)), 'inputTokens': 10, 'outputTokens': 5,
                'durationMs': 20, 'requestAttempts': 1, 'selectedIds': [], 'model': {'validationIssue': 'SCHEMA_FIELDS'}}
            network = {**original, 'strategy': 'DENSE', 'errorCategory': 'MODEL_CALL_ERROR'}
            calls = []
            def parse(target, row, raw):
                calls.append(raw)
                return {'status': 'COMPLETED', 'conclusion': 'NO_CONFIRMED_FINDINGS', 'hypotheses': [],
                        'inputTokens': None, 'requestAttempts': 0, 'errorCategory': None, 'validationIssue': None}
            rows = reparse_rows({'batchId': 'original', 'samples': [original, network]},
                {'a': {'sourceHash': 'h'}}, root, parse, 'jar-hash')
            self.assertEqual(1, len(calls))
            self.assertEqual('NO_REPORT', rows[0]['prediction'])
            self.assertEqual(10, rows[0]['model']['inputTokens'])
            self.assertEqual(1, rows[0]['requestAttempts'])
            self.assertEqual('FAILED', rows[0]['parseReplay']['originalStatus'])
            self.assertEqual('UNKNOWN', rows[1]['prediction'])
            self.assertEqual('FAILED', original['status'])
