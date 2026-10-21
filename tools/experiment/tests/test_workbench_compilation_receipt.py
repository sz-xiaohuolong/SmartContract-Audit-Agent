"""工作台封口必须保存候选阶段实际清单，并保持原预览目标身份。"""
import copy
import hashlib
import unittest
from unittest.mock import patch
import test_compiler_facts as fixtures
from test_audit_workbench import Runtime
from verirag.audit.audit_workbench import AuditWorkbench


class WorkbenchCompilationReceiptTest(unittest.TestCase):
    def test_实际候选清单与逐合约错误可从历史完整回读(self):
        fixture = fixtures.CompilerFactsTest(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        # 清单绑定工作台清理后的实际字节；不让测试用原注释收据绕过治理。
        fixture.source = fixture.source.split('\n', 1)[1]
        fixture.input['sources']['contracts/C.sol']['content'] = fixture.source
        (fixture.root / 'contracts/C.sol').write_text(fixture.source)
        source_hash = hashlib.sha256(fixture.source.encode()).hexdigest()
        fixture.binding['sourceUnits']['contracts/C.sol']['sha256'] = source_hash
        fixture.manifest['expectedSourceHash'] = source_hash
        from verirag.analysis.compiler_facts import _walk
        for node in _walk(fixture.output['sources']['contracts/C.sol']['ast']):
            node['src'] = f'0:{len(fixture.source.encode())}:0'
        fixture.seal()
        runtime = Runtime()
        runtime.model_runner = lambda *args: {'status': 'COMPLETED', 'hypotheses': [
            {'contract': name, 'function': 'f', 'riskLine': 2,
             'vulnerabilityType': 'ACCESS_CONTROL', 'riskOperation': 'WRITE',
             'reason': '候选身份回归', 'evidenceIds': []} for name in ['C', '不存在']]}
        def context(root, target, view, mode):
            view['discoveryCompilation'] = fixture.manifest
        workbench = AuditWorkbench(fixture.root, runtime_factory=lambda profile: runtime,
            target_loader=lambda: [], tool=lambda *args: [{'engine': 'SLITHER', 'status': 'SKIPPED', 'issues': []}])
        choice = {'source': fixture.source, 'mechanism': 'ACCESS_CONTROL', 'function': 'f'}
        with patch('verirag.analysis.risk_catalog.prepare_model_context', side_effect=context):
            preview = workbench.preview(choice)
            original = copy.deepcopy(preview['target'])
            result = workbench.execute(workbench.prepare({**choice, 'planHash': preview['planHash']}))
        manifest = result.get('compilationManifest', {})
        self.assertEqual('contract-map', manifest.get('provider'))
        self.assertIn('C', manifest['manifests'])
        self.assertIn('不存在', manifest['errors'])
        self.assertEqual(original, result['target'])
        self.assertEqual(manifest, workbench.read(result['runId'])['compilationManifest'])
