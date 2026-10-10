# VeriRAG 毕业论文工程：文档入口

更新：2026-10-10。当前在主目录 `main` 开发，实际提交以 Git 历史为准。

## 当前定位

- 最近工程工作包：S9「单合约深度审计与 D2 闭环」，存量路径标识为 `R1-S9`；其[规格](releases/R1/SPEC.md#s9-spec)、[实施计划](releases/R1/IMPLEMENTATION_PLAN.md#s9-implementation-plan)和[验证记录](releases/R1/VERIFICATION.md#s9-verification)继续提供该局部范围的批准与验收依据。
- 整体 Release 边界与完整有效需求尚未统一；不能仅凭 `R1-Sx` 目录名认定每个 Slice 都是独立 Release，也不能把 S9 的局部验收状态扩展为 R1 整体验收。历史局部批准与验证记录保留。
- 当前执行状态、验证及下一任务以 [PROGRESS](PROGRESS.md) 为准。
- 最新真实 API 批量实验：[2026-10-10 三策略与 D2 报告](experiments/2026-10-10_API_BATCH_REPORT.md)，159 次真实请求已结束；模型标签指标与工具／D2 结果分别列出。
- 使用者为论文作者与审核者；正式标签、数据比例及 D1/D2 方法创新结论仍需后续审核与研究证据。

## 唯一文档地图

本表是仓库唯一权威地图，只导航职责与来源。恢复时先读本表和 PROGRESS，再按当前任务读取对应事实源；不默认拼接全部历史 Slice 文档。

| 职责 | 实际路径 | 状态 | 定位依据 |
|---|---|---|---|
| Agent 规则与验证命令 | [AGENTS](../../AGENTS.md) | 现行 | 主目录开发、离线测试及提交同步约定；末段旧架构仅适用于历史 `src/` |
| 当前执行位置、缺口与下一任务 | [PROGRESS](PROGRESS.md) | 现行 | 首屏为当前任务；下方按时间保留实验与工程记录 |
| 当前完整有效需求与整体 Release 边界 | 尚无统一入口；局部依据见 [S0 规格](releases/R1/SPEC.md#s0-spec)、[S9 规格](releases/R1/SPEC.md#s9-spec)及相关历史切片 | 待整合 | 存量批准覆盖各局部范围；未建立统一 R1 基线，目录名不能证明发布边界 |
| 最近 S9 工作包的局部需求 | [S9 规格](releases/R1/SPEC.md#s9-spec) | 已冻结的局部范围，暂沿用 | 文件记录需求来源、八项验收条件与边界；不覆盖全部既有产品行为 |
| 最近工作包的计划与工程验收 | [S9 实施计划](releases/R1/IMPLEMENTATION_PLAN.md#s9-implementation-plan)、[验收](releases/R1/VERIFICATION.md#s9-verification)、[评审](releases/R1/REVIEW.md#s9-review) | 既有工程证据，暂沿用 | 工程提交 `4dfc7e1`；验收指向本机 `.evidence/R1-S9/`，本次归档未重跑该历史应用验收 |
| 当前实际架构 | [TECH_DESIGN](TECH_DESIGN.md) 的「当前架构（2026-10-10）」部分 | 现行部分；同文件混有历史调查 | Java/Python、D1、工具、D2 与工作台入口；下半部为 2026-09-18 旧源码调查，待分离 |
| 操作命令与数据契约 | [实验工具说明](../../tools/experiment/README.md)、[根 README](../../README.md) | 沿用，按实际模块核对 | 当前实现入口为 `audit-mvp/` 与 `tools/experiment/`；历史 `src/` 单独构建 |
| 最新真实 API 实验结论 | [2026-10-10 实验报告](experiments/2026-10-10_API_BATCH_REPORT.md) | 已记录的实验事实 | 报告提交 `9beb7b8`；模型指标、工具失败和 D2 未知分别列出 |
| 实验原始证据与可复核快照 | `.evidence/experiments/2026-10-10-546fe566368e4b0ea7b6aeb58b235939/`；完整原件 `.local/auto-benchmark-runs/546fe566368e4b0ea7b6aeb58b235939/` | 小型快照已跟踪；完整原件仅本机 | 执行清单、计划、验证 JSON 与浏览器记录在 Git；完整 JSONL/CSV 不宣称可跨机器取回 |
| 研究准入、标签与来源依据 | [S3 来源登记](releases/R1/data/SOURCE_REGISTRY.json)、[准入记录](releases/R1/research/S3_D1_KB_READINESS.md)、[S5 数据验收](releases/R1/VERIFICATION.md#s5-verification)、[S8 自动标注验收](releases/R1/VERIFICATION.md#s8-auto-experiment-verification) | 各自记录的资料层级，暂沿用 | 已审案例、待审候选和自动标注知识须保留来源与准入区别；不以目录日期替代审核 |
| 研究目标、设计与创新边界 | [论文总体图](THESIS_ARCHITECTURE.md)、[S6 研究设计](releases/R1/research/S6_RESEARCH_DESIGN.md)、[第二轮查新裁决](../../thesis/D1_D2第二轮查新与立题裁决_20260924.md) | 研究方案及历史裁决 | 总体图核查时间为 2026-10-04，混合目标与当时进度；当前研究验证结果读最新实验报告 |
| 被程序读取的登记与分配资产 | [首批登记](releases/R1/evidence/S3/first-batch-intake.json)、[首批分配](releases/R1/evidence/S3/first-batch-assignment.json)；本机 `.local/r1-s5/formal-v2/ledger.json` | 运行依赖，已随归档同步路径 | `mvp_runtime.py` 与 `formal_targets.py` 显式读取上述登记／分配，后者还读取本机 ledger；运行与测试引用已同步 |
| R1 历史规格、计划与验证 | [R1 归档](releases/R1/README.md)、[Slice Map](releases/R1/IMPLEMENTATION_PLAN.md#slice-map) | 已归档 | 原 S0–S9 合并为文档章节；原始材料按职责收纳，旧切片目录已移除 |
| 历史重构提案与旧源码调查 | [R0 提案](releases/R0-20260918/PROJECT_BRIEF.md)、[审核记录](releases/R0-20260918/REVIEW.md)及 TECH_DESIGN 历史部分 | 历史 | R0 提案为 DRAFT；2026-09-18 调查基于当时代码，不覆盖后续批准或当前架构 |

## 文档组织

R1 历史文档已归档到 [R1 入口](releases/R1/README.md)。规格、计划、验证、设计和评审分别合并为一份文件，S0–S9 通过章节及统一 Slice Map 定位；旧的十个 `R1-Sx` 目录已移除。

日常定位、进度和当前架构继续由 PROJECT、PROGRESS、TECH_DESIGN 承担；当前需求、计划和验收按上方地图读取。独立实验报告继续保存在 `experiments/`。

R1 内的研究资料、操作记录、决定、调查及原始证据按用途收纳。`evidence/S0` 至 `evidence/S5` 只区分证据和夹具来源，不承载独立切片文档套件；首批登记、分配和合成夹具的程序／测试引用已同步。迁移清单记录原路径、来源提交、摘要与归档位置。

归档保留各局部批准、验收条件与研究缺口；不改变历史验证或发布状态。后续同一 Release 内的 Slice 只维护统一计划和进度记录。

## 开发与验证

直接在当前主目录开发，保留未提交改动。根构建 Java 21 / Spring Boot 4.1.1 / Spring AI 2.0.1，默认模块 `audit-mvp`；旧 `src/` 经 `legacy/pom.xml` 单独构建。
每个小版本完成并验证后，在主目录检查改动、提交并同步远程 `origin/main`；同步前处理远程新增提交，避免覆盖他人工作。历史源码与研究原件保留，旧工作树不再使用。

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
```

默认测试完全离线。真实模型、embedding、Milvus 和工具环境验证需显式配置；不自动批量实验、换端点或重建旧知识库。凭证可通过环境变量或被 Git 忽略的 `config/providers.local.properties` 提供，不得提交真实密钥。
