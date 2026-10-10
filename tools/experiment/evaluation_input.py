"""评测输入去除注释侧答案与来源提示，原件和原始位置单独留证。"""
import hashlib


def clean_evaluation_source(source):
    """只改注释；用等长空白保留行列，字符串中的任何内容原样保留。"""
    if not isinstance(source, str) or not source.strip() or '\x00' in source:
        raise ValueError('评测源码为空或包含无效字符')
    cleaned = list(source)
    removed = []
    at = 0
    while at < len(source):
        if source[at] in ('"', "'"):
            quote = source[at]
            at += 1
            while at < len(source) and source[at] != quote:
                at += 2 if source[at] == '\\' else 1
            if at >= len(source):
                raise ValueError('评测源码字符串未闭合，无法可靠清理注释')
            at += 1
            continue
        if source.startswith('//', at):
            end = at + 2
            while end < len(source) and source[end] not in '\r\n':
                end += 1
            kind = 'LINE_COMMENT'
        elif source.startswith('/*', at):
            close = source.find('*/', at + 2)
            if close < 0:
                raise ValueError('评测源码块注释未闭合，无法可靠清理注释')
            end, kind = close + 2, 'BLOCK_COMMENT'
        else:
            at += 1
            continue
        removed.append({'kind': kind, 'lineStart': source.count('\n', 0, at) + 1,
                        'lineEnd': source.count('\n', 0, end) + 1})
        cleaned[at:end] = [value if value in '\r\n\t ' else ' ' for value in source[at:end]]
        at = end
    full_source = ''.join(cleaned)
    original_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    source_hash = hashlib.sha256(full_source.encode('utf-8')).hexdigest()
    return {'originalSource': source, 'originalSourceHash': original_hash,
            'source': full_source, 'fullSource': full_source,
            'sourceHash': source_hash, 'fullSourceHash': source_hash,
            'inputGovernanceReceipt': {'schemaVersion': '1', 'policy': 'COMMENTS_MASKED_V1',
                'originalSourceHash': original_hash, 'fullSourceHash': source_hash,
                'lineNumbersPreserved': True, 'columnsPreserved': True,
                'removedComments': removed}}
