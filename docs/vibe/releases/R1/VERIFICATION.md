# R1 验证矩阵

| 范围 | 验证事实 |
|---|---|
| 工程 | `4dfc7e1` 的 S9 八项局部条件有历史验收证据 |
| 研究 | D1 增益与 D2 准确率 UNVERIFIED；真实批次 D2 全部 UNKNOWN |
| 来源 | 原测试、浏览器和逐次记录见[证据目录](../../../../.evidence/R1/)，本页不将旧测试称为本轮重跑 |

需求：[SPEC](SPEC.md)。原逐次验证全文见[历史验证快照](../../../../.evidence/R1/document-archive/VERIFICATION.md)。

<a id="r1-core-evidence"></a>
## 核心验收

| 原 AC | 历史证据 | 结果与限制 |
|---|---|---|
| S9-01 输入与事实 | 目标及歧义回归、Chromium 预置和粘贴路径 | VERIFIED（局部工程）；受限事实不是完整编译器 AST |
| S9-02 Nomic 与 D1 | 固定 768 维／600 文本快照，预算边界回归 | VERIFIED（工程）；4096 字节不是 token 公平 |
| S9-03 假设 | 实际 loopback Java 网关、名称／操作／引用／拒绝项回归 | VERIFIED（工程）；不证明模型准确率 |
| S9-04 工具 | Slither 子进程夹具、故障／超时／缺配置回归 | VERIFIED（故障处理）；真实项目编译仍有限制 |
| S9-05 D2 | 六项义务、来源绑定、错位置、权限覆盖及消费入口回归 | VERIFIED（受限路径）；研究效果未验证 |
| S9-06 页面与历史 | [浏览器检查](../../../../.evidence/R1/S9/browser-summary.json)、[网络](../../../../.evidence/R1/S9/browser-network.log)、[控制台](../../../../.evidence/R1/S9/browser-console.log) | VERIFIED；390px 无溢出，注入为文本，历史仅 GET |
| S9-07 批量 | [三策略工程冒烟](../../../../.evidence/R1/S9/batch-smoke.json) | 完成 3、失败 0、未知 3；不计算模型效果 |
| S9-08 本机与配置 | Host/Origin、票据、大小、并发及 Java 配置实际消费 | VERIFIED；[配置根因调查](../../bugs/BUG-001_CONFIGURATION_SNAPSHOT.md)已闭环 |

2026-10-10 的历史完整检查为 Java 75 项、Python 245 项通过且无跳过；[Maven 日志](../../../../.evidence/R1/S9/maven.log)、[Python 日志](../../../../.evidence/R1/S9/python.log)及[CLI 帮助](../../../../.evidence/R1/S9/cli-help.log)保留。

<a id="r1-baseline-evidence"></a>
## 基础模块证据

S0 模型／解析／进程契约、S1 清单／快照／恢复，以及 S2 检索／绑定／预算均有对应离线记录。原命令、次数、环境和限制分别保存在[基础日志](../../../../.evidence/R1/S0/)、[数据基础日志](../../../../.evidence/R1/S1/)、[检索日志](../../../../.evidence/R1/S2/)与历史验证快照中；不能用当时通过替代当前回归。

<a id="r1-data-evidence"></a>
## 数据与准入

正式早期知识为三组真实补丁对、六条向量，独立验证三组；后续默认 Nomic 知识是 300 组自动标注对、600 条文本。二者来源层级不同，不能把自动标签改写为逐案安全证明。[准入记录](attachments/D1_KB_READINESS.md)、[原件核对](../../../../.evidence/R1/S5/source-review.json)、[来源登记](../../../../data/audit/r1/source-registry.json)及[正式源码镜像](../../../../data/audit/r1/formal-expansion/originals/)保留。

公开候选 442 组／742 条向量曾隔离入库；向量数量不能代替独立事件、真实配对或可靠标签。跨划分、项目／补丁／克隆与人工适用性审核仍按具体资料留缺口。

<a id="r1-model-comparison"></a>
## 真实模型与 D2 结果

最新[真实 API 报告](experiments/2026-10-10_API_BATCH_REPORT.md)对应 `546fe566368e4b0ea7b6aeb58b235939`，53 目标 × 三策略、159 次请求，模型有效 159、重试 0。

| 策略 | 模型标签 F1 |
|---|---|
| DENSE | 0.9462 |
| FIELD_FILTER | 0.9362 |
| D1 | 0.9348 |

未观察到 D1 改进。Slither 12 项成功、147 项进程错误；D2 159 项 UNKNOWN，最终 148 项 UNRESOLVED、11 项 NO_CONFIRMED_FINDINGS。模型标签指标不等于工具或 D2 核验结果；该批次不能建立方法有效性。

小型[执行快照](../../../../.evidence/R1/experiments/2026-10-10-546fe566368e4b0ea7b6aeb58b235939/)随 Git 保留，完整原件仍在本机 `.local/auto-benchmark-runs/`。真实编译、真值隔离、事实覆盖和先导由 R2 继续核验。
