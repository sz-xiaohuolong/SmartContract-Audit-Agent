# R1-S3 工程交付与研究门禁验证记录

日期：2026-09-24。范围：来源准入、谱系隔离与 D1 离线证伪流水线，以及 D2 固定候选最小契约。开发在当前主目录完成；真实模型未调用。工程交付与研究效果分别验收，后者仍受 G1–G3 门禁约束。

## 按需求核验

| 需求 | 当前结果 | 证据与未满足部分 |
|---|---|---|
| S3-01 来源准入 | 部分完成 | 来源登记固定四个仓库提交；机器门禁要求真实样本的源码、报告、补丁、漏洞位置和审核引用齐备。逐事件真实性与许可仍待人工核对，真实准入数为 0。 |
| S3-02 谱系隔离 | 工程门禁通过，真实数据未审 | 合成泄漏报告与离线回归覆盖项目、事件、补丁、精确重复、近克隆候选和衍生材料；锁定集拒绝打开。 |
| S3-03 独立标签 | 契约通过，真实标签缺失 | 判断格式与 UNKNOWN 分母有回归；没有独立审核员对真实目标—案例出具标签。 |
| S3-04 同池同预算对照 | 合成机制通过，真实 token 公平未验证 | 七策略复用同一候选池；字段过滤基线保留可用反证，避免人为削弱。合成码点适配器不能替代真实模型 tokenizer 与消息模板。 |
| S3-05 D1 消融与指标 | 合成机制通过，研究效果未验证 | 两项消融、逐样本指标和错误分解可重放；真实开发样本为 0。 |
| S3-06 D2 固定候选 | 最小契约通过 | guard 两项基线与 UNKNOWN 分母可重放；真实真假候选尚无独立证据。 |
| S3-07 付费运行控制 | 本轮无需付费运行 | 未选择真实运行，未调用付费 API；后续真实实验仍需请求及 token 上界 dry-run。 |
| S3-08 研究裁决 | 暂停效果结论 | G1 未通过；D1 仅保留离线证伪方案，D2 停留在挑战契约。 |

因此本次只能确认 S3 的工程部分可重放，不能将 S3 整体标为研究验收通过或 `READY_TO_SHIP`。

## 来源审核与 G1 状态

[来源登记](SOURCE_REGISTRY.json)保存四个仓库的固定提交、许可状态、公开材料入口及未核实字段。本轮依据各项目原始 GitHub 仓库和论文入口核对，未下载数据集到本项目，也没有给真实样本编造源码摘要或人工真值。

| 来源 | 仓库许可 | 已见原始材料 | 仍需人工核实 |
|---|---|---|---|
| SCRUBD | 未核实；仓库 API 未报告许可 | `SCRUBD-CD/data`、重入标签及注释入口 | 每条合约源码版本、报告/评论对应、补丁谱系、RE=0 的保护语义 |
| SmartBugs Curated | 仓库 Apache-2.0 | 类别目录、源码注释、`vulnerabilities.json` | 原项目谱系、逐事件报告、真实修复对；库中漏洞样本不自动产生安全负例 |
| ASE 2025 AC 基准 | 仓库 MIT | `datasets.xlsx`、DeFiHackLabsCVEs、Code4rena | 各行原始报告、准确源码/修复提交、负例定义与项目/克隆关联 |
| ACFix | 未核实；仓库 API 未报告许可 | `data`、README 中 original/modified 与测试日志入口 | 真实人工补丁与模型输出区分、原始报告、源码提交、许可及修复正确性 |

仓库许可证仅说明仓库声明，不代替对上游第三方合约/报告再分发范围的逐项核对。G1 **未通过**：当前没有逐事件经审查的真实目标—案例标签、可靠补丁对和安全负例。因此未执行真实开发集先导，未打开锁定测试，D1 科研效果状态为 **UNVERIFIED**。

## 工程门禁与数据契约

