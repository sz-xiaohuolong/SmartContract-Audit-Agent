"""冻结快照到无目标标签候选池的召回测试。"""
import tempfile
import unittest
from pathlib import Path
from test_isolation import manifest
from snapshots import build_snapshot
from storage import fingerprint
from recall import recall_pool


class RecallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = build_snapshot(self.root, manifest(),
            [{"id": "a", "sample_id": "a", "text": "withdraw vulnerable"}, {"id": "b", "sample_id": "a", "text": "withdraw guarded"}],
            {"model": "fixture", "dimension": 2, "revision": "1"}, {"version": "1"}, {"a": [1, 0], "b": [.8, .2]})
        self.catalog = {"snapshotId": self.snapshot, "cases": {}}
        for key, role in [("a", "VULNERABLE"), ("b", "DEFENSE")]:
            self.catalog["cases"][key] = {"caseId": key, "pairId": "pair", "role": role, "mechanism": "REENTRANCY", "riskKind": "CALL",
                "conditions": [{"predicate": "STATE_WRITE_BEFORE", "subject": "$actor", "resource": "$resource", "expected": role == "DEFENSE"}], "reviewed": True}

    def test_same_vector_candidates_are_stable_without_target_labels(self):
        first = recall_pool(self.root, self.snapshot, self.catalog, [1, 0], "withdraw", 2, target_source_hash="b" * 64)
        self.assertEqual(first, recall_pool(self.root, self.snapshot, self.catalog, [1, 0], "withdraw", 2, target_source_hash="b" * 64))
        self.assertEqual(["a", "b"], [c["caseId"] for c in first["pool"]["candidates"]])
        self.assertAlmostEqual(1, first["pool"]["candidates"][0]["denseScore"])
        self.assertNotIn('"types"', __import__('json').dumps(first))
        self.assertNotIn('"split"', __import__('json').dumps(first))

    def test_target_must_be_in_nonknowledge_split(self):
        for target in [None, "a" * 64, "f" * 64]:
            with self.assertRaises(ValueError): recall_pool(self.root, self.snapshot, self.catalog, [1, 0], "", 2, target_source_hash=target)

    def test_unreviewed_catalog_snapshot_mismatch_and_bad_vector_rejected(self):
        self.catalog["cases"]["a"]["reviewed"] = False
        with self.assertRaises(ValueError): recall_pool(self.root, self.snapshot, self.catalog, [1, 0], "", 2, target_source_hash="b" * 64)
        self.catalog["cases"]["a"]["reviewed"] = True
        for query in [[1], [0, 0], [float('nan'), 1]]:
            with self.assertRaises(ValueError): recall_pool(self.root, self.snapshot, self.catalog, query, "", 2, target_source_hash="b" * 64)
        self.catalog["snapshotId"] = "b" * 64
        with self.assertRaises(ValueError): recall_pool(self.root, self.snapshot, self.catalog, [1, 0], "", 2, target_source_hash="b" * 64)

    def test_remote_unknown_duplicate_or_wrong_score_cannot_enter_pool(self):
        for hits in [[{"id": "unknown", "distance": 1}, {"id": fingerprint("b"), "distance": .9701425}],
                     [{"id": fingerprint("a"), "distance": 1}, {"id": fingerprint("a"), "distance": 1}],
                     [{"id": fingerprint("a"), "distance": .5}, {"id": fingerprint("b"), "distance": .9701425}]]:
            with self.assertRaises(ValueError):
                recall_pool(self.root, self.snapshot, self.catalog, [1, 0], "", 2, target_source_hash="b" * 64, search=lambda query, limit: hits)
