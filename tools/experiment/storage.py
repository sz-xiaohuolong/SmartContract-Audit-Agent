"""本地实验产物的规范编码、持久写入与单写者锁。"""
import fcntl
import gzip
import json
import os
import tempfile
import zlib
from contextlib import contextmanager
from pathlib import Path
from offline import digest, _unique_object


def artifact_exists(path):
    """历史原件允许无损压缩；逻辑文件名及原始字节摘要保持不变。"""
    path = Path(path)
    return path.is_file() or path.with_name(path.name + '.gz').is_file()


def read_artifact(path, max_bytes=512 * 1024 * 1024):
    """透明读取原件或其 gzip 归档，损坏和超限均报错，不返回空成功。"""
    path = Path(path)
    archived = path.with_name(path.name + '.gz')
    if path.is_file():
        if archived.is_file():
            raise ValueError('原件与压缩归档同时存在，须先核对唯一来源')
        opener = path.open
    else:
        if archived.is_symlink():
            raise ValueError('压缩原件不接受符号链接')
        opener = lambda mode: gzip.open(archived, mode)
    try:
        with opener('rb') as source:
            data = source.read(max_bytes + 1)
    except (gzip.BadGzipFile, EOFError, zlib.error) as error:
        raise ValueError('历史原件压缩归档损坏') from error
    if len(data) > max_bytes:
        raise ValueError('历史原件解压后超过读取上限')
    return data


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode(data):
    def invalid(value):
        raise ValueError("JSON 不允许非有限数值")
    return json.loads(data, object_pairs_hook=_unique_object, parse_constant=invalid)


def fingerprint(value):
    return digest(encode(value))


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def durable_write(path, data):
    with Path(path).open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def atomic_json(path, value):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encode(value) + b"\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


@contextmanager
def exclusive_lock(path):
    # 锁文件永久保留，避免删除后出现两个 inode 上的并发锁。
    with Path(path).open("a+b") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error: raise ValueError("已有进程正在写入该实验或快照") from error
        try: yield
        finally: fcntl.flock(lock, fcntl.LOCK_UN)
