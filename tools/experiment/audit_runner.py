"""兼容命令入口；实际实现位于 verirag.audit.audit_runner。"""
from verirag.audit.audit_runner import main


if __name__ == '__main__':
    raise SystemExit(main())
