# 当前工程架构

现行工程为 Java 21 / Spring Boot 4.1.1 / Spring AI 2.0.1 与 Python 混合管线。[R1-S9 规格](releases/R1/SPEC.md#r1-workbench)、[实施计划](releases/R1/IMPLEMENTATION_PLAN.md#s9)和[验证记录](releases/R1/VERIFICATION.md#r1-core-evidence)描述当前完整闭环。命令行不启动 Spring 容器，Python 本机 HTTP 服务提供单合约工作台和批量对照。

| 模块 | 当前职责 |
|---|---|
| `audit_target.py` / `program_facts.py` | 校验预置或粘贴目标，提取受限合约/函数语法结构、调用、状态写入与 CEI；保持全文摘要与绝对行号 |
| `BenchmarkRuntime` / Java retrieval | 固定本机 Nomic 768 维活动快照，复用 300 组/600 条自动标注知识；三策略同池，D1 对照上下文最多 4096 UTF-8 字节 |
| `HypothesisCli` / `HypothesisService` | Java 结构化模型网关，最多三项假设，校验名称、操作、位置、引用；缺失 usage 保留 null |
| `ToolCli` / `ToolAnalyzer` | Slither 与可选 Mythril 子进程，保存状态、版本、耗时、告警和目标源码身份 |
| `d2_verify.py` | 绑定假设、事实和工具，逐项输出 actor/resource/pre_risk_guard/entry_coverage/state_version/bypass；漏洞裁决与保护裁决分开 |
| `audit_workbench.py` / `local_ui.py` | 预览摘要、一次性运行票据、单写者锁、六阶段事件、报告与只读历史；`workbench.html` 展示过程，`agent.html` 保留批量比较 |

工作台先绑定源码、范围、池、检索上下文和配置摘要，再执行模型及工具。真实配置与环境凭证捕获后只在内存及权限 600 的临时文件消费，执行结束清理；报告保存摘要，不保存凭证。历史摘要校验失败拒绝回放，服务重启后未封口运行显示 INTERRUPTED，不自动重发模型。新报告 schemaVersion=2，旧历史只读。

受限语法结构不是完整编译器 AST，D2 仅证明可识别的简单路径；继承、别名、分支、跨函数调用或工具缺口保持 UNKNOWN。HYPOTHESES_REFUTED 只表示已提出的假设被反驳，NO_CONFIRMED_FINDINGS 只表示没有确证发现，均不能推断合约安全。科研效果和等 token 公平不由工程验收证明。


## 构建边界与运行入口

已验工程基线为 `4dfc7e1`。当前 R2 工作区正在补工具环境、清理输入与派生重放；其验收状态见[R2 矩阵](releases/R2-20261010/VERIFICATION.md)，目标方案见[R2 设计](releases/R2-20261010/PROPOSED_DESIGN.md)。

默认构建为 `mvn clean verify`；Python 离线验证为 `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`。CLI 为 `java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help`。本机页面由 `tools/experiment/local_ui.py` 提供，启动与配置见[工具说明](../../tools/experiment/README.md)。

旧 `src/` 通过 `legacy/pom.xml` 单独构建；其 2026-09-18 的源码调查归入[R0 调查](releases/R0-20260918/SOURCE_SURVEY.md)。
