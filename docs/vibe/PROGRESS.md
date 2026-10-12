# 当前工作进度

2026-10-12 AST升级后的单次真实API复验已封口：53目标×三策略，159单元；共同有效46目标F1：VANILLA 0.9000、DENSE 0.9136、D1 0.8718；D2 12支持／0反驳／115未知（90.55%）。完整口径与限制见[本次报告](releases/R2-20261010/experiments/2026-10-12_AST_API_REVALIDATION_REPORT.md)，历史批次保持原统计。

| 当前事项 | 状态与入口 |
| --- | --- |
| 当前工作 | R2-20261010 长目标已由用户冻结；[统一规格](releases/R2-20261010/SPEC.md)、[统一计划](releases/R2-20261010/IMPLEMENTATION_PLAN.md)、[验收矩阵](releases/R2-20261010/VERIFICATION.md)已建立 |
| 当前缺口 | 本次D2仍有115／127未知（90.55%）、0反驳；独立标签、完整保护闭包、精确token公平与四基线未验，研究效果UNVERIFIED |
| 下一步 | 依据本次保存证明缺口继续零模型分析，并完成原121条未知的完整同候选重放；正常返回、部署和资金初态不足继续UNKNOWN。本次单批API授权已消费 |

## 当前恢复位置

| 字段 | 核验事实 |
|---|---|
| 当前任务 | AST局部工程提交 `f84dc21` 已同步；正式 `9c480f3256884d5a90c1a6bb3e2d8095`、冒烟 `3ceaa993593146289246bb1bb0ff6b71` 已完成，原两批及派生不改写 |
| 本次检查 | 92项冻结摘要一致；正式141次尝试、冒烟2次，18阻断零请求；usage缺失0，候选池冲突0。见[本次验收](releases/R2-20261010/VERIFICATION.md#2026-10-12-ast-升级后单次真实-api-复验) |
| 当前整体 Release / Workflow State | R2-20261010 / BUILDING / ACTIVE；本轮需求 FROZEN，研究验证 UNVERIFIED，正式部署未授权 |
| 当前长目标 | 继续推进；本轮真实采集完成，D2证明覆盖与研究效果仍未完成。新旧候选变化，不以批次未知率差异代替同候选因果证据 |
| 最近工程工作包 | S9 单合约深度审计与 D2 闭环，存量标识 `R1-S9`；原局部批准及验收依据继续沿用 |
| 最近已验工程提交 | AST容差与别名局部提交 `f84dc218b868ac28e30685c2f668c7e53e5efdb3`；工作区662项Python／109项Java、独立提交635项Python／97项Java通过，原证据见本轮AST验收 |
| 最近实验报告 | [AST升级后真实复验](releases/R2-20261010/experiments/2026-10-12_AST_API_REVALIDATION_REPORT.md)；第二次、原批次与根因派生按各自历史报告复核 |
| 执行目录与分支 | 当前主目录，分支 `main`；无关未提交修改保留 |

第二次预检与执行分别保留在 `.evidence/R2-20261010/D1-D2-real-revalidation-ready/`、`.evidence/R2-20261010/API-revalidation-20261012/`；本轮AST升级后的预检、授权、执行与只读分析位于 `.evidence/R2-20261010/API-ast-revalidation-20261012/`。凭证远程路由由冒烟验证，配置只读且未写入报告。原始模型、工具和D2结果留在被忽略的 `.local/auto-benchmark-runs/`；不将新候选比例与旧保存候选的变化混为因果效果。

本轮初始提交为 `00fecf5`。基线证据 `.evidence/R2-20261010/baseline.json`，无关改动恢复材料 `.local/r2/preexisting.patch`。环境与输入任务文件所有权独立，公共编排串行整合；小版本验证后依 AGENTS 提交同步。尚未完成的真实路径、先导、页面与毕设交付不得以S10局部结果替代。

## Apple 工作台界面局部交付

`agent.html` 已重构为 macOS 浅色三栏工作台，使用原生 HTML/CSS/JavaScript，无编译链。支持预置与粘贴输入、D1 漏洞／修复配对、工具诊断、六项保护义务、只读历史、源码定位及 JSON／打印 PDF；批量入口保留。模拟读取已登记合成夹具，新增模型请求 0。验收与启动方式见 [界面局部验收](releases/R2-20261010/VERIFICATION.md#apple-工作台界面局部验收)，原始证据 `.evidence/R2-20261010/apple-workspace/`。此交付不代表 S11 路径证明、整个 S12 或研究效果完成。

## 最近基线与实验

R1 已验工程提交 `4dfc7e1`，历史证据见[R1 验证](releases/R1/VERIFICATION.md)。最近[真实 API 报告](releases/R1/experiments/2026-10-10_API_BATCH_REPORT.md)为 53 目标 × 三策略、159 次模型有效请求；Slither 147 项进程错误，D2 全部 UNKNOWN，研究效果 UNVERIFIED。编译环境、输入隔离和相关路径由 R2 接续。

## 本次文档整理

根目录只维护 PROJECT、PROGRESS、TECH_DESIGN；R1、R2 各自维护版本正文，Slice 进入计划表。旧日志和正文快照归入 `.evidence/`，运行登记与源码放 `data/audit/r1/`，合成夹具放 `tools/experiment/fixtures/`。本次本地引用、章节锚点、证据身份与相关离线回归检查通过；业务功能与研究状态保持原记录。

历史每日记录见[原 PROGRESS 快照](../../.evidence/R1/document-archive/PROGRESS.md)；目录与事实源只在[唯一地图](PROJECT.md)导航。
