# VeriRAG 毕业论文工程：文档入口

更新：2026-09-24。本轮开发起点：`66161d5b74a6df980425f37c913e63591d246d2a`，分支 `main`；后续实际提交以 Git 历史为准。

## 当前定位

- 当前 Release：`R1-S3` 首个工程切片；范围依用户 2026-09-24 指令冻结。见 [有效 SPEC](releases/R1-S3/SPEC.md)。
- 当前执行状态、验证及下一任务以 [PROGRESS](PROGRESS.md) 为准。
- S0：新 `audit-mvp` 模块，多供应商单次 CLI 和离线测试；[验证记录](releases/R1-S0/VERIFICATION.md)。
- S1a：只读清单、严格类型评估；S1b：审核划分、知识快照和实验恢复。见 [实施计划](releases/R1-S1/IMPLEMENTATION_PLAN.md)、[验证记录](releases/R1-S1/VERIFICATION.md)、[工具说明](../../tools/experiment/README.md)。
- S2：D1 条件对比检索、轻量程序事实与四策略独立比较；工程测试、独立复审及本地 Milvus 冒烟已通过；真实效果实验尚未执行。见 [S2 验证](releases/R1-S2/VERIFICATION.md)。
- S3：已完成[定向查新裁决](../../thesis/D1_D2第二轮查新与立题裁决_20260924.md)；工程部分已实现来源登记、谱系门禁和合成夹具离线先导。真实数据 G1 未通过，D1/D2 效果未验证。见 [S3 验证](releases/R1-S3/VERIFICATION.md)。D1 仅谨慎保留，D2 宽版本撤回创新主张。
- 使用者为论文作者与审核者；正式标签、数据比例及 D1/D2 方法创新结论仍需后续审核与研究证据。

## 事实源职责

| 内容 | 文档 |
|---|---|
| 当前执行位置、恢复入口、已知限制 | [PROGRESS](PROGRESS.md) |
| 当前工程范围 | [R1-S3 SPEC](releases/R1-S3/SPEC.md) |
| 下一研发阶段与研究门禁 | [R1-S3 SPEC](releases/R1-S3/SPEC.md)、[DESIGN](releases/R1-S3/DESIGN.md)、[实施计划](releases/R1-S3/IMPLEMENTATION_PLAN.md) |
| 实施步骤和验收证据 | 当前 Release 的 IMPLEMENTATION_PLAN / VERIFICATION |
| 实际命令与数据契约 | [tools/experiment/README](../../tools/experiment/README.md) 和根 README |
| 旧源码调查与重构动机 | [TECH_DESIGN](TECH_DESIGN.md)，历史观察以当前代码核验 |
| 历史提案与研究路线 | [R0 审核记录](releases/R0-20260918/REVIEW.md)及同目录提案 |

R0 文档保留历史状态，其旧待审核说明不覆盖后续用户批准。论文需求与工程实现分开管理，不把工程修复收益当作方法创新。

## 开发与验证

直接在当前主目录开发，保留未提交改动。根构建 Java 21 / Spring Boot 4.1.1 / Spring AI 2.0.1，默认模块 `audit-mvp`；旧 `src/` 经 `legacy/pom.xml` 单独构建。
每个小版本完成并验证后，在主目录检查改动、提交并同步远程 `origin/main`；同步前处理远程新增提交，避免覆盖他人工作。历史源码与研究原件保留，旧工作树不再使用。

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
```

默认测试完全离线。真实模型、embedding、Milvus 和工具环境验证需显式配置；不自动批量实验、换端点或重建旧知识库。凭证只通过环境变量提供。
