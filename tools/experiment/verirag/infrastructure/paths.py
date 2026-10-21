"""统一定位实验代码与仓库资源，覆盖实际生产源码的身份扫描。"""
from pathlib import Path


EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = EXPERIMENT_ROOT.parent.parent


def python_source_files(directory):
    """包含兼容入口和包内实现；测试、夹具及前端资源不作为执行源码。"""
    directory = Path(directory)
    return tuple(sorted((*directory.glob('*.py'), *(directory / 'verirag').rglob('*.py'))))
