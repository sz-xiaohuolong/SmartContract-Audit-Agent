"""快照发布、损坏检测与 Milvus 离线契约夹具。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_isolation import manifest
from snapshots import build_snapshot, verify_snapshot, activate_snapshot, active_snapshot, MilvusIndex


class ClientFixture:
    def __init__(self, damage=None):
        self.collections = {}
        self.damage = damage

    def has_collection(self, collection_name): return collection_name in self.collections
    def create_collection(self, collection_name, **kwargs): self.collections[collection_name] = []
    def insert(self, collection_name, data, **kwargs): self.collections[collection_name].extend(copy.deepcopy(data))
    def flush(self, collection_name, **kwargs): pass
    def query_iterator(self, collection_name, **kwargs):
        rows = copy.deepcopy(self.collections[collection_name])
        if self.damage == "missing": rows = rows[:-1]
        if self.damage == "vector": rows[0]["vector"][0] = 9.0
        if self.damage == "duplicate": rows.append(rows[0])
        class Iterator:
            def next(self):
                nonlocal rows
                result, rows = rows[:kwargs["batch_size"]], rows[kwargs["batch_size"]:]
                return result
            def close(self): pass
        return Iterator()


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docs = [{"id": "d1", "sample_id": "a", "text": "案例一"},
                     {"id": "d2", "sample_id": "a", "text": "案例二"}]
        self.embedding = {"model": "offline-fixture", "dimension": 2, "revision": "1"}
        self.chunking = {"version": "manual-v1"}
        self.vectors = {"d1": [0.1, 0.2], "d2": [0.3, 0.4]}

    def build(self):
        return build_snapshot(self.root, manifest(), self.docs, self.embedding, self.chunking, self.vectors)

    def test_content_addressed_build_verify_and_atomic_activate(self):
        snapshot = self.build()
        self.assertEqual(snapshot, self.build())
        self.assertEqual(2, len(verify_snapshot(self.root, snapshot)["rows"]))
        activate_snapshot(self.root, snapshot)
        self.assertEqual(snapshot, active_snapshot(self.root)["snapshot_id"])

    def test_interrupted_build_never_activates(self):
        with patch("snapshots.os.replace", side_effect=OSError("模拟断电")):
            with self.assertRaises(OSError): self.build()
        self.assertFalse((self.root / "active.json").exists())
        for path in self.root.glob(".building-*"):
            with self.assertRaises(ValueError): activate_snapshot(self.root, path.name)
        self.assertEqual(self.build(), self.build())

    def test_tamper_rejected_and_old_pointer_preserved(self):
        snapshot = self.build()
        activate_snapshot(self.root, snapshot)
        old = (self.root / "active.json").read_bytes()
        path = self.root / snapshot / "snapshot.json"
        payload = json.loads(path.read_text())
        payload["rows"].pop()
        path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError): activate_snapshot(self.root, snapshot)
        with self.assertRaises(ValueError): active_snapshot(self.root)
        self.assertEqual(old, (self.root / "active.json").read_bytes())

    def test_invalid_vectors_cannot_publish(self):
        for vectors in [{"d1": [1, 2]}, {"d1": [1], "d2": [2]},
                        {"d1": [float("nan"), 1], "d2": [1, 2]},
                        {"d1": [True, 1], "d2": [1, 2]}]:
            self.vectors = vectors
            with self.assertRaises(ValueError): self.build()
        self.assertFalse((self.root / "active.json").exists())

    def test_milvus_readback_checks_every_page(self):
        self.docs = [{"id": "d" + str(i), "sample_id": "a", "text": "案例" + str(i)} for i in range(260)]
        self.vectors = {doc["id"]: [0.1, 0.2] for doc in self.docs}
        snapshot = self.build()
        client = ClientFixture()
        adapter = MilvusIndex(client)
        pointer = activate_snapshot(self.root, snapshot, adapter)
        self.assertEqual(260, len(list(adapter.read(pointer["collection"]))))
        client.collections[pointer["collection"]][-1]["vector"] = [9, 9]
        with self.assertRaises(ValueError): active_snapshot(self.root, adapter)

    def test_milvus_full_readback_before_activation(self):
        snapshot = self.build()
        client = ClientFixture()
        adapter = MilvusIndex(client)
        activate_snapshot(self.root, snapshot, adapter)
        pointer = active_snapshot(self.root, adapter)
        self.assertTrue(pointer["collection"].startswith("s1b_"))
        self.assertEqual(2, len(client.collections[pointer["collection"]]))
        for damage in ["missing", "vector", "duplicate"]:
            old = (self.root / "active.json").read_bytes()
            with self.subTest(damage=damage), self.assertRaises(ValueError):
                activate_snapshot(self.root, snapshot, MilvusIndex(ClientFixture(damage)))
            self.assertEqual(old, (self.root / "active.json").read_bytes())
        client.damage = "missing"
        with self.assertRaises(ValueError): active_snapshot(self.root, adapter)
        with self.assertRaises(ValueError): active_snapshot(self.root)
