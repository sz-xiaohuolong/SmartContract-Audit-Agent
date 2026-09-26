# 第一批真实案例核验记录

更新：2026-09-26。用户已批准访问控制、重入两个方向，并要求本轮先导严格控制在 **10～15 个高质量样本**；随后又确认十项候选的审核意见为通过。该意见记录为**候选选择认可**，仍须逐项补齐原始报告、许可、真实补丁和可引用的独立标签依据，不能将无原件条目直接改为研究真值。当前仅选出 **10 个待审候选，合格准入 0 个**。候选的固定源码 URL、SHA-256、事件和阻塞项见[机器可读名单](evidence/first-batch-intake.json)；[源码复核记录](evidence/first-batch-source-check.json)表明十项固定源码字节摘要一致、三条 SCRUBD 标签行与 V6.0 一致。此项只证明文件和行定位，不证明漏洞标签。未分配知识／开发／验证／锁定测试划分，未建立正式知识快照。

## 本次实际核验

| 方向 | 候选 | 已核实 | 尚不能准入的原因 |
|---|---:|---|---|
| 访问控制 | 5 | ASE 基准中的五个不同项目均有固定源码提交、源码字节摘要及 Code4rena 报告入口。Basin 的 [H-01 原始报告](https://code4rena.com/reports/2024-07-basin)明确指出 `_authorizeUpgrade` 缺少权限限制；PoolTogether 的[维护者修复 PR 7](https://github.com/GenerationSoftware/pt-v5-vault/pull/7)已合并。 | 其余事件的项目许可或真实补丁仍待查；即便有补丁，也须逐行核对是否覆盖目标漏洞，且所有标签需独立复核。 |
| 重入 | 5 | 两个候选沿 Proof-of-Patch 链接到 [Caviar H-01](https://code4rena.com/reports/2023-04-caviar) 和 [AI Arena H-08](https://code4rena.com/reports/2024-02-ai-arena) 原始报告；另三个 SCRUBD V6.0 候选的标签行及固定源码文件已定位并计算摘要。Caviar 的[修复 PR 12](https://github.com/outdoteth/caviar-private-pools/pull/12)已合并，原始审计报告还记录了修复复审确认。 | SCRUBD 未声明数据仓库许可，三个事件均缺可核验的原始漏洞报告与修复；AI Arena 的修复仓库 API 当前返回 404，不能仅凭缓存页面认定补丁可用；Caviar 补丁差异和标签仍待独立复核。 |

七份上游源码文件可见 SPDX 声明，其中六份为 MIT、一份 Gondi 为 AGPL-3.0；另三份 SCRUBD 源码未见文件声明。文件头声明不代替对仓库、原始报告及衍生知识文档使用范围的核验。候选均以项目为暂定组，十项暂未发现相同项目 ID；这**不是**已通过的近克隆或跨划分隔离报告。只有取得各材料后，才能运行现有分组图与近克隆门禁。报告、源码、补丁、摘要和知识文档必须继承最终组 ID。

此次抽查发现两个不能照搬数据表的例子：[ASE 表中 yAxis 第 77 项](https://github.com/HelayLiu/AccessControlVulnerabilities/blob/a96ad42a1a974b635f9ddecc9025c74f8a9a566f/datasets/datasets.xlsx)将 `addStrategy` 指向 `M3`，但[原始报告](https://code4rena.com/reports/2021-09-yaxis)中相关权限问题为 `M-13`；Proof-of-Patch 的 `054`、`098` 虽在元数据中归为重入，原始报告描述的主要问题分别是转账返回值与假余额。这三项未纳入十项名单。

## 下一步及门禁状态

先沿 PoolTogether、Basin、Caviar 的原始报告和维护者提交核对漏洞前后代码，再处理其余候选的许可、事件报告及修复；只保留真实来源、可引用证据与独立审核均过关的项目。若十项中不足十项合格，可在 **15 项总上限内**替换失败候选；绝不把待审样本补成安全负例。SCRUBD 若无法取得逐事件报告和许可，应暂停其正式准入，记录不足而不扩大地毯式检索。

当前 G1 **未通过**：合格真实样本 0／待审 10，真实安全负例 0，正式知识快照与 Milvus 激活均未执行，D1 真实对照和付费模型运行均未执行。离线页面继续仅展示合成演示结果。
