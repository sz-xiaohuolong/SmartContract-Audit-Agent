# R1 实施计划

需求依据：[PROJECT_BRIEF](PROJECT_BRIEF.md)与[SPEC](SPEC.md)。本表归纳原执行记录，详细逐次计划保存在[历史快照](../../../../.evidence/R1/document-archive/IMPLEMENTATION_PLAN.md)。

## Slice Map

| 切片 | 范围 | 依赖 | 原结果及验证入口 |
|---|---|---|---|
| <a id="s0"></a>S0 | 默认 Java 模块、模型网关、严格结果与受控工具进程 | 无 | 已实施；[基础证据](VERIFICATION.md#r1-baseline-evidence) |
| <a id="s1"></a>S1 | 只读清单、知识快照、实验持久化和恢复 | S0 | 离线工程已验；[数据证据](VERIFICATION.md#r1-data-evidence) |
| <a id="s2"></a>S2 | 程序事实、条件检索与四策略接口 | S0、S1 | 工程已验，研究未验证；[基础证据](VERIFICATION.md#r1-baseline-evidence) |
| <a id="s3"></a>S3 | 来源、谱系、标签、预算与合成先导 | S1、S2 | 工程已实施，真实准入缺口保留；[数据证据](VERIFICATION.md#r1-data-evidence) |
| <a id="s4"></a>S4 | 检索、模型、工具、D2 与单样本报告 | S0–S3 | 工程已验；[核心证据](VERIFICATION.md#r1-core-evidence) |
| <a id="s5"></a>S5 | 三组正式知识、三组独立验证及页面 | S3、S4 | 数据与页面已实施；[数据证据](VERIFICATION.md#r1-data-evidence) |
| <a id="s6"></a>S6 | 同池三策略批量、逐项 JSONL 与保守指标 | S4、S5 | 工程已实施；[模型对照](VERIFICATION.md#r1-model-comparison) |
| <a id="s7"></a>S7 | 公开语料待审采集与隔离入库 | S3 | 候选已入库，未据此转正；[数据证据](VERIFICATION.md#r1-data-evidence) |
| <a id="s8"></a>S8 | 自动标注探索、Nomic 快照及原文派生重放 | S2、S6、S7 | 工程与探索运行已记录，D1 增益未证实；[模型对照](VERIFICATION.md#r1-model-comparison) |
| <a id="s9"></a>S9 | 单合约透视工作台与 D2 六义务闭环 | S0–S8 | 八项局部工程条件已验；[核心证据](VERIFICATION.md#r1-core-evidence) |

## 验证与交付

任务沿依赖推进，共享配置、报告及事实契约串行修改；模型与工具通过本地 HTTP／子进程夹具验证。适用页面使用真实 Chromium 检查交互、下载、控制台和注入边界。

工程完成提交为 `4dfc7e1`，实验报告提交为 `9beb7b8`。S9 原计划与评审中的开发、验证和同步授权继续保留；局部完成不覆盖研究门禁或正式发布授权。R1 没有新增执行任务，当前工作看[R2 计划](../R2-20261010/IMPLEMENTATION_PLAN.md)。
