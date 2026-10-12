"""从原始 SmartBugs 源码和标注提取探索性目标并筛查知识侧重复。"""
import hashlib
import json
import re
from pathlib import Path

from s3 import _tokens


CATEGORIES = {'access_control': 'ACCESS_CONTROL', 'reentrancy': 'REENTRANCY'}


def _sample_id(category, relative):
    """沿用原加工文档编号，使历史记录仍能定位同一原始合约。"""
    def slug(value):
        value = value.replace('\\', '/').replace('/', '_')
        return re.sub(r'_+', '_', re.sub(r'[^0-9A-Za-z._-]+', '_', value)).strip('_') or 'unknown'
    suffix = hashlib.sha1(relative.encode('utf-8')).hexdigest()[:10]
    return slug(category) + '__' + slug(relative.replace('.sol', '')) + '__' + suffix


def load_targets(directory, knowledge_rows, near_threshold=.85):
    if not isinstance(knowledge_rows, list) or not 0 < near_threshold <= 1:
        raise ValueError('探索目标筛查输入无效')
    reference = []
    for row in knowledge_rows:
        if not isinstance(row, dict) or not isinstance(row.get('text'), str) or not isinstance(row.get('project'), str):
            raise ValueError('知识候选元数据无效')
        reference.append((row['project'], hashlib.sha256(row['text'].encode()).hexdigest(),
                          _tokens(row['text'].encode())))
    directory = Path(directory).resolve()
    metadata_path = directory / 'vulnerabilities.json'
    if not metadata_path.is_file():
        raise ValueError('缺少原始 SmartBugs 数据集标注：' + str(metadata_path))
    metadata = metadata_path.read_bytes()
    entries = json.loads(metadata.decode('utf-8'))
    if not isinstance(entries, list) or not entries:
        raise ValueError('SmartBugs 标注必须是非空列表')
    metadata_hash = hashlib.sha256(metadata).hexdigest()
    result, seen = [], set()
    for entry in entries:
        relative = entry.get('path') if isinstance(entry, dict) else None
        if not isinstance(relative, str) or not relative or relative in seen:
            raise ValueError('SmartBugs 源码路径缺失或重复')
        path = directory / relative
        if (Path(relative).is_absolute() or path.suffix != '.sol'
                or directory / 'dataset' not in path.resolve().parents):
            raise ValueError('SmartBugs 源码路径越界：' + relative)
        seen.add(relative)
        vulnerabilities = entry.get('vulnerabilities')
        if (not isinstance(vulnerabilities, list) or not vulnerabilities
                or any(not isinstance(v, dict) or not isinstance(v.get('category'), str)
                       for v in vulnerabilities)):
            raise ValueError('SmartBugs 漏洞类别缺失：' + relative)
        categories = sorted({v['category'].strip() for v in vulnerabilities})
        if len(categories) != 1 or categories[0] not in CATEGORIES:
            continue
        category = categories[0]
        origin = entry.get('source')
        if (not isinstance(origin, str) or not origin.strip()
                or any(not isinstance(v.get('lines'), list)
                       or any(type(line) is not int or line < 1 for line in v['lines'])
                       for v in vulnerabilities) or not path.is_file()):
            raise ValueError('SmartBugs 漏洞源码或行标签缺失：' + relative)
        source = path.read_bytes().decode('utf-8')
        lines = sorted({line for v in vulnerabilities for line in v['lines']})
        origin = origin.strip()
        if not source.strip() or not lines or any(line > len(source.splitlines()) for line in lines):
            raise ValueError('SmartBugs 漏洞行超出源码或标签为空：' + relative)
        digest = hashlib.sha256(source.encode()).hexdigest()
        tokens = _tokens(source.encode())
        overlap = max((max(len(tokens & other) / len(tokens | other),
                            len(tokens & other) / min(len(tokens), len(other)))
                       if tokens and other else 0.0 for _, _, other in reference), default=0.0)
        if any(origin == project or digest == other_hash for project, other_hash, _ in reference) or overlap >= near_threshold:
            continue
        result.append({'sampleId': _sample_id(category, relative), 'source': source, 'sourceHash': digest,
                       'documentHash': None, 'sourcePath': relative,
                       'metadataPath': 'vulnerabilities.json', 'metadataHash': metadata_hash,
                       'projectHint': origin, 'mechanism': CATEGORIES[category],
                       'vulnerableLines': lines, 'split': 'exploratory-test',
                       'labelStatus': 'SOURCE_METADATA_ONLY', 'researchEligible': False,
                       'maxCandidateCloneSimilarity': round(overlap, 6)})
    if len({item['sampleId'] for item in result}) != len(result):
        raise ValueError('探索目标 ID 重复')
    return sorted(result, key=lambda row: row['sampleId'])
