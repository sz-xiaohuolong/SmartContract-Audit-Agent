# R1 归档入口

归档日期：2026-10-10。原 `R1-S0` 至 `R1-S9` 的文档和资产已统一收纳到本目录。Slice 通过章节与 Slice Map 定位，目录中不再保存十套切片规格／计划／验证文件。

| 内容 | 入口 |
|---|---|
| 历史局部需求与批准依据 | [SPEC](SPEC.md) |
| 原实施计划与 Slice Map | [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md) |
| 历史验收条件、结果和限制 | [VERIFICATION](VERIFICATION.md) |
| 历史目标方案与设计 | [PROPOSED_DESIGN](PROPOSED_DESIGN.md) |
| 历史独立评审 | [REVIEW](REVIEW.md) |
| 数据准入与研究记录 | [research](research/) |
| 来源登记 | [来源登记](data/SOURCE_REGISTRY.json) |
| 操作记录、决定与调查 | [operations](operations/)、[decisions](decisions/)、[investigations](investigations/) |
| 原始证据、源码与可执行夹具 | [evidence](evidence/)；按来源 S0–S5 区分资产 |
| 旧交接材料与账本 | [history](history/) |
| 旧架构图 | [交互图](assets/SYSTEM_ARCHITECTURE.html) |
| 原路径、摘要与归档位置 | [迁移清单](ARCHIVE_MANIFEST.json) |

当前任务和有效文档仍由[项目地图](../../PROJECT.md)及[进度](../../PROGRESS.md)导航。本次归档不将历史局部批准升级为整体冻结或发布，不改变 D1/D2 科研验证状态。历史证据中的旧路径及摘要保留原貌；对应原件可从清单所记 Git 提交取回。本机 `.local/` 与 `.evidence/` 的运行产物保持原位置，文档链接已按新位置修正。

## 归档验证

2026-10-10：156 份原文件均有可定位的归档记录；101 份证据／源码保持原字节，2 份可执行合成夹具仅更新路径。404 个本地引用及 137 个章节锚点检查通过，原十个切片目录均已移除。

受影响的来源隔离、本机页面、正式目标及 MVP 测试在当前工作区全部通过；当前工作区包含并行研发的既有修改，归档提交仅纳入目录、正文合并和路径调整，不纳入并行研发业务改动。未调用真实模型或修改知识快照。
