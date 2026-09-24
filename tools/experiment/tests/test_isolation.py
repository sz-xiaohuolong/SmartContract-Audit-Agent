"""审核划分与知识衍生文档的隔离测试。"""
import copy
import unittest

from isolation import validate_manifest, validate_documents


def sample(identifier, split="test", project=None, source_hash=None):
    return {"id": identifier, "path": identifier + ".sol", "source_hash": source_hash or identifier * 64,
            "exact_group": source_hash or identifier * 64, "project_group": project or identifier,
            "clone_groups": [], "origin": "fixture/" + identifier, "split": split,
            "types": [], "review_status": "REVIEWED"}


def manifest():
    return {"schema_version": "1", "categories": ["r"],
            "samples": [sample("a", "knowledge"), sample("b")]}


class IsolationTest(unittest.TestCase):
    def test_accepts_reviewed_disjoint_groups(self):
        self.assertEqual(2, len(validate_manifest(manifest())))

    def test_rejects_each_shared_group_across_splits(self):
        for field, value in [("source_hash", "a" * 64), ("project_group", "a"),
                             ("clone_groups", ["clone-1"])]:
            data = manifest()
            data["samples"][0][field] = value
            data["samples"][1][field] = value
            if field == "source_hash":
                data["samples"][1]["exact_group"] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_manifest(data)

    def test_missing_review_lineage_invalid_split_and_duplicates_fail_closed(self):
        for field, value in [("origin", None), ("project_group", None),
                             ("clone_groups", None), ("review_status", "UNREVIEWED"),
                             ("split", "unknown"), ("source_hash", "invalid"),
                             ("exact_group", "f" * 64), ("path", "../a.sol")]:
            data = manifest()
            data["samples"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_manifest(data)
        data = manifest()
        data["samples"].append(copy.deepcopy(data["samples"][0]))
        with self.assertRaises(ValueError): validate_manifest(data)

    def test_document_must_inherit_knowledge_source_and_nonempty_content(self):
        data = manifest()
        valid = {"id": "doc", "sample_id": "a", "text": "审计案例"}
        self.assertEqual([valid], validate_documents(data, [valid]))
        for document in [dict(valid, sample_id="b"), dict(valid, sample_id="absent"), dict(valid, text="")]:
            with self.assertRaises(ValueError): validate_documents(data, [document])
        with self.assertRaises(ValueError): validate_documents(data, [valid, valid])
