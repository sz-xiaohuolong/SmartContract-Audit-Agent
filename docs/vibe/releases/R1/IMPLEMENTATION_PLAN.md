# R1 实施计划与切片记录

整理日期：2026-10-10。本文按原文来源合并历史记录，仅调整标题层级与路径。各章节的状态和“当前”均指原记录时点；归档不追加整体冻结、验收或发布结论。

| 原切片／记录 | 归档章节 |
|---|---|
| R1-S0 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s0-implementation-plan) |
| R1-S1 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s1-implementation-plan) |
| R1-S2 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s2-implementation-plan) |
| R1-S3 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s3-implementation-plan) |
| R1-S4 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s4-implementation-plan) |
| R1-S5 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s5-implementation-plan) |
| R1-S6 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s6-implementation-plan) |
| R1-S8 / `AUTO_EXPERIMENT_PLAN.md` | [AUTO_EXPERIMENT_PLAN.md](#s8-auto-experiment-plan) |
| R1-S8 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s8-implementation-plan) |
| R1-S8 / `NOMIC_IMPLEMENTATION_PLAN.md` | [NOMIC_IMPLEMENTATION_PLAN.md](#s8-nomic-implementation-plan) |
| R1-S9 / `IMPLEMENTATION_PLAN.md` | [IMPLEMENTATION_PLAN.md](#s9-implementation-plan) |

## Slice Map

| 切片 | 原范围 | 规格与验证 |
|---|---|---|
| S0 | CLI 与工具基础 | [规格](SPEC.md#s0-spec)；[原验证](VERIFICATION.md#s0-verification) |
| S1 | 清单、快照与断点续跑 | [规格](SPEC.md#s1-spec)；[原验证](VERIFICATION.md#s1-verification) |
| S2 | D1 条件检索与事实 | [规格](SPEC.md#s2-spec)；[原验证](VERIFICATION.md#s2-verification) |
| S3 | 数据准入与先导 | [规格](SPEC.md#s3-spec)；[原验证](VERIFICATION.md#s3-verification) |
| S4 | 单样本审计闭环 | [规格](SPEC.md#s4-spec)；[原验证](VERIFICATION.md#s4-verification) |
| S5 | 真实案例与知识 | [规格](SPEC.md#s5-spec)；[原验证](VERIFICATION.md#s5-verification) |
| S6 | 批量对照 | [规格](SPEC.md#s6-spec)；[原验证](VERIFICATION.md#s6-verification) |
| S7 | 公开语料待审入库 | 未单列规格；[原验证](VERIFICATION.md#s7-verification) |
| S8 | 候选准入、自动标注与 Nomic 对照 | 未单列规格；[原验证](VERIFICATION.md#s8-verification) |
| S9 | 单合约工作台与 D2 | [规格](SPEC.md#s9-spec)；[原验证](VERIFICATION.md#s9-verification) |

<a id="s0-implementation-plan"></a>

## S0 实施计划

依据：[SPEC](SPEC.md#s0-spec)。执行方式：主 Agent 在隔离 worktree 按任务执行，最终独立审查；延续用户已批准阶段方案，不重复请求开始许可。
技术：Java 21、Spring Boot 4.1.1、Spring AI 2.0.1；正式版本由 Maven Central 与官方文档核验。

### 任务 1：依赖隔离与测试入口

文件：根 pom.xml、legacy/pom.xml、audit-mvp/pom.xml。
保留旧 src；旧 pom 在 legacy 指向旧 src，新模块作为根默认构建。理由：Spring AI 2 从旧 M6 接口跨代升级，先导工程不能被未迁移演示类和付费测试拖入启动。
验证：`mvn -pl audit-mvp test` 默认只运行离线测试。

### 任务 2：Provider 配置与实际网关

文件：ProviderConfig、ProviderRegistry、SpringAiGateway 及 GatewayTest。
测试先行：本地 HttpServer 返回标准 chat completion；断言 /api/plan/v3/chat/completions、Bearer 请求、model 字段与 usage；第二 provider 的请求落到独立路径；无效配置和 401 不重试。
契约：GatewayReply complete(String provider, String system, String user)。
每个请求 maxRetries=0，时间和输出 Token 有限；使用 API 2.0 正式 builder。

### 任务 3：审计解析与 CLI

文件：AuditService、AuditCli；测试空文本、缺字段、多对象、false 与异常区分、源码哈希。
先写断言 `assertEquals(FAILED, service.audit(...).status())` 对无效 JSON，再实现严格解析。
入口：显式参数 --source、--config、可选 --provider；默认只显示帮助，无联网。

### 任务 4：受控进程和工具适配

文件：ProcessRunner、ToolAnalyzer、ProcessRunnerTest、ToolAnalyzerTest。
先测试挂起和持续输出不会绕过超时，测试失败 JSON 不等于空报警；再实现从启动计时、后台排空、输出上限和清理。

### 任务 5：集成与交付

运行 `mvn clean verify`；检查打包资源无旧本地配置/密钥；CLI 帮助离线；记录所有真实与未验证行为；更新 README、AGENTS、PROGRESS。

### 审查重点

URL 带自定义前缀不得被补成 /v1；密钥不能进入错误日志；usage 缺失不能记零；进程大输出不得阻塞；非法 JSON 不得形成安全结果。上述各项均加入对应测试。

<a id="s1-implementation-plan"></a>

## S1 数据与实验基础实施计划

使用 `superpowers:executing-plans` 在当前主目录逐项执行；保留已有未提交文件。

目标：落实 [SPEC](SPEC.md#s1-spec) 的 S1a/S1b 工程范围。技术栈为 Python 标准库和已有 Java CLI，不引入服务依赖，不迁移旧集合。用户 2026-09-21 明确授权 S1b 实现；以下为内部实现选择。

### 已完成 S1a

只读 inventory、严格 evaluate 及 7 项离线测试，保留原验证记录。

### S1b 执行顺序

- [x] T1 分组隔离：新增 `isolation.py` 与 `tests/test_isolation.py`。接受人工审核的来源、项目组、克隆组、字节组和 split；对全部样本统一验证，同组不得跨划分；knowledge 文档必须继承原样本谱系。先用同字节、同项目、近似克隆和缺审核信息的夹具证明拒绝，再实现。
- [x] T2 知识快照：新增 `snapshots.py` 与 `tests/test_snapshots.py`。快照绑定完整清单、文档内容、分块参数、embedding 模型与维度；逐条验证向量、ID、数量和哈希。先写半构建、内容损坏、索引缺项测试，再实现临时目录构建、完整验证后原子发布和激活指针替换。索引通过可注入适配接口读回核对，离线文件索引用于确定性验收；旧集合不修改。
- [x] T3 批处理：新增 `batch.py` 与 `tests/test_batch.py`。计划绑定源码、规范类型映射、配置、执行产物和知识快照；单写者锁内每个 START/RESULT 事件 fsync 到 JSONL。先验证中断、尾部残行、配置变化、重复记录、失败负例，再实现 run/resume/replay。完成和失败记录默认跳过；有 START 无 RESULT 的调用保留为不确定，不自动付费重试。显式指定样本方可重试失败/不确定项。Replay 只读日志，复用 evaluate。
- [x] T4 命令与文档：提供离线快照及隔离命令、显式 Java 批处理入口、子进程夹具端到端测试，更新工具 README、PROJECT/PROGRESS 与 VERIFICATION。
- [x] T5 验证与复审：运行 Python 全套、`mvn clean verify`、CLI 帮助和 diff 检查；按 `requesting-code-review` 进行独立复审，修复重要问题并记录证据。

### 重点检查

1. 调用已发出但结果未持久化：默认不得盲目重发，无法保证跨外部 API 的 exactly-once。
2. JSONL 只有末尾非完整行可恢复，完整行损坏必须拒绝；重放不修改原日志。
3. 恢复前校验全部源码、配置和产物；不得到批处理中途才发现输入漂移。
4. 半成品、重复 ID、非有限向量和索引读回不符不能更新 active；失败保持旧快照。
5. 划分校验不能只比较 sample ID；项目/克隆/源码关联与知识衍生文档同样参与。

### 验证命令

```bash
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
mvn clean verify
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
git diff --check
```

不自动提交、推送或发布；不运行真实模型、embedding 或 Milvus。真实部署适配的连通性不计入离线验证结论。

### 本轮执行记录（2026-09-21）

- T1/T2/T3 首次运行分别因新模块尚不存在而失败；随后各自离线测试通过。T4 命令闭环首次因入口尚不存在而失败，实现后通过。
- 补充未映射类型 usage 测试明确复现 `12 != None`，定位为类型映射失败统一丢弃结果；修复后保留原始响应和实际 usage，仍计 FAILED。
- 独立复审及增量复核未发现阻断问题；另外补齐 RESULT 落盘中断、多页索引读回、冻结 JAR/配置三项边界测试。最终 35 项 Python 与 19 项 Java 测试通过。
- 实现选择：JSONL 本身作为 checkpoint；in-flight 调用保守记录为 UNRESOLVED，显式重试才重新调用。知识块由调用方提供，避免在本轮隐式运行 embedding 或改动旧集合。
- 本轮保持未提交状态，未执行外部发布。证据见 [VERIFICATION](VERIFICATION.md#s1-verification)。

<a id="s2-implementation-plan"></a>

## S2 D1 实施计划

使用 `superpowers:executing-plans` 在当前目录执行；遵循 TDD，末尾独立复审。规格：[SPEC](SPEC.md#s2-spec)。用户已授权 S2 与本地 Milvus 使用，无需重新批准开始实现。

- [x] T1：新增 `tools/experiment/program_facts.py` 和对应测试。词法屏蔽注释/字符串，匹配作用域与声明，输出状态变量/函数/动作。展开已定义且无参数的简单修饰器；分支、继承、汇编、未知调用等降级，保留明确位置。先验证安全检查与错误主体、过晚检查、旁路、未知、注释伪造。
- [x] T2：新增 `audit-mvp/.../retrieval` 的事实/案例/候选/证据数据与独立 `RetrievalStrategy` 接口。共享候选池冻结并去重，提供 Dense、Hybrid、普通正反例、D1 的确定性实现。先验证条件 TRUE/FALSE/UNKNOWN、成对匹配、缺口、相同预算及失败拒绝。
- [x] T3：提供 Python 事实子进程适配与 Java 离线 D1 CLI，使用只读 JSON 候选池进行可导出比较。事实响应必须绑定源码摘要；超时、截断、无效 JSON 不得参与条件推断。
- [x] T4：通过 S1b 已验证快照导出目标无标签的候选池；提供本地余弦召回与可选 Milvus 搜索适配。固定合成向量离线测试，同一候选池进入所有策略。若本地服务可启动，单列真实 Milvus 冒烟证据，不纳入单元测试依赖。
- [x] T5（工程验证与独立复审完成）：运行 Python 全套、`mvn clean verify`、CLI 闭环，独立复审；记录源码摘要、限制与证据，更新 PROGRESS/PROJECT。

### 内部实现选择

案例使用显式角色条件（检查在风险前、同资源状态更新在调用前），按作用域和源码顺序解释。配对关系来自审核元数据，不能从正负标签自动推定有效补丁。共享预算按文本 UTF-8 字节保守计量（可导出计量版本），避免无锁定 tokenizer 时声称精确模型 token 数；后续真实模型实验需冻结 tokenizer。

本轮不做数据迁移、真实标签写回、旧集合重建、付费模型调用或提交发布。对照输出不包含目标真值。

### 执行结果

2026-09-21：T1—T4 已实现；Maven 33 项与 Python 50 项通过。真实本地 Milvus 已完成合成向量/完整快照冒烟；四策略离线 CLI 报告已导出。T5 的独立复审子代理因账户额度失败，主会话已完成本地复查和回归修复，具体见 REVIEW 与 VERIFICATION；不把替代检查记作独立复审通过。研究配对与下游效果实验仍未执行。

2026-09-22：T5 已闭环，独立复审发现的五项问题已修复，最新 Maven 35 项、Python 52 项及四策略 CLI 全部通过。工程范围 READY_TO_SHIP，未提交或发布；研究先导仍待真实审核数据与冻结预算。

<a id="s3-implementation-plan"></a>

## R1-S3 下一线程实施计划

状态：首个工程切片已交付并通过离线验证；2026-09-24 已实现离线门禁与合成夹具先导，真实数据 G1 未通过。下列“部分完成”与“阻塞”项属于 S3 研究验收所需后续工作，不得改写为已完成。

1. [x] 恢复项目状态：读 AGENTS、PROJECT、PROGRESS、R1-S2 DESIGN/VERIFICATION、S3 SPEC/DESIGN 与第二轮查新；列出已有能力和可复用接口；不改历史 release 证据。
2. [x] 数据可用性调查：核对 SCRUBD、SmartBugs Curated、ASE AC 基准、ACFix 的下载、许可、原始报告、源码版本、补丁与安全标签；形成来源登记，未核实不入真值。若无法取得必要数据，停在可审查的阻塞报告。
3. [x] 设计并实现分组图、近重复候选审查和 knowledge/dev/validation/locked-test 泄漏门禁；先用离线夹具验证同项目、同补丁、近克隆不跨组。
4. [部分完成] 实现可人工复核的案例—目标标签格式与校验；真实开发先导清单因来源/许可/补丁未审而阻塞，不伪造专家标签。
5. [工程接口完成，真实 tokenizer 未审] 复用 S2 检索，补简单字段过滤基线及实际 token 预算计数；保证各策略同 pool、同模板、同候选和预算；加离线适用性/互补性指标和逐样本错误报告。
6. [x] 建立 D2 固定候选与保护覆盖义务挑战数据契约及 guard 存在性/引用行基线；未确认真值时只输出资料不足。不要直接扩展成全 Agent/符号执行系统。
7. [工程验证完成，真实先导阻塞] 运行 Maven/Python 离线验证和合成夹具先导，记录版本、哈希、预算与负结果；更新 PROGRESS 与 S3 VERIFICATION。付费模型仅在另行 dry-run、显式指定真实运行参数后执行。

交付可复查数据谱系、运行命令、原始逐样本结果、聚合脚本、失败/未知分母、研究门禁结论。代码量不是验收目标；能否把简单强基线排除才决定是否继续投 D1/D2。

本轮验收与阻塞证据见 [VERIFICATION](VERIFICATION.md#s3-verification)。锁定测试保持封存；本切片直接拒绝含锁定样本的清单。

<a id="s4-implementation-plan"></a>

## R1-S4 单样本审计工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. User requires direct work in the current main directory; do not create a worktree or delegate shared-file edits.

**Goal:** 让已登记开发源码在本机完成正式 Milvus → D1 → 结构化模型假设 → 工具证据 → D2 → 可回放报告 → 页面的一次审计工程链路。

**Architecture:** Python 负责谱系、快照、编排、持久化与本机 HTTP；Java CLI 负责现有 D1、Spring AI 结构化模型阶段和工具解析。正式 `s1b_` 集合只读，Python／Java 以版本化 JSON 通信；离线夹具替代真实模型、Milvus 和工具。

**Tech Stack:** Java 21、Spring Boot 4.1.1、Spring AI 2.0.1、Python 3 标准库、固定 BGE 本地模型、Milvus REST、本机静态 HTML／JavaScript。

**Spec:** [SPEC](SPEC.md#s4-spec)、[PROPOSED_DESIGN](PROPOSED_DESIGN.md#s4-proposed-design)、[追加决定](decisions/S4_CHANGE_PROPOSAL.md)。

### Global Constraints

- 当前主目录开发，保留现有未提交修改；所有新增说明和代码注释使用简体中文。
- 默认测试完全离线、确定性；真实模型运行仅由使用者在页面明确选择，一次点击最多一次请求、2048 输出 token、零自动重试。
- 不改变已激活正式知识集合，不将旧 `mvp_` 当正式库；不打开锁定测试，不把工程试跑当 D1／D2 科研效果。
- 失败、超时、解析错误与工具缺失不能映射为安全；usage 缺失保留 `null`。
- 每个完整可验收小版本通过相应测试后，核查凭证、暂存区和远程变更，仅提交本版本文件并同步 `origin/main`；不连带提交已有用户改动。

### File Map

| 文件 | 单一职责 |
|---|---|
| `tools/experiment/formal_targets.py` | 开发目标白名单、谱系、函数范围、源码摘要和运行资格 |
| `tools/experiment/formal_recall.py` | 正式快照与同版 BGE／Milvus 召回、Java D1 预览适配 |
| `tools/experiment/recall.py` | 将候选池组装逻辑复用给受限工程目标，原研究入口约束不变 |
| `audit-mvp/.../HypothesisService.java`、`HypothesisCli.java` | 新版结构化假设与独立 CLI，不改旧三字段结果 |
| `audit-mvp/.../ToolCli.java` | 受控调用现有 `ToolAnalyzer` 并序列化工具状态 |
| `tools/experiment/d2_verify.py` | 六项保护覆盖义务与 UNKNOWN 优先的确定性判断 |
| `tools/experiment/audit_run.py` | 单样本阶段编排、模型计费边界、JSONL 与恢复 |
| `tools/experiment/local_ui.py`、`tools/experiment/local_ui/agent.html`、`agent.js` | 本机受限接口与可视化回看 |
| `docs/vibe/releases/R1/VERIFICATION.md#s4-verification`、`docs/vibe/PROGRESS.md`、`tools/experiment/README.md` | 实际验证、恢复入口和运行命令 |

### Review Focus

1. 目标源码在列表查询与运行之间发生变化时，任务 1／4 的测试须证明运行拒绝而非继续调用模型。
2. 正式快照的 Milvus 结果缺条、错 ID、错分数或激活指针变化时，任务 2 的测试须证明不会回退到 `mvp_`。
3. 函数级片段恰好超出完整模型提示预算时，任务 1／4 的测试须证明拒绝；不能静默截取更多行或宣称全合约结论。
4. 模型已发起但进程中断、HTTP 重放、用户重复点击时，任务 4／5 的测试须证明最多一次请求且旧运行只读。
5. 工具空告警、超时、解析错误或 D2 保护证据不全时，任务 3／4 的测试须证明结果为 `UNKNOWN`／`UNRESOLVED`，usage 缺失为 `null`。

---

#### Task 1：固定开发目标与分析范围

**Files:** Create `tools/experiment/formal_targets.py`、`tools/experiment/tests/test_formal_targets.py`、`docs/vibe/releases/R1/VERIFICATION.md#s4-verification`（随任务逐项增补实际证据）。

**Interfaces:** `list_targets(root: Path) -> list[dict]` 返回四个固定开发 ID 的资格和阻塞理由；`load_target(root: Path, sample_id: str) -> dict` 返回完整源码摘要、分配摘要、项目／事件组、`FULL|FUNCTION` 范围、用于模型的原始行号片段和片段摘要。未知 ID、知识／验证侧、源码变化与跨组关系抛出 `ValueError`。函数级仅允许 `RE-SCRUBD-001` 的 `matchOrderWithReserve`；整份目标按完整提示硬上限筛选。

- [x] **Step 1：写失败测试。** `test_four_registered_targets_and_scope` 断言两份短访问控制为整份、重入 001 为函数级且行号含第 608 行、重入 002 被阻塞；`test_source_hash_and_group_mismatch_fail_closed` 修改临时副本摘要或制造知识同组边，断言拒绝。
- [x] **Step 2：运行红灯。** `PYTHONPATH=tools/experiment python3 -m unittest tools/experiment/tests/test_formal_targets.py -v`，预期新接口不存在或断言失败。
- [x] **Step 3：实现。** 只从固定 intake／assignment／本机源码构建目标；复用 `first_batch.prepare` 与 `s3.audit_lineage`，用配对花括号确定函数范围，保留完整源码与片段双摘要；不读取模型或网络。
- [x] **Step 4：运行绿灯并记录。** 同 Step 2 命令全部通过，将结果写入 `VERIFICATION.md`；检查既有用户改动仍在。

#### Task 2：正式快照与 D1 检索预览

**Files:** Create `tools/experiment/formal_recall.py`, `tools/experiment/tests/test_formal_recall.py`；修改 `tools/experiment/recall.py`、`tools/experiment/tests/test_recall.py`。

**Interfaces:** `preview(root: Path, target: dict, index, encoder, java_runner) -> dict` 返回固定快照／catalog 摘要、同版 384 维 query、共享候选池、`facts` 与 D1 证据包。受限工程目标经 Task 1 校验后调用新内部候选池组装函数；公开研究 `recall_pool(...)` 的“目标必须在正式 manifest 非知识划分”行为保持原样。`RE-SCRUBD-001` 以完整源码的 `matchOrderWithReserve` 第 608 行 `CALL` 为工程检查点；短访问控制目标无同类风险事实时返回显式缺口，不伪造事实。

- [x] **Step 1：写失败测试。** 假快照／假 Milvus 返回四条配对；断言正式 snapshot ID、角色配对、`UNKNOWN` 绑定与无风险事实缺口；错 ID／分数、激活指针改变、词法哈希模型或 `mvp_` 集合均拒绝。
- [x] **Step 2：运行红灯。** `PYTHONPATH=tools/experiment:tools/experiment/tests python3 -m unittest tools/experiment/tests/test_formal_recall.py tools/experiment/tests/test_recall.py -v`；原命令的测试目录导入问题已记入执行裁决。
- [x] **Step 3：实现。** 通过 `snapshots.active_snapshot` 完整校验 `s1b_`、固定 `d1_embed.load_local_encoder` 编码片段、Milvus 同池召回与 Java `RetrievalCli`；只重构 `recall.py` 的候选池组装，不放宽研究入口。
- [x] **Step 4：运行绿灯与回归。** 同 Step 2 命令通过，再运行 Java `RetrievalCliTest`，记录 D1 预览所选／未知证据。

#### Task 3：结构化模型假设与工具 CLI

**Files:** Create `audit-mvp/src/main/java/com/xhl/audit/HypothesisService.java`、`HypothesisCli.java`、`ToolCli.java` 与对应 `HypothesisServiceTest.java`、`HypothesisCliTest.java`、`ToolCliTest.java`；修改 `AuditCli.java`、`SpringAiGateway.java`、`GatewayTest.java`。

**Interfaces:** 新 `--hypotheses` CLI 输入完整源码摘要、`FULL|FUNCTION` 范围、D1 证据包、固定配置并返回版本 2 的 0–3 条假设；严格校验类别、实际行号、证据 ID、无额外字段、截断和 usage。`--tools` CLI 只从本地固定配置执行 `ToolAnalyzer`，输出引擎／状态／位置／用时；旧 `AuditCli` 三字段入口不变。模型网关增加仅供新版调用的严格 schema 配置，测试本地假 HTTP，不接真实 API。

- [x] **Step 1：写失败测试。** 假模型分别返回有效空数组、有效假设、额外字段、虚构行号、错证据 ID、截断和缺失 usage；假工具分别返回告警、空告警、超时和非法 JSON，断言状态独立且不产生安全结论。
- [x] **Step 2：运行红灯。** `mvn -pl audit-mvp -Dtest=HypothesisServiceTest,HypothesisCliTest,ToolCliTest,GatewayTest test`。
- [x] **Step 3：实现。** 新版服务与 CLI 独立于旧 `AuditService`；严格 schema 限制假设数组与字段；工具通过现有 `ProcessRunner` 清理子进程，路径仅来自本机配置。失败记录 `UNRESOLVED`，usage 缺失为 `null`。
- [x] **Step 4：运行绿灯。** 同 Step 2 命令通过，再运行旧 `AuditServiceTest` 与 `AuditCliTest` 保证兼容。

#### Task 4：D2 初版与持久化编排

**Files:** Create `tools/experiment/d2_verify.py`、`tools/experiment/audit_run.py`、`tools/experiment/tests/test_d2_verify.py`、`tools/experiment/tests/test_audit_run.py`。

**Interfaces:** `evaluate(hypothesis: dict, facts: dict, tools: list[dict]) -> dict` 返回六项义务及主张 `SUPPORTED|REFUTED|UNKNOWN`；`RunDependencies` 持有 `index`、`encoder`、`java_retriever`、`model_runner`、`tool_runner` 五个可替换依赖；`run_once(root: Path, sample_id: str, mode: str, dependencies: RunDependencies) -> dict` 串联 Task 1–3，建立 `.local/audit-runs/<runId>/`，写 `plan.json`、`events.jsonl`、`sample.jsonl`、原子 `result.json`；`replay(root: Path, run_id: str) -> dict` 只读。`mode=offline` 的依赖强制由固定夹具构造，`mode=real` 经显式调用且一次最多一个模型请求、零重试。

- [x] **Step 1：写失败测试。** 全义务支持／单项具体反驳／缺任一关键证据／工具失败分别断言 D2 结论；编排测试断言计划绑定双源码摘要、逐事件 fsync、缺失 usage 为 `null`、中断后只读恢复、重复 ID 和篡改产物拒绝、函数提示超限不发请求。
- [x] **Step 2：运行红灯。** `PYTHONPATH=tools/experiment python3 -m unittest tools/experiment/tests/test_d2_verify.py tools/experiment/tests/test_audit_run.py -v`。
- [x] **Step 3：实现。** D2 只根据代码行／事实／工具引用给出确定性义务；运行器在模型调用前写启动事件，失败与 UNKNOWN 单列分母，任何异常不映射为安全。复用 `storage.atomic_json` 与 S1b 的持久化／恢复模式。
- [x] **Step 4：运行绿灯。** 同 Step 2 命令通过，检查 `.local/audit-runs/` 被 Git 忽略且无凭证写入。

#### Task 5：本机页面、受限 API 与可下载报告

**Files:** Modify `tools/experiment/local_ui.py`、`tools/experiment/local_ui/style.css`、`tools/experiment/tests/test_local_ui.py`；Create `tools/experiment/local_ui/agent.html`、`agent.js`。

**Interfaces:** 新 `/agent.html` 调用 `/api/agent/status`、`/api/agent/targets`、`/api/agent/preview?sampleId=...`、`POST /api/agent/runs`（仅 `sampleId`、`mode`）、`GET /api/agent/runs[/<runId>]` 和 `/report`。所有读取零模型调用；写入只接受白名单与精确 JSON，保持 `127.0.0.1`、Host／Origin、请求大小与单写者锁。旧 `/` 和 `/mvp.html` 行为不变。

- [x] **Step 1：写失败测试。** 假运行器记录调用次数；断言页面、状态、预览、历史和下载均不调用模型，离线／真实 POST 分开；跨源、超大体、额外字段、未知样本、并发请求拒绝；页面使用 `textContent` 而非注入 HTML。
- [x] **Step 2：运行红灯。** `PYTHONPATH=tools/experiment python3 -m unittest tools/experiment/tests/test_local_ui.py -v`。
- [x] **Step 3：实现。** 新页面展示范围、快照、D1 候选与 UNKNOWN、模型假设、工具证据、D2 义务、usage、错误和报告位置；真实按钮前展示端点、模型、一次请求及输出上限。
- [x] **Step 4：运行绿灯。** 同 Step 2 命令通过；本机 HTTP 夹具实际请求检查报告文件与页面 API 一致。

#### Task 6：离线整链验收与文档收尾

**Files:** Modify `tools/experiment/README.md`、`docs/vibe/PROJECT.md`、`docs/vibe/PROGRESS.md`、`docs/vibe/releases/R1/VERIFICATION.md#s4-verification`；按实际实现更新 `docs/vibe/TECH_DESIGN.md`。

**Interfaces:** 离线端到端夹具覆盖固定访问控制无 D1 风险事实、重入函数 D1 `UNKNOWN`、有效假设／工具证据／D2 `UNKNOWN`、失败恢复与页面回看；不得借此计算研究指标。

- [x] **Step 1：写并运行整链离线测试。** `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`，覆盖所有 S4-01～S4-08；失败先修复再重跑。
- [x] **Step 2：运行 Java 全套。** `mvn clean verify`；记录测试数、退出码、提交摘要和环境，确认旧入口未退化。
- [x] **Step 3：人工本机验收。** 启动 `python3 tools/experiment/local_ui.py --port 8767`，在 `/agent.html` 做离线演练、回放与 JSONL 下载；只读核对 Attu 正式 `s1b_` 集合与运行报告。真实 API 冒烟仅在使用者页面显式选择时发生，不列为完成离线验收的必需项。
- [x] **Step 4：完成文档和状态。** `VERIFICATION.md` 逐项列 S4-01～S4-08 的实际证据、失败／UNKNOWN 分母及研究限制；更新 `PROGRESS.md`、`PROJECT.md`、README 和成立的当前架构。
- [x] **Step 5：检查并同步。** `git diff --check`、逐文件检查密钥与待提交内容；只提交 R1-S4 完成文件，不包含此前 `DATASET_SELECTION_PROPOSAL.md`、三个用户预先暂存删除或 `.aris/`。先检查并整合 `origin/main` 的新提交，重新验证后按既有授权推送；若验证未完成，不以完成名义同步。

<a id="s5-implementation-plan"></a>

## R1-S5 真实数据与页面对照实施计划

> 执行方式：用户要求直接在主目录推进；保留全部已有未提交改动，不创建工作树。各任务先写失败测试，再实现并核对结果。

**目标：** 固定真实补丁对与独立验证集，离线发布完整的新版知识快照，并从本机页面逐次运行可回放的 D1 对照。

**架构：** 复用 S3 来源登记、S1b 原子快照和 S4 单样本工作台。数据准入与谱系、检索策略选择、单次模型调用和结果汇总分别保持独立；旧快照与旧运行只读保留。

**技术栈：** Python 3 离线工具、Java 21 / Spring AI 2.0.1、固定 BGE 模型、Milvus REST、本机 HTML/JavaScript。

**规格：** [SPEC](SPEC.md#s5-spec)。

### 全局约束与复审重点

- 所有新文档和注释使用简体中文；不上传凭证、不打开锁定测试、不自动调用付费 API。
- 正式数据仅在来源、修复范围、标签和分组均可追溯时准入；不把修复后的整份合约判为安全。
- 重点复审：同一项目跨划分、审计版与修复前版本不一致、候选池变化、UTF-8 字节冒充 token、空模型结果被当作安全、历史回放触发付费请求。

### 任务 1：真实案例准入与隔离

**文件：** 新建 `evidence/intake.json`、`evidence/assignment.json`、`evidence/decisions.json`、`evidence/source-review.json`；修改 `tools/experiment/d1_admission.py`；测试 `tools/experiment/tests/test_d1_admission.py`。

- [ ] 写测试：合并既有已准入清单与新增条目时，项目或近克隆跨 `knowledge/validation` 必须拒绝；许可证据按固定源码 SPDX 核验，不接受空声明。
- [ ] 运行定向测试并确认因新能力缺失而失败。
- [ ] 固定 RabbitHole、JPEG’d、Infinity 的源码、原始裁决与修复版本；记录审计版至修复前版本的对应关系、文件摘要与候选状态。只把通过复核的条目写入准入清单。
- [ ] 实现最小合并准入；输出新谱系与泄漏报告，运行定向测试。

### 任务 2：新版正式知识快照

**文件：** 复用 `tools/experiment/d1_embed.py`、`d1_kb.py`、`snapshots.py`；新增本轮快照收据；测试 `tools/experiment/tests/test_d1_kb.py`。

- [ ] 写失败测试：新补丁对的条件见证不成立、验证案例混入知识、向量数或文档摘要不符时拒绝。
- [ ] 审核知识配对元数据，不支持的防御机理保持待审，不伪装成既有条件。
- [ ] 固定模型离线编码，创建内容寻址快照；本机 Milvus 新集合全量读回后激活，失败继续指向旧集合。
- [ ] 记录快照 ID、集合、文档数、谱系报告及读回结果。

### 任务 3：验证目标与三策略同池检索

**文件：** 修改 `tools/experiment/formal_targets.py`、`formal_recall.py` 及相应测试。

- [ ] 写失败测试：独立验证样本按固定源码／函数行号加载；目标与知识同组、源码变化、过长片段拒绝。
- [ ] 写失败测试：`DENSE`、`FIELD_FILTER`、`D1` 共享一个候选池摘要和知识快照；条件未知不自动升格为适用。
- [ ] 实现可审查的目标注册和策略选择，保持旧工程目标与旧 CLI 行为。

### 任务 4：单次运行、页面和报告

**文件：** 修改 `tools/experiment/audit_run.py`、`local_ui.py`、`local_ui/agent.html`、`local_ui/agent.js` 及其测试。

- [ ] 写失败测试：请求只能传已登记目标、显式模式和白名单策略；每次真实点击最多一次模型请求，历史 GET 零调用。
- [ ] 在计划与逐样本 JSONL 中绑定策略、候选池摘要、快照、源码和模型配置；增加页面策略选择与结果并列回看。
- [ ] 在真实 tokenizer / 标签未审核时明确显示“工程运行，不能报告 D1 提升”。失败与 UNKNOWN 分母、缺失 usage 原样展示。

### 任务 5：验证与同步

- [ ] 运行根 Maven 和 Python 全套离线测试；单列本机 Milvus 与页面的只读／离线冒烟。
- [ ] 更新 `VERIFICATION.md`、`docs/vibe/PROGRESS.md` 和重放命令；核对新增数据、凭证与既有用户改动。
- [ ] 仅提交本轮通过验证的文件；按项目约定同步 `origin/main`，不得把工程链路写成 D1 科研提升。

<a id="s6-implementation-plan"></a>

## R1-S6 实施步骤

1. 对照两个活动指针和 Milvus 集合清单，删除无引用的旧集合并复核剩余列表。
2. 调研同行的样本规模和计数单位，核对本项目 D1 评估缺口；写出按项目、事件和近克隆隔离的扩充与标注方案。
3. 先为批量计划、逐项持久化、续跑防重复、指标空值和页面接口写离线测试；再实现批量编排与 UI。
4. 通过本机正式快照做三目标、三策略离线 HTTP 冒烟，记录逐样本路径和失败/未知分母；运行 Java 与 Python 全量验证。
5. 更新进度及验证记录。未达到研究真值和 token 公平门槛时不启动付费批量实验，不扩充未经审查的正式知识片段。

<a id="s8-auto-experiment-plan"></a>

## R1-S8 自动标注知识与批量实验实施方案

目标：把已有 300 组 AutoMESC 前后片段作为可追溯的自动标注知识层构建 S1b 快照，扩展 D1 条件与软配对检索，并在本机页面运行公开数据集三策略批量审计，输出逐样本记录与有定义的指标。

### 数据身份

新快照的 `review_status=AUTO_LABELED`、`label_rule` 与来源提交保留在清单中；不改写旧 `REVIEWED` 语义。每组前后向量来自已经固定的本地 BGE 权重和原始候选收据。显式保护特征由确定性规则提取；仅有改动差异但无法识别保护的组可参加软配对，不能声称补丁已证实安全。新的 `s1b_` 集合必须 600 条完整读回后才能切换活动指针，旧集合保留。

### 检索与评估

正式与自动标注候选池采用不同 schema。三策略共用同一 Milvus 召回池和上下文限制；D1 优先显式条件配对，缺失时使用同补丁对两侧的向量相关度与差异重排，并在证据中标记软配对。公开 SmartBugs 的漏洞头标签与本机 `safe_contracts` 的安全标签作为**数据集标签**，与独立人工裁决分开。审计 TP／FP／FN 等只从实际模型返回的结构化假设计算；错误、超时、无结论保持 UNKNOWN，不记安全。没有目标—知识适用性标注时，检索 Hit@K 只能作为类别代理指标，不冒充案例相关性真值。

### 页面与验收

页面增加自动标注快照的独立批量实验区域，显式选择目标、策略与离线／真实模式；后台逐项持久化，支持恢复与 JSONL／CSV 导出。真实模型只在用户点击后启动，不自动重试。按项目现有 `mvn clean verify`、Python 离线单元测试和本机 Milvus 全量读回验收；至少运行一轮可重放的离线批次，真实模型仅在固定计划与可用凭证下运行。指标报告同时展示失败、UNKNOWN 和有标签分母。

### 实施顺序

1. 用先失败后通过的测试实现自动差异特征、自动标注清单、600 向量快照和激活读回。
2. 用 Java／Python 测试扩展修饰器绑定、同对补齐与 D1 软配对，并检查三策略同池。
3. 实现带数据集标签的目标登记、逐项模型调用、断点续跑、真实 TP／FP／FN 与 token／耗时聚合。
4. 接入 UI 选择、进度、指标和 JSONL／CSV 下载，执行完整离线验证与本机实际冒烟。

<a id="s8-implementation-plan"></a>

## R1-S8 批量准入与正式对照实施计划

> 执行依据：沿用 `vibe-workflow` 的项目事实源，在当前主目录逐项实施；每项用离线测试和可重放记录核对。原有未提交修改不纳入本阶段提交。

**目标：**从现有待审语料中逐案核实可用的真实漏洞—修复对，建立扩大后的正式知识快照，并使页面对独立验证目标批量生成审计报告和有明确分母的策略指标。

**架构：**本地原件和谱系清单仍是事实源；Milvus 仅保存经审核快照的可重建向量索引。待审集合不能直接改名或复制到正式集合。批量编排从已审核目标登记读取样本，所有策略共用一个快照和候选池。

**技术：**Python 标准库、固定本地 BGE 模型、Milvus REST、Java D1 检索、现有本机 HTTP 页面。

**依据：**[S6 数据与实验设计](research/S6_RESEARCH_DESIGN.md)、[S7 候选语料核验](VERIFICATION.md#s7-verification)、[S3 正式准入器](../../../../tools/experiment/d1_kb.py)。

### 全局约束

- 仅研究访问控制和重入；不把字节码、合成注入、模型生成修复或普通代码重构冒充真实补丁对。
- 原始源码、报告、补丁、标签和知识文档继承项目、事件、补丁对与近克隆组；验证和测试项目不得进入知识侧。
- 待审、失败、超时和解析错误均不得算作安全；未知标签不参与已知真值分母。缺失 usage 保留 `null`。
- 自动化测试完全离线；真实模型只在页面显式选择后调用。运行前固定策略、目标、模型、快照和请求数。
- 本轮不打开锁定测试集调参；真实效果优劣以完整提示 token 公平和独立人工适用性标签为前提。

### 实施与验收

#### 任务一：逐案准入清单

- [x] 为 300 组 AutoMESC 改动及 142 条 FORGE 资料生成可重放的逐项审核队列，记录原件身份、缺失项与可核对链接；任何缺报告、完整修复版本或独立判断的项保持 `PENDING`。
- [ ] 补采公开的真实补丁对，逐案复核修复前后源码和漏洞机制。修复类别与实际代码不符的条目必须拒绝，不能按来源标签自动转正。
- [ ] 建立项目、漏洞事件、补丁、完全重复和近克隆隔离报告；合格知识与独立验证分别计数，不能以向量条数代替案例数。

#### 任务二：正式知识快照

- [ ] 对每个合格知识事件登记报告、原版和实际补丁，并标注适用条件、支持与反证角色。
- [ ] 用固定本地 BGE 编码，构建内容寻址快照；Milvus 全量读回正文、向量和元数据后原子切换活动指针，失败时保留旧指针。
- [ ] 实测三种策略同池检索，检查新增案例能否被 D1 选中；若条件事实缺失，修正事实提取或将该目标保持 `UNKNOWN`。

#### 任务三：批量目标与页面

- [x] 移除当前三目标硬编码上限，批量选择仅来自经审核、与知识侧隔离的目标登记；防止前端提交未知或锁定样本。
- [ ] 保留逐项 JSONL、断点保护和历史只读回放；页面显示快照、目标数、策略、模型及运行上下界。
- [ ] 页面与报告同时展示每策略完成、失败、未知、证据入选和可得 usage；可核真值与完整 token 公平具备时再启用 Recall@K、nDCG、误选率及检测指标，否则显示缺失原因而非零。

#### 任务四：最终验证

- [x] 运行 `mvn clean verify`、Python 全量离线测试和 JavaScript 语法检查。
- [x] 用本机 Milvus 和页面实际完成一轮独立验证目标 × 三策略离线批量运行，重放逐样本报告并核对指标分母与同池证据；真实模型对照仍待正式知识与目标扩充。
- [ ] 更新 `VERIFICATION.md` 和 `PROGRESS.md`，报告正式准入数量、排除原因、泄漏结果、实际审计输出和 D1 保留／收窄／暂停判断；未满足科研门禁时不得声称 D1 提升。

### 当前事实

开始时正式知识为 3 个事件／6 条向量，独立验证为 3 个事件；待审集合为 300 组 AutoMESC 片段和 142 条 FORGE 资料／742 条向量。当前批量计划最多允许 3 个目标，效果指标默认 `null`。这些数字是本计划的起点，不是验收目标已达成的证明。

<a id="s8-nomic-implementation-plan"></a>

## Nomic 嵌入对照与结构化输出修复实施计划

2026-10-09。需求状态：用户已明确授权，FROZEN；无待确认问题。在当前主目录开发、保留已有改动，完成验证后按 AGENTS 同步远程。

### 验收目标

1. 复用现有 AutoMESC 300 组、600 条原始文本，以本机 Ollama `nomic-embed-text:latest` 生成 768 维向量；模型摘要固定，文档和查询分别使用任务前缀。新建独立快照目录和 `s1b_nomic_` 集合，完整读回才能激活；BGE 与历史报告保留。
2. 相同的 SmartBugs 49 个漏洞目标和 4 个安全对照、三策略、同池候选、同一 `deepseek-v4-flash` 端点，运行 159 个真实审计单元并保存 JSONL／CSV／指标；增加页面嵌入选择。
3. 清理输出围栏与外围文本、接受附加字段、归一化行号与声明名称；空证据视为无引用。重复键、越界位置、不存在的声明或证据仍为失败／UNKNOWN。保留失败原文。
4. HTTP 429 和连接中断最多退避一次，SDK 重试关闭；每单元最多两次 HTTP 尝试，记录实际次数。解析失败不重新调用模型，支持原文离线重放并另存派生结果。
5. `mvn clean verify`、Python 全量离线测试与页面脚本检查通过；横向报告区分原始失败和解析重放，包含共同有效分母及版本混杂说明。

### 实施次序

- 编码器、向量断点、模型身份与截取回执；独立快照和动态维度检索。
- 解析与网关回归测试；修复完整合约误限制为单函数、旧无名回退函数错误名称，以及构造函数大小写别名问题。
- 离线 53 × 3 验证；冻结运行 JAR 后执行真实批量，过程中不清理或替换 JAR。
- 真实批量结束后，以最终解析器离线重放已保存失败原文；原始 JSONL 不修改。
- 导出两模型完整表与所有策略共同有效表，核对知识／测试源码摘要及候选池一致性；更新验收与进度，检查凭证后同步。

### 实测窗口修正

用户期望比较 512 与 8192 token，但本机模型摘要对应元数据有效窗口为 2048，显式 `num_ctx=8192` 下长输入仍被拒绝。故交付按 **BGE 512 对 Nomic 本机有效 2048** 标注；保留期望配置 8192 和真实截取回执，不能据此报告 8192 的科研结论。仅遇到明确窗口拒绝时按字符前缀逐步搜索可接收范围，完整知识文本仍保存，查询采用相同规则。

本轮自动标签、单次重复和上下文字节预算的研究限制沿用已有说明。解析器升级也使旧 BGE 与新 Nomic 的全量结果存在版本差异，输出可比较的描述性结果，不归因于嵌入窗口单一因素。D2 不扩展。

<a id="s9-implementation-plan"></a>

## R1-S9 实施计划与技术边界

当前阶段：Testing 已完成；状态：READY_TO_SHIP / ACTIVE；工程验证 VERIFIED，正式发布授权 NOT_REQUESTED。需求基线见 [SPEC](SPEC.md#s9-spec)，[评审](REVIEW.md#s9-review)和[验收](VERIFICATION.md#s9-verification)保存完成证据。开发基点：`0b40b4b`；本轮完成提交以 Git 历史为准，开始时无关改动保留。

复用 `BenchmarkRuntime` 的 Nomic/BGE 查询与 Java D1、`audit_run.model_runner/tool_runner` 的受控子进程。新增工作台编排负责目标输入、预览冻结、六阶段事件和内容摘要校验。HTTP 使用现有本机服务与全局运行锁；不接受可执行路径、模型端点或集合名。前端使用独立静态资源，源码和模型输出只作为文本。

1. 输入与编排：解析受限语法树，绑定源码/函数/行范围；预置与粘贴统一进入固定快照；计划绑定源码、候选池、上下文、模式与供应商。默认离线不会运行模型或真实工具。
2. D2：逐项核查六类义务；`verdict` 针对漏洞，`protectionVerdict` 针对保护；证据不足保持 UNKNOWN。此纯函数任务与新前端可并行，其他公共接口串行整合。
3. 前端：预览后才运行，显示六阶段与过程证据，下载和重放报告，链接批量台。
4. 集成：单样本与批量共用 D2；更新旧入口聚合语义，历史 schema=1 不重写。
5. Review：独立审查规格与代码，抽查安全与公用函数；局部测试通过后才进入系统验收。
6. Testing：根 Maven、Python、脚本检查及真实 Chromium；固定本机 Nomic 检索冒烟零付费请求。证据在 `.evidence/R1-S9/`，不把工程演练写成科研结论。
7. 依项目约定检查差异和凭证，完成后提交及同步 origin/main；外部正式部署/发布不在本次范围。

任务契约：目标为 SPEC 中的七项功能与输入门禁；测试缝为注入检索、模型、工具适配器及临时目录 HTTP。**REQUIRED SUB-SKILL:** Use superpowers:test-driven-development。初轮可用目录未列出 superpowers，采用原生失败用例→实现→回归、方案比较、依赖顺序与代理契约；复审修复阶段发现缓存中的 TDD 与 verification-before-completion 文件并完整读取执行。独立规格、代码、消肿和安全评审记录在 REVIEW。配置差异反复出现时暂停补丁，按 investigate 完成根因调查与恢复。

持久化仅新增 `.local/audit-workbench-runs/`，每个运行保存 plan、target、preview、events、result 与 sample.jsonl；摘要覆盖目标、检索、计划和结果。读取方为 HTTP、页面和离线报告；运行中状态来自内存活动编号与事件，服务重启后未封口运行标为 INTERRUPTED，不自动补发模型请求。
