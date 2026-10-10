# VeriRAG 毕业论文工程：文档入口

更新：2026-10-10。当前在主目录 `main` 开发，实际提交以 Git 历史为准。

## 当前定位

- 最近工程工作包：S9「单合约深度审计与 D2 闭环」，存量路径标识为 `R1-S9`；其[规格](releases/R1-S9/SPEC.md)、[实施计划](releases/R1-S9/IMPLEMENTATION_PLAN.md)和[验证记录](releases/R1-S9/VERIFICATION.md)继续提供该局部范围的批准与验收依据。
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
| 当前完整有效需求与整体 Release 边界 | 尚无统一入口；局部依据见 [S0 规格](releases/R1-S0/SPEC.md)、[S9 规格](releases/R1-S9/SPEC.md)及相关历史切片 | 待整合 | 存量批准覆盖各局部范围；未建立统一 R1 基线，目录名不能证明发布边界 |
| 最近 S9 工作包的局部需求 | [S9 规格](releases/R1-S9/SPEC.md) | 已冻结的局部范围，暂沿用 | 文件记录需求来源、八项验收条件与边界；不覆盖全部既有产品行为 |
| 最近工作包的计划与工程验收 | [S9 实施计划](releases/R1-S9/IMPLEMENTATION_PLAN.md)、[验收](releases/R1-S9/VERIFICATION.md)、[评审](releases/R1-S9/REVIEW.md) | 既有工程证据，暂沿用 | 工程提交 `4dfc7e1`；验收指向本机 `.evidence/R1-S9/`，本次 init 未重跑应用测试 |
| 当前实际架构 | [TECH_DESIGN](TECH_DESIGN.md) 的「当前架构（2026-10-10）」部分 | 现行部分；同文件混有历史调查 | Java/Python、D1、工具、D2 与工作台入口；下半部为 2026-09-18 旧源码调查，待分离 |
| 操作命令与数据契约 | [实验工具说明](../../tools/experiment/README.md)、[根 README](../../README.md) | 沿用，按实际模块核对 | 当前实现入口为 `audit-mvp/` 与 `tools/experiment/`；历史 `src/` 单独构建 |
| 最新真实 API 实验结论 | [2026-10-10 实验报告](experiments/2026-10-10_API_BATCH_REPORT.md) | 已记录的实验事实 | 报告提交 `9beb7b8`；模型指标、工具失败和 D2 未知分别列出 |
| 实验原始证据与可复核快照 | `.evidence/experiments/2026-10-10-546fe566368e4b0ea7b6aeb58b235939/`；完整原件 `.local/auto-benchmark-runs/546fe566368e4b0ea7b6aeb58b235939/` | 小型快照已跟踪；完整原件仅本机 | 执行清单、计划、验证 JSON 与浏览器记录在 Git；完整 JSONL/CSV 不宣称可跨机器取回 |
| 研究准入、标签与来源依据 | [S3 来源登记](releases/R1-S3/SOURCE_REGISTRY.json)、[准入记录](releases/R1-S3/D1_KB_READINESS.md)、[S5 数据验收](releases/R1-S5/VERIFICATION.md)、[S8 自动标注验收](releases/R1-S8/AUTO_EXPERIMENT_VERIFICATION.md) | 各自记录的资料层级，暂沿用 | 已审案例、待审候选和自动标注知识须保留来源与准入区别；不以目录日期替代审核 |
| 研究目标、设计与创新边界 | [论文总体图](THESIS_ARCHITECTURE.md)、[S6 研究设计](releases/R1-S6/RESEARCH_DESIGN.md)、[第二轮查新裁决](../../thesis/D1_D2第二轮查新与立题裁决_20260924.md) | 研究方案及历史裁决 | 总体图核查时间为 2026-10-04，混合目标与当时进度；当前研究验证结果读最新实验报告 |
| 被程序读取的登记与分配资产 | [首批登记](releases/R1-S3/evidence/first-batch-intake.json)、[首批分配](releases/R1-S3/evidence/first-batch-assignment.json)；本机 `.local/r1-s5/formal-v2/ledger.json` | 运行依赖，保留原路径 | `mvp_runtime.py` 与 `formal_targets.py` 显式读取上述登记／分配，后者还读取本机 ledger；迁移需同步引用 |
| 历史切片规格、计划与验证 | [存量目录](releases/)中的 `R1-S0` 至 `R1-S9` | 历史切片组织，部分仍承担当前职责 | 十个 Slice 独立建目录；尚未物理搬迁。以上单列的局部契约、研究资料和运行资产继续沿用 |
| 历史重构提案与旧源码调查 | [R0 提案](releases/R0-20260918/PROJECT_BRIEF.md)、[审核记录](releases/R0-20260918/REVIEW.md)及 TECH_DESIGN 历史部分 | 历史 | R0 提案为 DRAFT；2026-09-18 调查基于当时代码，不覆盖后续批准或当前架构 |

