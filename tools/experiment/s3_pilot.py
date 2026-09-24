"""S3 同池离线检索先导；真实模型 tokenizer 由显式冻结适配器提供。"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from s3 import audit_lineage, score_sample, token_budget_select, validate_judgments
from storage import decode, encode, fingerprint, durable_write


def _text(path): return Path(path).read_text(encoding='utf-8')


def tokenizer_adapter(path, expected_hash):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('tokenizer 代码摘要不符')
    def count(prompt):
        result = subprocess.run([sys.executable, str(path)], input=encode({'prompt':prompt}),
                                capture_output=True, timeout=10, check=True)
        if len(result.stdout) > 256 or result.stderr: raise ValueError('tokenizer 输出无效')
        value = decode(result.stdout)
        if not isinstance(value,dict) or set(value) != {'tokens'} or type(value['tokens']) is not int or value['tokens'] < 0:
            raise ValueError('tokenizer 计数无效')
        return value['tokens']
    return count


def _cases(selections):
    return [row['candidate'] for row in selections]


def strategies(comparison, pool):
    results = {row['strategy']: _cases(row['selected']) for row in comparison['results']}
    if set(results) != {'DENSE','HYBRID','CONTRASTIVE','D1'}: raise ValueError('S2 对照策略不完整')
    if len({row['poolHash'] for row in comparison['results']}) != 1: raise ValueError('候选池摘要不一致')
    evaluations = comparison['results'][0]['evaluations']
    candidates = pool['candidates']
    results['FIELD_FILTER'] = sorted((c for c in candidates if evaluations[c['chunkId']]['applicability'] in ('SUPPORTED','CONTRADICTED')),
                                     key=lambda c:(-c['denseScore'],c['caseId'],c['chunkId']))
    results['D1_NO_COMPLEMENT'] = [row['candidate'] for row in next(row for row in comparison['results'] if row['strategy']=='D1')['selected'] if row['use']=='SUPPORT']
    by_pair = {}
    for candidate in candidates: by_pair.setdefault(candidate['pairId'], []).append(candidate)
    raw_pairs = []
    for pair in by_pair.values():
        left = sorted((c for c in pair if c['role']=='VULNERABLE'),key=lambda c:(-c['denseScore'],c['chunkId']))
        right = sorted((c for c in pair if c['role']=='DEFENSE'),key=lambda c:(-c['denseScore'],c['chunkId']))
        if (left and right and left[0]['caseId'] != right[0]['caseId'] and left[0]['reviewed'] and right[0]['reviewed']
                and left[0]['mechanism']==right[0]['mechanism'] and left[0]['riskKind']==right[0]['riskKind']
                and { (v['predicate'],v['subject'],v['resource']) for v in left[0]['conditions'] } ==
                    { (v['predicate'],v['subject'],v['resource']) for v in right[0]['conditions'] }
                and any(a['expected'] != b['expected'] for a in left[0]['conditions'] for b in right[0]['conditions']
                        if (a['predicate'],a['subject'],a['resource'])==(b['predicate'],b['subject'],b['resource']))):
            raw_pairs.append((-(left[0]['denseScore']+right[0]['denseScore']),left[0]['caseId'],left[0],right[0]))
    results['D1_NO_BINDING'] = [c for _,_,left,right in sorted(raw_pairs) for c in (left,right)]
    return results


def run(ledger, root, plan, labels, tokenizer, jar, worker):
    lineage = audit_lineage(ledger, root)
    if not lineage['ok']: raise ValueError('谱系存在跨划分泄漏')
    if plan.get('schemaVersion') != '1' or not isinstance(plan.get('targets'),list) or not plan['targets']: raise ValueError('先导计划无效')
    samples = {r['id']:r for r in ledger['samples']}
    for target in plan['targets']:
        sample = samples.get(target.get('id'))
        if sample is None or sample['split'] not in ('development','validation'):
            raise ValueError('仅允许开发或验证划分；锁定测试不可打开')
    profile = plan.get('tokenProfile')
    if not isinstance(profile,dict) or profile.get('purpose') not in ('FIXTURE','MODEL') or not all(
        isinstance(profile.get(k),str) and profile[k] for k in ('model','version','templateVersion','system','question','tool','format')):
        raise ValueError('完整提示/tokenizer 配置未冻结')
    count = tokenizer_adapter(tokenizer, profile.get('sha256'))
    if profile['purpose']=='MODEL' and (profile.get('attestationStatus')!='REVIEWED' or not profile.get('tokenizerEvidence') or not profile.get('promptTemplateEvidence')):
        raise ValueError('模型 tokenizer 与完整提示模板尚未经独立核验')
    max_tokens = profile.get('maxTokens')
    if type(max_tokens) is not int or max_tokens <= 0: raise ValueError('token 上限无效')
    output = []
    for target in plan['targets']:
        identifier = target.get('id')
        sample = samples.get(identifier)
        if sample is None or sample['split'] not in ('development','validation'):
            raise ValueError('仅允许开发或验证划分；锁定测试不可打开')
        request = decode(Path(target['request']).read_bytes())
        pool = request['pool']
        source = (Path(root)/sample['path']).read_text(encoding='utf-8')
        if sample['sourceHash'] != pool['sourceHash'] or hashlib.sha256(source.encode()).hexdigest() != sample['sourceHash']:
            raise ValueError('目标源码与候选池不一致')
        if request.get('budget',{}).get('maxCases',0) < len(pool['candidates']):
            raise ValueError('S2 案例数量预算先于统一 token 预算截断候选')
        possible_bytes = sum(len((f"[{c['caseId']}/{c['chunkId']}|{c['role']}]\n{c['text']}\n").encode('utf-8')) for c in pool['candidates'])
        if request['budget'].get('maxBytes',0) < possible_bytes:
            raise ValueError('S2 字节预算先于统一 token 预算截断候选')
        case_sources = target.get('caseSamples')
        if not isinstance(case_sources,dict) or set(case_sources) != {c['caseId'] for c in pool['candidates']}:
            raise ValueError('候选谱系未覆盖完整候选池')
        for case_id, sample_id in case_sources.items():
            if sample_id not in samples or samples[sample_id]['split'] != 'knowledge':
                raise ValueError('知识案例来源不在 knowledge')
        for candidate in pool['candidates']:
            origin = samples[case_sources[candidate['caseId']]]
            if candidate['pairId'] != origin['patchPairId'] or not candidate['provenance'].endswith('@'+origin['sourceHash']):
                raise ValueError('候选配对或来源摘要与谱系不符')
            matched = False
            for artifact in origin['artifacts']:
                if artifact['kind'] not in ('SOURCE','KNOWLEDGE'): continue
                content = (Path(root)/artifact['path']).read_bytes()
                if hashlib.sha256(content).hexdigest() == artifact['sha256'] and content.decode('utf-8') == candidate['text']:
                    matched = True
            if not matched: raise ValueError('候选正文未绑定经核验的知识材料')
        relevant = [row for row in labels if row.get('targetId') == identifier]
        validate_judgments(relevant, identifier, set(case_sources))
        pair_by_case = {c['caseId']:c['pairId'] for c in pool['candidates']}
        if any(row['pairId'] != pair_by_case[row['caseId']] for row in relevant):
            raise ValueError('人工判断配对 ID 与候选池不一致')
        cmd = ['java','-jar',str(jar),'--retrieval','--source',str(Path(root)/sample['path']),
               '--request',str(target['request']),'--worker',str(worker),'--strategy','compare']
        try:
            proc = subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        except subprocess.TimeoutExpired:
            output.append({'id':identifier,'projectId':sample['projectId'],'status':'FAILED',
                           'reason':'S2 离线检索超时','usage':None,'strategies':{}})
            continue
        if proc.returncode or len(proc.stdout)>8_388_608:
            output.append({'id':identifier,'projectId':sample['projectId'],'status':'FAILED',
                           'reason':'S2 离线检索失败','usage':None,'strategies':{}})
            continue
        try:
            comparison = decode(proc.stdout)
            if comparison['facts']['sourceHash'] != sample['sourceHash']:
                raise ValueError('事实来源摘要不符')
            candidates = strategies(comparison,pool)
        except (ValueError,KeyError,TypeError):
            output.append({'id':identifier,'projectId':sample['projectId'],'status':'FAILED',
                           'reason':'S2 离线检索解析失败','usage':None,'strategies':{}})
            continue
        base = {k:profile[k] for k in ('system','question','tool','format')}
        base['source']=source
        rows = {}
        for name, ranked in candidates.items():
            selected, used, overhead = token_budget_select(ranked,base,count,max_tokens)
            ids = [c['caseId'] for c in selected]
            metric = score_sample(ids,relevant,identifier,target.get('k',min(5,len(case_sources))))
            breakdown = {}
            judgments = {r['caseId']:r for r in relevant}
            evaluated = comparison['results'][0]['evaluations']
            for candidate in selected:
                label = judgments[candidate['caseId']]
                for condition in evaluated[candidate['chunkId']]['conditions']:
                    key = condition['condition']['predicate'] + ':' + condition['state']
                    bucket = breakdown.setdefault(key,{'selected':0,'wrong':0,'unknownLabel':0})
                    bucket['selected'] += 1
                    bucket['wrong'] += label['reviewStatus']=='REVIEWED' and label['applicability']==0
                    bucket['unknownLabel'] += label['reviewStatus']!='REVIEWED'
            rows[name] = {'selected':ids,'promptTokens':used,'basePromptTokens':overhead,
                          'budgetTokens':max_tokens,'metrics':metric,'conditionBreakdown':breakdown}
        admissible = all(x not in lineage['pendingSamples'] for x in [identifier,*case_sources.values()])
        admissible &= all(r['reviewStatus']=='REVIEWED' and r['reviewerType']=='INDEPENDENT' for r in relevant)
        output.append({'id':identifier,'projectId':sample['projectId'],'originType':sample['originType'],
                       'status':'COMPLETED','researchEligible':admissible and profile['purpose']=='MODEL',
                       'poolHash':comparison['results'][0]['poolHash'],'snapshotId':pool['snapshotId'],
                       'strategies':rows,'usage':None})
    projects = {}
    for row in output: projects.setdefault(row['projectId'],[]).append(row['id'])
    project_metrics = {}
    for project, target_ids in projects.items():
        group = [row for row in output if row['projectId'] == project and row['status']=='COMPLETED']
        if not group: continue
        project_metrics[project] = {'targetIds':target_ids, 'originTypes':sorted({r['originType'] for r in group}),
                                    'researchEligible':all(r['researchEligible'] for r in group), 'strategies':{}}
        for strategy in group[0]['strategies']:
            metrics = {}
            for metric in ('recallAtK','ndcgAtK','wrongSelectedRate','complementCoverage'):
                values = [r['strategies'][strategy]['metrics'][metric] for r in group]
                metrics[metric] = sum(values)/len(values) if all(v is not None for v in values) else None
            project_metrics[project]['strategies'][strategy] = metrics
    by_origin = {}
    for origin in ('REAL_PATCH','MANUAL_VARIANT','SYNTHETIC'):
        units = [v for v in project_metrics.values() if origin in v['originTypes']]
        by_origin[origin] = {'projects':len(units),'targets':sum(len(v['targetIds']) for v in units),
                             'researchEligibleProjects':sum(v['researchEligible'] for v in units)}
    return {'schemaVersion':'1','planHash' :fingerprint(plan),'ledgerHash':lineage['ledgerHash'],
            'lineage':lineage,'tokenProfile':{k:profile[k] for k in ('model','version','templateVersion','purpose','sha256','maxTokens')},
            'samples':output,'projectUnits':projects,'projectMetrics':project_metrics,'byOrigin':by_origin,
            'denominators':{'planned':len(output),'completed':sum(r['status']=='COMPLETED' for r in output),
                'failed':sum(r['status']=='FAILED' for r in output),
                'researchEligible':sum(r.get('researchEligible',False) for r in output),
                'unknownJudgments':sum(max((v['metrics']['unknownPool'] for v in r['strategies'].values()),default=0) for r in output)}}


def main():
    parser=argparse.ArgumentParser(description='S3 同池离线检索证伪先导')
    for key in ('ledger','root','plan','labels','tokenizer','jar','worker','output'):
        parser.add_argument('--'+key,required=True)
    args=parser.parse_args()
    try:
        result=run(decode(Path(args.ledger).read_bytes()),args.root,
                   decode(Path(args.plan).read_bytes()),decode(Path(args.labels).read_bytes()),
                   args.tokenizer,args.jar,args.worker)
        durable_write(args.output,encode(result)+b'\n')
        print(encode(result['denominators']).decode())
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        parser.exit(2,'S3 先导失败：'+str(error)+'\n')

if __name__=='__main__': main()
