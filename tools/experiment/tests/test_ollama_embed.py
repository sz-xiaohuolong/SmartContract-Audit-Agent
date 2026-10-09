"""Ollama 编码适配的离线确定性测试。"""
import unittest

from ollama_embed import ContextLengthError, OllamaEncoder


class OllamaEncoderTest(unittest.TestCase):
    def test_模型摘要前缀维度与上下文截取(self):
        calls = []
        def transport(path, payload):
            if path == '/api/tags':
                return {'models': [{'name': 'nomic-embed-text:latest', 'digest': 'a' * 64,
                    'details': {'embedding_length': 768, 'context_length': 2048}}]}
            calls.append(payload)
            if len(payload['prompt']) > 100:
                raise ContextLengthError('窗口不足')
            return {'embedding': [1.0] + [0.0] * 767}
        encoder = OllamaEncoder(transport=transport, expected_digest='a' * 64)
        vector, receipt = encoder.encode_document('x' * 120)
        self.assertEqual(768, len(vector))
        self.assertTrue(receipt['truncated'])
        self.assertLessEqual(len(calls[-1]['prompt']), 100)
        self.assertTrue(calls[-1]['prompt'].startswith('search_document: '))
        query, query_receipt = encoder.encode_query('guard')
        self.assertEqual(768, len(query))
        self.assertFalse(query_receipt['truncated'])
        self.assertTrue(calls[-1]['prompt'].startswith('search_query: '))
        self.assertEqual(8192, calls[-1]['options']['num_ctx'])

    def test_模型摘要变化拒绝复用快照(self):
        def transport(path, payload):
            return {'models': [{'name': 'nomic-embed-text:latest', 'digest': 'b' * 64,
                'details': {'embedding_length': 768}}]}
        with self.assertRaisesRegex(ValueError, '摘要'):
            OllamaEncoder(transport=transport, expected_digest='a' * 64)


if __name__ == '__main__':
    unittest.main()
