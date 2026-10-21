"""兼容命令入口；实际实现位于 verirag.evaluation.d1_offline_check。"""
from verirag.evaluation.d1_offline_check import main


if __name__ == '__main__':
    raise SystemExit(main())
