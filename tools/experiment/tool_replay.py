"""兼容命令入口；实际实现位于 verirag.evaluation.tool_replay。"""
from verirag.evaluation.tool_replay import main


if __name__ == '__main__':
    raise SystemExit(main())
