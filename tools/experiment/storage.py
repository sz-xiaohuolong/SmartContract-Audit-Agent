"""本地实验产物的规范编码、持久写入与单写者锁。"""
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from offline import digest, _unique_object


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
