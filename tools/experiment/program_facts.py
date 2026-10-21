"""兼容命令入口；实际实现位于 verirag.analysis.program_facts。"""
from verirag.analysis.program_facts import main


if __name__ == '__main__':
    raise SystemExit(main())
