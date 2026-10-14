# 有限核验引擎的第一次工程闭环

这份 2026-10-11 报告说明编译器与 Slither 怎样共同支撑 D2。原 172 条保存候选重放后为 6 支持、0 反驳、166 未知，未知率从 100% 降至 96.5116%；这次覆盖增加仍不足以证明研究目标完成。

先读 [概念与案例](attachments/CONCEPTS_AND_WALKTHROUGH.md) 理解术语，再对照 [当前实验看板](attachments/EXPERIMENT_DASHBOARD.md)。

<details>
<summary>展开原技术分析、表格与可复核记录</summary>

# S11／S12 防御静态核验工程报告

日期：2026-10-11。范围为有限 D2 保护证明、编译／工具双收据、保存候选派生重放与工作台展示。工程验收通过；历史候选 UNKNOWN 的下降幅度有限，尚未证明统计显著性，整个 R2 的研究有效性仍为 UNVERIFIED。

## 实现与裁决边界

`compiler_facts.py`、`compilation_runtime.py` 用固定本机 solc 生成并重新核验 standard-json 收据，保留完整依赖、设置、声明和字节跨度。`bound_slither.py` 使用官方 Slither 适配器独立编译，核对源码闭包、AST、ABI、字节码、告警、工具实现和环境身份；只有实际相符的工具可参与佐证。

六义务按实际程序事实计算：主体与资源绑定、风险前条件、公开入口覆盖、状态版本和保护旁路。权限证明追踪委派状态与相关写入口，包含修饰器实参、初始化、fallback／receive；重入证明只覆盖有限 CEI 和统一互斥锁模式，检查相关余额读取、付款与更新入口。名称相似、空告警和局部保护不足以证明完整覆盖。

| 对象 | SUPPORTED | REFUTED | UNKNOWN |
|---|---|---|---|
| 漏洞假设 `verdict` | 合法资金建态、正常退出的有限 CEI 顺序反例与同源同类真实告警共同成立 | 六义务、相关入口和权限／状态闭包完整，且双收据 MATCH | 信息、范围、工具、可满足性或身份不足 |
| 保护义务 `obligations[].status` | 该项保护事实成立 | 该项保护被防御断言反证 | 该项证据不足 |

两种三态语义相反，页面分别展示。`REFUTED` 只反驳给定假设，不声称整合约安全。低级调用后的状态顺序反例不声称攻击可利用性；没有攻击程序、交易载荷或外部目标。

`audit_runner.py` 提供保存假设的零模型核验入口。工作台、批量执行器和派生重放复用编译、工具与 D2 接缝。固定编译器目录启用自动 AST 流程；含导入须使用完整登记模板；旧单 solc 网关保持兼容入口。编译或工具失败独立计为失败，裁决保留未知，usage 缺失保留 null。

## 验收证据

本机原始证据目录：`.evidence/R2-20261010/S11-S12-final/`，默认不入 Git。固定源码、编译器和案例原件仍需按登记在本机恢复；此报告不宣称原始收据可跨机器直接取得。

| 验收 | 结果与原始证据 |
|---|---|
| 全量 Python 3.12 | 509 项通过，无失败或跳过；`python-final-after-modifier.log` |
| Java 21 根构建 | `mvn clean verify`，88 项通过，无失败或跳过；`maven-clean-verify.log` |
| Java CLI | JAR `--help` 退出 0；`cli-help.log` |
| 独立评审 | `REVIEW.md` 及增量复审无未修阻断；可信 CSO 未进入扫描，源码规模超限，不能表述为 CSO 扫描通过 |
| 旧 AST 兼容 | 官方旧 compact AST 的无括号修饰器 `arguments=null` 按无实参处理；红绿回归与三份实际旧 AST 复核通过；`old-modifier-*.log`、`replay-errors-fixed.log` |
| 真实正裁决 | SimpleDAO 与 Reentrance 保存 CALL 候选在三策略中各 3 条获 SUPPORTED；真实编译、Slither、资金建态、正常退出及同类告警相符 |
| 防御机制对照 | 基于公开 SimpleDAO 的本机防御夹具：仅前移部分扣减仍 UNKNOWN；完整余额检查与前置扣减得到 REFUTED、MATCH 和六义务 SUPPORTED；`simpledao-cei-*-result.json`。这是生成的机制夹具，不是维护者修复或新增学术样本，不计入历史重放分母 |
| Chromium 工作台 | SimpleDAO 预置演练、预览后离线开始审计、导出、历史、派生逐样本与候选切换通过；所选 UNKNOWN 候选不会借用聚合 SUPPORTED；`browser-*.log` |
| 布局与控制台 | 1440／834／390px 无横向溢出，六义务实际呈现 3 绿／3 红；控制台错误和警告均 0；`workbench-*.png`、`browser-console-final.log` |
| 隔离与请求 | 原实验、数据划分与 Nomic 快照未改；新增模型请求 0。测试仅使用本机 HTTP、子进程夹具和离线数据 |

