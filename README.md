# VeriRAG-Agent 毕业论文重构

当前开发版本为 [R2-20261010](docs/vibe/releases/R2-20261010/SPEC.md)，支持预置或粘贴 Solidity、查看源码与候选、重放核验和导出报告。D1 提供漏洞与修复对照，D2 逐项核验漏洞候选并保存依据；批量入口比较同池三策略。工程整体部分完成，D1 的研究增益与 D2 的核验准确率尚未验证，当前结果见[项目总览](docs/vibe/PROJECT.md)、[当前进度](docs/vibe/PROGRESS.md)和 [R2 验收](docs/vibe/releases/R2-20261010/VERIFICATION.md)。2026-09-24 的[第二轮查新](thesis/D1_D2第二轮查新与立题裁决_20260924.md)撤回 D2 宽创新主张。

新模块使用 Java 21。根 `pom.xml` 通过 Spring Boot 4.1.1 的父工程管理构建，并通过 Spring AI 2.0.1 BOM 管理依赖版本；`audit-mvp/pom.xml` 直接声明 `spring-ai-openai`。`SpringAiGateway` 在显式单次审计时调用 Spring AI 模型接口。命令行不启动 Spring 应用容器；D1 检索与 S3 离线实验使用普通 Java/Python 代码，不经过 Spring AI 的 RAG 组件。

## 构建与运行

在当前工作树根目录执行：

```bash
mvn clean verify
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
```

默认测试仅使用本机 HTTP 服务和 Java 子进程夹具，不要求 Milvus、Slither、Mythril 或模型凭证。首次构建仍需下载 Maven 依赖。

已有本机 Nomic、Milvus 与固定知识快照时，启动交互工作台：

```bash
.local/d1-embed-venv/bin/python tools/experiment/local_ui.py --port 8771
```

打开 `http://127.0.0.1:8771/workbench.html`，选择预置样本或粘贴源码，先预览再运行。默认离线流程只查询本机知识并演练后续阶段；真实模式需要显式选择现有供应商与工具配置。批量对照在 `/agent.html`，不会因查看历史或下载 JSONL 再次发起请求。粘贴输入不写入知识库或研究真值。

真实单合约调用前，在本机的 `config/providers.local.properties` 中找到 `providers.ark.api-key=`，把**火山方舟 Agent Plan** 的 Key 填在等号后面，不加引号。该文件已加入 `.gitignore`，不会随代码提交；请核对账户可用的模型标识和端点。示例使用 Agent Plan 的 `/api/plan/v3`；不能混用 Coding Plan 或按量计费端点。若仍想从环境变量读取，可使用 `config/providers.example.properties` 中的 `ARK_API_KEY` 配置。

```bash
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar \
  --source /绝对路径/Contract.sol \
  --config config/providers.local.properties \
  --provider ark
```

上述命令会向所选供应商发送源码并调用一次模型。`deepseek-v4.1-flash` 是用户目标配置，尚未通过实际账户验证。`--provider custom` 可切换到另一个已配置的 OpenAI Chat Completions 兼容接口；不支持未经适配的供应商原生协议。SDK 重试关闭，超时及输出 token 上限可配置。程序优先读取本地配置中的 `providers.<名称>.api-key`；该值为空时才读取 `providers.<名称>.api-key-env` 指向的环境变量。错误信息和结果不会打印 Key。

无参数只显示帮助。源码必须为 UTF-8，最大 1 MiB。退出码：`0` 审计完成、`1` 模型调用或输出失败、`2` 输入/配置无效。标准输出为单条 JSON，可重定向保存。

## 当前实现

| 模块 | 作用 |
| --- | --- |
| ProviderRegistry / SpringAiGateway | 命名供应商、端点与模型切换、环境凭证、usage 和耗时 |
| AuditService / AuditCli | 源码摘要、严格 JSON 校验、单次审计命令行 |
| HypothesisService / HypothesisCli | 最多三条结构化假设、合约与函数名称、绝对位置和证据 ID 绑定 |
| ProcessRunner | 独立排空输出、有限留存、进程超时与清理状态 |
| ToolAnalyzer / ToolCli | Slither / Mythril 进程适配、告警位置、源码摘要与版本 |
| audit_workbench / d2_verify | 六阶段持久化、六项保护义务三态核验、保守汇总与只读回放 |

