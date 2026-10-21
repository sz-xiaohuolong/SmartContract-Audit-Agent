"""兼容命令入口；实际实现位于 verirag.analysis.bound_slither。"""
from verirag.analysis.bound_slither import main


if __name__ == '__main__':
    raise SystemExit(main())
