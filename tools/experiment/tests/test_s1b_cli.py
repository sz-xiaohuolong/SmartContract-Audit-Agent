"""使用本地子进程夹具验证命令闭环，不调用外部服务。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from offline import digest
from test_isolation import sample

CLI = Path(__file__).resolve().parents[1] / "s1b.py"


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = b"contract C {}"
        (self.root / "a.sol").write_bytes(self.source)
        self.manifest = {"schema_version": "1", "categories": ["r"], "samples": [sample("a", source_hash=digest(self.source))]}
        self.plan = {"schema_version": "1", "manifest": self.manifest, "sample_ids": ["a"],
                     "type_mapping": {"重入": ["r"]}, "mode": "Vanilla", "kb_snapshot": None}
        (self.root / "plan.json").write_text(json.dumps(self.plan))
        (self.root / "config.properties").write_text("providers.fixture.model=offline\n")
        (self.root / "fixture.jar").write_bytes(b"offline-artifact")
        self.counter = self.root / "counter"
        self.java = self.root / "java-fixture"
        self.java.write_text("#!" + sys.executable + "\n" + '''import sys, json, hashlib, os
from pathlib import Path
args = sys.argv
source = Path(args[args.index('--source') + 1]).read_bytes()
counter = Path(os.environ['S1B_FIXTURE_COUNTER'])
with counter.open('a') as output: output.write('call\\n')
result = {'schemaVersion':'1', 'sourceHash':hashlib.sha256(source).hexdigest(), 'status':'COMPLETED',
'conclusion':'NO_CONFIRMED_FINDINGS','vulnerabilityType':'','reason':'夹具结果',
'provider':'fixture','model':'offline','inputTokens':None,'outputTokens':None,'durationMs':0,'errorCategory':None}
print(json.dumps(result))
''')
        self.java.chmod(0o755)
        self.args = ["--plan", str(self.root / "plan.json"), "--root", str(self.root),
                     "--journal", str(self.root / "run.jsonl"), "--jar", str(self.root / "fixture.jar"),
                     "--config", str(self.root / "config.properties"), "--provider", "fixture",
                     "--java", str(self.java)]

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                              env=dict(os.environ, S1B_FIXTURE_COUNTER=str(self.counter)), timeout=10)

    def test_run_resume_replay_and_configuration_binding(self):
        first = self.cli("run", *self.args)
        self.assertEqual(0, first.returncode, first.stderr)
        second = self.cli("resume", *self.args)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual("call\n", self.counter.read_text())
        saved = self.root / "run.jsonl"
        before = saved.read_bytes()
        replay = self.cli("replay", "--journal", str(saved))
        self.assertEqual(0, replay.returncode, replay.stderr)
        self.assertEqual(1, json.loads(replay.stdout)["metrics"]["completed"])
        self.assertEqual(before, saved.read_bytes())
        (self.root / "config.properties").write_text("providers.fixture.model=changed\n")
        rejected = self.cli("resume", *self.args)
        self.assertEqual(2, rejected.returncode)
        self.assertEqual("call\n", self.counter.read_text())

    def test_invalid_split_or_source_prevents_subprocess(self):
        self.plan["manifest"]["samples"][0]["review_status"] = "UNREVIEWED"
        (self.root / "plan.json").write_text(json.dumps(self.plan))
        result = self.cli("run", *self.args)
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.counter.exists())

    def test_subprocess_timeout_remains_failed_on_resume(self):
        self.java.write_text("#!" + sys.executable + "\nimport time\ntime.sleep(60)\n")
        result = self.cli("run", *self.args, "--timeout", "0.1")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(1, json.loads(result.stdout)["metrics"]["failed"])
        resumed = self.cli("resume", *self.args, "--timeout", "0.1")
        self.assertEqual(1, resumed.returncode, resumed.stderr)
        self.assertEqual(1, json.loads(resumed.stdout)["results"][0]["attempt"])

    def test_executor_uses_frozen_jar_and_config_bytes(self):
        from java_adapter import JavaExecutor
        from unittest.mock import patch
        self.java.write_text("#!" + sys.executable + "\n" + """import sys
from pathlib import Path
args = sys.argv
assert Path(args[args.index('-jar') + 1]).read_bytes() == b'offline-artifact'
assert Path(args[args.index('--config') + 1]).read_text() == 'providers.fixture.model=offline\\n'
print('{"status":"COMPLETED"}')
""")
        executor = JavaExecutor(self.root / "fixture.jar", self.root / "config.properties", "fixture", java=str(self.java))
        (self.root / "fixture.jar").write_bytes(b"changed")
        (self.root / "config.properties").write_text("changed")
        self.assertEqual({"status": "COMPLETED"}, executor({}, self.source))

    def test_snapshot_commands_and_isolation(self):
        self.manifest["samples"][0]["split"] = "knowledge"
        bundle = {"manifest": self.manifest, "documents": [{"id": "d", "sample_id": "a", "text": "案例"}],
                  "embedding": {"model": "fixture", "dimension": 2, "revision": "1"},
                  "chunking": {"version": "manual-v1"}, "vectors": {"d": [0.1, 0.2]}}
        (self.root / "bundle.json").write_text(json.dumps(bundle))
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        checked = self.cli("validate-splits", "--manifest", str(self.root / "manifest.json"))
        self.assertEqual(0, checked.returncode, checked.stderr)
        built = self.cli("snapshot-build", "--root", str(self.root / "kb"), "--bundle", str(self.root / "bundle.json"))
        self.assertEqual(0, built.returncode, built.stderr)
        identifier = json.loads(built.stdout)["snapshot_id"]
        for command in ["snapshot-verify", "snapshot-activate"]:
            result = self.cli(command, "--root", str(self.root / "kb"), "--id", identifier)
            self.assertEqual(0, result.returncode, result.stderr)
