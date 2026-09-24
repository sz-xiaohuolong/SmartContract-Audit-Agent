# VeriRAG-Agent 毕业论文重构

当前工程已完成单次审计入口、离线数据与实验基础、受限程序事实和 D1 条件对比检索。[S3 首个工程切片](docs/vibe/releases/R1-S3/VERIFICATION.md)也已实现来源登记、隔离门禁及合成夹具对照。D1 的真实研究效果尚未验证；D2 仅建立了固定候选与简单防护检查的数据契约。2026-09-24 的[第二轮查新](thesis/D1_D2第二轮查新与立题裁决_20260924.md)撤回 D2 宽创新主张。

新模块使用 Java 21。根 `pom.xml` 通过 Spring Boot 4.1.1 的父工程管理构建，并通过 Spring AI 2.0.1 BOM 管理依赖版本；`audit-mvp/pom.xml` 直接声明 `spring-ai-openai`。`SpringAiGateway` 在显式单次审计时调用 Spring AI 模型接口。命令行不启动 Spring 应用容器；D1 检索与 S3 离线实验使用普通 Java/Python 代码，不经过 Spring AI 的 RAG 组件。

## 构建与运行

在当前工作树根目录执行：

```bash
mvn clean verify
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
```

默认测试仅使用本机 HTTP 服务和 Java 子进程夹具，不要求 Milvus、Slither、Mythril 或模型凭证。首次构建仍需下载 Maven 依赖。

真实单合约调用前，复制 `config/providers.example.properties` 到自己的配置文件，核对账户模型标识和端点，并在运行环境设置 `ARK_API_KEY`。配置文件只引用环境变量名称。示例使用 Agent Plan 的 `/api/plan/v3`；不能混用 Coding Plan 或按量计费端点。

```bash
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar \
  --source /绝对路径/Contract.sol \
  --config config/providers.example.properties \
  --provider ark
```

上述命令会向所选供应商发送源码并调用一次模型。`deepseek-v4.1-flash` 是用户目标配置，尚未通过实际账户验证。`--provider custom` 可切换到另一个已配置的 OpenAI Chat Completions 兼容接口；不支持未经适配的供应商原生协议。SDK 重试关闭，超时及输出 token 上限可配置。

无参数只显示帮助。源码必须为 UTF-8，最大 1 MiB。退出码：`0` 审计完成、`1` 模型调用或输出失败、`2` 输入/配置无效。标准输出为单条 JSON，可重定向保存。

## 当前实现

| 模块 | 作用 |
| --- | --- |
| ProviderRegistry / SpringAiGateway | 命名供应商、端点与模型切换、环境凭证、usage 和耗时 |
| AuditService / AuditCli | 源码摘要、严格 JSON 校验、单次审计命令行 |
| ProcessRunner | 独立排空输出、有限留存、进程超时与清理状态 |
| ToolAnalyzer | Slither / Mythril 可执行路径适配与结构化结果解析 |

`FAILED / UNRESOLVED` 与无发现分离；`NO_CONFIRMED_FINDINGS` 仅表示模型未报告漏洞；`VULNERABILITY_REPORTED` 尚未经过 D2 验证。缺失 usage 保留 `null`，真实零值仍保留为零。

工具适配器目前为 Java 接口，可使用 `ToolAnalyzer.analyze(engine, executable, source, timeout)` 单独调用。S0 的 CLI 尚不编排工具或 RAG，也不安装编译器与解析项目依赖。真实 Slither / Mythril 兼容性需后续环境验收；工具结果不能当成安全证明。`cleanedUp` 仅覆盖父进程与已观察到的后代；瞬间脱离父进程的后台任务无法由纯 Java 可靠追踪，此执行器不提供沙箱或进程组级隔离。

## S1a 离线实验基础

新增 [离线实验工具](tools/experiment/README.md)：生成源码哈希与完全重复组，并从保存的标签/预测重算多标签类型指标。使用 Python 标准库；测试命令为 `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`。

已生成旧数据集待审核清单：400 份源码、7 组字节重复（14 个文件）。项目谱系、近似克隆、标签与划分仍待复核。知识快照、断点恢复和结果规范化已在 S1b 实现，见[当前进度](docs/vibe/PROGRESS.md)；其工程实现不能替代科研标签审核。

## 旧系统与研究文档

原 `src/` 保留为历史系统，未纳入新模块默认构建。原依赖迁移到 `legacy/pom.xml`，需要旧构建时显式运行 `mvn -f legacy/pom.xml test`，这可能触发真实外部服务，不能当成离线测试。旧实验路径仍需复核，已有实验缺陷并未因为保留代码而解决。

旧示例曾把供应商密钥写入源码，现改为从 `DASHSCOPE_API_KEY` 环境变量读取；旧值已进入历史提交，需在供应商侧撤销或轮换。不要把真实凭证写入配置文件或提交记录。

- [当前进度](docs/vibe/PROGRESS.md)
- [S0 有效需求](docs/vibe/releases/R1-S0/SPEC.md)
- [S0 实施计划](docs/vibe/releases/R1-S0/IMPLEMENTATION_PLAN.md)
- [S0 验证记录](docs/vibe/releases/R1-S0/VERIFICATION.md)
- [S2 验证记录](docs/vibe/releases/R1-S2/VERIFICATION.md)
- [S3 需求与实施计划](docs/vibe/releases/R1-S3/SPEC.md)
- [历史 README](legacy/README-historical.md)：仅为旧状态存档。

依赖依据：[Spring AI 官方入门](https://docs.spring.io/spring-ai/reference/getting-started.html)、[OpenAI 适配文档](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html)。Agent Plan 端点依据：[火山引擎 OpenViking 配置示例](https://github.com/volcengine/OpenViking/blob/main/examples/ov.conf.example)。
