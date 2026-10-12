"""研究原件、外部数据与本机环境的唯一目录映射；历史路径保留兼容入口。"""

# 子目录先移动，父目录最后移动；旧入口链接只定位同一份原件，不复制数据。
MAPPINGS = (
    ('.local/auto-benchmark-runs', 'research-artifacts/runs/benchmarks'),
    ('.local/auto-benchmark-diagnostics', 'research-artifacts/diagnostics/benchmark'),
    ('.local/audit-runs', 'research-artifacts/runs/audits'),
    ('.local/audit-workbench-runs', 'research-artifacts/runs/workbench'),
    ('.local/audit-batches', 'research-artifacts/runs/batches'),
    ('.local/mvp-runs', 'research-artifacts/runs/mvp'),
    ('.local/d1-exploratory-runs', 'research-artifacts/runs/exploratory'),
    ('.local/embedding-comparison', 'research-artifacts/runs/embedding-comparison'),
    ('.local/r2/tool-replays', 'research-artifacts/runs/derived'),
    ('.local/r2/d1-offline', 'research-artifacts/runs/d1-offline'),
    ('.local/r2/feasibility', 'research-artifacts/inputs/compilation-baseline'),
    ('.local/d1-kb-snapshots', 'research-artifacts/snapshots/bge'),
    ('.local/d1-nomic-snapshots', 'research-artifacts/snapshots/nomic'),
    ('.local/d1-nomic-embeddings', 'research-artifacts/snapshots/nomic-vectors'),
    ('.local/mvp-kb', 'research-artifacts/snapshots/mvp'),
    ('.local/d1-kb-v1', 'research-artifacts/inputs/knowledge-v1'),
    ('.local/d1-kb-candidates', 'research-artifacts/inputs/knowledge-candidates'),
    ('.local/first-batch', 'research-artifacts/inputs/first-batch'),
    ('.local/r1-s5', 'research-artifacts/inputs/formal-v2'),
    ('.local/evidence-archives', 'research-artifacts/archives'),
    ('.evidence/R2-20261010/S11-resolution/tool-bridge', 'research-artifacts/receipts/slither-legacy'),
    ('.evidence/R2-20261010/D2-deep-upgrade-20261012/tool', 'research-artifacts/receipts/slither'),
    ('.evidence/R2-20261010/D2-deep-upgrade-20261012/evm', 'research-artifacts/receipts/evm'),
    ('.evidence/R2-20261010/S11-S12-final/compilations', 'research-artifacts/receipts/compilations'),
    ('.local/dataset-candidates', 'data/external/candidates'),
    ('.local/atomicloans-upstream', 'data/external/atomicloans'),
    ('.local/r1-archive', '.local/recovery/r1-documents'),
    ('.local/doc-layout-20261010', '.local/recovery/document-layout'),
    ('.local/legacy-retirement-20261012', '.local/recovery/legacy-retirement'),
    ('.local/d1-embed-venv', '.local/envs/embedding'),
    ('.local/d1-embedding-model', '.local/models/bge'),
    ('.local/mvp-milvus', '.local/services/milvus'),
    ('.local/experiment-ui', '.local/services/ui'),
    ('.local/r2', '.local/solidity'),
)


def canonical_name(value):
    """只替换明确登记的路径前缀，避免修改普通字符串或相近目录名。"""
    for old, new in sorted(MAPPINGS, key=lambda row: len(row[0]), reverse=True):
        if value == old or value.startswith(old + '/'):
            return new + value[len(old):]
    return value
