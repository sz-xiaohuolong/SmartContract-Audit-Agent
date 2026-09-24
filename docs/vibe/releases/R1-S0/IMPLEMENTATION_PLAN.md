# S0 实施计划

依据：[SPEC](SPEC.md)。执行方式：主 Agent 在隔离 worktree 按任务执行，最终独立审查；延续用户已批准阶段方案，不重复请求开始许可。
技术：Java 21、Spring Boot 4.1.1、Spring AI 2.0.1；正式版本由 Maven Central 与官方文档核验。

## 任务 1：依赖隔离与测试入口

文件：根 pom.xml、legacy/pom.xml、audit-mvp/pom.xml。
保留旧 src；旧 pom 在 legacy 指向旧 src，新模块作为根默认构建。理由：Spring AI 2 从旧 M6 接口跨代升级，先导工程不能被未迁移演示类和付费测试拖入启动。
验证：`mvn -pl audit-mvp test` 默认只运行离线测试。

## 任务 2：Provider 配置与实际网关

文件：ProviderConfig、ProviderRegistry、SpringAiGateway 及 GatewayTest。
测试先行：本地 HttpServer 返回标准 chat completion；断言 /api/plan/v3/chat/completions、Bearer 请求、model 字段与 usage；第二 provider 的请求落到独立路径；无效配置和 401 不重试。
契约：GatewayReply complete(String provider, String system, String user)。
每个请求 maxRetries=0，时间和输出 Token 有限；使用 API 2.0 正式 builder。

## 任务 3：审计解析与 CLI

文件：AuditService、AuditCli；测试空文本、缺字段、多对象、false 与异常区分、源码哈希。
先写断言 `assertEquals(FAILED, service.audit(...).status())` 对无效 JSON，再实现严格解析。
入口：显式参数 --source、--config、可选 --provider；默认只显示帮助，无联网。

## 任务 4：受控进程和工具适配

文件：ProcessRunner、ToolAnalyzer、ProcessRunnerTest、ToolAnalyzerTest。
先测试挂起和持续输出不会绕过超时，测试失败 JSON 不等于空报警；再实现从启动计时、后台排空、输出上限和清理。

## 任务 5：集成与交付

运行 `mvn clean verify`；检查打包资源无旧本地配置/密钥；CLI 帮助离线；记录所有真实与未验证行为；更新 README、AGENTS、PROGRESS。

## 审查重点

URL 带自定义前缀不得被补成 /v1；密钥不能进入错误日志；usage 缺失不能记零；进程大输出不得阻塞；非法 JSON 不得形成安全结果。上述各项均加入对应测试。