`tools/experiment/s3.py lineage` 检查源码和衍生材料 SHA-256、来源/版本、项目、漏洞事件、补丁对、精确字节、人工克隆组与跨划分关联边。报告产生连通组 ID 和近克隆候选；跨划分近克隆候选也阻断。源码、报告、摘要、知识块和模板的 `groupId` 必须继承样本补丁对组。真实补丁样本只有在来源四项状态均已核实、漏洞类别和行号有效、SOURCE/REPORT/PATCH 原件均已校验且报告和补丁材料由 `truthEvidence` 指向、独立审核员及版本有记录时，才会退出 `pendingSamples`。这些字段的真实性仍需人在原始仓库与报告中核查，程序不能仅凭填写 `INDEPENDENT` 字符串证明审核独立性。锁定测试源码在先导进程中从不打开。本切片无法验证外部封存证明的真实性，因此只要清单包含锁定测试样本便拒绝运行；锁定集的近克隆隔离仍需后续独立审核方案，不能宣称已完成。近克隆规范化指纹只是候选发现器，不能证明不存在其他克隆。

`judgments.json` 对每个目标—案例给出 0–3 级适用性、支持/反证价值、审查角色、标签版本、证据引用和 `REVIEWED/PENDING/DISPUTED`。支持与反证必须来自同一审核配对的不同案例。待审必须保持 UNKNOWN，评价要求覆盖整个候选池；只要池中尚有待审案例，Recall@K/nDCG 为 null，并显式报告未知总数及入选数。无已审核正例、无已知入选分母也为 null。按项目作为聚合单位；真实补丁、人工改造、合成样本分别计数。合成夹具作者的标签仅用于机制测试，`researchEligible=false`。

`tools/experiment/s3_pilot.py` 每个目标只调用一次 S2 `compare`，固定知识快照和候选池，再做字段条件过滤与两项消融：字段过滤保留条件已支持与已反证的案例，只排除 UNKNOWN，防止人为削弱反证基线；D1_NO_BINDING 使用配对元数据但不使用目标条件绑定，D1_NO_COMPLEMENT 保留适用候选但不选互补反例。检索超时与解析失败逐样本记 `FAILED`，不从分母消失。S2 字节/数量预算必须足以容纳全部候选，之后由同一显式 tokenizer 适配器对 **系统提示＋目标源码＋问题＋工具摘要＋输出格式＋已选证据** 完整计数；适配器文件、版本、模板和最大 token 数绑定计划。现有 UTF-8 字节数不作为 token 数。真实模型试验前还需独立核实 tokenizer 与指定模型版本、chat 消息序列化格式及全部提示字段一致；现有纯文本拼接尚未证明与真实 API 提示等价。示例使用码点计数，仅可验证流水线控制流，不能作为 token 公平的科研证据。固定提示本身超预算会拒绝运行。

D2 路径可行性过滤和双向错误曲线留待后续阶段；本切片只验固定候选、覆盖义务与 guard 两项简单基线。D2 的 [失败/未知分母](evidence/demo/d2-summary.json)显示合成固定候选计划 2、弃权 UNKNOWN 2、未知真值上的确定性判断 0、失败 0；没有可裁决结果，错误接受/拒绝率为 null。D2 的 `validate_d2_challenges` 要求固定候选源码摘要、风险行、声称路径、真值出处及六类保护义务。TRUE/FALSE 必须有审核证据，UNKNOWN 保留未知；真值 UNKNOWN 上的 TRUE/FALSE 输出另计 `unknownTruthDecisions`，不计正确。当前两个合成候选的 guard 存在性/具体行基线输出在 [D2 夹具](evidence/demo/d2-baselines.json)；基线的漏洞裁决始终 UNKNOWN，不把 guard 字样当安全。

## 可重放命令

在项目根目录执行：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/s3.py lineage \
  --ledger docs/vibe/releases/R1-S3/evidence/demo/ledger.json --root .

PYTHONPATH=tools/experiment python3 tools/experiment/s3_pilot.py \
  --ledger docs/vibe/releases/R1-S3/evidence/demo/ledger.json --root . \
  --plan docs/vibe/releases/R1-S3/evidence/demo/plan.json \
  --labels docs/vibe/releases/R1-S3/evidence/demo/judgments.json \
  --tokenizer docs/vibe/releases/R1-S3/evidence/demo/codepoint_tokenizer.py \
  --jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar \
  --worker tools/experiment/program_facts.py --output /tmp/s3-pilot-new.json

mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
```

`--output` 必须是不存在的文件，避免覆盖前次实验。源数据只是 [S2 合成机制夹具](../R1-S2/evidence/demo/bundle.json)，重新标为 development/knowledge 的 S3 演示划分；[谱系清单](evidence/demo/ledger.json)、[人工标签示例](evidence/demo/judgments.json)、[计划](evidence/demo/plan.json)、[逐样本输出](evidence/demo/pilot.json)均可复查。修正字段过滤基线后，合成示例中 D1 与字段过滤的 Recall@2 **均为 1**；D1 的 nDCG@2 为 1，字段过滤为 0.834。两者在作者构造案例上的差异**不是方法提升证据**。

## 最新验证证据

- [Maven 日志](evidence/maven-clean-verify.log)：`mvn clean verify`，35 项，0 失败/错误/跳过，BUILD SUCCESS。
- [Python 日志](evidence/python-unittest.log)：`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`，72 项，OK。新增回归先观察到报告/补丁待审样本被遗漏、空材料准入、来源材料错绑、反证基线缺失、超时丢分母、未知真值漏计及旧源码硬编码凭证，再修正相应行为。
- 旧模块仅执行 `mvn -o -f legacy/pom.xml -DskipTests compile`，离线编译成功；未运行旧集成测试，因其可能调用真实服务。
- [失败回归](evidence/review-red.log)与独立复审确认：共享报告跨划分、锁定证明伪造、候选正文注入、超预算、注释伪 guard 和标签伪配对均已阻断；[空清单失败回归](evidence/empty-ledger-red.log)及[修复后回归](evidence/empty-ledger-green.log)证明空来源/样本不会通过门禁。独立复审结论限于首切片工程门禁，无剩余已知阻断。
- [泄漏报告](evidence/demo/leakage-report.json)：合成 knowledge 2、development 1、跨划分错误 0；两个知识案例同一连通组。`pendingSamples=3`，因为合成夹具无真实来源许可/报告/补丁，科研准入仍为 0。
- [逐样本结果](evidence/demo/pilot.json)：七种检索/消融策略共享同一个 S2 `poolHash` 与快照，统一提示上限 600 个**合成码点计数单位**；实际完整提示 312 或 445 单位。原始输出包含每策略入选案例、Recall@K、nDCG、错误入选、互补覆盖、逐条件错误分解与 UNKNOWN 分母。真实模型 token 公平尚未验证。
- 本次在主目录重新执行谱系命令，结果为 3 个合成样本、跨划分错误 0、待审 3；重新执行先导后，分母为计划 1、完成 1、失败 0、科研准入 0，输出与仓库逐样本证据逐字段一致。四个来源仓库的远程 HEAD 与来源登记中的固定提交一致。

## 失败、UNKNOWN 与研究裁决

合成演示：计划 1、完成 1、失败 0、研究合格 0；UNKNOWN 判断 0。真实开发样本：0，真实研究指标全部未计算。近克隆门禁、锁定测试拒绝、待审标签 null 分母、token 总提示预算和 D2 UNKNOWN 均有确定性离线回归。

D1 裁决：**谨慎保留离线证伪方案，暂停效果结论**。下一步要先完成许可、来源、补丁、项目组及人工判断审核；再锁定真实 tokenizer 与完整提示预算，比较 D1 与最强非 D1 基线的项目级结果。若简单字段过滤解释全部收益，应收窄 D1；若可靠样本/标签无法取得，应暂停该科研主张。D2 继续停留在挑战数据契约，不进入多智能体或深度符号执行实现。锁定测试只在方法、阈值和预算冻结后由独立审核者开启。

旧 `src/` 中曾有形似真实的硬编码供应商密钥，本轮改为读取 `DASHSCOPE_API_KEY` 环境变量并加入源码扫描回归；该旧值已存在于此前提交历史，**源码修改不能撤销已暴露的凭证**，需在供应商控制台撤销或轮换。未尝试使用该凭证，也未改写 Git 历史。
