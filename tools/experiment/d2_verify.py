"""兼容命令入口；实际实现位于 verirag.analysis.d2_verify。"""
from verirag.analysis.d2_verify import main


if __name__ == '__main__':
    raise SystemExit(main())
