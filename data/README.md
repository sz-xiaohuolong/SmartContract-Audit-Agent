# 项目数据

数据原件集中在本目录；应用在 `audit-mvp/`，实验工具在 `tools/experiment/`。

| 数据 | 入口 | 原件与用途 |
|---|---|---|
| SmartBugs Curated 整理文档 | `benchmarks/smartbugs-curated/` | 143 份包含来源、标签与 Solidity 的 Markdown；批量目标加载和探索分析使用 |
| 历史合约基准 | `benchmarks/legacy-testset/` | 350 份漏洞标签源码及 350 份 CSV、50 份安全标签源码；保留原划分 |
| 示例合约 | `examples/contracts/` | 4 份早期示例源码 |
| 漏洞参考资料 | `reference/智能合约漏洞速查表.md` | 原参考文本 |
| 来源、审核与固定编译输入 | `audit/r1/`、`audit/r2/` | 原来源登记、配对、固定候选及编译清单 |

2026-10-12 从旧 `src/main/resources/` 迁移 898 份数据文件，原件字节保持不变。迁移前版本为 `4ba5750`；原始目录与标签可通过 Git 历史核对。

历史“安全”标签是来源登记，不构成合约安全证明；迁移不改变标签、评测划分或研究准入状态。运行环境、活动知识快照与原始运行目录仍在 `.local/`，验收日志与截图放 `.evidence/`。
