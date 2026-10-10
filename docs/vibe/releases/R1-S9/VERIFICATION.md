# R1-S9 工程验收记录

日期：2026-10-10。需求来源与范围见 [SPEC](SPEC.md)，实施边界见 [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md)。工程验证通过；独立复核与 Git 同步状态以 [PROGRESS](../../PROGRESS.md) 为准。科研效果仍未验证，正式发布授权为 NOT_REQUESTED。

## 自动验证

| 命令 | 最新结果 | 原始证据 |
|---|---|---|
| `mvn clean verify` | Java 75 项通过，失败/错误/跳过均 0 | [.evidence/R1-S9/maven.log](../../../../.evidence/R1-S9/maven.log) |
| `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` | Python 245 项通过，无跳过；包含真实 Java 模型与工具网关 | [python.log](../../../../.evidence/R1-S9/python.log) |
| `node --check tools/experiment/local_ui/workbench.js`、`node --check tools/experiment/local_ui/agent.js` | 均退出 0 | 本轮终端运行记录 |
| `java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help` | 退出 0，显示模型/假设/工具/检索入口 | [cli-help.log](../../../../.evidence/R1-S9/cli-help.log) |

全部模型测试仅访问 loopback HTTP，工具使用子进程夹具；没有外部付费模型调用。知识检索冒烟复用已有本机 Ollama/Milvus，不下载模型、不重建知识。

## 逐项验收

| 条件 | 证据与结果 | 状态 |
|---|---|---|
| S9-01：预置与粘贴、结构和事实 | 输入范围/CRLF/同名/同行歧义回归；Chromium 两条输入路径；展示解析限制、CALL/WRITE/CEI | VERIFIED |
| S9-02：固定 Nomic 与 D1 预算 | 复用快照 `a6d70058bb93a26505def7878553d01e7667248d387f41a101a4ff2f71bd36db`，768 维/600 向量；两个上下文 1627/1559 字节；4096 字节边界回归 | VERIFIED |
| S9-03：Java 结构化假设 | 本机 HTTP 实际返回非空 schemaVersion=2；usage 120/40；精确名称优先、歧义拒绝、原始行号、拒绝项未决聚合回归 | VERIFIED |
| S9-04：工具状态与失败 | Java Slither 子进程夹具实际执行，返回 `local-fixture`、源码摘要与 Contract.sol；超时/异常/缺配置/导入依赖回归，失败保留模型结果 | VERIFIED |
| S9-05：六义务与保守裁决 | D2 39 项正反例、来源绑定、类别/位置、权限覆盖和消费入口路径回归；完整保护反驳对应假设，缺证据保留 UNKNOWN | VERIFIED |
| S9-06：透视、报告、历史 | Chromium 六阶段、D1 对照、源码与六项表；下载真实 JSONL，历史仅 GET；原中断记录未重写、重启不重发 | VERIFIED |
| S9-07：同池批量 | 最新单目标×三策略离线运行完成 3、失败 0、未知 3；同池摘要一致；原模型指标、D2 与流水线失败分别展示 | VERIFIED |
| S9-08：本机与输入门禁 | HTTP Host/Origin/重复字段/大小/票据/并发回归；配置重序列化、冻结消费、空白凭证、清理回归；实际响应禁止框架嵌入；文本注入无图片节点 | VERIFIED |

## Chromium 与本机冒烟

当前入口：`http://127.0.0.1:8771/workbench.html`。最后重启的服务加载当前代码；原有 8769 服务保留。

- 预置 EtherStore：`245bea7409f848288ea820b2f87d894a`，六阶段、COMPLETED/UNRESOLVED；[桌面截图](../../../../.evidence/R1-S9/preset-desktop.png)、[浏览器下载报告](../../../../.evidence/R1-S9/preset-report.jsonl)。
- 粘贴权限合约：`3b3d0bdf0b8647be863e86bc0321ca95`，FUNCTION 范围、COMPLETED/UNRESOLVED；注释含 `<img src=x onerror=alert(1)>`，DOM 图片数为 0；六项未知表实测 6 行。[桌面](../../../../.evidence/R1-S9/pasted-desktop.png)、[390px 移动截图](../../../../.evidence/R1-S9/pasted-mobile.png)；页面宽度与窗口同为 390。
- [浏览器控制台](../../../../.evidence/R1-S9/browser-console.log) 无错误；[网络记录](../../../../.evidence/R1-S9/browser-network.log)、[历史读取网络](../../../../.evidence/R1-S9/history-network.log)和[结构化检查](../../../../.evidence/R1-S9/browser-summary.json)保存原始核对结果。历史读取无 POST。
- 最新本机三策略批量：`a132733766974dcb88ddde439a8d686b`；[结果](../../../../.evidence/R1-S9/batch-smoke.json)保留分母、usage 空值和 D2 未知，不计算模型 F1。

## 结论限制

受限结构语法树不是完整 Solidity 编译器 AST，D2 仅核验能够明确绑定的简单直线路径。权限接管的支持要求存在完整公开消费入口，且只有同权限检查及其后的敏感操作；附加检查、权限覆盖、额外调用或不完整入口保留未知。真实工具仍依赖已有编译器与项目依赖，含 import 的单文件目标跳过工具，不自行下载依赖。

六项保护全部支持只反驳相应漏洞假设；HYPOTHESES_REFUTED 和 NO_CONFIRMED_FINDINGS 均不表示合约安全。自动标注补丁不是逐案审核的安全负例，4096 字节不是等 token 预算。本轮完成工程闭环，不产生 D1 改进或 D2 准确率的科研结论。
