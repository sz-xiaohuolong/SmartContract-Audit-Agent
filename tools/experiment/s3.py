"""兼容命令入口；实际实现位于 verirag.experiments.s3。"""
from verirag.experiments.s3 import main


if __name__ == '__main__':
    raise SystemExit(main())
