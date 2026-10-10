# VeriRAG 毕业论文工程

| 项目定位 | 当前入口 |
|---|---|
| 使用者与目标 | 论文作者与审核者；可复现的智能合约审计与研究证据 |
| 当前 Release | R2-20261010；[需求基线](releases/R2-20261010/PROJECT_BRIEF.md)、[完整规格](releases/R2-20261010/SPEC.md) |
| 质量标准 | 工程验收与研究验证分别记录；构建、离线测试和适用真实验收按 [AGENTS](../../AGENTS.md) 执行 |

## 唯一文档地图

恢复顺序：先读本页和 PROGRESS，再读当前 Release 的 SPEC 及当前任务所需文件。根目录的三份文档持续更新，版本正文在各自 Release 内维护。

| 职责 | 入口 | 状态与依据 |
|---|---|---|
| 当前阶段、任务、证据和下一步 | [PROGRESS](PROGRESS.md) | 现行；按代码、Git 和运行证据核验 |
| 当前真实架构与运行入口 | [TECH_DESIGN](TECH_DESIGN.md) | 已验工程基线及当前构建边界 |
| 当前需求与完整行为 | [R2 基线](releases/R2-20261010/PROJECT_BRIEF.md)、[SPEC](releases/R2-20261010/SPEC.md) | 沿用既有 R2 冻结范围 |
| 当前目标方案与任务依赖 | [R2 设计](releases/R2-20261010/PROPOSED_DESIGN.md)、[计划](releases/R2-20261010/IMPLEMENTATION_PLAN.md) | 构建中；Slice 在统一计划中追踪 |
| 当前验收与先导资料 | [R2 验收](releases/R2-20261010/VERIFICATION.md)、[真实案例](releases/R2-20261010/attachments/REAL_CASE_PILOT.md) | 整体 UNVERIFIED；逐项据实更新 |
| 上一工程阶段的完整记录 | [R1 基线](releases/R1/PROJECT_BRIEF.md)、[规格](releases/R1/SPEC.md)、[计划](releases/R1/IMPLEMENTATION_PLAN.md)、[验收](releases/R1/VERIFICATION.md) | 以 `4dfc7e1` 工程及 `9beb7b8` 实验为依据；保留原局部批准 |
| 历史提案 | [R0 基线](releases/R0-20260918/PROJECT_BRIEF.md)、[旧源码调查](releases/R0-20260918/SOURCE_SURVEY.md) | 当时的 DRAFT 与调查记录 |
| 重大决定与缺陷调查 | [审计范围决定](decisions/DEC-001_SINGLE_AUDIT_SCOPE.md)、[配置冻结调查](bugs/BUG-001_CONFIGURATION_SNAPSHOT.md) | 原批准和修复依据沿用 |
| 原始证据与正文历史快照 | [.evidence/R1](../../.evidence/R1/)、[文档迁移清单](../../.evidence/document-layout/manifest.json)；当前证据 `.evidence/R2-20261010/` | 已跟踪旧证据继续跟踪；新增暂存默认忽略 |
| 运行数据、源文件与测试夹具 | [数据](../../data/audit/r1/)、[夹具](../../tools/experiment/fixtures/)、[工具说明](../../tools/experiment/README.md) | 程序读取的输入，继续版本控制 |

## 维护规则

同一 Release 内只维护一份完整规格、计划和验收矩阵；每个 Slice 在计划中一条记录，进度只记录当前执行事实。目标方案放 PROPOSED_DESIGN，已实现且核验的架构更新 TECH_DESIGN。

真实发布后才封存版本并记录发布后复盘；当前目录标识沿用 R1、R2-20261010。版本的变更或复盘按实际需要添加，避免空模板。历史状态和研究缺口不因文档整理改变。
