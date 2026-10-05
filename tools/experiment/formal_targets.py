"""仅允许固定开发样本进入正式知识快照的本机工程试跑。"""
import hashlib
from pathlib import Path

from first_batch import prepare
from program_facts import _tokens
from s3 import audit_lineage
from storage import decode, fingerprint


INTAKE = Path('docs/vibe/releases/R1-S3/evidence/first-batch-intake.json')
ASSIGNMENT = Path('docs/vibe/releases/R1-S3/evidence/first-batch-assignment.json')
FORMAL_LEDGER = Path('.local/d1-kb-v1/ledger.json')
SOURCE_DIR = '.local/first-batch/sources'
DEVELOPMENT_IDS = frozenset({'AC-ASE-006', 'AC-ASE-009', 'RE-SCRUBD-001', 'RE-SCRUBD-002'})
FUNCTION_SCOPE = {'RE-SCRUBD-001': 'matchOrderWithReserve'}
MAX_MODEL_SOURCE_BYTES = 6000


def _function_range(source, name):
    tokens, pairs = _tokens(source)
    matches = []
    for index, token in enumerate(tokens[:-1]):
        if token[0] != 'function' or tokens[index + 1][0] != name:
            continue
        opening = next((at for at in range(index + 2, len(tokens)) if tokens[at][0] in ('{', ';')), None)
        if opening is None or tokens[opening][0] != '{':
            raise ValueError('工程目标函数没有可核对的函数体')
        matches.append((token[2], tokens[pairs[opening]][2]))
    if len(matches) != 1:
        raise ValueError('工程目标函数不存在或定位不唯一')
    start, end = matches[0]
    lines = source.splitlines()
    return start, end, '\n'.join(lines[start - 1:end])


def _records(root):
    root = Path(root)
    intake = decode((root / INTAKE).read_bytes())
    assignment = decode((root / ASSIGNMENT).read_bytes())
    ledger, old_audit = prepare(intake, assignment, root, SOURCE_DIR)
    if not old_audit['ok']:
        raise ValueError('原开发清单存在谱系隔离错误')
    formal = decode((root / FORMAL_LEDGER).read_bytes())
    targets = [row for row in ledger['samples'] if row['split'] == 'development']
    if {row['id'] for row in targets} != DEVELOPMENT_IDS:
        raise ValueError('已登记开发目标与固定范围不一致')
    target_sources = {row['sourceId'] for row in targets}
    formal_ids = {row['id'] for row in formal['samples']}
    if DEVELOPMENT_IDS & formal_ids:
        raise ValueError('工程开发目标已进入正式知识或验证清单')
    combined = {'schemaVersion': '1', 'sources': formal['sources'] +
                [row for row in ledger['sources'] if row['id'] in target_sources],
                'samples': formal['samples'] + targets,
                'edges': [edge for edge in ledger['edges'] if edge['left'] in DEVELOPMENT_IDS and edge['right'] in DEVELOPMENT_IDS]}
    audit = audit_lineage(combined, root)
    if not audit['ok']:
        raise ValueError('开发目标与正式知识库同组或存在跨划分隔离错误')
    cases = {row['id']: row for row in intake['cases']}
    result = []
    for row in sorted(targets, key=lambda value: value['id']):
        source = (root / row['path']).read_bytes().decode('utf-8')
        name = FUNCTION_SCOPE.get(row['id'])
        if name:
            start, end, model_source = _function_range(source, name)
            scope = 'FUNCTION'
        else:
            start, end, model_source = 1, len(source.splitlines()), source
            scope = 'FULL'
        size = len(model_source.encode('utf-8'))
        result.append({'sampleId': row['id'], 'split': 'development', 'scope': scope,
                       'function': name or cases[row['id']]['function'],
                       'mechanism': 'REENTRANCY' if cases[row['id']]['direction'] == '重入' else 'ACCESS_CONTROL',
                       'runnable': size <= MAX_MODEL_SOURCE_BYTES,
                       'reason': None if size <= MAX_MODEL_SOURCE_BYTES else '超过首版单次提示上限',
                       'lineStart': start, 'lineEnd': end,
                       'fullSource': source, 'modelSource': model_source,
                       'fullSourceHash': row['sourceHash'],
                       'modelSourceHash': hashlib.sha256(model_source.encode('utf-8')).hexdigest(),
                       'assignmentHash': fingerprint(assignment),
                       'formalLedgerHash': fingerprint(formal), 'groupId': audit['groupIds'][row['id']],
                       'projectId': row['projectId'], 'eventId': row['eventId'],
                       'researchEligible': False})
    return result


def list_targets(root):
    return [{key: value for key, value in row.items() if key not in ('fullSource', 'modelSource')}
            for row in _records(root)]


def load_target(root, sample_id):
    if sample_id not in DEVELOPMENT_IDS:
        raise ValueError('目标未登记为工程开发样本')
    row = next(item for item in _records(root) if item['sampleId'] == sample_id)
    if not row['runnable']:
        raise ValueError(row['reason'])
    return row