`FAILED / UNRESOLVED` 与无发现分离；`NO_CONFIRMED_FINDINGS` 仅表示模型未报告漏洞；`VULNERABILITY_REPORTED` 尚未经过 D2 验证。缺失 usage 保留 `null`，真实零值仍保留为零。

工具通过 Java `--tools` 命令接入 Python 流水线，也可使用 `ToolAnalyzer.analyze(engine, executable, source, timeout)` 单独调用。真实工具需要本机已有编译器和完整依赖；单文件含 import 时标记 SKIPPED，缺配置、异常和空告警都不能证明安全。`cleanedUp` 仅覆盖父进程与已观察到的后代；瞬间脱离父进程的后台任务无法由纯 Java 可靠追踪，此执行器不提供沙箱或进程组级隔离。

## 离线实验与数据基础

新增 [离线实验工具](tools/experiment/README.md)：生成源码哈希与完全重复组，并从保存的标签/预测重算多标签类型指标。使用 Python 标准库；测试命令为 `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`。

历史旧数据集清单记录了 400 份源码、7 组字节重复（14 个文件），属于当时的输入快照。当前使用保留的原始数据集与独立对照，入口见下方数据说明；项目谱系、近似克隆、标签与划分仍待复核。知识快照、断点恢复和结果规范化已在 S1b 实现，见[当前进度](docs/vibe/PROGRESS.md)；其工程实现不能替代科研标签审核。

## 数据与研究文档

数据入口见 [data/](data/README.md)：公开源码与标注直接使用根目录保留的 `smartbugs-curated/`、`SolidiFI-benchmark/`；`data/` 保存版本登记、额外对照、固定实验输入、示例与参考资料。重复加工文档和源码副本已移除，历史标签及科研准入状态保持原记录。

旧 Java 应用、旧测试、配置、PDF 字体和 `legacy` 构建入口已退役；历史代码可从迁移前提交 `4ba5750` 恢复。当前默认构建继续使用 `audit-mvp`。

旧示例曾把供应商密钥写入源码，现改为从 `DASHSCOPE_API_KEY` 环境变量读取；旧值已进入历史提交，需在供应商侧撤销或轮换。不要把真实凭证写入受 Git 跟踪的配置或提交记录。

- [项目入口与唯一文档地图](docs/vibe/PROJECT.md)、[当前进度](docs/vibe/PROGRESS.md)、[当前工程架构](docs/vibe/TECH_DESIGN.md)。
- phase 4：访问控制事实引导与双向证据核验（原称 R4）：[ACTaint 分析](docs/vibe/releases/phase4-20261019/ACTAINT_ANALYSIS.md)、[优化计划](docs/vibe/releases/phase4-20261019/IMPLEMENTATION_PLAN.md)。当前仅完成规划，阶段名称与历史路径对应关系见唯一文档地图。
- phase 2：差分检索与路径证据核验（原 R2）：[需求基线](docs/vibe/releases/R2-20261010/PROJECT_BRIEF.md)、[完整规格](docs/vibe/releases/R2-20261010/SPEC.md)、[方案](docs/vibe/releases/R2-20261010/PROPOSED_DESIGN.md)、[计划](docs/vibe/releases/R2-20261010/IMPLEMENTATION_PLAN.md)、[验收](docs/vibe/releases/R2-20261010/VERIFICATION.md)。
- phase 1：审计原型与实验基线（原 R1）：[需求基线](docs/vibe/releases/R1/PROJECT_BRIEF.md)、[完整规格](docs/vibe/releases/R1/SPEC.md)、[计划](docs/vibe/releases/R1/IMPLEMENTATION_PLAN.md)、[验收](docs/vibe/releases/R1/VERIFICATION.md)。
- [旧源码调查](docs/vibe/releases/R0-20260918/SOURCE_SURVEY.md)：仅为历史调查记录。

依赖依据：[Spring AI 官方入门](https://docs.spring.io/spring-ai/reference/getting-started.html)、[OpenAI 适配文档](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html)。Agent Plan 端点依据：[火山引擎 OpenViking 配置示例](https://github.com/volcengine/OpenViking/blob/main/examples/ov.conf.example)。
