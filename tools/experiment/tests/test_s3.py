"""S3 来源隔离、人工标签、预算及离线指标回归。"""
import hashlib
import json
import tempfile
import unittest
from unittest import mock
import subprocess
from pathlib import Path
from s3 import audit_lineage, score_sample, token_budget_select, validate_judgments, d2_baselines, validate_d2_challenges, d2_denominators
from s3_pilot import strategies, run

H = lambda text: hashlib.sha256(text.encode()).hexdigest()


class S3Test(unittest.TestCase):
    def ledger(self, root):
        (root / 'a.sol').write_text('contract A { uint x; function f() public { x = 1; } }')
        (root / 'b.sol').write_text('pragma solidity ^0.8.0; contract B { address owner; event E(); function g() external { emit E(); } }')
        def row(identifier, path, split, project, event, pair):
            return {'id': identifier, 'sourceId': 's', 'path': path,
                    'sourceHash': H((root/path).read_text()), 'split': split,
                    'projectId': project, 'eventId': event, 'patchPairId': pair,
                    'cloneGroups': [], 'originType': 'REAL_PATCH', 'labelStatus': 'PENDING',
                    'artifacts': [{'id': identifier + '-report', 'kind': 'REPORT', 'path': path,
                                   'sha256': H((root/path).read_text()), 'groupId': pair}]}
        return {'schemaVersion': '1', 'sources': [{'id': 's', 'url': 'https://example.invalid/s',
            'revision': 'a'*40, 'licenseStatus': 'PENDING', 'license': None,
            'sourceStatus': 'PENDING', 'reportStatus': 'PENDING', 'patchStatus': 'PENDING'}],
            'samples': [row('a', 'a.sol', 'knowledge', 'p', 'e1', 'pair1'),
                        row('b', 'b.sol', 'development', 'q', 'e2', 'pair2')], 'edges': []}

    def test_empty_lineage_cannot_pass_gate(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'不能为空'):
                audit_lineage({'schemaVersion':'1','sources':[],'samples':[],'edges':[]},td)

    def test_pending_report_or_patch_keeps_samples_pending(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ledger = self.ledger(root)
            ledger['sources'][0].update(licenseStatus='VERIFIED', license='MIT', sourceStatus='VERIFIED')
            for row in ledger['samples']:
                row['labelStatus'] = 'REVIEWED'
            self.assertEqual(['a', 'b'], audit_lineage(ledger, root)['pendingSamples'])
            ledger['sources'][0]['reportStatus'] = 'VERIFIED'
            self.assertEqual(['a', 'b'], audit_lineage(ledger, root)['pendingSamples'])
            ledger['sources'][0]['patchStatus'] = 'VERIFIED'
            self.assertEqual(['a', 'b'], audit_lineage(ledger, root)['pendingSamples'])

    def test_self_reported_review_without_artifacts_cannot_pass_research_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ledger = self.ledger(root)
            ledger['sources'][0].update(licenseStatus='VERIFIED', license='MIT', sourceStatus='VERIFIED',
                                        reportStatus='VERIFIED', patchStatus='VERIFIED')
            for row in ledger['samples']:
                row.update(labelStatus='REVIEWED', truthEvidence=['随意字符串'], artifacts=[])
            result = audit_lineage(ledger, root)
            self.assertTrue(result['ok'])
            self.assertEqual(['a', 'b'], result['pendingSamples'])

    def test_research_source_artifact_must_match_sample_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ledger = self.ledger(root)
            for name, content in (('other.sol','contract Other {}'),('report.txt','原始报告'),
                                  ('patch.sol','contract Patched {}')):
                (root/name).write_text(content)
            ledger['sources'][0].update(licenseStatus='VERIFIED', license='MIT', sourceStatus='VERIFIED',
                                        reportStatus='VERIFIED', patchStatus='VERIFIED')
            row = ledger['samples'][0]
            row.update(labelStatus='REVIEWED', vulnerabilityType='ACCESS_CONTROL', vulnerabilityLine=1,
                       truthReviewerType='INDEPENDENT', truthReviewer='reviewer', truthReviewVersion='v1',
                       truthEvidence=['report','patch'], artifacts=[
                           {'id':'other','kind':'SOURCE','path':'other.sol','sha256':H((root/'other.sol').read_text()),'groupId':'pair1'},
                           {'id':'report','kind':'REPORT','path':'report.txt','sha256':H((root/'report.txt').read_text()),'groupId':'pair1'},
                           {'id':'patch','kind':'PATCH','path':'patch.sol','sha256':H((root/'patch.sol').read_text()),'groupId':'pair1'}])
            self.assertIn('a', audit_lineage(ledger, root)['pendingSamples'])

    def test_project_event_patch_clone_and_artifacts_cannot_cross_split(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ledger = self.ledger(root)
            self.assertTrue(audit_lineage(ledger, root)['ok'])
            for key in ('projectId', 'eventId', 'patchPairId'):
                altered = json.loads(json.dumps(ledger)); altered['samples'][1][key] = altered['samples'][0][key]
                self.assertFalse(audit_lineage(altered, root)['ok'], key)
            altered = json.loads(json.dumps(ledger)); altered['samples'][1]['cloneGroups'] = ['clone']
            altered['samples'][0]['cloneGroups'] = ['clone']
            self.assertFalse(audit_lineage(altered, root)['ok'])
            altered = json.loads(json.dumps(ledger)); altered['samples'][1]['artifacts'][0]['groupId'] = 'pair1'
            self.assertFalse(audit_lineage(altered, root)['ok'])
            altered = json.loads(json.dumps(ledger)); altered['edges'] = [{'left': 'a', 'right': 'b', 'kind': 'NEAR_CLONE', 'reviewed': False}]
            self.assertFalse(audit_lineage(altered, root)['ok'])

    def test_unreviewed_and_unknown_judgment_remain_in_denominator(self):
        labels = [{'targetId':'t','caseId':'a','reviewStatus':'REVIEWED','reviewer':'human','reviewerType':'INDEPENDENT','labelVersion':'v1','pairId':'pair',
                   'evidence':['line:1'],'applicability':3,'support':'YES','contrast':'NO'},
                  {'targetId':'t','caseId':'b','reviewStatus':'PENDING','reviewer':None,'pairId':'pair',
                   'evidence':[],'applicability':None,'support':'UNKNOWN','contrast':'UNKNOWN'}]
        validate_judgments(labels, 't', {'a','b'})
        score = score_sample(['a','b'], labels, 't', 2)
        self.assertEqual(1, score['unknownSelected'])
        self.assertIsNone(score['recallAtK'])
        self.assertIsNone(score['ndcgAtK'])

    def test_full_prompt_budget_counts_fixed_sections(self):
        count = lambda prompt: len(prompt)
        base = {'system':'系统','source':'源码','question':'问题','tool':'工具','format':'格式'}
        rows = [{'caseId':'a','chunkId':'a','role':'DEFENSE','text':'案例一'}, {'caseId':'b','chunkId':'b','role':'VULNERABLE','text':'案例二'}]
        selected, used, overhead = token_budget_select(rows, base, count, 16)
        self.assertGreater(overhead, 0)
        self.assertLessEqual(used, 16)
        self.assertEqual(0, len(selected))

    def test_d2_unknown_is_not_safe(self):
        out = d2_baselines('function f() public { require(msg.sender == owner); x = 1; }',
                           {'id':'h','truth':'UNKNOWN','guardLine':None})
        self.assertEqual('UNKNOWN', out['judgment'])
        self.assertEqual('UNKNOWN', out['guardLine'])


    def test_locked_source_is_never_opened_during_audit_or_pilot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ledger = self.ledger(root)
            row = json.loads(json.dumps(ledger['samples'][1]))
            row.update(id='locked', path='sealed/does-not-exist.sol', sourceHash='f'*64,
                       split='locked-test',projectId='sealed-project',eventId='sealed-event',patchPairId='sealed-pair',artifacts=[])
            ledger['samples'].append(row)
            with self.assertRaisesRegex(ValueError, '封存'):
                audit_lineage(ledger,root)
            ledger['lockedAttestation']={'status':'REVIEWED','covers':['locked'],
                'fingerprint':'f'*64,'reviewer':'independent-curator','evidence':['sealed-audit:1']}
            with self.assertRaisesRegex(ValueError,'封存'):
                audit_lineage(ledger,root)

    def test_shared_pool_field_filter_and_ablations(self):
        def case(ident,role,pair,score):
            return {'caseId':ident,'chunkId':ident,'pairId':pair,'role':role,'denseScore':score,'text':ident,
                    'reviewed':True,'mechanism':'ACCESS_CONTROL','riskKind':'WRITE',
                    'conditions':[{'predicate':'CHECK_BEFORE','subject':'$actor','resource':'$authority','expected':role=='DEFENSE'}]}
        bad=case('bad','VULNERABLE','p',.9); good=case('good','DEFENSE','p',.8)
        pool={'candidates':[bad,good]}
        rows=[]
        for name in ('DENSE','HYBRID','CONTRASTIVE','D1'):
            selected=[{'candidate':good,'use':'SUPPORT'},{'candidate':bad,'use':'CONTRAST'}] if name=='D1' else [{'candidate':bad,'use':'RETRIEVED'},{'candidate':good,'use':'RETRIEVED'}]
            rows.append({'strategy':name,'poolHash':'a'*64,'selected':selected,
                         'evaluations':{'bad':{'applicability':'CONTRADICTED'},'good':{'applicability':'SUPPORTED'}}})
        result=strategies({'results':rows},pool)
        self.assertEqual(['bad','good'],[c['caseId'] for c in result['FIELD_FILTER']])
        self.assertEqual(['bad','good'],[c['caseId'] for c in result['D1_NO_BINDING']])
        self.assertEqual(['good'],[c['caseId'] for c in result['D1_NO_COMPLEMENT']])

    def test_d2_true_label_requires_evidence_and_unknown_stays_unknown(self):
        row={'id':'h','sourceHash':'a'*64,'riskLine':3,'claim':'可重入','attackPath':'调用后更新',
             'sourceRef':'contract.sol:3','truth':'TRUE','originType':'REAL_PATCH','reviewStatus':'PENDING',
             'obligations':{k:'UNKNOWN' for k in ('actor','resource','beforeRisk','entryCoverage','stateVersion','bypass')}}
        with self.assertRaises(ValueError): validate_d2_challenges([row])
        row.update(truth='UNKNOWN')
        self.assertTrue(validate_d2_challenges([row]))


    def test_shared_derived_report_hash_connects_different_projects(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); ledger=self.ledger(root)
            ledger['samples'][1]['artifacts'][0].update(path='a.sol',sha256=H((root/'a.sol').read_text()))
            self.assertFalse(audit_lineage(ledger,root)['ok'])

    def test_prompt_overhead_above_limit_is_error(self):
        base={'system':'aaaa','source':'bbbb','question':'cccc','tool':'dddd','format':'eeee'}
        with self.assertRaises(ValueError): token_budget_select([],base,len,1)

    def test_guard_in_comment_is_not_present(self):
        row={'id':'h','truth':'UNKNOWN','guardLine':None}
        result=d2_baselines('// require(msg.sender == owner);\nfunction f() public { x = 1; }',row)
        self.assertEqual('ABSENT',result['guardPresence'])


    def test_identifier_renaming_is_near_clone_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); ledger=self.ledger(root)
            first='contract Vault { uint balances; function withdraw(uint amount) public { balances = amount; } }'
            second='contract Safe { uint credits; function redeem(uint value) public { credits = value; } }'
            for ident,text in [('a',first),('b',second)]:
                file=root/(ident+'.sol'); file.write_text(text)
                row=next(r for r in ledger['samples'] if r['id']==ident)
                row['sourceHash']=H(text); row['artifacts'][0]['sha256']=H(text)
            result=audit_lineage(ledger,root)
            self.assertFalse(result['ok'])
            self.assertTrue(any(e['kind']=='NEAR_CLONE_CANDIDATE' for e in result['errors']))


    def test_candidate_text_cannot_hide_target_or_locked_content(self):
        from storage import decode
        base=Path('docs/vibe/releases/R1-S3/evidence/demo')
        ledger=decode((base/'ledger.json').read_bytes())
        plan=decode((base/'plan.json').read_bytes())
        labels=decode((base/'judgments.json').read_bytes())
        with tempfile.TemporaryDirectory() as td:
            request=decode(Path(plan['targets'][0]['request']).read_bytes())
            request['pool']['candidates'][0]['text']='合约目标的隐藏正文'
            path=Path(td)/'tampered.json'; path.write_text(json.dumps(request,ensure_ascii=False))
            plan['targets'][0]['request']=str(path)
            with self.assertRaisesRegex(ValueError,'候选正文'):
                run(ledger,'.',plan,labels,base/'codepoint_tokenizer.py','absent.jar','absent.py')


    def test_d2_unknown_and_failure_have_separate_denominators(self):
        summary=d2_denominators([{'truth':'TRUE','judgment':'UNKNOWN'},
                                 {'truth':'FALSE','judgment':'FAILED'}])
        self.assertEqual((2,1,1),(summary['planned'],summary['unknown'],summary['failed']))
        self.assertIsNone(summary['falseAcceptRate'])

    def test_d2_unknown_truth_with_definite_prediction_remains_counted(self):
        summary = d2_denominators([{'truth':'UNKNOWN','judgment':'TRUE'}])
        self.assertEqual(1, summary['unknownTruthDecisions'])
        self.assertEqual(0, summary['knownDecisions'])
        self.assertIsNone(summary['falseAcceptRate'])

    def test_s2_timeout_is_recorded_as_failed_sample(self):
        from storage import decode
        base = Path('docs/vibe/releases/R1-S3/evidence/demo')
        ledger = decode((base/'ledger.json').read_bytes())
        plan = decode((base/'plan.json').read_bytes())
        labels = decode((base/'judgments.json').read_bytes())
        with mock.patch('s3_pilot.tokenizer_adapter', return_value=len), mock.patch(
                's3_pilot.subprocess.run', side_effect=subprocess.TimeoutExpired('java', 30)):
            result = run(ledger, '.', plan, labels, base/'codepoint_tokenizer.py', 'missing.jar', 'missing.py')
        self.assertEqual(1, result['denominators']['failed'])
        self.assertEqual('FAILED', result['samples'][0]['status'])
        self.assertIsNone(result['samples'][0]['usage'])

if __name__ == '__main__': unittest.main()
