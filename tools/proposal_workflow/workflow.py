"""管理开题报告任务、证据快照与可恢复的验收状态。"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone


DEPENDENCIES = {
    'T00': [], 'T01': ['T00'], 'T02': ['T01'], 'T03': ['T01'],
    'T04': ['T01'], 'T05': ['T03', 'T04'],
    'T06': ['T02', 'T03', 'T04', 'T05'], 'T07': ['T06'],
    'T08': ['T07'], 'T09': ['T08'], 'T10': ['T09'],
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    """先持久化临时文件，再替换权威状态，不留下半写 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.proposal-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Workflow:
    def __init__(self, root, run):
        self.root = Path(root).resolve()
        self.run = Path(run).resolve()
        self.run.relative_to(self.root)
        self.control = self.run.parent.parent
        self.state_file = self.control / '运行状态.json'

    @contextmanager
    def locked(self):
        self.control.mkdir(parents=True, exist_ok=True)
        with (self.control / '.state.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = json.loads(self.state_file.read_text())
            if state['轮次'] != self.run.name:
                raise ValueError('状态指向另一轮，不能覆盖')
            yield state
            atomic_json(self.state_file, state)

    def verify_inputs(self):
        manifest = json.loads((self.run / '输入清单.json').read_text())
        failed = []
        for item in manifest['资料']:
            relative = item.get('快照', item['来源'])
            path = (self.root / relative).resolve()
            path.relative_to(self.root)
            if not path.is_file() or digest(path) != item['摘要']:
                failed.append(relative)
        if failed:
            raise ValueError('输入摘要漂移或缺失：' + '；'.join(failed))
        return manifest

    def event(self, kind, task, **extra):
        record = {'日期': datetime.now(timezone.utc).isoformat(),
                  '轮次': self.run.name, '动作': kind, '任务': task, **extra}
        with (self.control / '事件记录.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def start(self, task, agent='总控'):
        self.verify_inputs()
        with self.locked() as state:
            entry = state['任务'][task]
            if entry['状态'] in ('执行中', '已验收'):
                raise ValueError('任务已经执行或验收，禁止重复派发')
            if any(state['任务'][x]['状态'] != '已验收' for x in DEPENDENCIES[task]):
                raise ValueError('前置任务尚未验收')
            if agent != '总控':
                if state.get('派发次数', 0) >= 12:
                    raise ValueError('已达到派发上限')
                active = sum(x.get('代理', '总控') != '总控' and x['状态'] == '执行中'
                             for x in state['任务'].values())
                if active >= 3:
                    raise ValueError('已达到活跃子代理上限')
                state['派发次数'] = state.get('派发次数', 0) + 1
            entry.update({'状态': '执行中', '代理': agent})
            self.event('派发', task, 代理=agent)

    def accept(self, task, outputs, note):
        self.verify_inputs()
        files = []
        if not outputs:
            raise ValueError('验收需要实际文件')
        for name in outputs:
            path = Path(name).resolve()
            path.relative_to(self.run)
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError('输出缺失或为空：' + str(path))
            files.append({'路径': str(path.relative_to(self.run)), '摘要': digest(path)})
        with self.locked() as state:
            entry = state['任务'][task]
            if entry['状态'] not in ('执行中', '待验收', '待修订'):
                raise ValueError('该任务不处于可验收状态')
            entry.update({'状态': '已验收', '产物': files, '验收说明': note})
            self.event('验收', task, 产物=files, 说明=note)

    def status(self):
        state = json.loads(self.state_file.read_text())
        changed = []
        for name, task in state['任务'].items():
            for item in task.get('产物', []):
                path = self.run / item['路径']
                if not path.is_file() or digest(path) != item['摘要']:
                    changed.append(name)
        return {'状态': state, '需重验任务': sorted(set(changed)),
                '活动任务说明': '执行中状态必须由总控核验会话句柄，不能据日志自动判定终止'}

    def initialize(self, config):
        """使用显式清单初始化新轮次，不覆盖既有轮次或活动控制状态。"""
        if self.run.exists() or self.state_file.exists():
            raise ValueError('运行目录或权威状态已存在，请先检查 status，禁止覆盖')
        commit = subprocess.check_output(['git', 'rev-parse', '--verify',
                                         config['commit'] + '^{commit}'], cwd=self.root, text=True).strip()
        materials = []
        pending = []
        for kind, names in [('已提交快照', config.get('git_paths', [])),
                            ('本地原件', config.get('local_paths', []))]:
            for name in names:
                rel = Path(name)
                if rel.is_absolute() or '..' in rel.parts:
                    raise ValueError('输入路径必须在项目内')
                if rel.name in ('.env', 'providers.local.properties') or rel.suffix in ('.pem', '.key'):
                    raise ValueError('不能将凭证文件加入快照')
                source = (self.root / rel).resolve(); source.relative_to(self.root)
                if kind == '已提交快照':
                    data = subprocess.check_output(['git', 'show', commit + ':' + rel.as_posix()], cwd=self.root)
                    dest = self.run / '快照' / rel
                    item = {'类型': kind, '来源': str(rel), '快照': str(dest.relative_to(self.root)), '提交': commit}
                    pending.append((dest, data))
                else:
                    data = source.read_bytes()
                    if hashlib.sha256(data).hexdigest() != digest(source):
                        raise ValueError('本地原件正在变化，请固定后重试')
                    item = {'类型': kind, '来源': str(rel)}
                item['摘要'] = hashlib.sha256(data).hexdigest(); materials.append(item)
        if not materials:
            raise ValueError('初始化需要显式输入资料')
        self.run.mkdir(parents=True)
        for dest, data in pending:
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
        atomic_json(self.run / '输入清单.json', {'轮次': self.run.name, '基点': commit, '资料': materials,
                    '研究批次': config.get('batch_id'), '新研究付费请求上限': 0})
        atomic_json(self.state_file, {'轮次': self.run.name, '状态': '材料核验', '基点': commit,
                    '派发次数': 0, '任务': {k: {'状态': '待执行'} for k in DEPENDENCIES}})
        self.event('初始化', 'T00', 基点=commit)

    def assemble(self, sources, output):
        """仅合成已验收且摘要未变的正文，不自动推断段落顺序或事实。"""
        self.verify_inputs()
        state = self.status()
        if state['需重验任务']:
            raise ValueError('已验收产物漂移，先重验')
        accepted = {str((self.run / p['路径']).resolve())
                    for t in state['状态']['任务'].values() if t['状态'] == '已验收'
                    for p in t.get('产物', [])}
        target = Path(output).resolve(); target.relative_to(self.run)
        pieces = []
        for source in sources:
            p = Path(source).resolve()
            if str(p) not in accepted:
                raise ValueError('不能合成未验收产物：' + str(p))
            if p == target: raise ValueError('合成输出不能覆盖输入')
            pieces.append(p.read_text().strip())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('\n\n'.join(pieces) + '\n')
        self.event('合成辅助', 'T06', 输出=str(target.relative_to(self.run)), 摘要=digest(target))


def bib_entries(text):
    """读取本地括号型 BibTeX，按配对花括号保留完整条目。"""
    entries = {}
    for match in re.finditer(r'@(\w+)\s*\{\s*([^,]+),', text):
        depth, end = 1, match.end()
        while end < len(text) and depth:
            if text[end] == '{' and (end == 0 or text[end - 1] != '\\'):
                depth += 1
            elif text[end] == '}' and (end == 0 or text[end - 1] != '\\'):
                depth -= 1
            end += 1
        if depth:
            raise ValueError('BibTeX 花括号未闭合')
        key = match.group(2).strip()
        if key in entries:
            raise ValueError('重复引用键：' + key)
        block = text[match.end():end - 1]
        fields = {}
        for field in re.finditer(r'(\w+)\s*=\s*\{', block):
            n, i = 1, field.end()
            while i < len(block) and n:
                if block[i] == '{' and block[i - 1] != '\\': n += 1
                elif block[i] == '}' and block[i - 1] != '\\': n -= 1
                i += 1
            fields[field.group(1).lower()] = block[field.end():i - 1].replace('\\_', '_')
        entries[key] = {'type': match.group(1).lower(), 'fields': fields,
                        'raw': text[match.start():end]}
    return entries


def check_markdown(path, bib):
    path = Path(path)
    text = path.read_text()
    entries = bib_entries(Path(bib).read_text())
    keys = re.findall(r'\[@([^\]]+)\]', text)
    missing_keys = sorted(set(keys) - set(entries))
    missing_links = []
    for target in re.findall(r'\]\(([^)]+)\)', text):
        target = target.split('#')[0]
        if target and not re.match(r'https?://|mailto:', target):
            if not (path.parent / target).resolve().exists(): missing_links.append(target)
    return {'引用次数': len(keys), '使用键': list(dict.fromkeys(keys)),
            '缺失键': missing_keys, '失效链接': missing_links,
            '围栏闭合': text.count('```') % 2 == 0,
            '需语义复核': sorted(set(re.findall(r'首次|不可推翻|保证提升|杜绝预训练污染', text)))}


def check_metric_claims(claims, summary):
    """核对明确登记的数字路径与父批次；不以词法匹配代替全文语义审查。"""
    if claims['batchId'] != summary['batchId']:
        raise ValueError('数字登记与汇总来自不同批次')
    errors = []
    for claim in claims['values']:
        actual = summary
        for key in claim['path'].split('.'):
            actual = actual[key]
        expected = claim['value']
        if isinstance(actual, (int, float)) and not isinstance(actual, bool):
            match = abs(actual - expected) <= claim.get('tolerance', 0)
        else: match = actual == expected
        if not match: errors.append(claim['path'])
    return {'父批次': summary['batchId'], '核对数': len(claims['values']), '错误路径': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    parser.add_argument('--run', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('verify')
    sub.add_parser('status')
    init = sub.add_parser('init'); init.add_argument('config')
    assemble = sub.add_parser('assemble'); assemble.add_argument('output'); assemble.add_argument('sources', nargs='+')
    metrics = sub.add_parser('metrics'); metrics.add_argument('claims'); metrics.add_argument('summary')
    start = sub.add_parser('start'); start.add_argument('task'); start.add_argument('--agent', default='总控')
    accept = sub.add_parser('accept'); accept.add_argument('task'); accept.add_argument('outputs', nargs='+'); accept.add_argument('--note', required=True)
    check = sub.add_parser('check'); check.add_argument('markdown'); check.add_argument('bib')
    args = parser.parse_args()
    flow = Workflow(args.root, args.run)
    if args.command == 'init': flow.initialize(json.loads(Path(args.config).read_text())); result = flow.status()
    elif args.command == 'assemble': flow.assemble(args.sources, args.output); result = {'输出': args.output}
    elif args.command == 'metrics': result = check_metric_claims(json.loads(Path(args.claims).read_text()), json.loads(Path(args.summary).read_text()))
    elif args.command == 'verify': result = flow.verify_inputs()
    elif args.command == 'status': result = flow.status()
    elif args.command == 'start': flow.start(args.task, args.agent); result = flow.status()
    elif args.command == 'accept': flow.accept(args.task, args.outputs, args.note); result = flow.status()
    else: result = check_markdown(args.markdown, args.bib)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == 'check' and (result['缺失键'] or result['失效链接'] or not result['围栏闭合']): return 1
    if args.command == 'metrics' and result['错误路径']: return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
