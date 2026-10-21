"""模板必须回查知识原件；实例绑定不升级条件或漏洞裁决。"""
import copy
import hashlib
import unittest


class CheckTemplatesTest(unittest.TestCase):
    def setUp(self):
        self.source = {'id': 'p', 'split': 'knowledge', 'origin': 'https://example.test/p',
                       'project_group': 'p', 'source_hash': hashlib.sha256(b'before').hexdigest()}
        self.snapshot = {'manifest': {'samples': [self.source]}, 'documents': [
            {'id': 'p_before', 'sample_id': 'p', 'text': 'before'},
            {'id': 'p_after', 'sample_id': 'p', 'text': 'after'}]}
        self.template = {'id': 'AC-1', 'version': '1', 'mechanism': 'ACCESS_CONTROL',
            'pairId': 'p', 'sourceHash': self.source['source_hash'], 'origin': self.source['origin'],
            'chunks': [{'chunkId': 'p_before', 'sha256': self.source['source_hash']},
                       {'chunkId': 'p_after', 'sha256': hashlib.sha256(b'after').hexdigest()}],
            'reviewStatus': 'UNREVIEWED', 'question': '检查同主体同资源权限',
            'requiredSlots': ['entry', 'resource', 'stateVersion'],
            'prerequisites': ['必须核对完整路径和其他写入者'], 'steps': ['核对声明与实际路径'],
            'contractType': '状态写入合约', 'patchPointer': 'p_before → p_after'}

    def test_知识划分或原件摘要漂移拒绝模板(self):
        from verirag.retrieval.check_templates import verify_templates
        self.assertEqual(1, len(verify_templates([self.template], self.snapshot)))
        changed = copy.deepcopy(self.snapshot); changed['manifest']['samples'][0]['split'] = 'test'
        with self.assertRaises(ValueError): verify_templates([self.template], changed)
        changed = copy.deepcopy(self.snapshot); changed['documents'][1]['text'] = '伪补丁'
        with self.assertRaises(ValueError): verify_templates([self.template], changed)

    def test_状态版本和路径缺失不得猜测完全绑定(self):
        from verirag.retrieval.check_templates import instantiate_template
        operation = {'contract': 'C', 'entrySignature': 'f()', 'entryDeclarationId': 1,
            'factId': 'x', 'riskOperation': 'WRITE', 'span': {'start': 4, 'length': 2},
            'sourceUnit': 'C.sol'}
        instance = instantiate_template(self.template, operation, None)
        self.assertEqual('PARTIAL', instance['status'])
        self.assertIn('resource', instance['unboundSlots'])
        self.assertIn('stateVersion', instance['unboundSlots'])
        self.assertEqual('UNKNOWN', instance['applicability'])

    def test_预算不足整条拒绝不截断必要前提(self):
        from verirag.retrieval.check_templates import render_template
        self.assertIsNone(render_template(self.template, [], max_bytes=10))
        text = render_template(self.template, [], max_bytes=4096)
        self.assertIn('必须核对完整路径和其他写入者', text)
        self.assertIn('未经审核', text)
