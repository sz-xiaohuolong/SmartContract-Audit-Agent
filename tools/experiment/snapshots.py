"""知识快照与原子激活；Milvus 是可重建索引，本地快照为事实源。"""
import math
import os
import re
import shutil
import struct
import tempfile
import uuid
from pathlib import Path

from isolation import nonempty, sha256_value, validate_documents
from storage import atomic_json, decode, durable_write, encode, exclusive_lock, fingerprint, sync_directory


def vector32(vector, dimension):
    if not isinstance(vector, list) or len(vector) != dimension:
        raise ValueError("向量维度不匹配")
    result = []
    for number in vector:
        if type(number) not in (int, float) or not math.isfinite(number):
            raise ValueError("向量必须是有限数值")
        try: value = struct.unpack("!f", struct.pack("!f", number))[0]
        except (OverflowError, struct.error) as error: raise ValueError("向量超出 float32 范围") from error
        if not math.isfinite(value): raise ValueError("向量超出 float32 范围")
        result.append(value)
    if not any(result): raise ValueError("余弦索引不能使用零向量")
    return result


def _validate(payload):
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "manifest", "documents", "embedding", "chunking", "rows"}:
        raise ValueError("快照字段不完整")
    if payload["schema_version"] != "1": raise ValueError("快照版本无效")
    documents = validate_documents(payload["manifest"], payload["documents"])
    embedding, chunking = payload["embedding"], payload["chunking"]
    if (not isinstance(embedding, dict) or set(embedding) != {"model", "dimension", "revision"}
            or not nonempty(embedding["model"]) or not nonempty(embedding["revision"])
            or type(embedding["dimension"]) is not int or embedding["dimension"] <= 0
            or not isinstance(chunking, dict) or not nonempty(chunking.get("version"))):
        raise ValueError("embedding 与分块版本信息无效")
    rows = payload["rows"]
    if not isinstance(rows, list) or len(rows) != len(documents): raise ValueError("快照向量数量不完整")
    for document, row in zip(documents, rows):
        expected = {"id": fingerprint(document["id"]), "document": document}
        if (not isinstance(row, dict) or set(row) != {"id", "document", "vector"}
                or row["id"] != expected["id"] or row["document"] != document
                or vector32(row["vector"], embedding["dimension"]) != row["vector"]):
            raise ValueError("快照文档、ID 或向量不一致")
    return payload


def build_snapshot(root, manifest, documents, embedding, chunking, vectors):
    validate_documents(manifest, documents)
    if not isinstance(vectors, dict) or set(vectors) != {d["id"] for d in documents}:
        raise ValueError("向量必须精确覆盖所有知识文档")
    payload = {"schema_version": "1", "manifest": manifest, "documents": documents,
               "embedding": embedding, "chunking": chunking,
               "rows": [{"id": fingerprint(d["id"]), "document": d,
                         "vector": vector32(vectors[d["id"]], embedding["dimension"])} for d in documents]}
    _validate(payload)
    identifier = fingerprint(payload)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(root / ".snapshot.lock"):
        if (root / identifier).exists():
            verify_snapshot(root, identifier)
            return identifier
        temporary = Path(tempfile.mkdtemp(prefix=".building-", dir=root))
        try:
            durable_write(temporary / "snapshot.json", encode(payload) + b"\n")
            # 在发布之前对落盘字节重新校验，不使用内存成功标志。
            saved = _validate(decode((temporary / "snapshot.json").read_bytes()))
            if fingerprint(saved) != identifier: raise ValueError("快照落盘校验失败")
            sync_directory(temporary)
            os.replace(temporary, root / identifier)
            sync_directory(root)
        finally:
            if temporary.exists(): shutil.rmtree(temporary)
    return identifier


def verify_snapshot(root, identifier):
    if not sha256_value(identifier): raise ValueError("快照 ID 无效或仍处于构建中")
    directory = Path(root) / identifier
    if directory.is_symlink() or (directory / "snapshot.json").is_symlink():
        raise ValueError("快照不接受符号链接")
    payload = _validate(decode((directory / "snapshot.json").read_bytes()))
    if fingerprint(payload) != identifier: raise ValueError("快照完整性摘要不匹配")
    return payload


def _check_index(payload, rows):
    expected = {row["id"]: row for row in payload["rows"]}
    actual = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "document", "vector"} or row["id"] in actual:
            raise ValueError("索引返回重复或无效条目")
        row = dict(row, vector=vector32(row["vector"], payload["embedding"]["dimension"]))
        actual[row["id"]] = row
    if actual != expected: raise ValueError("索引读回内容与快照不一致，禁止激活")


def activate_snapshot(root, identifier, index=None):
    root = Path(root)
    with exclusive_lock(root / ".snapshot.lock"):
        payload = verify_snapshot(root, identifier)
        collection = None
        if index is not None:
            collection = "s1b_" + uuid.uuid4().hex
            index.build(collection, payload)
            _check_index(payload, index.read(collection))
        pointer = {"snapshot_id": identifier, "backend": "milvus" if index is not None else "local",
                   "collection": collection}
        atomic_json(root / "active.json", pointer)
        return pointer


def active_snapshot(root, index=None):
    pointer = decode((Path(root) / "active.json").read_bytes())
    if not isinstance(pointer, dict) or set(pointer) != {"snapshot_id", "backend", "collection"}:
        raise ValueError("激活指针无效")
    payload = verify_snapshot(root, pointer["snapshot_id"])
    if pointer["backend"] == "milvus":
        if index is None: raise ValueError("必须读回已激活的 Milvus 索引")
        _check_index(payload, index.read(pointer["collection"]))
    elif pointer["backend"] != "local" or pointer["collection"] is not None:
        raise ValueError("激活后端无效")
    return pointer


class MilvusIndex:
    """注入同步 MilvusClient；只创建专用新集合，不修改已有集合或别名。"""
    def __init__(self, client): self.client = client

    def build(self, collection, payload):
        if not re.fullmatch(r"s1b_[0-9a-f]{32}", collection) or self.client.has_collection(collection_name=collection):
            raise ValueError("只允许创建尚不存在的 S1b 集合")
        self.client.create_collection(collection_name=collection, dimension=payload["embedding"]["dimension"],
                                      primary_field_name="id", id_type="string", max_length=64,
                                      vector_field_name="vector", metric_type="COSINE", auto_id=False,
                                      enable_dynamic_field=True, consistency_level="Strong", timeout=60)
        rows = [{"id": r["id"], "vector": r["vector"], "payload": encode(r["document"]).decode("utf-8")}
                for r in payload["rows"]]
        for start in range(0, len(rows), 128):
            self.client.insert(collection_name=collection, data=rows[start:start + 128], timeout=60)
        self.client.flush(collection_name=collection, timeout=60)

    def read(self, collection):
        if not isinstance(collection, str) or not re.fullmatch(r"s1b_[0-9a-f]{32}", collection):
            raise ValueError("索引集合名无效")
        iterator = self.client.query_iterator(collection_name=collection, batch_size=256,
                                             output_fields=["id", "vector", "payload"],
                                             consistency_level="Strong", timeout=60)
        try:
            while True:
                try: rows = iterator.next()
                except StopIteration: break
                if not rows: break
                for row in rows:
                    yield {"id": row["id"], "vector": list(row["vector"]), "document": decode(row["payload"])}
        finally: iterator.close()
