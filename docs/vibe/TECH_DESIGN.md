# 当前工程架构

现行工程为 Java 21 / Spring Boot 4.1.1 / Spring AI 2.0.1 与 Python 混合管线。[R1-S9 规格](releases/R1/SPEC.md#r1-workbench)、[实施计划](releases/R1/IMPLEMENTATION_PLAN.md#s9)和[验证记录](releases/R1/VERIFICATION.md#r1-core-evidence)描述当前完整闭环。命令行不启动 Spring 容器，Python 本机 HTTP 服务提供单合约工作台和批量对照。

| 模块 | 当前职责 |
|---|---|
| `audit_target.py` / `program_facts.py` | 校验预置或粘贴目标，提取受限合约/函数语法结构、调用、状态写入与 CEI；保持全文摘要与绝对行号 |
| `BenchmarkRuntime` / Java retrieval | 固定本机 Nomic 768 维活动快照，复用 300 组/600 条自动标注知识；三策略同池，D1 对照上下文最多 4096 UTF-8 字节 |
| `HypothesisCli` / `HypothesisService` | Java 结构化模型网关，最多三项假设，校验名称、操作、位置、引用；缺失 usage 保留 null |
| `ToolCli` / `ToolAnalyzer` | Slither 与可选 Mythril 子进程，保存状态、版本、耗时、告警和目标源码身份 |
| `d2_verify.py` | 绑定假设、事实和工具，逐项输出 actor/resource/pre_risk_guard/entry_coverage/state_version/bypass；漏洞裁决与保护裁决分开 |
| `compiler_facts.py` | 显式绑定 standard-json 输入、输出、源码闭包、固定 solc、声明和 ABI 入口；每次实际重新编译完整 JSON 对照，执行前后核对编译器摘要 |
| `compiled_d2.py` | 从类型化 AST 展开内部调用和修饰器，按实际 CFG 支配、声明／key／字段和状态版本计算六义务；局部路径、条件前提与整候选缺口分别保存 |
| `audit_workbench.py` / `local_ui.py` | 预览摘要、一次性运行票据、单写者锁、六阶段事件、报告与只读历史；`workbench.html` 展示过程，`agent.html` 保留批量比较 |

工作台先绑定源码、范围、池、检索上下文和配置摘要，再执行模型及工具。真实配置与环境凭证捕获后只在内存及权限 600 的临时文件消费，执行结束清理；报告保存摘要，不保存凭证。历史摘要校验失败拒绝回放，服务重启后未封口运行显示 INTERRUPTED，不自动重发模型。新报告 schemaVersion=2，旧历史只读。

默认受限语法结构不等于编译器 AST。提供显式 `compilation_manifest` 与项目根目录时，D2 使用绑定编译产物重新核验；不会把调用方填写的事实或证明范围当作证据。内部调用、单占位符修饰器和有限分支使用类型化 CFG；循环、别名、动态调用、未覆盖入口与交易可行性仍保留 UNKNOWN。HYPOTHESES_REFUTED 只表示已提出的假设被反驳，NO_CONFIRMED_FINDINGS 只表示没有确证发现，均不能推断合约安全。科研效果和等 token 公平不由工程验收证明。

本机登记目标可携带 `compilerManifest`；工作台预览保存 `compiledFacts` 与计划中的 `compilerBinding`，执行前再核验，漂移在模型之前终止。批量运行也在模型之前核验编译绑定，D2 公共入口随后自行重载。消费的清理源码必须与编译目标字节一致；不能把原件 AST 直接套在不同摘要的清理输入上。历史报告只读，不因接入重新发送模型请求。S11 的路径 CLI 与本机原件恢复要求见[工具说明](../../tools/experiment/README.md#r2-s11真实编译事实与有限路径)。


## 构建边界与运行入口

S9 已验工程基线为 `4dfc7e1`；R2 的 S10 局部工程验收已通过，当前状态见[R2 矩阵](releases/R2-20261010/VERIFICATION.md)，目标方案见[R2 设计](releases/R2-20261010/PROPOSED_DESIGN.md)。

S10 增加 `evaluation_input.py`：原件和清理文本分别绑定摘要，注释以空白遮蔽并保留行列，字符串原样保存。发现任务不能用评分真值选函数、风险或查询；已有候选核验显式标为 `CLAIM_VALIDATION`。模型与查询消费清理输入，历史模型保持原污染限制。

`tool_environment.py` 按全部有效 pragma 交集选择固定 solc，并绑定工具、依赖、参数和实际二进制摘要。Java 工具网关保存编译探测与运行的版本、耗时、退出码及脱敏诊断；Python 在执行前后重新核验完整环境。`tool_replay.py` 对保存候选执行零模型派生重放，源码/环境/代码身份控制缓存，封口时核对原批次全部文件和当前实现/JAR，不覆盖原输出。53 次真实运行中 51 成功、2 因 Slither 旧 tuple IR 兼容断言失败；这些故障保留未知。S11 已增加显式编译事实和有限路径提供器；真实案例的整候选正反裁决仍待完整入口和可行性证据。

默认构建为 `mvn clean verify`；Python 离线验证为 `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`。CLI 为 `java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help`。本机页面由 `tools/experiment/local_ui.py` 提供，启动与配置见[工具说明](../../tools/experiment/README.md)。

旧 `src/` 通过 `legacy/pom.xml` 单独构建；其 2026-09-18 的源码调查归入[R0 调查](releases/R0-20260918/SOURCE_SURVEY.md)。
