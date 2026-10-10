# VeriRAG-Agent 毕业论文重构

当前 [R1-S9](docs/vibe/releases/R1/SPEC.md#s9-spec) 打通预置或粘贴 Solidity、受限语法与事实、Nomic D1 配对检索、Java 结构化假设、Slither、D2 六项义务和持久化报告。单合约工作台可查看全部阶段、源码位置与保护证据，批量入口继续比较同池三策略。工程验收见[验证记录](docs/vibe/releases/R1/VERIFICATION.md#s9-verification)；D1 的科研改进与 D2 的核验准确率尚未建立，2026-09-24 的[第二轮查新](thesis/D1_D2第二轮查新与立题裁决_20260924.md)撤回 D2 宽创新主张。

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

## S1a 离线实验基础

新增 [离线实验工具](tools/experiment/README.md)：生成源码哈希与完全重复组，并从保存的标签/预测重算多标签类型指标。使用 Python 标准库；测试命令为 `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`。

已生成旧数据集待审核清单：400 份源码、7 组字节重复（14 个文件）。项目谱系、近似克隆、标签与划分仍待复核。知识快照、断点恢复和结果规范化已在 S1b 实现，见[当前进度](docs/vibe/PROGRESS.md)；其工程实现不能替代科研标签审核。

## 旧系统与研究文档

原 `src/` 保留为历史系统，未纳入新模块默认构建。原依赖迁移到 `legacy/pom.xml`，需要旧构建时显式运行 `mvn -f legacy/pom.xml test`，这可能触发真实外部服务，不能当成离线测试。旧实验路径仍需复核，已有实验缺陷并未因为保留代码而解决。

旧示例曾把供应商密钥写入源码，现改为从 `DASHSCOPE_API_KEY` 环境变量读取；旧值已进入历史提交，需在供应商侧撤销或轮换。不要把真实凭证写入受 Git 跟踪的配置或提交记录。

- [当前进度](docs/vibe/PROGRESS.md)
- [S0 有效需求](docs/vibe/releases/R1/SPEC.md#s0-spec)
- [S0 实施计划](docs/vibe/releases/R1/IMPLEMENTATION_PLAN.md#s0-implementation-plan)
- [S0 验证记录](docs/vibe/releases/R1/VERIFICATION.md#s0-verification)
- [S2 验证记录](docs/vibe/releases/R1/VERIFICATION.md#s2-verification)
- [S3 需求与实施计划](docs/vibe/releases/R1/SPEC.md#s3-spec)
- [历史 README](legacy/README-historical.md)：仅为旧状态存档。

依赖依据：[Spring AI 官方入门](https://docs.spring.io/spring-ai/reference/getting-started.html)、[OpenAI 适配文档](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html)。Agent Plan 端点依据：[火山引擎 OpenViking 配置示例](https://github.com/volcengine/OpenViking/blob/main/examples/ov.conf.example)。
