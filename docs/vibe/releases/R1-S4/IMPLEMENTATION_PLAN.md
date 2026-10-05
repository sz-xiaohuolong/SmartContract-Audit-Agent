# R1-S4 单样本审计工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. User requires direct work in the current main directory; do not create a worktree or delegate shared-file edits.

**Goal:** 让已登记开发源码在本机完成正式 Milvus → D1 → 结构化模型假设 → 工具证据 → D2 → 可回放报告 → 页面的一次审计工程链路。

**Architecture:** Python 负责谱系、快照、编排、持久化与本机 HTTP；Java CLI 负责现有 D1、Spring AI 结构化模型阶段和工具解析。正式 `s1b_` 集合只读，Python／Java 以版本化 JSON 通信；离线夹具替代真实模型、Milvus 和工具。

**Tech Stack:** Java 21、Spring Boot 4.1.1、Spring AI 2.0.1、Python 3 标准库、固定 BGE 本地模型、Milvus REST、本机静态 HTML／JavaScript。

**Spec:** [SPEC](SPEC.md)、[PROPOSED_DESIGN](PROPOSED_DESIGN.md)、[追加决定](CHANGE_PROPOSAL.md)。

## Global Constraints

- 当前主目录开发，保留现有未提交修改；所有新增说明和代码注释使用简体中文。
- 默认测试完全离线、确定性；真实模型运行仅由使用者在页面明确选择，一次点击最多一次请求、2048 输出 token、零自动重试。
- 不改变已激活正式知识集合，不将旧 `mvp_` 当正式库；不打开锁定测试，不把工程试跑当 D1／D2 科研效果。
- 失败、超时、解析错误与工具缺失不能映射为安全；usage 缺失保留 `null`。
- 每个完整可验收小版本通过相应测试后，核查凭证、暂存区和远程变更，仅提交本版本文件并同步 `origin/main`；不连带提交已有用户改动。

## File Map

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
| `docs/vibe/releases/R1-S4/VERIFICATION.md`、`docs/vibe/PROGRESS.md`、`tools/experiment/README.md` | 实际验证、恢复入口和运行命令 |

## Review Focus

1. 目标源码在列表查询与运行之间发生变化时，任务 1／4 的测试须证明运行拒绝而非继续调用模型。
2. 正式快照的 Milvus 结果缺条、错 ID、错分数或激活指针变化时，任务 2 的测试须证明不会回退到 `mvp_`。
3. 函数级片段恰好超出完整模型提示预算时，任务 1／4 的测试须证明拒绝；不能静默截取更多行或宣称全合约结论。
4. 模型已发起但进程中断、HTTP 重放、用户重复点击时，任务 4／5 的测试须证明最多一次请求且旧运行只读。
5. 工具空告警、超时、解析错误或 D2 保护证据不全时，任务 3／4 的测试须证明结果为 `UNKNOWN`／`UNRESOLVED`，usage 缺失为 `null`。

---

### Task 1：固定开发目标与分析范围

**Files:** Create `tools/experiment/formal_targets.py`、`tools/experiment/tests/test_formal_targets.py`、`docs/vibe/releases/R1-S4/VERIFICATION.md`（随任务逐项增补实际证据）。

**Interfaces:** `list_targets(root: Path) -> list[dict]` 返回四个固定开发 ID 的资格和阻塞理由；`load_target(root: Path, sample_id: str) -> dict` 返回完整源码摘要、分配摘要、项目／事件组、`FULL|FUNCTION` 范围、用于模型的原始行号片段和片段摘要。未知 ID、知识／验证侧、源码变化与跨组关系抛出 `ValueError`。函数级仅允许 `RE-SCRUBD-001` 的 `matchOrderWithReserve`；整份目标按完整提示硬上限筛选。

- [x] **Step 1：写失败测试。** `test_four_registered_targets_and_scope` 断言两份短访问控制为整份、重入 001 为函数级且行号含第 608 行、重入 002 被阻塞；`test_source_hash_and_group_mismatch_fail_closed` 修改临时副本摘要或制造知识同组边，断言拒绝。
- [x] **Step 2：运行红灯。** `PYTHONPATH=tools/experiment python3 -m unittest tools/experiment/tests/test_formal_targets.py -v`，预期新接口不存在或断言失败。
- [x] **Step 3：实现。** 只从固定 intake／assignment／本机源码构建目标；复用 `first_batch.prepare` 与 `s3.audit_lineage`，用配对花括号确定函数范围，保留完整源码与片段双摘要；不读取模型或网络。
- [x] **Step 4：运行绿灯并记录。** 同 Step 2 命令全部通过，将结果写入 `VERIFICATION.md`；检查既有用户改动仍在。