## 文档整理方向（建议，尚未执行整合）

日常浏览按职责组织。沿用 `docs/vibe/` 和本地图；以下缺失的统一文件是建议目标，本次 init 不创建空文档或把它们标成已生效需求。

| 建议入口 | 只维护的主要内容 |
|---|---|
| `PROJECT.md` | 唯一文档地图与当前项目定位 |
| `SPEC.md` | 经核对的完整有效行为、REQ/AC、批准来源和验收接缝；整合时保留原标识 |
| `TECH_DESIGN.md` | 当前代码与配置能够支持的实际架构 |
| `IMPLEMENTATION_PLAN.md` | 一份实施计划；Slice Map 记录 S0–S9 的范围、依赖、需求映射与证据链接 |
| `PROGRESS.md` | 当前任务、状态、缺口、下一步；每个 Slice 一条状态记录，详细证据通过链接定位 |
| `VERIFICATION.md` | 统一需求—验收—证据矩阵，逐项保留结果、提交与限制 |
| `experiments/` | 按实验保存独立报告，记录输入、配置、结果与证据来源 |

真正具有明确基线和交付边界的 Release 可继续使用 `releases/<release-id>/`；发布后的材料封存。日常入口直接导航到有效事实源，同一 Release 内的 Slice 使用计划表和进度记录，不再新建独立目录或整套文档。复杂调查按具体职责增加单份文件并链接。

整理顺序：

1. 先修正文档地图和当前恢复入口，区分现行事实、研究方案、历史记录与运行依赖；本次 init 完成这一层。
2. 逐项核对既有批准与后续变更，整合完整有效需求、统一 Slice Map 和验证矩阵；未确认或未验证项明确保留缺口。
3. 将 TECH_DESIGN 的当前架构与旧源码调查分离；研究目标和准入资料按职责导航，保持来源可追溯。
4. 核对代码、测试、文档链接和数据保留要求后，再处理历史目录的物理归档与运行资产位置；不直接整包搬走 `evidence/`。

本次审计沿用现有路径，未移动或改写历史切片文件。论文需求与工程实现分别按其事实源核对，工程验收不证明方法创新。

## 开发与验证

直接在当前主目录开发，保留未提交改动。根构建 Java 21 / Spring Boot 4.1.1 / Spring AI 2.0.1，默认模块 `audit-mvp`；旧 `src/` 经 `legacy/pom.xml` 单独构建。
每个小版本完成并验证后，在主目录检查改动、提交并同步远程 `origin/main`；同步前处理远程新增提交，避免覆盖他人工作。历史源码与研究原件保留，旧工作树不再使用。

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
```

默认测试完全离线。真实模型、embedding、Milvus 和工具环境验证需显式配置；不自动批量实验、换端点或重建旧知识库。凭证可通过环境变量或被 Git 忽略的 `config/providers.local.properties` 提供，不得提交真实密钥。
