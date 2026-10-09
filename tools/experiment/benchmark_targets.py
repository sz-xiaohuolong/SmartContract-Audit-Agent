"""登记公开漏洞目标与本机安全对照源，保留原数据集标签等级。"""
import hashlib
from pathlib import Path

from exploratory_targets import load_targets
from program_facts import _tokens as solidity_tokens
from s3 import _tokens as clone_tokens


SAFE_FUNCTIONS = {'safe_23_Ownable.sol': 'transferOwnership',
                  'safe_24_Ownable2Step.sol': 'acceptOwnership',
                  'safe_25_AccessControl.sol': 'grantRole',
                  'safe_30_Pausable.sol': '_pause'}


def _scopes(source):
    tokens, pairs = solidity_tokens(source)
    values = [item[0] for item in tokens]
    rows = []
    for index, value in enumerate(values[:-1]):
        if value not in ('function', 'constructor', 'fallback', 'receive'):
            continue
        name = ('fallback' if values[index + 1] == '(' else values[index + 1]) if value == 'function' else value
        end = next((at for at in range(index + 2, len(values)) if values[at] in ('{', ';')), None)
        if end is not None and values[end] == '{':
            rows.append((name, tokens[index][2], tokens[pairs[end]][2]))
    return rows


def _similarity(source, rows):
    tokens = clone_tokens(source.encode())
    best = 0.0
    for row in rows:
        other = clone_tokens(row['text'].encode())
        if tokens and other:
            shared = len(tokens & other)
            best = max(best, shared / len(tokens | other), shared / min(len(tokens), len(other)))
    return best


def _record(sample_id, source, mechanism, function, span, truth, label_source, project, document_hash=None):
    lines = source.splitlines()
    start, end = span if span is not None else (1, len(lines))
    excerpt = '\n'.join(lines[start - 1:end]) if span is not None else source
    full = source if len(source.encode()) <= 6000 else excerpt
    scope = 'FULL' if full == source else 'FUNCTION'
    if span is not None and not truth:
        full, scope = excerpt, 'FUNCTION'
    line_start, line_end = (start, end) if scope == 'FUNCTION' else (1, len(lines))
    return {'sampleId': sample_id, 'split': 'validation', 'source': source,
            'fullSource': source, 'modelSource': full, 'scope': scope,
            'sourceHash': hashlib.sha256(source.encode()).hexdigest(),
            'fullSourceHash': hashlib.sha256(source.encode()).hexdigest(),
            'modelSourceHash': hashlib.sha256(full.encode()).hexdigest(),
            'documentHash': document_hash, 'projectGroup': project,
            'mechanism': mechanism, 'function': function or '',
            'lineStart': line_start, 'lineEnd': line_end,
            'runnable': bool(function and len(full.encode()) <= 6000),
            'groundTruth': {'hasVulnerability': truth,
                            'vulnerabilityType': mechanism if truth else None,
                            'labelSource': label_source}, 'researchEligible': False}


def load_benchmark_targets(root, knowledge_rows):
    root = Path(root)
    positives = load_targets(root / 'src/main/resources/document/smartbugs_kb', knowledge_rows)
    targets = []
    for row in positives:
        source = row['source']
        scopes = _scopes(source)
        matches = [item for item in scopes if any(item[1] <= line <= item[2] for line in row['vulnerableLines'])]
        selected = min(matches, key=lambda item: item[2] - item[1]) if matches else None
        item = _record(row['sampleId'], source, row['mechanism'], selected[0] if selected else None,
                       selected[1:] if selected else None, True, 'SMARTBUGS_CURATED_HEADER',
                       row['projectHint'], row['documentHash'])
        item['vulnerableLines'] = row['vulnerableLines']
        item['maxCandidateCloneSimilarity'] = row['maxCandidateCloneSimilarity']
        targets.append(item)
    safe_dir = root / 'src/main/resources/testset/safe_contracts'
    if any('openzeppelin-contracts' in row['project'].lower() for row in knowledge_rows):
        return targets
    for filename, function in SAFE_FUNCTIONS.items():
        path = safe_dir / filename
        if not path.is_file():
            continue
        source = path.read_text(encoding='utf-8')
        similarity = _similarity(source, knowledge_rows)
        if similarity >= .85 or any(row['sourceHash'] == hashlib.sha256(source.encode()).hexdigest() for row in targets):
            continue
        spans = [item[1:] for item in _scopes(source) if item[0] == function]
        selected = spans[-1] if spans else None
        item = _record(path.stem, source, 'ACCESS_CONTROL', function, selected, False,
                       'LEGACY_SAFE_CONTRACTS', 'https://github.com/OpenZeppelin/openzeppelin-contracts',
                       hashlib.sha256(path.read_bytes()).hexdigest())
        item['vulnerableLines'] = []
        item['maxCandidateCloneSimilarity'] = round(similarity, 6)
        targets.append(item)
    if len({item['sampleId'] for item in targets}) != len(targets):
        raise ValueError('公开批量目标编号重复')
    return targets
