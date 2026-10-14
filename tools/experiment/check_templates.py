"""知识配对检查模板及保守实例化；保持原召回、排序、快照和条件 UNKNOWN。"""
import hashlib
import json
from pathlib import Path

from storage import fingerprint


def verify_templates(templates, snapshot):
    """逐个核对知识来源与两个冻结文档，不能用案例名替代原字节。"""
    samples = {s['id']: s for s in snapshot['manifest']['samples']}
    documents = {d['id']: d for d in snapshot['documents']}
    seen = set()
    for template in templates:
        if template['id'] in seen:
            raise ValueError('模板 ID 重复')
        seen.add(template['id'])
        source = samples.get(template['pairId'], {})
        if (source.get('split') != 'knowledge' or source.get('source_hash') != template['sourceHash']
                or source.get('origin') != template['origin']):
            raise ValueError('模板知识划分或来源身份不一致')
        if len(template['chunks']) != 2:
            raise ValueError('模板缺完整变化前后原件')
        for chunk in template['chunks']:
            document = documents.get(chunk['chunkId'], {})
            if (document.get('sample_id') != template['pairId']
                    or hashlib.sha256(document.get('text', '').encode()).hexdigest() != chunk['sha256']):
                raise ValueError('模板原件字节身份不一致')
        if template['mechanism'] not in {'ACCESS_CONTROL', 'REENTRANCY'}:
            raise ValueError('模板超出冻结机制')
    return templates


def instantiate_template(template, operation, fact):
    """入口、声明／索引／字段和实际路径分别绑定；未决槽不填写猜测值。"""
    resource = fact.get('resource') if fact else None
    slots = {'entry': {'contract': operation['contract'], 'signature': operation['entrySignature'],
                      'declarationId': operation['entryDeclarationId']},
             'resource': resource, 'stateVersion': None, 'path': None,
             'operation': {'factId': operation['factId'], 'kind': operation['riskOperation'],
                           'sourceUnit': operation['sourceUnit'], 'span': operation['span']}}
    unbound = [key for key in template['requiredSlots'] if slots.get(key) is None]
    return {'schemaVersion': 'template-instance-1', 'templateId': template['id'],
        'templateVersion': template['version'], 'templateHash': fingerprint(template),
        'status': 'PARTIAL' if unbound else 'BOUND', 'slots': slots, 'unboundSlots': unbound,
        'applicability': 'UNKNOWN', 'sourceReferences': template['chunks'],
        'targetReferences': [{'factId': operation['factId'], 'sourceUnit': operation['sourceUnit'],
                              'span': operation['span']}],
        'reason': '结构绑定独立于适用性；状态版本及正常提交路径须由 D2 证据建立'}


def render_template(template, instances, max_bytes=4096):
    """预算不够时整条拒绝，保留必要前提、来源和未绑定槽。"""
    text = ('【检查模板·未经审核·条件 UNKNOWN】\n' + template['id'] + '：' + template['question']
        + '\n适用前提：' + '；'.join(template['prerequisites'])
        + '\n检查步骤：' + '；'.join(template['steps'])
        + '\n来源：' + template['pairId'] + '；' + template['origin']
        + '\n实例：' + json.dumps(instances, ensure_ascii=False, separators=(',', ':')) + '\n')
    return text if len(text.encode()) <= max_bytes else None


def prepare_template_presentation(root, view, snapshot):
    """只为已入选配对提供新呈现，不重新检索，也不覆盖原上下文。"""
    path = Path(root) / 'data/audit/r2/check-templates.json'
    if not path.is_file():
        return
    registry = json.loads(path.read_text())
    if registry['snapshotId'] != view.get('snapshotId'):
        view['templatePresentation'] = {'status': 'UNAVAILABLE', 'reason': '知识快照不同'}
        return
    templates = verify_templates(registry['templates'], snapshot)
    selected = {item['candidate']['pairId'] for item in view['d1'].get('selected', [])}
    facts = {fact['id']: fact for fact in view.get('compiledFacts', {}).get('facts', [])}
    operations = view.get('riskCatalog', {}).get('operations', [])
    parts, instances, accepted, rejected, used = [], [], [], [], 0
    for template in templates:
        if template['pairId'] not in selected or template['mechanism'] != view.get('targetMechanism'):
            continue
        bound = [instantiate_template(template, operation, facts.get(operation['factId']))
                 for operation in operations if (operation['riskOperation'] == 'WRITE')
                    == (template['mechanism'] == 'ACCESS_CONTROL')]
        text = render_template(template, bound, 4096 - used)
        if text is None:
            rejected.append({'templateId': template['id'], 'reason': '完整模板及实例超出剩余预算'})
            continue
        parts.append(text); instances.extend(bound); accepted.append(template['id']); used += len(text.encode())
    view['templatePresentation'] = {'schemaVersion': 'template-presentation-1',
        'status': 'AVAILABLE' if accepted else 'NO_MATCH', 'context': ''.join(parts),
        'contextSha256': hashlib.sha256(''.join(parts).encode()).hexdigest(), 'usedBytes': used,
        'maxBytes': 4096, 'templateIds': accepted, 'instances': instances, 'rejected': rejected,
        'registryHash': fingerprint(registry), 'selectedPairIds': sorted(selected),
        'consumedByModel': False, 'applicability': 'UNKNOWN',
        'reason': '首期提供独立可审查呈现；默认请求仍消费原配对上下文'}
