"""四臂共享原候选身份；弱过滤与证明、样本标签与候选真值严格分开。"""
import copy
import unittest
import four_arm_report


class FourArmReportTest(unittest.TestCase):
    def rows(self):
        source = 'contract C {\n modifier onlyOwner { _; }\n function f() public onlyOwner {\n require(msg.sender==owner);\n x=1;\n }\n}'
        hypothesis = {'contract': 'C', 'function': 'f', 'riskLine': 5,
                      'riskOperation': 'WRITE', 'vulnerabilityType': 'ACCESS_CONTROL'}
        row = {'sampleId': 's', 'strategy': 'D1', 'source': source, 'sourceHash': 's',
               'model': {'status': 'COMPLETED', 'hypotheses': [hypothesis]},
               'd2': {'assessments': [{'hypothesisIndex': 0, 'verdict': 'UNKNOWN'}]},
               'inputTokens': None, 'outputTokens': None}
        return [row]

    def test_同候选四臂保留分母与真实三态且不把来源标签当真值(self):
        original = self.rows()
        derived = copy.deepcopy(original)
        derived[0]['d2']['assessments'][0].update(verdict='SUPPORTED', status='COMPLETED')
        summary, rows = four_arm_report.compare_arms(original, derived,
            {'batchId': 'old', 'planHash': 'p', 'labels': {'s': {'hasVulnerability': True}}})
        self.assertEqual(1, summary['candidateCount'])
        self.assertEqual(4, len(rows))
        self.assertEqual(1, len({row['candidateId'] for row in rows}))
        self.assertEqual(['ACCEPTED', 'REJECTED', 'REJECTED', 'ACCEPTED'], [r['prediction'] for r in rows])
        self.assertTrue(all(r['candidateTruth'] is None for r in rows))
        self.assertTrue(all(v['confusionMatrix'] is None for v in summary['arms'].values()))
        self.assertIsNone(summary['historicalUsage']['inputTokens']['total'])
        self.assertEqual(0, summary['newModelRequests'])

    def test_缺assessment或失败仍在UNKNOWN分母(self):
        original = self.rows(); derived = copy.deepcopy(original)
        derived[0]['d2']['assessments'] = []
        summary, rows = four_arm_report.compare_arms(original, derived, {'batchId': 'old'})
        self.assertEqual(1, summary['arms']['FULL_D2']['counts']['UNKNOWN'])
        self.assertEqual(4, len(rows))
        derived[0]['d2']['assessments'] = [{'hypothesisIndex': 0, 'verdict': 'SUPPORTED', 'status': 'FAILED'}]
        summary, _ = four_arm_report.compare_arms(original, derived, {'batchId': 'old'})
        self.assertEqual(1, summary['arms']['FULL_D2']['counts']['UNKNOWN'])

    def test_禁止删单元换候选重复单元或混批(self):
        original = self.rows()
        changed = copy.deepcopy(original); changed[0]['model']['hypotheses'][0]['riskLine'] = 4
        for derived in ([], original + original, changed):
            with self.assertRaises(ValueError):
                four_arm_report.compare_arms(original, derived, {'batchId': 'old'})

    def test_无关合约工具失败不改写候选独立绑定裁决(self):
        original = self.rows(); derived = copy.deepcopy(original)
        derived[0]['d2']['assessments'][0].update(verdict='SUPPORTED', status='COMPLETED',
            toolBinding={'status': 'MATCH'})
        derived[0]['tools'] = [{'contract': 'C', 'status': 'OK'}, {'contract': 'Other', 'status': 'FAILED'}]
        summary, _ = four_arm_report.compare_arms(original, derived, {'batchId': 'old'})
        self.assertEqual(1, summary['arms']['FULL_D2']['counts']['ACCEPTED'])

    def test_注释与其他函数的guard不影响当前弱基线(self):
        rows = self.rows()
        rows[0]['source'] = 'contract C {\nfunction f() public {\n// onlyOwner require(false);\nx=1;\n}\nfunction other() public onlyOwner {require(false);}\n}'
        rows[0]['model']['hypotheses'][0]['riskLine'] = 4
        _, output = four_arm_report.compare_arms(rows, copy.deepcopy(rows), {'batchId': 'old'})
        self.assertEqual(['ACCEPTED', 'ACCEPTED', 'ACCEPTED', 'UNKNOWN'], [r['prediction'] for r in output])

    def test_核验失败缺失及证明范围均逐候选保留(self):
        original = self.rows(); derived = copy.deepcopy(original)
        assessment = derived[0]['d2']['assessments'][0]
        assessment.update(verdict='REFUTED', status='FAILED', candidateProof={
            'proofKind': 'ACCESS_CONTROL_GUARDED_CALL', 'proofScope': {'property': 'CALL_REACHABILITY_ONLY'},
            'executionBinding': {'status': 'UNKNOWN', 'failureKind': 'BUDGET_EXHAUSTED'}})
        summary, _ = four_arm_report.compare_arms(original, derived, {'batchId': 'old'})
        self.assertEqual({'SUPPORTED': 0, 'REFUTED': 0, 'UNKNOWN': 0, 'FAILED': 1}, summary['verification']['counts'])
        self.assertEqual(0, summary['verification']['decisiveCoverage'])
        self.assertEqual('CALL_REACHABILITY_ONLY', summary['changes'][0]['proofProperty'])
        self.assertEqual('BUDGET_EXHAUSTED', summary['changes'][0]['executionFailureKind'])
        derived[0]['d2']['assessments'] = []
        summary, _ = four_arm_report.compare_arms(original, derived, {'batchId': 'old'})
        self.assertEqual(1, summary['verification']['counts']['UNKNOWN'])
        derived[0]['d2'].update(status='FAILED')
        summary, _ = four_arm_report.compare_arms(original, derived, {'batchId': 'old'})
        self.assertEqual(1, summary['verification']['counts']['FAILED'])

    def test_重复错位候选索引不能静默计分(self):
        original = self.rows()
        for indexes in ([0, 0], [1], [-1], [True]):
            derived = copy.deepcopy(original)
            derived[0]['d2']['assessments'] = [{'hypothesisIndex': i, 'verdict': 'REFUTED'} for i in indexes]
            with self.subTest(indexes=indexes), self.assertRaises(ValueError):
                four_arm_report.compare_arms(original, derived, {'batchId': 'old'})
