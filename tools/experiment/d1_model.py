"""从固定镜像获取按摘要锁定的本地嵌入模型，不调用付费模型接口。"""
import argparse
import hashlib
import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from d1_embed import DIMENSION, MODEL, MODEL_MANIFEST, REVISION, verify_model_dir
from storage import decode


MIRROR = 'https://modelscope.cn/models/BAAI/bge-small-en-v1.5/resolve/master/'


def fetch_model(root, manifest, opener=urllib.request.urlopen):
    if (manifest.get('modelId') != MODEL or manifest.get('revision') != REVISION
            or manifest.get('dimension') != DIMENSION or manifest.get('mirror') != MIRROR
            or not isinstance(manifest.get('files'), dict) or not manifest['files']):
        raise ValueError('固定模型清单身份无效')
    root = Path(root).resolve()
    for relative, expected in manifest['files'].items():
        path = Path(relative)
        candidate = root / path
        target = candidate.resolve()
        if (path.is_absolute() or '..' in path.parts or not target.is_relative_to(root)
                or candidate.is_symlink() or not isinstance(expected, str) or len(expected) != 64):
            raise ValueError('固定模型路径或摘要无效')
        if target.exists():
            if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError('既有模型文件摘要不符，禁止覆盖')
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            request = urllib.request.Request(MIRROR + urllib.parse.quote(relative), headers={'User-Agent': 'd1-model-fetch/1'})
            with opener(request, timeout=60) as response, tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                temporary = Path(output.name)
                digest = hashlib.sha256()
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 150_000_000:
                        raise ValueError('模型单文件超过上限')
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if digest.hexdigest() != expected:
                raise ValueError('下载模型文件摘要不符：' + relative)
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    verify_model_dir(root, manifest['files'])
    return {'model': MODEL, 'revision': REVISION, 'verifiedFiles': len(manifest['files'])}


def main():
    parser = argparse.ArgumentParser(description='获取并校验固定版本的本地语义嵌入模型')
    parser.add_argument('--model-dir', default='.local/d1-embedding-model')
    args = parser.parse_args()
    try:
        result = fetch_model(args.model_dir, decode(MODEL_MANIFEST.read_bytes()))
    except (ValueError, OSError) as error:
        parser.exit(2, '固定模型获取失败：' + str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