本轮第一次全量失败及中间重放保留；不覆盖失败日志，不修改旧测试断言掩盖问题。Java 的既有无关工作区修改保留，未纳入本轮提交。

## 历史派生重放

原批次：`546fe566368e4b0ea7b6aeb58b235939`。最终派生运行：`cd592f4847454f939dfc75e87fecc9fd`，目录 `.local/r2/tool-replays/cd592f4847454f939dfc75e87fecc9fd/`。封口 `manifest.json` 为 COMPLETED，原批次全部文件与四项派生产物的 SHA-256 核对通过。原 `samples.jsonl` 摘要为 `f85d9614575897a0a3129ced888edebdcd1bec844e9985629081cc9d665c007a`。

| 口径 | 原始／派生结果 |
|---|---|
| 规模 | 53 个目标、159 个单元、172 条保存假设；53 次工具执行 |
| 保存假设 UNKNOWN | 172／172（100%）→166／172（96.5116%）；下降 3.4884 个百分点 |
| 逐假设迁移 | UNKNOWN→SUPPORTED：6；UNKNOWN→UNKNOWN：166；REFUTED：0 |
| 单元 D2 | SUPPORTED：6；UNKNOWN：153；单元与假设分母分别保留 |
| 实际 assessment | SUPPORTED：6；UNKNOWN：144；另外 22 条缺编译 assessment 仍纳入 172 条分母，计为 UNKNOWN |
| 工具单元状态 | OK：150；PROCESS_ERROR：9；对应 50 个唯一目标成功、3 个失败 |
| 流水线状态 | COMPLETED：113；FAILED：46；故障不计为安全 |
| D2 执行异常 | 最终 0；旧 AST 空实参问题已修复 |
| 新模型请求 | 0；原模型假设与 usage 原样保留 |

剩余 166 条 UNKNOWN 的汇总原因：风险操作／字节跨度／调用上下文不能唯一绑定 112 条；机制、合约或源码身份不匹配 22 条；编译绑定失败 22 条；局部路径、可满足性、入口或工具证据不足 10 条。细节、证明缺口、迁移与引用均保存在 `assessments.jsonl`；不可通过改写原假设的 WRITE 为 CALL、移动风险行或删除失败候选扩大收益。

本轮证据证明已打通此前恒 UNKNOWN 的工程路径，但**没有达到“UNKNOWN 显著下降”的研究目标**。该批次包含历史答案污染、模型错绑与有限证明范围限制；6 条迁移来自 2 个目标，三策略重复结果不能视为 6 个独立学术样本。完整来源复核、维护者真实修复正反对照、四基线和新的模型发现实验仍按统一计划追踪。

## 复核与展示入口

```bash
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
mvn clean verify
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
PYTHONPATH=tools/experiment python3 tools/experiment/local_ui.py --port 8765
```

重放须先构建 Java，并使用新的 32 位十六进制输出目录；执行过程中不能改变生产源码或 JAR。完整命令与本机环境要求见[工具说明](../../../../tools/experiment/README.md#r2-s11真实编译事实与有限路径)。在工作台运行历史中可只读打开最终派生报告、逐假设对照和 JSONL，不触发模型请求。提交同步身份记录于本机证据 `git-sync.json`，精确提交相关工具、测试和当前 Release 文档，保留启动时的无关修改。

</details>

返回 [唯一文档地图](../../PROJECT.md)。
