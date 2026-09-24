"""S1b 命令入口；模型批处理必须显式选择配置与供应商。"""
import argparse
from pathlib import Path

from batch import replay, run_batch
from isolation import validate_manifest
from java_adapter import JavaExecutor
from snapshots import activate_snapshot, build_snapshot, verify_snapshot
from storage import decode, encode


def read(path):
    return decode(Path(path).read_bytes())


def main():
    parser = argparse.ArgumentParser(description="审核划分、知识快照与实验断点恢复")
    commands = parser.add_subparsers(dest="command", required=True)
    split = commands.add_parser("validate-splits", help="离线检查人工审核清单的组隔离")
    split.add_argument("--manifest", required=True)
    build = commands.add_parser("snapshot-build", help="从审核文档和已有向量构建离线快照")
    build.add_argument("--root", required=True)
    build.add_argument("--bundle", required=True)
    for name in ("snapshot-verify", "snapshot-activate"):
        command = commands.add_parser(name, help="校验快照" if name.endswith("verify") else "原子激活本地完整快照")
        command.add_argument("--root", required=True)
        command.add_argument("--id", required=True)
    for name in ("run", "resume"):
        command = commands.add_parser(name, help="显式执行或恢复批处理；会调用所选模型")
        for option in ("plan", "root", "journal", "jar", "config", "provider"):
            command.add_argument("--" + option, required=True)
        command.add_argument("--java", default="java")
        command.add_argument("--timeout", type=float, default=660)
        command.add_argument("--snapshot-root")
        command.add_argument("--retry-id", action="append", default=[], help="明确授权重试该失败或不确定样本")
    replay_command = commands.add_parser("replay", help="只读重算日志报告，不调用模型")
    replay_command.add_argument("--journal", required=True)
    args = parser.parse_args()
    try:
        status = 0
        if args.command == "validate-splits":
            indexed = validate_manifest(read(args.manifest))
            result = {"validated": len(indexed), "isolation": "PASSED"}
        elif args.command == "snapshot-build":
            bundle = read(args.bundle)
            if not isinstance(bundle, dict) or set(bundle) != {"manifest", "documents", "embedding", "chunking", "vectors"}:
                raise ValueError("快照输入字段不完整")
            result = {"snapshot_id": build_snapshot(args.root, **bundle)}
        elif args.command == "snapshot-verify":
            payload = verify_snapshot(args.root, args.id)
            result = {"snapshot_id": args.id, "rows": len(payload["rows"]), "integrity": "PASSED"}
        elif args.command == "snapshot-activate":
            result = activate_snapshot(args.root, args.id)
        elif args.command == "replay":
            result = replay(args.journal)
        else:
            if args.command == "resume" and not Path(args.journal).is_file(): raise ValueError("恢复需要已有日志")
            executor = JavaExecutor(args.jar, args.config, args.provider, args.timeout, args.java)
            result = run_batch(read(args.plan), args.root, args.journal, executor, executor.execution,
                               retry_ids=args.retry_id, snapshot_root=args.snapshot_root)
            status = 0 if result["metrics"]["completed"] == result["metrics"]["planned"] else 1
        print(encode(result).decode("utf-8"))
        return status
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        # 不输出异常原文，避免配置或第三方错误携带密钥。
        parser.exit(2, "输入或产物无效：请检查审核清单、摘要绑定、日志完整性与路径；未自动切换配置或重试。\n")


if __name__ == "__main__":
    raise SystemExit(main())
