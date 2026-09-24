"""逐样本持久记录、付费调用恢复边界与只读重放。"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline import digest
from isolation import validate_manifest
from storage import decode, encode, exclusive_lock, fingerprint
from test_isolation import sample
from batch import run_batch, replay, normalize_result


def reply(row, status="COMPLETED", conclusion="NO_CONFIRMED_FINDINGS", vulnerability_type=""):
    return {"schemaVersion": "1", "sourceHash": row["source_hash"], "status": status,
            "conclusion": conclusion, "vulnerabilityType": vulnerability_type, "reason": "夹具结果",
            "provider": "fixture", "model": "offline", "inputTokens": None, "outputTokens": None,
            "durationMs": 0, "errorCategory": None if status == "COMPLETED" else "MODEL_CALL_ERROR"}


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rows = []
        for identifier in ("a", "b"):
            content = ("contract " + identifier.upper() + " {}").encode()
            (self.root / (identifier + ".sol")).write_bytes(content)
            rows.append(sample(identifier, source_hash=digest(content)))
        self.plan = {"schema_version": "1", "manifest": {"schema_version": "1", "categories": ["r"], "samples": rows},
                     "sample_ids": ["a", "b"], "type_mapping": {"重入": ["r"]},
                     "mode": "Vanilla", "kb_snapshot": None}
        self.execution = {"config_hash": "a" * 64, "artifact_hash": "b" * 64,
                          "provider": "fixture", "timeout_seconds": 10}
        self.journal = self.root / "run.jsonl"
        self.calls = []

    def executor(self, row, source):
        self.calls.append(row["id"])
        self.assertEqual(row["source_hash"], digest(source))
        return reply(row)

    def run_batch(self, executor=None, **kwargs):
        return run_batch(self.plan, self.root, self.journal, executor or self.executor, self.execution, **kwargs)

    def test_restart_skips_completed_and_replay_is_read_only(self):
        self.run_batch()
        before = self.journal.read_bytes()
        self.run_batch()
        self.assertEqual(["a", "b"], self.calls)
        report = replay(self.journal)
        self.assertEqual(2, report["metrics"]["completed"])
        self.assertIsNone(report["results"][0]["input_tokens"])
        self.assertEqual(before, self.journal.read_bytes())

    def test_interrupted_call_is_unresolved_and_only_unstarted_is_called(self):
        def interrupted(row, source):
            self.calls.append(row["id"])
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.run_batch(interrupted)
        self.assertIn(b'"START"', self.journal.read_bytes())
        self.run_batch()
        self.assertEqual(["a", "b"], self.calls)
        self.assertEqual(1, replay(self.journal)["metrics"]["unresolved"])
        self.run_batch(retry_ids=["a"])
        self.assertEqual(["a", "b", "a"], self.calls)
        self.assertEqual(2, replay(self.journal)["metrics"]["completed"])

    def test_partial_tail_recovered_but_replay_does_not_truncate(self):
        self.run_batch()
        good = self.journal.read_bytes()
        with self.journal.open("ab") as output: output.write(b'{"unfinished":')
        before = self.journal.read_bytes()
        self.assertTrue(replay(self.journal)["incomplete_tail"])
        self.assertEqual(before, self.journal.read_bytes())
        self.run_batch()
        self.assertEqual(good, self.journal.read_bytes())
        self.assertEqual(["a", "b"], self.calls)

    def test_binding_changes_and_source_drift_rejected_before_calls(self):
        self.run_batch()
        for location, key, value in [(self.execution, "config_hash", "c" * 64),
                                     (self.execution, "artifact_hash", "d" * 64),
                                     (self.plan, "type_mapping", {"改名": ["r"]})]:
            original = location[key]
            location[key] = value
            with self.assertRaises(ValueError): self.run_batch()
            location[key] = original
        (self.root / "b.sol").write_text("contract Changed {}")
        with self.assertRaises(ValueError): self.run_batch()
        self.assertEqual(["a", "b"], self.calls)

    def test_full_line_corruption_and_duplicate_event_rejected(self):
        self.run_batch()
        data = self.journal.read_bytes()
        for corrupted in [data.replace(b'"COMPLETED"', b'"BROKEN"', 1), data + data.splitlines(keepends=True)[-1]]:
            self.journal.write_bytes(corrupted)
            with self.assertRaises(ValueError): self.run_batch()
            with self.assertRaises(ValueError): replay(self.journal)
        self.assertEqual(["a", "b"], self.calls)

    def test_failed_negative_is_not_safe_and_not_automatically_retried(self):
        def failed(row, source):
            self.calls.append(row["id"])
            raise RuntimeError("不要持久化异常中的凭证")
        self.run_batch(failed)
        self.run_batch()
        result = replay(self.journal)
        self.assertEqual(2, result["metrics"]["failed"])
        self.assertEqual(0, result["metrics"]["correct_completed"])
        self.assertEqual(["a", "b"], self.calls)
        self.assertNotIn("凭证", self.journal.read_text())

    def test_unknown_type_or_source_mismatch_never_becomes_safe(self):
        row = self.plan["manifest"]["samples"][0]
        for raw in [reply(row, conclusion="VULNERABILITY_REPORTED", vulnerability_type="未知"),
                    dict(reply(row), sourceHash="f" * 64), dict(reply(row), inputTokens=True),
                    dict(reply(row), conclusion="UNRESOLVED")]:
            result = normalize_result(raw, row, self.plan, self.execution)
            self.assertEqual("FAILED", result["status"])
            self.assertEqual([], result["types"])
        result = normalize_result(reply(row, conclusion="VULNERABILITY_REPORTED", vulnerability_type="重入"), row, self.plan, self.execution)
        self.assertEqual(["r"], result["types"])

    def test_unmapped_type_preserves_observed_usage_and_raw_response(self):
        row = self.plan["manifest"]["samples"][0]
        raw = dict(reply(row, conclusion="VULNERABILITY_REPORTED", vulnerability_type="未映射"),
                   inputTokens=12, outputTokens=7)
        result = normalize_result(raw, row, self.plan, self.execution)
        self.assertEqual("FAILED", result["status"])
        self.assertEqual(12, result["input_tokens"])
        self.assertEqual(7, result["output_tokens"])
        self.assertEqual(raw, result["raw"])
        self.run_batch(lambda row, source: dict(raw, sourceHash=row["source_hash"]))
        self.assertEqual(2, replay(self.journal)["metrics"]["failed"])

    def test_bound_snapshot_is_required_and_must_match_full_isolation_manifest(self):
        from snapshots import build_snapshot
        knowledge = sample("c", "knowledge")
        self.plan["manifest"]["samples"].append(knowledge)
        kb = self.root / "kb"
        identifier = build_snapshot(kb, self.plan["manifest"], [{"id": "doc", "sample_id": "c", "text": "案例"}],
                                    {"model": "fixture", "dimension": 2, "revision": "1"},
                                    {"version": "1"}, {"doc": [1, 2]})
        self.plan["kb_snapshot"] = identifier
        with self.assertRaises(ValueError): self.run_batch()
        self.plan["manifest"]["samples"][-1]["project_group"] = "changed"
        with self.assertRaises(ValueError): self.run_batch(snapshot_root=kb)
        self.assertEqual([], self.calls)
        self.plan["manifest"]["samples"][-1]["project_group"] = "c"
        self.run_batch(snapshot_root=kb)
        self.assertEqual(["a", "b"], self.calls)

    def test_concurrent_writer_rejected(self):
        with exclusive_lock(str(self.journal) + ".lock"):
            with self.assertRaises(ValueError): self.run_batch()
        self.assertEqual([], self.calls)

    def test_fsync_failure_before_start_prevents_external_call(self):
        with patch("storage.os.fsync", side_effect=OSError("落盘失败")):
            with self.assertRaises(OSError): self.run_batch()
        self.assertEqual([], self.calls)

    def test_result_write_interruption_does_not_repeat_paid_call(self):
        import batch
        original = batch._append
        def interrupted(output, events, payload):
            if payload["kind"] == "RESULT":
                output.write(b'{"partial-result":')
                output.flush()
                raise OSError("结果持久化中断")
            original(output, events, payload)
        with patch("batch._append", side_effect=interrupted):
            with self.assertRaises(OSError): self.run_batch()
        self.assertEqual(["a"], self.calls)
        self.run_batch()
        self.assertEqual(["a", "b"], self.calls)
        self.assertEqual(1, replay(self.journal)["metrics"]["unresolved"])

    def test_retry_completed_or_unknown_id_is_rejected(self):
        self.run_batch()
        for identifiers in [["a"], ["unknown"]]:
            with self.assertRaises(ValueError): self.run_batch(retry_ids=identifiers)
        self.assertEqual(["a", "b"], self.calls)
