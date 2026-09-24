"""校验人工审核清单；拒绝字节、项目和已审核克隆组跨划分。"""
import re
from pathlib import PurePosixPath
from offline import evaluate


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def sha256_value(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1":
        raise ValueError("清单版本无效")
    rows = manifest.get("samples")
    if not isinstance(rows, list) or not rows:
        raise ValueError("审核清单不能为空")
    indexed, groups, paths = {}, {}, set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("清单条目无效")
        identifier, path = row.get("id"), row.get("path")
        if not nonempty(identifier) or identifier in indexed:
            raise ValueError("样本 ID 为空或重复")
        if (not nonempty(path) or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
                or "\\" in path or path in paths):
            raise ValueError("源码路径无效或重复")
        paths.add(path)
        if not sha256_value(row.get("source_hash")) or row.get("exact_group") != row["source_hash"]:
            raise ValueError("源码摘要与字节组不一致")
        if (row.get("review_status") != "REVIEWED" or not nonempty(row.get("origin"))
                or not nonempty(row.get("project_group"))):
            raise ValueError("来源与项目谱系必须经审核")
        clones = row.get("clone_groups")
        if not isinstance(clones, list) or any(not nonempty(c) for c in clones) or len(set(clones)) != len(clones):
            raise ValueError("需明确列出审核后的克隆组，无已知关联时使用空列表")
        split = row.get("split")
        if split not in ("knowledge", "train", "validation", "test"):
            raise ValueError("划分未审核或无效")
        keys = [("bytes", row["source_hash"]), ("project", row["project_group"])]
        keys.extend(("clone", c) for c in clones)
        for key in keys:
            if key in groups and groups[key] != split:
                raise ValueError("同组数据跨划分泄漏")
            groups[key] = split
        indexed[identifier] = row
    evaluate(manifest.get("categories"), [{"id": r["id"], "types": r.get("types")} for r in rows], [])
    return indexed


def validate_documents(manifest, documents):
    indexed = validate_manifest(manifest)
    if not isinstance(documents, list) or not documents:
        raise ValueError("知识文档不能为空")
    identifiers = set()
    for document in documents:
        if not isinstance(document, dict) or set(document) != {"id", "sample_id", "text"}:
            raise ValueError("知识文档字段无效")
        identifier = document["id"]
        if not nonempty(identifier) or identifier in identifiers or not nonempty(document["text"]):
            raise ValueError("知识文档 ID 重复或内容为空")
        source = indexed.get(document["sample_id"])
        if source is None or source["split"] != "knowledge":
            raise ValueError("知识衍生文档只能来自已审核 knowledge 样本")
        identifiers.add(identifier)
    return documents
