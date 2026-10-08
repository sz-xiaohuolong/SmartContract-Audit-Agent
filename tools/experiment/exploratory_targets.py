"""从本地 SmartBugs 文档提取探索性目标并筛查知识侧重复。"""
import hashlib
import re
from pathlib import Path

from s3 import _tokens


CATEGORIES = {'access_control': 'ACCESS_CONTROL', 'reentrancy': 'REENTRANCY'}


def _field(header, name):
    match = re.search(r'^' + re.escape(name) + r':\s*(.+)$', header, re.MULTILINE)
    return match.group(1).strip() if match else None


def load_targets(directory, knowledge_rows, near_threshold=.85):
    if not isinstance(knowledge_rows, list) or not 0 < near_threshold <= 1:
        raise ValueError('探索目标筛查输入无效')
    reference = []
    for row in knowledge_rows:
        if not isinstance(row, dict) or not isinstance(row.get('text'), str) or not isinstance(row.get('project'), str):
            raise ValueError('知识候选元数据无效')
        reference.append((row['project'], hashlib.sha256(row['text'].encode()).hexdigest(),
                          _tokens(row['text'].encode())))
    result = []
    for path in sorted(Path(directory).glob('*.md')):
        text = path.read_text(encoding='utf-8')
        header = text.split('---', 2)
        if len(header) != 3:
            raise ValueError('SmartBugs 文档头缺失：' + path.name)
        category = _field(header[1], 'Category')
        if category not in CATEGORIES:
            continue
        origin = _field(header[1], 'Source')
        vulnerable = _field(header[1], 'Vulnerable-Lines')
        code = re.search(r'```solidity\s*\n([\s\S]*?)\n```', text)
        if (not origin or not vulnerable or not code or
                not re.fullmatch(r'\d+(?:\s*,\s*\d+)*', vulnerable)):
            raise ValueError('SmartBugs 漏洞源码或行标签缺失：' + path.name)
        source = code.group(1)
        lines = [int(value.strip()) for value in vulnerable.split(',')]
        if not source.strip() or any(line < 1 or line > len(source.splitlines()) for line in lines):
            raise ValueError('SmartBugs 漏洞行超出源码：' + path.name)
        digest = hashlib.sha256(source.encode()).hexdigest()
        tokens = _tokens(source.encode())
        overlap = max((max(len(tokens & other) / len(tokens | other),
                            len(tokens & other) / min(len(tokens), len(other)))
                       if tokens and other else 0.0 for _, _, other in reference), default=0.0)
        if any(origin == project or digest == other_hash for project, other_hash, _ in reference) or overlap >= near_threshold:
            continue
        result.append({'sampleId': path.stem, 'source': source, 'sourceHash': digest,
                       'documentHash': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'projectHint': origin, 'mechanism': CATEGORIES[category],
                       'vulnerableLines': lines, 'split': 'exploratory-test',
                       'labelStatus': 'SOURCE_HEADER_ONLY', 'researchEligible': False,
                       'maxCandidateCloneSimilarity': round(overlap, 6)})
    if len({item['sampleId'] for item in result}) != len(result):
        raise ValueError('探索目标 ID 重复')
    return result
