# S0 验证记录

日期：2026-09-19；范围：隔离工作树 `codex/s0-provider` 的新 `audit-mvp` 模块。
本地软件验证通过；真实供应商与工具环境尚未验收。代码未提交、合并或发布。

## 最新证据

- `mvn clean verify`：退出码 0，19 项测试、0 失败、0 错误、0 跳过；可执行 JAR 成功打包。见 [构建日志](evidence/maven-clean-verify.log)与[测试摘要](evidence/test-summary.json)。
- `java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help`：退出码 0，无凭证显示中文帮助，无模型请求。
- 打包检查：应用文件 18 个；未包含旧 application-coding 配置、测试集或知识库路径。
- `git diff --check`：通过；原 `src/` 无修改；原工作区 `.gitignore` 修改保持原样。

## 需求对应

| 需求 | 已验证行为 | 证据及边界 |
| --- | --- | --- |
| S0-01 | Boot 4.1.1、Spring AI 2.0.1 可干净构建 | 新模块构建通过；旧模块未运行 |
| S0-02 | 默认/显式供应商、不同请求路径与 model、Bearer 凭证、配置校验 | GatewayTest 的本地 HTTP 集成 |
| S0-03 | 原文及 usage 返回、缺失 null、真实零保留；错误不转安全 | GatewayTest、AuditServiceTest、CliIntegrationTest |
| S0-04 | 显式参数调用与 JSON 输出、失败非零退出 | AuditCliTest、CliIntegrationTest |
| S0-05 | 持续输出不绕过超时，stdout/stderr 分开限量，非零/启动错误分开，观察后代清理 | ProcessRunnerTest；非沙箱，见限制 |
| S0-05 | Slither/Mythril 严格结果结构、超时和解析错误分开、可执行路径可配置 | ToolAnalyzerTest；实际工具运行尚未验收 |
| S0-06 | 默认测试不调用真实外部服务；401/500 不重试 | 6 个测试类，本地服务器真实经过 Spring AI 与 SDK |
| S0-07 | sourceHash、status、结论、usage、时间输出；错误脱敏 | AuditServiceTest、CliIntegrationTest |

## 失败与修复记录

1. 测试先于初始实现运行，缺类型编译失败后补齐代码。
2. 缺失 usage 被 Spring AI `EmptyUsage` 表示为零：回归失败后修正为 null；真实零值单独验证。
3. 独立审查发现 Slither 0.11.3 默认有发现退出 255、无发现省略 detectors：加入 `--fail-none`，兼容有 results 对象但省略 detectors，仍拒绝缺失 results。
4. 每次模型调用新建 HTTP 客户端无释放：改为显式持有 SDK 客户端，模型复用其同步/异步视图，finally 关闭。
5. 父进程正常退出后遗留已观察子进程：Java 夹具复现失败，增加运行期间追踪及退出后清理，回归通过。

## 审查与限制

独立复审已通过，未发现新的重要阻塞问题；复审只读核对源码和现有测试报告，最终构建由主 Agent 执行。独立审查者已实际核对本机 Slither 0.11.3 源码及 Mythril report.py 成功 JSON 格式，并发现以上工具、资源和进程问题；不是仅根据接口名称推断。

- 清理仅覆盖父进程及运行期间观察到的后代。瞬间 fork 后脱离的进程可能逃过 Java 轮询；`cleanedUp` 不表示操作系统进程组已彻底清空。严格隔离应在后续工具部署使用容器或进程组监管。
- 没有发起真实火山模型请求；账户授权、模型名称、配额、延迟均待联调。示例不能当作可用性证明。
- 工具测试使用 JSON / Java 进程夹具，没有宣称跑通真实 Solidity 编译、Slither/Mythril 全链路。多文件项目及编译依赖尚未管理。
- 旧 M6 代码和旧实验的问题仍然存在，未纳入默认构建。D1/D2 与正式实验尚未实现。
- 输出记录配置的模型标识，不证明服务端实际模型版本；服务端版本追踪将在实验记录切片补充。
- S0 CLI 不编排 RAG/工具。它用于先把错误状态、供应商与执行契约稳定下来。
