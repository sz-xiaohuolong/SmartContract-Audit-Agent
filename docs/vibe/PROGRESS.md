# 当前工作进度

2026-10-14完成SYNAPSE全文与现行代码对照，纠正Gemini对指标、已有行号容差、有限EVM见证及不变量范围的判断。分析见[文献附件](releases/R2-20261010/attachments/SYNAPSE_REVIEW_20261014.md)，优化任务SYN-01～06已进入[统一计划](releases/R2-20261010/IMPLEMENTATION_PLAN.md#synapse-优化任务)，顺序为证据身份接缝、真实修复正反、焦点上下文、D1检查模板、确定性复核及研究准入。**本次只交付文档；任务均为PROPOSED，生产代码未修改，新增模型／嵌入请求0。** 旧133／历史151／新163的结果、冻结门槛及研究UNVERIFIED保持原记录；业务状态不变量作为后续范围提案。

2026-10-13 用户新授权的单次真实API采集已封口：53目标×三策略159次正式请求＋2次冒烟，零重试；156个有效模型结果、3个校验失败，usage缺失0。51个共同有效目标F1：VANILLA 0.9892、DENSE 1.0000、D1 0.9783；新163候选全部UNKNOWN，148条报告风险事实ID绑定失败。已定位发现／候选编译收据环境摘要的接缝，零模型同收据诊断可支持SimpleDAO原候选，但未并入正式结果或宣称产品修复。见[本次真实报告](releases/R2-20261010/experiments/2026-10-13_STAGE1_5_REAL_API_REPORT.md)。正式计划 `b178fb5443564be0b6de38690513f292` 因文档提交改变HEAD而保护阻断后，仅续采未请求单元；4＋2＋153完整覆盖159单元，原阻断及续采原件均保留。本次单次授权已消费，旧133／历史151分母和下面零模型工程结论不变。

2026-10-13 阶段1～5零模型工程接通并完成本机验证，**整体验收PARTIAL，冻结研究目标未完成**。旧133候选完整重放为75支持／0反驳／58未知（43.61%），UNKNOWN由121减少63条，但未达到≤13；新151单独为80／0／71（47.02%）。两批各159单元、四臂全部候选、原件及实现身份逐项核对通过；新增模型／嵌入请求均0。全量734项Python、111项Java、CLI、真实工具与工作台浏览器通过，详见[本轮工程报告](releases/R2-20261010/experiments/2026-10-13_STAGE1_5_OFFLINE_REPORT.md)。未将红色保护义务卡片计作最终候选REFUTED；不更改冻结候选、分母或原行号。

2026-10-12 思考模式与完整源码输入复验已封口：53目标×三策略，159单元各有一次真实API请求，输入阻断0；共同有效51目标F1：VANILLA 0.9783、DENSE 1.0000、D1 0.9783；D2 12支持／0反驳／139未知（92.05%）。完整口径见[历史报告](releases/R2-20261010/experiments/2026-10-12_THINKING_FULLSOURCE_API_REPORT.md)，旧批次保持原统计。

此前AST升级复验的共同有效46目标F1为VANILLA 0.9000、DENSE 0.9136、D1 0.8718；D2为12支持／0反驳／115未知（90.55%），见[历史报告](releases/R2-20261010/experiments/2026-10-12_AST_API_REVALIDATION_REPORT.md)。两批输入资格及模型设置不同，不以F1差值作单参数因果结论。

| 当前事项 | 状态与入口 |
| --- | --- |
| 当前工作 | R2-20261010 长目标已由用户冻结；[统一规格](releases/R2-20261010/SPEC.md)、[统一计划](releases/R2-20261010/IMPLEMENTATION_PLAN.md)、[验收矩阵](releases/R2-20261010/VERIFICATION.md)已建立 |
| 当前规划 | SYNAPSE分析与SYN-01～06优化计划已编写；任务均PROPOSED，见[统一计划](releases/R2-20261010/IMPLEMENTATION_PLAN.md#synapse-优化任务) |
| 当前缺口 | 旧133仍有58未知、新151有71未知，均0反驳；Parity三单元缺固定solc0.4.9兼容协议，真实修复正反、独立标签、完整保护闭包与精确token公平未验 |
| 下一步 | 依据最终逐候选缺口推进编译协议、动态／跨合约资源与维护者修复闭环；来源／候选独立审核及tokenizer核实另行补齐。本次付费授权已消费；优先零模型修复事实ID接缝，不追加新批次，不据未知反推错误候选 |

## 当前恢复位置

| 字段 | 核验事实 |
|---|---|
| 当前任务 | 2026-10-14 SYNAPSE文献／代码对照与优化计划文档交付；未实施SYN-01～06。此前单次真实采集COMPLETED／VERIFIED_COLLECTION与双批次派生结论保持原记录 |
| 本次文档检查 | 论文全文／表2与表4、现行源码与封口统计对照；本地链接／锚点、格式、凭证与提交范围核对通过，见[文档核验](../../.evidence/R2-20261010/synapse-review-20261014/verification.json)。未重跑全量应用测试，未实施新方案 |
| 最近工程检查 | 159正式＋2冒烟、全部原件指针、零请求阻断及续采、usage、身份前后与共同分母独立核对；生产源码／JAR未变，734项Python／111项Java沿用。旧双批次四臂与浏览器验收继续保留 |
| 当前整体 Release / Workflow State | R2-20261010 / BUILDING / ACTIVE；本轮需求 FROZEN，研究验证 UNVERIFIED，正式部署未授权 |
| 当前长目标 | 五阶段工程已接通；UNKNOWN门槛、真实维护者修复双向裁决、独立真值及精确token公平仍未完成 |
| 最近工程工作包 | S11／S12阶段1～5零模型接通；S9等历史局部验收继续保留 |
| 最近已验工程提交 | 生产基点 `f222e7c`；本次源码／JAR相同，734项Python／111项Java通过；真实报告提交同步另存本次证据 `git-sync.json` |
| 最近实验报告 | [2026-10-13真实API采集](releases/R2-20261010/experiments/2026-10-13_STAGE1_5_REAL_API_REPORT.md)；[阶段1～5零模型工程](releases/R2-20261010/experiments/2026-10-13_STAGE1_5_OFFLINE_REPORT.md)；所有真实API批次按原历史报告复核 |
| 执行目录与分支 | 当前主目录，分支 `main`；无关未提交修改保留 |

本轮最终证据 `.evidence/R2-20261010/stage1-5-final-20261013/`，包含测试、身份核对、时间漂移修复对照、浏览器与下载；双账本位于 `data/audit/r2/research-review/20261013/`，恢复材料 `.local/r2/stage1-5-start-20261013/` 保留。

此前预检、冒烟、执行与只读分析位于 `.evidence/R2-20261010/API-thinking-fullsource-20261012/`；AST升级后的原证据位于 `.evidence/R2-20261010/API-ast-revalidation-20261012/`，再前两轮的预检与执行分别保留在 `.evidence/R2-20261010/D1-D2-real-revalidation-ready/`、`.evidence/R2-20261010/API-revalidation-20261012/`。凭证远程路由由冒烟验证，配置只读且未写入报告。原始模型、工具和D2结果留在被忽略的 `research-artifacts/runs/benchmarks/`，旧 `.local/auto-benchmark-runs/` 为兼容入口；不将新候选比例与旧保存候选的变化混为因果效果。

本轮初始提交为 `00fecf5`。基线证据 `.evidence/R2-20261010/baseline.json`，无关改动恢复材料 `.local/r2/preexisting.patch`。环境与输入任务文件所有权独立，公共编排串行整合；小版本验证后依 AGENTS 提交同步。尚未完成的真实路径、先导、页面与毕设交付不得以S10局部结果替代。

## Apple 工作台界面局部交付

`agent.html` 已重构为 macOS 浅色三栏工作台，使用原生 HTML/CSS/JavaScript，无编译链。支持预置与粘贴输入、D1 漏洞／修复配对、工具诊断、六项保护义务、只读历史、源码定位及 JSON／打印 PDF；批量入口保留。模拟读取已登记合成夹具，新增模型请求 0。验收与启动方式见 [界面局部验收](releases/R2-20261010/VERIFICATION.md#apple-工作台界面局部验收)，原始证据 `.evidence/R2-20261010/apple-workspace/`。此交付不代表 S11 路径证明、整个 S12 或研究效果完成。

## 最近基线与实验

R1 已验工程提交 `4dfc7e1`，历史证据见[R1 验证](releases/R1/VERIFICATION.md)。最近[真实 API 报告](releases/R1/experiments/2026-10-10_API_BATCH_REPORT.md)为 53 目标 × 三策略、159 次模型有效请求；Slither 147 项进程错误，D2 全部 UNKNOWN，研究效果 UNVERIFIED。编译环境、输入隔离和相关路径由 R2 接续。

## 本次文档整理

根目录只维护 PROJECT、PROGRESS、TECH_DESIGN；R1、R2 各自维护版本正文，Slice 进入计划表。旧日志和正文快照归入 `.evidence/`，运行登记与源码放 `data/audit/r1/`，合成夹具放 `tools/experiment/fixtures/`。本次本地引用、章节锚点、证据身份与相关离线回归检查通过；业务功能与研究状态保持原记录。

2026-10-12 按用户要求补充 AGENTS 的证据预算与保留规则，清理 1,895 份重复／构建文件并无损压缩历史输出，净减少文件内容约 276 MiB；保护正在运行的真实实验、工具与编译收据、已有工作区改动及唯一恢复快照。原件摘要、归档还原和本地引用核对通过；清理与超限保留例外见 `.evidence/R2-20261010/evidence-retention-20261012/README.md`。

历史每日记录见[原 PROGRESS 快照](../../.evidence/R1/document-archive/PROGRESS.md)；目录与事实源只在[唯一地图](PROJECT.md)导航。

## 数据迁移与旧应用退役

2026-10-12 按用户要求，将旧资源中的 898 份数据迁至 `data/`，保留原件字节、标签与划分；旧 Java 应用、测试、配置、字体和独立构建退役。当前入口见[数据说明](../../data/README.md)。独立提交内容的 Maven 97 项、Python 636 项及 CLI 帮助通过，原 53 目标身份与标签保持一致；[本次验收](releases/R2-20261010/VERIFICATION.md#数据迁移与旧应用退役)。本次新增模型请求 0，R2 研究状态沿原记录。

## 原始数据源去重与目录整理

2026-10-12 用户明确要求去掉重复副本并整理 `data/`。本任务沿用 53 个目标编号、漏洞类型、标签值与漏洞行；公开源码和标注直接读取根目录两个原始仓库，额外对照单独登记；历史实验与固定输入保持原记录。已删除 844 份重复或可重建文件，50 份对照原样移至 `data/controls/openzeppelin/`；来源版本与校验登记在 [datasets.json](../../data/datasets.json)。局部状态 `VERIFIED`：独立提交内容的 Maven 97 项、Python 641 项、CLI、来源摘要和逐份身份核对通过，新增真实模型请求 0；29 个目标仅因原始空白恢复改变摘要，新输入不能续写旧计划，旧保存目标仍可续跑。见[本次验收](releases/R2-20261010/VERIFICATION.md#原始数据源去重与目录整理)；整体研究验证仍为 `UNVERIFIED`。

## 本机存储拆分与无损归档

2026-10-13 按用户要求清理被最终结果替代的7个零模型中间重放、21个重复离线演练及2,092个专属生成收据目录，共22,823文件，磁盘占用减少约440 MiB。保留26,222文件SHA一致；30个模型批次、6个保留派生回放及9个HTTP下载通过，最终133／151候选身份、源码／JAR及四臂裁决仍一致。保留时间漂移关键旧对照与全部真实模型原件，新增模型请求0；清单与限制见[原件说明](../../research-artifacts/README.md)，本机证据 `.evidence/R2-20261010/obsolete-runs-cleanup-20261013/`。

2026-10-12 按用户要求将 33 个现存目录原地分类，研究原件归 `research-artifacts/`，外部仓库归 `data/external/`，`.local/` 保留本机环境及恢复材料。6,248 份文件无损归档，净释放约 672 MiB；15,040 份原件 SHA、30 批次指标／候选／D2、3 个派生报告保持一致，6 份快照与6份编译绑定通过。只读 HTTP 下载维持原字节，新增模型请求0；独立提交内容650项Python全量、网关1项补验及97项Java／CLI通过，最终整理幂等。规则、一键入口和限制见[整理报告](releases/R2-20261010/STORAGE_LAYOUT_REPORT.md)，验收见[R2记录](releases/R2-20261010/VERIFICATION.md#本机存储拆分与无损归档)。原件远程备份未配置，R2研究验证保持UNVERIFIED。
