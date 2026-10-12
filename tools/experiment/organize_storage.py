"""一键拆分本机环境与研究原件，并无损压缩已封口的大型输出。"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import gzip
import hashlib
import http.client
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

from artifact_layout import MAPPINGS
from benchmark_batch import replay_batch
from snapshots import verify_snapshot
from storage import atomic_json, exclusive_lock, read_artifact


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(directory):
    """不跟随目录链接，也不把可再生成的字节码和锁内容当成研究原件。"""
    result = {}
    for path in sorted(directory.rglob('*')):
        if '__pycache__' in path.parts or path.name.endswith('.lock'):
            continue
        name = path.relative_to(directory).as_posix()
        if path.is_symlink():
            result[name] = {'link': os.readlink(path)}
        elif path.is_file():
            data = path.read_bytes()
            result[name] = {'bytes': len(data), 'sha256': sha(data)}
    return result


def migrate(root, mappings=MAPPINGS):
    """逐目录核对后原地重命名；旧入口保留相对链接，历史清单不改字节。"""
    root = Path(root).resolve()
    plan = []
    for old, new in mappings:
        source, destination = root / old, root / new
        if source.exists() and not source.resolve().is_relative_to(root):
            raise ValueError('迁移来源超出项目目录')
        if not destination.resolve().is_relative_to(root):
            raise ValueError('迁移目标超出项目目录')
        if source.is_symlink():
            if source.resolve() != destination.resolve() or not destination.is_dir():
                raise ValueError('旧入口不是已登记的兼容链接：' + old)
            continue
        if not source.exists():
            continue
        if not source.is_dir() or destination.exists():
            raise ValueError('目标冲突，禁止覆盖：' + new)
        plan.append((old, new))
    result = []
    for old, new in plan:
        source, destination = root / old, root / new
        before = inventory(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        source.symlink_to(os.path.relpath(destination, source.parent), target_is_directory=True)
        if inventory(destination) != before:
            raise ValueError('目录迁移后字节或链接发生变化：' + new)
        result.append({'old': old, 'new': new, 'files': len(before),
                       'bytes': sum(row.get('bytes', 0) for row in before.values()),
                       'treeSha256': sha(json.dumps(before, sort_keys=True, separators=(',', ':')).encode())})
    return result


def restore_compatibility(root, mappings=MAPPINGS):
    """从规范原件恢复旧入口；预留尚未运行的 EVM 收据，避免再次写入证据目录。"""
    root = Path(root).resolve()
    reserved = 'research-artifacts/receipts/evm'
    plan = []
    for old, new in mappings:
        source, destination = root / old, root / new
        if not destination.resolve().is_relative_to(root):
            raise ValueError('兼容目标超出项目目录')
        if source.is_symlink():
            if source.resolve() != destination.resolve() or not destination.is_dir():
                raise ValueError('旧入口不是已登记的兼容链接：' + old)
            continue
        if source.exists():
            raise ValueError('旧入口尚未迁移：' + old)
        if destination.exists() and not destination.is_dir():
            raise ValueError('兼容目标不是目录：' + new)
        if destination.is_dir() or new == reserved:
            if not source.parent.resolve().is_relative_to(root):
                raise ValueError('兼容入口超出项目目录')
            plan.append((old, new))
    result = []
    # 恢复时先建立父目录入口，子入口才会落在规范目录中。
    for old, new in sorted(plan, key=lambda row: len(Path(row[0]).parts)):
        source, destination = root / old, root / new
        destination.mkdir(parents=True, exist_ok=True)
        source.parent.mkdir(parents=True, exist_ok=True)
        source.symlink_to(os.path.relpath(destination, source.parent), target_is_directory=True)
        result.append({'old': old, 'new': new})
    return result


def archive_file(path):
    """写入临时归档、验证还原字节，再替换和删除源文件；重复调用不重压缩。"""
    path = Path(path)
    destination = path.with_name(path.name + '.gz')
    if not path.is_file():
        return None
    data = path.read_bytes()
    if destination.is_symlink():
        raise ValueError('归档目标不接受链接')
    if destination.exists():
        if gzip.decompress(destination.read_bytes()) != data:
            raise ValueError('既有归档与原件不一致')
    else:
        temporary = destination.with_name(destination.name + '.pending')
        with temporary.open('xb') as output:
            output.write(gzip.compress(data, compresslevel=6, mtime=0))
            output.flush()
            os.fsync(output.fileno())
        if gzip.decompress(temporary.read_bytes()) != data:
            raise ValueError('压缩原件不能按字节还原')
        temporary.rename(destination)
    if path.read_bytes() != data:
        raise ValueError('压缩期间原件被写入，停止删除')
    path.unlink()
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data),
            'archiveBytes': destination.stat().st_size}


def compact(root):
    """未完成批次保留可续写原件；已封口原件只改变存储编码。"""
    root = Path(root).resolve()
    result = []
    store = root / 'research-artifacts/runs/benchmarks'
    for plan in sorted(store.glob('*/plan.json')):
        report = replay_batch(store, plan.parent.name)
        if report['status'] != 'COMPLETED':
            continue
        for name in ('samples.jsonl', 'summary.json', 'samples.csv'):
            path = plan.parent / name
            if path.is_file() and path.stat().st_size > 64 * 1024:
                item = archive_file(path)
                result.append(item)
    derived = root / 'research-artifacts/runs/derived'
    for manifest in sorted(derived.glob('*/manifest.json')):
        if json.loads(manifest.read_bytes()).get('status') != 'COMPLETED':
            continue
        for name in ('samples.jsonl', 'assessments.jsonl', 'summary.json'):
            path = manifest.parent / name
            if path.is_file() and path.stat().st_size > 64 * 1024:
                result.append(archive_file(path))
    for base in ('research-artifacts/receipts/slither', 'research-artifacts/receipts/slither-legacy',
                 'research-artifacts/receipts/compilations'):
        for path in sorted((root / base).rglob('*.json')):
            if path.stat().st_size > 4 * 1024:
                result.append(archive_file(path))
    for base in ('research-artifacts/snapshots/bge', 'research-artifacts/snapshots/nomic'):
        for path in sorted((root / base).glob('*/snapshot.json')):
            verify_snapshot(path.parent.parent, path.parent.name)
            if path.stat().st_size > 64 * 1024:
                result.append(archive_file(path))
    baseline = root / 'research-artifacts/inputs/compilation-baseline'
    for path in sorted(baseline.glob('*/compiler*output.json')):
        if path.stat().st_size > 64 * 1024:
            result.append(archive_file(path))
    for item in result:
        item['path'] = str(Path(item['path']).relative_to(root))
        if sha(read_artifact(root / item['path'])) != item['sha256']:
            raise ValueError('归档读取摘要不一致')
    return result


def local_processes(root):
    """只识别工作目录属于本项目的实验进程，不读取或输出凭证环境。"""
    rows = subprocess.check_output(['ps', '-eo', 'pid=,command='], text=True).splitlines()
    servers, busy = [], []
    for row in rows:
        parts = row.strip().split(None, 1)
        if len(parts) != 2 or 'python' not in parts[1].split()[0].lower():
            continue
        pid, command = int(parts[0]), shlex.split(parts[1])
        scripts = [value for value in command[1:] if value.endswith('.py')]
        if not scripts or Path(scripts[0]).name not in ('local_ui.py', 'benchmark_cli.py', 'bound_slither.py', 'tool_replay.py', 'evm_witness.py'):
            continue
        cwd = subprocess.run(['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'], capture_output=True, text=True, timeout=5)
        if not any(line == 'n' + str(root) for line in cwd.stdout.splitlines()):
            continue
        if Path(scripts[0]).name != 'local_ui.py':
            busy.append(pid)
        else:
            port = int(command[command.index('--port') + 1]) if '--port' in command else 8765
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
            try:
                connection.request('GET', '/api/storage/status')
                response = connection.getresponse()
                body = response.read()
                if response.status == 200 and json.loads(body).get('running'):
                    raise ValueError('本机页面正在执行实验，保留原件并停止整理')
            finally:
                connection.close()
            servers.append({'pid': pid, 'command': command, 'port': port})
    if busy:
        raise ValueError('有真实实验或工具进程正在运行，保留原件并停止整理')
    return servers


def start_servers(root, servers):
    """仅恢复本次停止的本机页面，不请求模型或工具端点。"""
    logs = root / '.local/services/ui'
    logs.mkdir(parents=True, exist_ok=True)
    restored = []
    for server in servers:
        with (logs / ('storage-layout-' + str(server['port']) + '.log')).open('ab') as output:
            process = subprocess.Popen(server['command'], cwd=root, stdout=output, stderr=output, start_new_session=True)
        for attempt in range(80):
            if process.poll() is not None:
                raise ValueError('本机页面重启失败：' + str(server['port']))
            try:
                connection = http.client.HTTPConnection('127.0.0.1', server['port'], timeout=1)
                connection.request('GET', '/agent.html')
                response = connection.getresponse()
                response.read()
                connection.close()
                if response.status == 200:
                    restored.append({'port': server['port'], 'pid': process.pid})
                    break
            except OSError:
                pass
            time.sleep(0.1)
        else:
            raise ValueError('本机页面没有恢复响应')
    return restored


def main():
    parser = argparse.ArgumentParser(description='一键整理本机环境、外部数据和研究原件；默认只预览')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--apply', action='store_true', help='执行迁移与无损压缩')
    parser.add_argument('--restart-ui', action='store_true', help='短暂停止并恢复本项目的本机页面')
    args = parser.parse_args()
    root = args.root.resolve()
    if not args.apply:
        print(json.dumps([{'old': old, 'new': new} for old, new in MAPPINGS if (root / old).exists()], ensure_ascii=False, indent=2))
        return
    servers = local_processes(root)
    if servers and not args.restart_ui:
        raise ValueError('本机页面仍运行；使用 --restart-ui 使其加载压缩读取支持')
    (root / '.local').mkdir(exist_ok=True)
    stopped, restored = [], []
    with ExitStack() as locks:
        locks.enter_context(exclusive_lock(root / '.local/.storage-layout.lock'))
        seen = set()
        for old, new in MAPPINGS:
            directory = root / (new if (root / old).is_symlink() else old)
            for path in sorted(directory.rglob('*.lock')):
                inode = path.stat().st_dev, path.stat().st_ino
                if inode not in seen:
                    seen.add(inode)
                    locks.enter_context(exclusive_lock(path))
        try:
            for server in servers:
                os.kill(server['pid'], signal.SIGTERM)
                stopped.append(server)
            for server in stopped:
                for attempt in range(50):
                    try:
                        os.kill(server['pid'], 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.1)
                else:
                    raise ValueError('本机页面未退出，停止整理')
            moved = migrate(root)
            compatible = restore_compatibility(root)
            archived = compact(root)
            record = {'schemaVersion': 1, 'at': datetime.now(timezone.utc).isoformat(),
                      'moved': moved, 'archived': archived,
                      'restoredCompatibility': compatible,
                      'bytesReleased': sum(item['bytes'] - item['archiveBytes'] for item in archived),
                      'newModelRequests': 0}
            directory = root / 'research-artifacts/migrations'
            directory.mkdir(parents=True, exist_ok=True)
            atomic_json(directory / ('storage-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '.json'), record)
        finally:
            restored = start_servers(root, stopped)
    print(json.dumps({'movedDirectories': len(moved), 'archivedFiles': len(archived),
                      'restoredCompatibility': len(compatible),
                      'bytesReleased': record['bytesReleased'], 'restoredUi': restored,
                      'newModelRequests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