### Task 2：正式快照与 D1 检索预览

**Files:** Create `tools/experiment/formal_recall.py`, `tools/experiment/tests/test_formal_recall.py`；修改 `tools/experiment/recall.py`、`tools/experiment/tests/test_recall.py`。

**Interfaces:** `preview(root: Path, target: dict, index, encoder, java_runner) -> dict` 返回固定快照／catalog 摘要、同版 384 维 query、共享候选池、`facts` 与 D1 证据包。受限工程目标经 Task 1 校验后调用新内部候选池组装函数；公开研究 `recall_pool(...)` 的“目标必须在正式 manifest 非知识划分”行为保持原样。`RE-SCRUBD-001` 以完整源码的 `matchOrderWithReserve` 第 608 行 `CALL` 为工程检查点；短访问控制目标无同类风险事实时返回显式缺口，不伪造事实。

- [x] **Step 1：写失败测试。** 假快照／假 Milvus 返回四条配对；断言正式 snapshot ID、角色配对、`UNKNOWN` 绑定与无风险事实缺口；错 ID／分数、激活指针改变、词法哈希模型或 `mvp_` 集合均拒绝。
- [x] **Step 2：运行红灯。** `PYTHONPATH=tools/experiment:tools/experiment/tests python3 -m unittest tools/experiment/tests/test_formal_recall.py tools/experiment/tests/test_recall.py -v`；原命令的测试目录导入问题已记入执行裁决。
- [x] **Step 3：实现。** 通过 `snapshots.active_snapshot` 完整校验 `s1b_`、固定 `d1_embed.load_local_encoder` 编码片段、Milvus 同池召回与 Java `RetrievalCli`；只重构 `recall.py` 的候选池组装，不放宽研究入口。
- [x] **Step 4：运行绿灯与回归。** 同 Step 2 命令通过，再运行 Java `RetrievalCliTest`，记录 D1 预览所选／未知证据。

### Task 3：结构化模型假设与工具 CLI

**Files:** Create `audit-mvp/src/main/java/com/xhl/audit/HypothesisService.java`、`HypothesisCli.java`、`ToolCli.java` 与对应 `HypothesisServiceTest.java`、`HypothesisCliTest.java`、`ToolCliTest.java`；修改 `AuditCli.java`、`SpringAiGateway.java`、`GatewayTest.java`。

**Interfaces:** 新 `--hypotheses` CLI 输入完整源码摘要、`FULL|FUNCTION` 范围、D1 证据包、固定配置并返回版本 2 的 0–3 条假设；严格校验类别、实际行号、证据 ID、无额外字段、截断和 usage。`--tools` CLI 只从本地固定配置执行 `ToolAnalyzer`，输出引擎／状态／位置／用时；旧 `AuditCli` 三字段入口不变。模型网关增加仅供新版调用的严格 schema 配置，测试本地假 HTTP，不接真实 API。

- [x] **Step 1：写失败测试。** 假模型分别返回有效空数组、有效假设、额外字段、虚构行号、错证据 ID、截断和缺失 usage；假工具分别返回告警、空告警、超时和非法 JSON，断言状态独立且不产生安全结论。
- [x] **Step 2：运行红灯。** `mvn -pl audit-mvp -Dtest=HypothesisServiceTest,HypothesisCliTest,ToolCliTest,GatewayTest test`。
- [x] **Step 3：实现。** 新版服务与 CLI 独立于旧 `AuditService`；严格 schema 限制假设数组与字段；工具通过现有 `ProcessRunner` 清理子进程，路径仅来自本机配置。失败记录 `UNRESOLVED`，usage 缺失为 `null`。
- [x] **Step 4：运行绿灯。** 同 Step 2 命令通过，再运行旧 `AuditServiceTest` 与 `AuditCliTest` 保证兼容。

### Task 4：D2 初版与持久化编排

**Files:** Create `tools/experiment/d2_verify.py`、`tools/experiment/audit_run.py`、`tools/experiment/tests/test_d2_verify.py`、`tools/experiment/tests/test_audit_run.py`。

**Interfaces:** `evaluate(hypothesis: dict, facts: dict, tools: list[dict]) -> dict` 返回六项义务及主张 `SUPPORTED|REFUTED|UNKNOWN`；`RunDependencies` 持有 `index`、`encoder`、`java_retriever`、`model_runner`、`tool_runner` 五个可替换依赖；`run_once(root: Path, sample_id: str, mode: str, dependencies: RunDependencies) -> dict` 串联 Task 1–3，建立 `.local/audit-runs/<runId>/`，写 `plan.json`、`events.jsonl`、`sample.jsonl`、原子 `result.json`；`replay(root: Path, run_id: str) -> dict` 只读。`mode=offline` 的依赖强制由固定夹具构造，`mode=real` 经显式调用且一次最多一个模型请求、零重试。

