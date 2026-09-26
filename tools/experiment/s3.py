"""S3 离线谱系门禁、人工判断与可证伪检索指标。"""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from storage import decode, encode, fingerprint

SPLITS = {'knowledge', 'development', 'validation', 'locked-test'}
SOLIDITY_KEYWORDS = {'contract','function','public','external','internal','private','view','pure','payable','returns','return','if','else','for','while','require','assert','address','uint','int','bool','string','bytes','mapping','memory','storage','calldata','msg','sender','tx','origin','call','send','transfer','modifier','event','error','true','false'}
ORIGINS = {'REAL_PATCH', 'REAL_UNPAIRED', 'MANUAL_VARIANT', 'SYNTHETIC'}
KINDS = {'SOURCE', 'REPORT', 'SUMMARY', 'KNOWLEDGE', 'TEMPLATE', 'PATCH'}


def _needed(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' 缺失')
    return value


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _file(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in relative:
        raise ValueError('来源路径必须在根目录内')
    target = (Path(root) / path).resolve()
    if not target.is_relative_to(Path(root).resolve()) or not target.is_file():
        raise ValueError('来源文件缺失或越界')
    return target.read_bytes()


def _tokens(data):
    text = data.decode('utf-8')
    text = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*', ' ', text)
    parts = re.findall(r'[A-Za-z_$][\w$]*|\d+|[^\s]', text)
    parts = [v if v in SOLIDITY_KEYWORDS else ('NUM' if v[0].isdigit() else 'ID' if re.fullmatch(r'[A-Za-z_$][\w$]*',v) else v) for v in parts]
    return set(tuple(parts[i:i+5]) for i in range(max(0,len(parts)-4)))


def _research_evidence_ready(row, source, raw):
    if row['originType'] != 'REAL_PATCH' or row['labelStatus'] != 'REVIEWED': return False
    if any(source[field] != 'VERIFIED' for field in ('licenseStatus','sourceStatus','reportStatus','patchStatus')):
        return False
    if not isinstance(row.get('vulnerabilityType'), str) or not row['vulnerabilityType'].strip(): return False
    line = row.get('vulnerabilityLine')
    if type(line) is not int or line <= 0 or line > len(raw.splitlines()): return False
    if row.get('truthReviewerType') != 'INDEPENDENT' or not row.get('truthReviewer') or not row.get('truthReviewVersion'):
        return False
    artifacts = row['artifacts']
    by_kind = {kind:[item for item in artifacts if item['kind'] == kind]
               for kind in ('SOURCE','REPORT','PATCH')}
    if any(not items for items in by_kind.values()): return False
    if not any(item['path'] == row['path'] and item['sha256'] == row['sourceHash']
               for item in by_kind['SOURCE']): return False
    if any(item['path'] == row['path'] for kind in ('REPORT','PATCH') for item in by_kind[kind]): return False
    if not any(report['path'] != patch['path'] and report['sha256'] != patch['sha256']
               for report in by_kind['REPORT'] for patch in by_kind['PATCH']): return False
    evidence = row.get('truthEvidence')
    if not isinstance(evidence, list) or not all(isinstance(value, str) for value in evidence): return False
    names = set(evidence)
    return all(any(item['id'] in names for item in by_kind[kind]) for kind in ('REPORT','PATCH'))


def audit_lineage(ledger, root, near_threshold=.85):
    if not isinstance(ledger, dict) or ledger.get('schemaVersion') != '1':
        raise ValueError('谱系清单版本无效')
    sources, samples, edges = ledger.get('sources'), ledger.get('samples'), ledger.get('edges')
    if not isinstance(sources, list) or not isinstance(samples, list) or not isinstance(edges, list):
        raise ValueError('谱系清单结构无效')
    if not sources or not samples: raise ValueError('来源和样本清单不能为空')
    source_ids = set()
    for source in sources:
        if not isinstance(source, dict) or source.get('id') in source_ids:
            raise ValueError('来源 ID 重复或无效')
        source_ids.add(_needed(source.get('id'), '来源 ID'))
        _needed(source.get('url'), '来源 URL')
        _needed(source.get('revision'), '来源版本')
        for field in ('licenseStatus', 'sourceStatus', 'reportStatus', 'patchStatus'):
            if source.get(field) not in ('VERIFIED', 'PENDING', 'UNAVAILABLE'):
                raise ValueError('来源状态无效')
        if source['licenseStatus'] == 'VERIFIED': _needed(source.get('license'), '许可证')
    locked = [r.get('id') for r in samples if isinstance(r,dict) and r.get('split') == 'locked-test']
    if locked:
        raise ValueError('锁定测试封存证明无法由本切片核验，拒绝准入且不打开源码')
    ids, groups, files, errors, warnings = {}, {}, {}, [], []
    links = []
    for row in samples:
        if not isinstance(row, dict): raise ValueError('样本条目无效')
        identifier = _needed(row.get('id'), '样本 ID')
        if identifier in ids: raise ValueError('样本 ID 重复')
        if row.get('sourceId') not in source_ids: raise ValueError('未知来源')
        if row.get('split') not in SPLITS or row.get('originType') not in ORIGINS:
            raise ValueError('划分或样本类型无效')
        if row.get('labelStatus') not in ('REVIEWED', 'PENDING', 'DISPUTED'):
            raise ValueError('标签审核状态无效')
        if not _hash(row.get('sourceHash')): raise ValueError('源码摘要无效')
        _needed(row.get('path'), '源码路径')
        if row['split'] == 'locked-test':
            files[identifier] = None
        else:
            raw = _file(root, row['path'])
            if hashlib.sha256(raw).hexdigest() != row['sourceHash']: raise ValueError('源码摘要不符')
            files[identifier] = raw
        keys = [('project', row.get('projectId')), ('event', row.get('eventId')),
                ('patch', row.get('patchPairId')), ('exact', row['sourceHash'])]
        clones = row.get('cloneGroups')
        if not isinstance(clones, list) or len(clones) != len(set(clones)):
            raise ValueError('克隆分组无效')
        keys += [('clone', clone) for clone in clones]
        artifacts = row.get('artifacts')
        if not isinstance(artifacts, list): raise ValueError('衍生材料列表缺失')
        for item in artifacts:
            if not isinstance(item, dict) or item.get('kind') not in KINDS or not _hash(item.get('sha256')):
                raise ValueError('衍生材料字段无效')
            _needed(item.get('id'), '材料 ID')
            group = _needed(item.get('groupId'), '材料组 ID')
            if group != row['patchPairId']:
                errors.append({'kind':'ARTIFACT_INHERITANCE', 'samples':[identifier], 'group':group})
            _needed(item.get('path'), '材料路径')
            if row['split'] != 'locked-test' and hashlib.sha256(_file(root, item['path'])).hexdigest() != item['sha256']:
                raise ValueError('衍生材料摘要不符')
            keys.extend([('artifact', group), ('artifact-bytes', item['sha256']), ('artifact-path', item['path'])])
        for kind, value in keys:
            key = (kind, _needed(value, kind + ' ID'))
            prior = groups.get(key)
            if prior: links.append((prior[0], identifier))
            if prior and prior[1] != row['split']:
                errors.append({'kind':kind.upper(), 'samples':[prior[0], identifier], 'group':value})
            groups[key] = (identifier, row['split'])
        ids[identifier] = row
    for edge in edges:
        if not isinstance(edge, dict) or edge.get('left') not in ids or edge.get('right') not in ids:
            raise ValueError('关联边引用无效')
        if edge.get('kind') not in ('SAME_PROJECT', 'SAME_EVENT', 'PATCH_PAIR', 'NEAR_CLONE') or type(edge.get('reviewed')) is not bool:
            raise ValueError('关联边类型无效')
        links.append((edge['left'], edge['right']))
        if ids[edge['left']]['split'] != ids[edge['right']]['split']:
            errors.append({'kind':edge['kind'], 'samples':[edge['left'], edge['right']], 'reviewed':edge['reviewed']})
    keys = sorted(ids)
    token_sets = {key:_tokens(files[key]) for key in keys if files[key] is not None}
    for i, left in enumerate(keys):
        for right in keys[i+1:]:
            if left not in token_sets or right not in token_sets: continue
            a, b = token_sets[left], token_sets[right]
            score = len(a & b) / len(a | b) if a | b else 1.0
            if score >= near_threshold and ids[left]['sourceHash'] != ids[right]['sourceHash']:
                item = {'kind':'NEAR_CLONE_CANDIDATE', 'samples':[left,right], 'jaccard':round(score, 6)}
                links.append((left,right))
                if ids[left]['split'] != ids[right]['split']: errors.append(item)
                else: warnings.append(item)
    parent = {identifier:identifier for identifier in ids}
    def find(identifier):
        while parent[identifier] != identifier:
            parent[identifier] = parent[parent[identifier]]
            identifier = parent[identifier]
        return identifier
    for left,right in links:
        parent[find(right)] = find(left)
    components = {}
    for identifier in sorted(ids): components.setdefault(find(identifier),[]).append(identifier)
    group_ids = {identifier:fingerprint(members) for members in components.values() for identifier in members}
    source_by_id = {source['id']:source for source in sources}
    pending = [row['id'] for row in samples if not _research_evidence_ready(
        row, source_by_id[row['sourceId']], files[row['id']])]
    return {'schemaVersion':'1', 'ledgerHash':fingerprint(ledger), 'ok':not errors,
            'errors':errors, 'nearCloneCandidates':warnings, 'pendingSamples':pending,
            'sampleCount':len(samples), 'lockedNotOpened':len(locked), 'groupIds':group_ids, 'splitCounts':{split:sum(r['split']==split for r in samples) for split in sorted(SPLITS)}}


def validate_judgments(labels, target_id, case_ids):
    if not isinstance(labels, list): raise ValueError('人工判断必须是列表')
    seen = set()
    for row in labels:
        if not isinstance(row, dict) or row.get('targetId') != target_id or row.get('caseId') not in case_ids:
            raise ValueError('人工判断引用目标或案例无效')
        if row['caseId'] in seen: raise ValueError('重复人工判断')
        seen.add(row['caseId'])
        if row.get('reviewStatus') not in ('REVIEWED', 'PENDING', 'DISPUTED'):
            raise ValueError('判断审核状态无效')
        _needed(row.get('pairId'), '判断配对 ID')
        if row['reviewStatus'] == 'REVIEWED':
            if row.get('reviewerType') not in ('INDEPENDENT','FIXTURE') or not row.get('labelVersion'):
                raise ValueError('已审核判断缺少审查角色或标签版本')
            if row.get('applicability') not in (0,1,2,3) or not row.get('reviewer') or not row.get('evidence'):
                raise ValueError('已审核判断缺少等级、审查者或证据')
        elif row.get('applicability') is not None:
            raise ValueError('待审判断不能填入相关性真值')
        if row.get('support') not in ('YES','NO','UNKNOWN') or row.get('contrast') not in ('YES','NO','UNKNOWN'):
            raise ValueError('支持/反证标签无效')
        if row['reviewStatus'] != 'REVIEWED' and (row['support'] != 'UNKNOWN' or row['contrast'] != 'UNKNOWN'):
            raise ValueError('待审价值必须保持 UNKNOWN')
    if seen != case_ids: raise ValueError('判断必须覆盖完整候选池')


def score_sample(selected, labels, target_id, k):
    cases = {row['caseId']:row for row in labels if row['targetId'] == target_id}
    if type(k) is not int or k <= 0 or not set(selected) <= cases.keys(): raise ValueError('指标输入无效')
    if len(selected) != len(set(selected)): raise ValueError('同一案例不得重复计分')
    ranked = selected[:k]
    unknown_pool = sum(r['reviewStatus'] != 'REVIEWED' for r in cases.values())
    unknown_selected = sum(cases[c]['reviewStatus'] != 'REVIEWED' for c in ranked)
    known = [cases[c] for c in ranked if cases[c]['reviewStatus'] == 'REVIEWED']
    positive = sum(r['applicability'] >= 2 for r in cases.values() if r['reviewStatus']=='REVIEWED')
    recall = None
    ndcg = None
    if unknown_pool == 0 and positive:
        recall = sum(cases[c]['applicability'] >= 2 for c in ranked) / positive
        dcg = sum((2**cases[c]['applicability']-1)/math.log2(i+2) for i,c in enumerate(ranked))
        ideal = sorted((r['applicability'] for r in cases.values()), reverse=True)[:k]
        idcg = sum((2**v-1)/math.log2(i+2) for i,v in enumerate(ideal))
        ndcg = dcg/idcg if idcg else None
    wrong = sum(r['applicability'] == 0 for r in known)
    supports = {r['pairId'] for r in known if r['support']=='YES' and r['applicability']>=2}
    contrasts = {r['pairId'] for r in known if r['contrast']=='YES' and r['applicability']>=2}
    complementary = any(any(a['caseId'] != b['caseId'] and a['pairId']==b['pairId']==pair
        and a['support']=='YES' and b['contrast']=='YES' for a in known for b in known) for pair in supports & contrasts)
    return {'recallAtK':recall,'ndcgAtK':ndcg,'wrongSelectedRate':wrong/len(known) if known else None,
            'wrongSelected':wrong,'knownSelected':len(known),'unknownSelected':unknown_selected,
            'unknownPool':unknown_pool,'positiveKnown':positive,
            'complementCoverage':complementary if unknown_pool == 0 else None}


def _render(base, rows):
    return '\n'.join([base[key] for key in ('system','source','question','tool','format')]
                     + [f"[{row['caseId']}/{row['chunkId']}|{row['role']}]\n{row['text']}\n" for row in rows])


def token_budget_select(rows, base, count, limit):
    if type(limit) is not int or limit <= 0 or any(not isinstance(base.get(k),str) for k in ('system','source','question','tool','format')):
        raise ValueError('提示预算无效')
    overhead = count(_render(base, []))
    if overhead > limit: raise ValueError('固定提示已超过 token 上限')
    chosen = []
    seen = set()
    for row in rows:
        if row['caseId'] in seen: continue
        seen.add(row['caseId'])
        trial = chosen + [row]
        if count(_render(base, trial)) <= limit: chosen = trial
    return chosen, count(_render(base, chosen)), overhead


def validate_d2_challenges(challenges):
    if not isinstance(challenges,list): raise ValueError('D2 挑战清单无效')
    seen = set()
    for row in challenges:
        if not isinstance(row,dict): raise ValueError('D2 假设条目无效')
        identifier = _needed(row.get('id'),'假设 ID')
        if identifier in seen or not _hash(row.get('sourceHash')) or type(row.get('riskLine')) is not int or row['riskLine'] <= 0:
            raise ValueError('D2 假设位置或源码摘要无效')
        seen.add(identifier)
        for field in ('claim','attackPath','sourceRef'): _needed(row.get(field),field)
        if row.get('truth') not in ('TRUE','FALSE','UNKNOWN') or row.get('originType') not in ORIGINS:
            raise ValueError('D2 真值或来源类型无效')
        if row['truth'] != 'UNKNOWN' and (row.get('reviewStatus') != 'REVIEWED' or not row.get('truthEvidence')):
            raise ValueError('D2 真值缺少独立审核证据')
        if row['truth'] == 'UNKNOWN' and row.get('reviewStatus') == 'REVIEWED':
            raise ValueError('未知真值不能标为已审核')
        obligations = row.get('obligations')
        if not isinstance(obligations,dict) or set(obligations) != {'actor','resource','beforeRisk','entryCoverage','stateVersion','bypass'} or any(
            v not in ('SUPPORTED','REFUTED','UNKNOWN') for v in obligations.values()):
            raise ValueError('保护覆盖义务无效')
    return True


def d2_denominators(results):
    if not isinstance(results,list): raise ValueError('D2 结果无效')
    counts={'planned':len(results),'falseAccept':0,'falseReject':0,'unknown':0,'failed':0,
            'unknownTruthDecisions':0,'knownDecisions':0,'knownTrueDecisions':0,'knownFalseDecisions':0}
    for row in results:
        truth, judgment = row.get('truth'),row.get('judgment')
        if truth not in ('TRUE','FALSE','UNKNOWN') or judgment not in ('TRUE','FALSE','UNKNOWN','FAILED'):
            raise ValueError('D2 真值或判断无效')
        if judgment=='FAILED': counts['failed']+=1
        elif judgment=='UNKNOWN': counts['unknown']+=1
        elif truth=='UNKNOWN': counts['unknownTruthDecisions']+=1
        else:
            counts['knownDecisions']+=1
            counts['knownTrueDecisions' if truth=='TRUE' else 'knownFalseDecisions']+=1
            if truth=='TRUE' and judgment=='FALSE': counts['falseReject']+=1
            if truth=='FALSE' and judgment=='TRUE': counts['falseAccept']+=1
    counts['falseAcceptRate']=counts['falseAccept']/counts['knownFalseDecisions'] if counts['knownFalseDecisions'] else None
    counts['falseRejectRate']=counts['falseReject']/counts['knownTrueDecisions'] if counts['knownTrueDecisions'] else None
    return counts


def d2_baselines(source, hypothesis):
    if not isinstance(hypothesis, dict) or hypothesis.get('truth') not in ('TRUE','FALSE','UNKNOWN'):
        raise ValueError('固定假设真值无效')
    scrubbed = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|\"(?:\\.|[^\"\\])*\"',
                     lambda match: ''.join('\n' if ch=='\n' else ' ' for ch in match.group()), source)
    guards = [(i,line.strip()) for i,line in enumerate(scrubbed.splitlines(),1)
              if re.search(r'\b(require|assert)\s*\(', line)]
    requested = hypothesis.get('guardLine')
    if requested is not None and (type(requested) is not int or requested <= 0): raise ValueError('防护行无效')
    return {'hypothesisId':_needed(hypothesis.get('id'),'假设 ID'),
            'guardPresence':'PRESENT' if guards else 'ABSENT',
            'guardLine':'PRESENT' if requested is not None and any(i==requested for i,_ in guards) else 'UNKNOWN',
            'judgment':'UNKNOWN', 'truth':hypothesis['truth'], 'guardEvidence':guards,
            'obligations':{key:'UNKNOWN' for key in ('actor','resource','beforeRisk','entryCoverage','stateVersion','bypass')},
            'usage':None}


def main():
    parser = argparse.ArgumentParser(description='S3 离线来源谱系与标签校验')
    sub = parser.add_subparsers(dest='command', required=True)
    lineage = sub.add_parser('lineage'); lineage.add_argument('--ledger',required=True); lineage.add_argument('--root',required=True)
    args = parser.parse_args()
    try:
        report = audit_lineage(decode(Path(args.ledger).read_bytes()), args.root)
        print(encode(report).decode())
        return 0 if report['ok'] else 1
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as error:
        parser.exit(2, 'S3 清单校验失败：'+str(error)+'\n')

if __name__ == '__main__': raise SystemExit(main())
