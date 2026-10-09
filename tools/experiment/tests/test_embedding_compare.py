"""嵌入对照必须使用一致目标，并保留失败与共同有效分母。"""
import copy
import unittest
from embedding_compare import compare_reports


class EmbeddingCompareTest(unittest.TestCase):
    def report(self):
        return {'status': 'COMPLETED', 'batchId': 'a' * 32,
                'plan': {'sampleIds': ['a', 'b'], 'strategies': ['DENSE', 'D1'],
                         'sourceHashes': {'a': '1', 'b': '2'}, 'labels': {
                             'a': {'hasVulnerability': True}, 'b': {'hasVulnerability': False}},
                         'provider': {'model': 'fixture'}, 'mode': 'real'},
                'metrics': {}, 'denominators': {'failed': 0},
                'samples': [{'sampleId': sample, 'strategy': strategy,
                             'status': 'COMPLETED', 'prediction': 'REPORT', 'selectedIds': ['x']}
                            for sample in ['a', 'b'] for strategy in ['DENSE', 'D1']]}

    def test_六路共同分母排除任一路失败且保留选择变化(self):
        bge, nomic = self.report(), self.report()
        nomic['samples'][-1].update(status='FAILED', prediction='UNKNOWN')
        nomic['samples'][0]['selectedIds'] = ['y']
        result = compare_reports(bge, nomic)
        self.assertEqual(['a'], result['commonSampleIds'])
        self.assertEqual(1, result['commonMetrics']['nomic']['D1']['tp'])
        self.assertEqual(0, result['commonMetrics']['bge']['DENSE']['fp'])
        self.assertEqual(1, result['selectionChanges']['DENSE'])

    def test_目标摘要或供应商不一致不能横向归因(self):
        bge = self.report()
        for field in ('sourceHashes', 'provider'):
            other = copy.deepcopy(bge)
            other['plan'][field] = {}
            with self.assertRaises(ValueError): compare_reports(bge, other)
