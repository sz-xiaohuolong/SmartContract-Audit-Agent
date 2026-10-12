"""目录整理必须保持历史字节、指标、只读下载与模型调用边界。"""
import gzip
import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import threading

from benchmark_batch import make_plan, replay_batch, run_batch, save_summary
from organize_storage import archive_file, compact, migrate, restore_compatibility
from local_ui import create_server
from storage import read_artifact


class StorageLayoutTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def batch(self, complete=True):
        store = self.root / 'research-artifacts/runs/benchmarks'
        targets = [{'sampleId': 'a', 'sourceHash': 'a' * 64, 'runnable': True,
                    'groundTruth': {'hasVulnerability': True, 'labelSource': 'fixture'}}]
        plan = make_plan(['a'], ['D1'], 'real', targets, 'b' * 64)
        calls = []
        def runner(*args):
            calls.append(args)
            return {'status': 'FAILED', 'prediction': 'UNKNOWN', 'inputTokens': None,
                    'outputTokens': None, 'model': {'rawResponse': '原文' * 40000}, 'requestAttempts': 1}
        identifier = run_batch(store, plan, runner, 'c' * 32)
        if not complete:
            (store / identifier / 'samples.jsonl').write_bytes(b'')
        return store, identifier, plan, runner, calls

    def test_重命名保留字节及旧入口且重复执行不创建副本(self):
        source = self.root / '.local/runs'
        source.mkdir(parents=True)
        (source / 'raw.bin').write_bytes(b'\x00\xff\x01')
        mappings = (('.local/runs', 'research-artifacts/runs/test'),)
        moved = migrate(self.root, mappings)
        self.assertEqual(1, len(moved))
        self.assertTrue(source.is_symlink())
        self.assertEqual(b'\x00\xff\x01', (source / 'raw.bin').read_bytes())
        self.assertEqual([], migrate(self.root, mappings))

    def test_目标冲突在任何移动前拒绝(self):
        for name in ('.local/a', '.local/b', 'research-artifacts/b'):
            (self.root / name).mkdir(parents=True)
        with self.assertRaises(ValueError):
            migrate(self.root, (('.local/a', 'research-artifacts/a'), ('.local/b', 'research-artifacts/b')))
        self.assertFalse((self.root / '.local/a').is_symlink())

    def test_规范原件恢复旧入口并预留未来收据(self):
        destination = self.root / 'research-artifacts/runs/test'
        destination.mkdir(parents=True)
        (destination / 'raw.json').write_bytes(b'{"unknown":true}')
        mappings = (('.local/runs', 'research-artifacts/runs/test'),
                    ('.evidence/test/evm', 'research-artifacts/receipts/evm'),
                    ('.local/r2/runs', 'research-artifacts/runs/test'),
                    ('.local/r2', '.local/solidity'))
        (self.root / '.local/solidity').mkdir(parents=True)
        self.assertEqual(4, len(restore_compatibility(self.root, mappings)))
        self.assertEqual(b'{"unknown":true}', (self.root / '.local/runs/raw.json').read_bytes())
        self.assertEqual(b'{"unknown":true}', (self.root / '.local/r2/runs/raw.json').read_bytes())
        self.assertTrue((self.root / '.local/solidity/runs').is_symlink())
        (self.root / '.evidence/test/evm/new.json').write_bytes(b'{"status":"UNKNOWN"}')
        self.assertEqual(b'{"status":"UNKNOWN"}', (self.root / 'research-artifacts/receipts/evm/new.json').read_bytes())
        self.assertEqual([], restore_compatibility(self.root, mappings))

    def test_子目录先分离父目录再迁移保持旧入口(self):
        source = self.root / '.local/r2/runs'
        source.mkdir(parents=True)
        (source / 'raw.json').write_bytes(b'{"unknown":true}')
        migrate(self.root, (('.local/r2/runs', 'research-artifacts/runs/test'),
                            ('.local/r2', '.local/solidity')))
        self.assertEqual(b'{"unknown":true}', (source / 'raw.json').read_bytes())

    def test_压缩后指标原文和缺失usage不变且续跑零新增请求(self):
        store, identifier, plan, runner, calls = self.batch()
        before = replay_batch(store, identifier)
        samples = (store / identifier / 'samples.jsonl').read_bytes()
        original_summary = json.dumps(before, ensure_ascii=False).encode()
        (store / identifier / 'summary.json').write_bytes(original_summary)
        result = compact(self.root)
        self.assertEqual(2, len(result))
        self.assertEqual(samples, read_artifact(store / identifier / 'samples.jsonl'))
        self.assertEqual(before, replay_batch(store, identifier))
        run_batch(store, plan, runner, identifier)
        save_summary(store / identifier, replay_batch(store, identifier))
        self.assertEqual(original_summary, read_artifact(store / identifier / 'summary.json'))
        self.assertEqual(1, len(calls))
        self.assertEqual([], compact(self.root))

    def test_未封口批次保留可续写文件(self):
        store, identifier, _, _, _ = self.batch(complete=False)
        self.assertEqual([], compact(self.root))
        self.assertTrue((store / identifier / 'samples.jsonl').is_file())

    def test_摘要不复制完整模型工具与样本(self):
        store, identifier, _, _, _ = self.batch()
        report = replay_batch(store, identifier)
        save_summary(store / identifier, report)
        summary = json.loads((store / identifier / 'summary.json').read_bytes())
        self.assertNotIn('samples', summary)
        self.assertEqual(report['denominators'], summary['denominators'])
        self.assertEqual(report['metrics'], summary['metrics'])
        self.assertEqual('samples.jsonl', summary['sampleArtifact'])
        self.assertLess((store / identifier / 'summary.json').stat().st_size, 10000)

    def test_页面下载归档仍返回原始JSONL且不调用模型(self):
        store, identifier, _, _, calls = self.batch()
        original = (store / identifier / 'samples.jsonl').read_bytes()
        compact(self.root)
        server = create_server(self.root, 0, auto_store=store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
            connection.request('GET', '/api/agent/auto-benchmark/runs/' + identifier + '/samples.jsonl')
            response = connection.getresponse()
            self.assertEqual(200, response.status)
            self.assertEqual(original, response.read())
            connection.close()
            self.assertEqual(1, len(calls))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_压缩损坏超限和链接均拒绝(self):
        path = self.root / 'raw.json'
        archived = path.with_name(path.name + '.gz')
        archived.write_bytes('无效gzip'.encode())
        with self.assertRaises(ValueError): read_artifact(path)
        archived.write_bytes(gzip.compress(b'x' * 100))
        with self.assertRaises(ValueError): read_artifact(path, max_bytes=50)
        archived.unlink()
        target = self.root / 'other.gz'
        target.write_bytes(gzip.compress('原文'.encode()))
        archived.symlink_to(target)
        with self.assertRaises(ValueError): read_artifact(path)

    def test_归档冲突不删除原件(self):
        path = self.root / 'raw.json'
        path.write_bytes('原始字节'.encode())
        path.with_name(path.name + '.gz').write_bytes(gzip.compress('其他字节'.encode()))
        with self.assertRaises(ValueError): archive_file(path)
        self.assertEqual('原始字节'.encode(), path.read_bytes())


if __name__ == '__main__':
    unittest.main()