- [x] **Step 1：写失败测试。** 全义务支持／单项具体反驳／缺任一关键证据／工具失败分别断言 D2 结论；编排测试断言计划绑定双源码摘要、逐事件 fsync、缺失 usage 为 `null`、中断后只读恢复、重复 ID 和篡改产物拒绝、函数提示超限不发请求。
- [x] **Step 2：运行红灯。** `PYTHONPATH=tools/experiment python3 -m unittest tools/experiment/tests/test_d2_verify.py tools/experiment/tests/test_audit_run.py -v`。
- [x] **Step 3：实现。** D2 只根据代码行／事实／工具引用给出确定性义务；运行器在模型调用前写启动事件，失败与 UNKNOWN 单列分母，任何异常不映射为安全。复用 `storage.atomic_json` 与 S1b 的持久化／恢复模式。
- [x] **Step 4：运行绿灯。** 同 Step 2 命令通过，检查 `.local/audit-runs/` 被 Git 忽略且无凭证写入。

### Task 5：本机页面、受限 API 与可下载报告

**Files:** Modify `tools/experiment/local_ui.py`、`tools/experiment/local_ui/style.css`、`tools/experiment/tests/test_local_ui.py`；Create `tools/experiment/local_ui/agent.html`、`agent.js`。

**Interfaces:** 新 `/agent.html` 调用 `/api/agent/status`、`/api/agent/targets`、`/api/agent/preview?sampleId=...`、`POST /api/agent/runs`（仅 `sampleId`、`mode`）、`GET /api/agent/runs[/<runId>]` 和 `/report`。所有读取零模型调用；写入只接受白名单与精确 JSON，保持 `127.0.0.1`、Host／Origin、请求大小与单写者锁。旧 `/` 和 `/mvp.html` 行为不变。

- [x] **Step 1：写失败测试。** 假运行器记录调用次数；断言页面、状态、预览、历史和下载均不调用模型，离线／真实 POST 分开；跨源、超大体、额外字段、未知样本、并发请求拒绝；页面使用 `textContent` 而非注入 HTML。
- [x] **Step 2：运行红灯。** `PYTHONPATH=tools/experiment python3 -m unittest tools/experiment/tests/test_local_ui.py -v`。
- [x] **Step 3：实现。** 新页面展示范围、快照、D1 候选与 UNKNOWN、模型假设、工具证据、D2 义务、usage、错误和报告位置；真实按钮前展示端点、模型、一次请求及输出上限。
- [x] **Step 4：运行绿灯。** 同 Step 2 命令通过；本机 HTTP 夹具实际请求检查报告文件与页面 API 一致。

### Task 6：离线整链验收与文档收尾

**Files:** Modify `tools/experiment/README.md`、`docs/vibe/PROJECT.md`、`docs/vibe/PROGRESS.md`、`docs/vibe/releases/R1-S4/VERIFICATION.md`；按实际实现更新 `docs/vibe/TECH_DESIGN.md`。

**Interfaces:** 离线端到端夹具覆盖固定访问控制无 D1 风险事实、重入函数 D1 `UNKNOWN`、有效假设／工具证据／D2 `UNKNOWN`、失败恢复与页面回看；不得借此计算研究指标。

- [x] **Step 1：写并运行整链离线测试。** `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`，覆盖所有 S4-01～S4-08；失败先修复再重跑。
- [x] **Step 2：运行 Java 全套。** `mvn clean verify`；记录测试数、退出码、提交摘要和环境，确认旧入口未退化。
- [x] **Step 3：人工本机验收。** 启动 `python3 tools/experiment/local_ui.py --port 8767`，在 `/agent.html` 做离线演练、回放与 JSONL 下载；只读核对 Attu 正式 `s1b_` 集合与运行报告。真实 API 冒烟仅在使用者页面显式选择时发生，不列为完成离线验收的必需项。
- [x] **Step 4：完成文档和状态。** `VERIFICATION.md` 逐项列 S4-01～S4-08 的实际证据、失败／UNKNOWN 分母及研究限制；更新 `PROGRESS.md`、`PROJECT.md`、README 和成立的当前架构。
- [x] **Step 5：检查并同步。** `git diff --check`、逐文件检查密钥与待提交内容；只提交 R1-S4 完成文件，不包含此前 `DATASET_SELECTION_PROPOSAL.md`、三个用户预先暂存删除或 `.aris/`。先检查并整合 `origin/main` 的新提交，重新验证后按既有授权推送；若验证未完成，不以完成名义同步。
