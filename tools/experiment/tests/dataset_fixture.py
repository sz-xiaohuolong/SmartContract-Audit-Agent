"""生成最小原始数据集夹具，离线测试不依赖本机下载。"""
import json
from pathlib import Path


def smartbugs_fixture(directory, source, name='vault', category='reentrancy', lines=(1,),
                      origin='https://example.test/vault'):
    directory = Path(directory)
    relative = f'dataset/{category}/{name}.sol'
    path = directory / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source.encode('utf-8'))
    metadata = directory / 'vulnerabilities.json'
    entries = json.loads(metadata.read_text(encoding='utf-8')) if metadata.exists() else []
    entry = {'name': path.name, 'path': relative, 'source': origin,
             'vulnerabilities': [{'category': category, 'lines': list(lines)}]}
    entries = [row for row in entries if row['path'] != relative] + [entry]
    metadata.write_text(json.dumps(entries), encoding='utf-8')
    return path
