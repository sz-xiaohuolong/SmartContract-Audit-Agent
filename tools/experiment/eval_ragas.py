"""兼容命令入口；实际实现位于 verirag.evaluation.eval_ragas。"""
from verirag.evaluation.eval_ragas import main


if __name__ == '__main__':
    raise SystemExit(main())
