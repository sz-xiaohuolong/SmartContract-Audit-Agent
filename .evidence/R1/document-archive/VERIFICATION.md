# R1 历史验证归档

整理日期：2026-10-10。本文按原文来源合并历史记录，仅调整标题层级与路径。各章节的状态和“当前”均指原记录时点；归档不追加整体冻结、验收或发布结论。

| 原切片／记录 | 归档章节 |
|---|---|
| R1-S0 / `VERIFICATION.md` | [VERIFICATION.md](#s0-verification) |
| R1-S1 / `VERIFICATION.md` | [VERIFICATION.md](#s1-verification) |
| R1-S2 / `VERIFICATION.md` | [VERIFICATION.md](#s2-verification) |
| R1-S3 / `VERIFICATION.md` | [VERIFICATION.md](#s3-verification) |
| R1-S4 / `VERIFICATION.md` | [VERIFICATION.md](#s4-verification) |
| R1-S5 / `VERIFICATION.md` | [VERIFICATION.md](#s5-verification) |
| R1-S6 / `VERIFICATION.md` | [VERIFICATION.md](#s6-verification) |
| R1-S7 / `VERIFICATION.md` | [VERIFICATION.md](#s7-verification) |
| R1-S8 / `AUTO_EXPERIMENT_VERIFICATION.md` | [AUTO_EXPERIMENT_VERIFICATION.md](#s8-auto-experiment-verification) |
| R1-S8 / `NOMIC_VERIFICATION.md` | [NOMIC_VERIFICATION.md](#s8-nomic-verification) |
| R1-S8 / `VERIFICATION.md` | [VERIFICATION.md](#s8-verification) |
| R1-S9 / `VERIFICATION.md` | [VERIFICATION.md](#s9-verification) |

<a id="s0-verification"></a>

## S0 验证记录

日期：2026-09-19；范围：隔离工作树 `codex/s0-provider` 的新 `audit-mvp` 模块。
本地软件验证通过；真实供应商与工具环境尚未验收。代码未提交、合并或发布。

### 最新证据

- `mvn clean verify`：退出码 0，19 项测试、0 失败、0 错误、0 跳过；可执行 JAR 成功打包。见 [构建日志](evidence/S0/maven-clean-verify.log)与[测试摘要](evidence/S0/test-summary.json)。
- `java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help`：退出码 0，无凭证显示中文帮助，无模型请求。
- 打包检查：应用文件 18 个；未包含旧 application-coding 配置、测试集或知识库路径。
- `git diff --check`：通过；原 `src/` 无修改；原工作区 `.gitignore` 修改保持原样。

### 需求对应

| 需求 | 已验证行为 | 证据及边界 |
| --- | --- | --- |
| S0-01 | Boot 4.1.1、Spring AI 2.0.1 可干净构建 | 新模块构建通过；旧模块未运行 |
| S0-02 | 默认/显式供应商、不同请求路径与 model、Bearer 凭证、配置校验 | GatewayTest 的本地 HTTP 集成 |
| S0-03 | 原文及 usage 返回、缺失 null、真实零保留；错误不转安全 | GatewayTest、AuditServiceTest、CliIntegrationTest |
| S0-04 | 显式参数调用与 JSON 输出、失败非零退出 | AuditCliTest、CliIntegrationTest |
| S0-05 | 持续输出不绕过超时，stdout/stderr 分开限量，非零/启动错误分开，观察后代清理 | ProcessRunnerTest；非沙箱，见限制 |
| S0-05 | Slither/Mythril 严格结果结构、超时和解析错误分开、可执行路径可配置 | ToolAnalyzerTest；实际工具运行尚未验收 |
| S0-06 | 默认测试不调用真实外部服务；401/500 不重试 | 6 个测试类，本地服务器真实经过 Spring AI 与 SDK |
| S0-07 | sourceHash、status、结论、usage、时间输出；错误脱敏 | AuditServiceTest、CliIntegrationTest |

### 失败与修复记录

1. 测试先于初始实现运行，缺类型编译失败后补齐代码。
2. 缺失 usage 被 Spring AI `EmptyUsage` 表示为零：回归失败后修正为 null；真实零值单独验证。
3. 独立审查发现 Slither 0.11.3 默认有发现退出 255、无发现省略 detectors：加入 `--fail-none`，兼容有 results 对象但省略 detectors，仍拒绝缺失 results。
4. 每次模型调用新建 HTTP 客户端无释放：改为显式持有 SDK 客户端，模型复用其同步/异步视图，finally 关闭。
5. 父进程正常退出后遗留已观察子进程：Java 夹具复现失败，增加运行期间追踪及退出后清理，回归通过。

### 审查与限制

独立复审已通过，未发现新的重要阻塞问题；复审只读核对源码和现有测试报告，最终构建由主 Agent 执行。独立审查者已实际核对本机 Slither 0.11.3 源码及 Mythril report.py 成功 JSON 格式，并发现以上工具、资源和进程问题；不是仅根据接口名称推断。

- 清理仅覆盖父进程及运行期间观察到的后代。瞬间 fork 后脱离的进程可能逃过 Java 轮询；`cleanedUp` 不表示操作系统进程组已彻底清空。严格隔离应在后续工具部署使用容器或进程组监管。
- 没有发起真实火山模型请求；账户授权、模型名称、配额、延迟均待联调。示例不能当作可用性证明。
- 工具测试使用 JSON / Java 进程夹具，没有宣称跑通真实 Solidity 编译、Slither/Mythril 全链路。多文件项目及编译依赖尚未管理。
- 旧 M6 代码和旧实验的问题仍然存在，未纳入默认构建。D1/D2 与正式实验尚未实现。
- 输出记录配置的模型标识，不证明服务端实际模型版本；服务端版本追踪将在实验记录切片补充。
- S0 CLI 不编排 RAG/工具。它用于先把错误状态、供应商与执行契约稳定下来。

<a id="s1-verification"></a>

## S1a 验证记录

日期：2026-09-20。S1a 本地验收通过；S1b 尚未实现；没有研究性能结果。

- Python 测试：`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`，7 项通过。见 [日志](evidence/S1/unittest.log)。初次缺模块红测后实现，宏平均问题另有失败回归后修复。
- Maven 回归：`mvn clean verify`，19 项通过，无失败或跳过；见 [日志](evidence/S0/maven-clean-verify.log)。Python 测试需要单独执行，不声称 Maven 包含它们。
- 实际执行 inventory：400 个样本，7 组完全重复，共 14 个成员。见 [待审核清单](evidence/S1/legacy-inventory.json)。所有 labels / split / project_group 保留 null，未改原文件。
- 独立审查：只读审查并独立运行初始 6 项测试；指出 macro_f1 忽略未定义类别会改变分母。已添加“部分类别无定义”回归，先失败后通过。
- 修正后的 macro_f1 对预定义类别整体计算，任一类别无定义则整体 null；条件平均单独命名 macro_f1_defined_only，不能混用作跨方法主指标。

### 限制

字节重复不是近似克隆或项目级治理。清单不构成正式划分；没有把未经审核的目录标签用于计分。S0 自然语言类型尚未映射到规范类型，未实现实例级定位匹配、知识快照激活、阶段日志、checkpoint/resume/replay 或正式实验运行器。这些仍属于 S1b。

### S1b 本地验收（2026-09-21）

范围：本轮已授权的知识快照、隔离检查、持久记录与恢复工程行为。Verification Status：`VERIFIED`（离线工程范围）；Shipping Authorization：`NOT_REQUESTED`。不代表真实实验或研究数据已验收。

环境：主目录 `/Users/daiyifei/Documents/code/SmartContract-agent`；分支 `main`；基点 `66161d5b74a6df980425f37c913e63591d246d2a`，未提交。Python 3.14.7，Corretto Java 21.0.8。代码版本绑定见 [S1b 产物摘要](evidence/S1/s1b-artifact-hashes.json)。

| 验收行为 | 验证证据 | 结果 |
|---|---|---|
| 逐个样本 START/RESULT 持久化、自动跳过已有结果 | `test_restart_skips_completed_and_replay_is_read_only`、CLI run/resume 子进程计数 | 通过 |
| 调用中断或 RESULT 落盘失败后不自动重复调用 | `test_interrupted_call_is_unresolved_and_only_unstarted_is_called`、`test_result_write_interruption_does_not_repeat_paid_call` | 通过；不确定项需显式 retry-id |
| 尾部残行可恢复，完整行损坏与重复事件拒绝 | `test_partial_tail_recovered_but_replay_does_not_truncate`、`test_full_line_corruption_and_duplicate_event_rejected` | 通过 |
| 单写者、落盘失败时不发起调用 | `test_concurrent_writer_rejected`、`test_fsync_failure_before_start_prevents_external_call` | 通过 |
| 源码/配置/产物/类型映射/知识快照绑定 | binding、source drift、bound snapshot、冻结 JAR/配置测试 | 通过 |
| Replay 只读、失败不能当安全、usage 缺失为 null | replay、failed negative、unknown type、usage 回归及原 S1a 测试 | 通过 |
| 完整知识快照构建与原子发布/激活 | 构建中断、摘要篡改、维度/非有限向量、旧指针保留测试 | 通过 |
| Milvus 半集合不能激活，全部分页读回核对 | 缺项、错误向量、重复 ID、多页末项篡改测试 | 离线客户端契约通过；未连接真实 Milvus |
| 测试与检索库同组隔离 | 字节/项目/克隆跨划分，缺审核来源，知识文档引用测试样本拒绝 | 通过；不替代人工谱系审核 |

实际执行：

- `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`：**35 项通过，0 失败**；[完整日志](evidence/S1/s1b-unittest.log)。其中原 S1a 7 项保留。
- `mvn clean verify`：**19 项通过，0 失败/错误/跳过，BUILD SUCCESS**；[完整日志](evidence/S1/s1b-maven-clean-verify.log)。
- Java CLI 帮助与 S1b CLI 帮助：退出码均为 0；[Java](evidence/S1/s1b-java-help.log)、[S1b](evidence/S1/s1b-cli-help.log)。
- `git diff --check` 及本轮未跟踪文本文件的逐文件空白检查：通过；[检查摘要](evidence/S1/s1b-workspace-check.json)。
- 按 `requesting-code-review` 完成只读独立复审；初次 30 项、增量 32 项通过，均无阻断问题。其后补齐 3 项边界测试，最终主流程全套 35 项通过。见 [复审记录](REVIEW.md#s1-s1b-review)。

限制：未调用真实模型、embedding、Milvus 或真实漏洞工具；Milvus 适配器只验证注入客户端的契约行为，真实 SDK/服务兼容性未验证。文件原子重命名与 fsync 在本地 macOS 文件系统验收；网络文件系统及 Windows 未验收。旧 legacy RAG 启动导入未接入新快照。实际数据的项目谱系、克隆关联、标签和正式划分仍待审核，本轮不输出正式研究成绩。

<a id="s2-verification"></a>

## S2 D1 验证记录

日期：2026-09-22。执行目录：`/Users/daiyifei/Documents/code/SmartContract-agent`，分支 main，Git 基点 `66161d5b74a6df980425f37c913e63591d246d2a`。保留原有未提交修改，未创建隔离工作树，未提交/推送/发布。

Verification Status：VERIFIED（下表工程行为）；Review Status：独立复审通过，所发现问题已修复并通过回归。S2 研究效果：UNVERIFIED。Shipping Authorization：NOT_REQUESTED。

| 验收项 | 实际证据 | 结论 |
|---|---|---|
| D1-01 状态变量、主体、修饰器与调用时序 | `test_program_facts.py` 11 项；Java FactsAdapterTest 3 项 | 通过；受限语义覆盖见 DESIGN |
| D1-02 独立对照、相同候选池与预算 | RetrievalStrategy 四实现、RetrievalCliTest；`demo/comparison.json` | 通过，四策略共用同一 poolHash、同一 budget |
| D1-03 条件绑定、错误主体/资源、过晚、旁路和未知 | RetrievalTest；无效检查、动态索引、权限状态变化回归 | 通过；不支持语义不转为保护存在/不存在 |
| D1-04 正反例配对、过滤和缺口 | 审核 pairId/机制/风险种类/条件差异；未知和不足预算不选完整对 | 通过 |
| D1-05 解释、去重及硬预算 | 全候选 evaluations、作用域来源、重复块/条件配对、实际 context 字节断言 | 通过 |
| D1-06 保持离线测试 | Maven 35 项、Python 52 项 | 全部通过 |
| 本地 Milvus 可用性 | 独立容器 v2.6.4、快照集合完整读回与检索、对照本地余弦 | 通过，未依赖外部 embedding/模型 |

### 本轮实际执行

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --retrieval \
  --source docs/vibe/releases/R1/evidence/S2/demo/target.sol \
  --request docs/vibe/releases/R1/evidence/S2/demo/request.json \
  --worker tools/experiment/program_facts.py --strategy compare
```

- [Maven 完整日志](evidence/S2/maven-clean-verify.log)：35 tests，0 failures/errors/skipped，BUILD SUCCESS。原 19 项保留，新增 16 项。
- [Python 完整日志](evidence/S2/python-unittest.log)：52 tests，OK。原 S1 35 项保留，新增 17 项。
- [CLI 完整对照](evidence/S2/demo/comparison.json)、[摘要](evidence/S2/comparison-summary.json)：四策略候选池摘要相同；所选上下文均 282 字节。传统对照按相似度返回案例；D1 将条件适用的防御例标为 SUPPORT、漏洞例标为 CONTRAST。该结果只说明机制路径，不是性能提升或统计显著性。
- [CLI 帮助](evidence/S2/retrieval-help.log)：新入口可独立运行，不装配模型。
- [Milvus 冒烟](evidence/S2/milvus-smoke.json)：两份知识块、合成 2 维向量；本地与真实 Milvus 返回的 pool 完全相同。全量快照内容已读回并通过 S1b 激活门禁。
- 源码及文档摘要、空白检查记录在 [产物检查](evidence/S2/artifact-check.json)。

### Milvus 运行记录

本地已有镜像 `milvusdb/milvus:v2.6.4`（arm64）。使用本轮专属容器 `smartcontract-s2-milvus-20260921`，只绑定 `127.0.0.1:29530` 与 `127.0.0.1:29091`；使用嵌入式 etcd、本地存储和唯一 `s1b_` 集合，未访问或修改旧集合。

首次启动因镜像在命令行初始化前读取部署模式而失败，日志为 [首次启动记录](evidence/S2/milvus-initial-start.log)。核对 v2.6.4 源码后设置 `DEPLOY_MODE=STANDALONE`，健康检查 OK，后续创建/插入/读回/激活/搜索全部成功。验证后停止本轮容器释放资源，保留容器及合成数据，未删除用户镜像或现有服务。

自动化单元测试不连接该容器。REST 适配的网络测试仅启动临时本地 HTTP 夹具；Java 模型测试沿用原有本地 HTTP 夹具，程序事实执行本仓库确定性 Python 脚本。

### 审查与限制

见 [REVIEW](REVIEW.md#s2-review)：09-22 独立复审已完成，短路、多维索引、下标重绑定及双向别名问题已闭环，最新全套验证通过。当前工程状态为 READY_TO_SHIP；研究效果仍 UNVERIFIED，未执行发布。Milvus 冒烟运行日期为 09-21，本次未重启或修改该容器。

示例中的 REVIEWED 仅指人工构造机制夹具的明确预期，不能作为真实项目的人工/专家审核证据。没有真实开发配对、正式检索相关性标签、模型下游实验或同 token 预算显著性结果；S2 的“可证伪先导”研究部分仍需后续执行。轻量词法结构提取不提供编译、CFG、跨函数可达性或通用保护有效性证明；STATE_WRITE_BEFORE 不证明具体更新值已足以消除重入。未将工程接口完成表述为论文创新已经成立。

<a id="s3-verification"></a>

## R1-S3 工程交付与研究门禁验证记录

### 2026-10-04 D1 首版正式知识库增量

本轮按[准入裁决](evidence/S3/d1-kb-v1-decisions.json)从 8 项未排除候选中准入 3 项：知识 Maia `AC-ASE-030` 与 Atomic Loans `RE-ATOMIC-001`，验证 PoolTogether `AC-ASE-040`。PoolTogether 修复为固定接收方，不符合现有 `CHECK_BEFORE` 防护字段，因此从知识侧转出。Basin、Gondi 和 3 个 SCRUBD 候选仍待审，未把它们从原始候选清单抹掉。Atomic Loans 审计范围 `Loans.sol` SHA-1 与提交 `3632e622e0b3fedf468866db0b878b7b74dd757e` 完全一致；到 PR #23 基线只变化 ERC20 返回值检查，重入关键状态顺序未变。外部原始审计与真实补丁支撑漏洞事件真值；**没有把外部报告冒充对本项目目标—案例适用性的独立打分**。

[首版谱系报告](evidence/S3/d1-kb-v1-leakage-report.json)：知识 2、验证 1、开发 0、锁定 0；`errors=[]`、`nearCloneCandidates=[]`、首版 `pendingSamples=[]`，另外 5 项候选见 `excludedFromV1`。实际生成[知识配对](evidence/S3/d1-kb-v1-pairs.json)各有漏洞与修复片段，访问控制要求补丁新增修饰器见证，重入要求状态更新与外部调用顺序反转。模型十个本地文件按[固定摘要](../../../../tools/experiment/d1-embedding-model.json)验证，离线编码四条 384 维向量；候选向量包的正文摘要与快照正文绑定，避免误把旧向量用于新文本。

[Milvus 收据](evidence/S3/d1-kb-v1-snapshot-receipt.json)：快照 `9fc63d0e8828a8caa78145e133b8f954f9fedaf79469ea0927434d7dbef725c8`，集合 `s1b_612ad26b068c4b64842463a633d6d1ba`，强一致性全量读回 4/4 后激活；随后 `active_snapshot` 再次读回一致。四条向量自检索均命中自身，PoolTogether 目标的本地与 Milvus 候选排序一致。此项是技术冒烟，不是 Recall@K、nDCG 或准确率的科研验证。Attu 本地 `http://127.0.0.1:3000` 可查看集合。

新增 Java 契约回归确认访问控制可以以 `CALL` 为风险操作；Maia 知识元数据据实标为 `CALL`。真实 Maia 原版与修复版经现有 `program_facts.py` 提取均为 `PARTIAL`，`payableCall` 作用域 `complete=false`，因此 D1 条件绑定保持 `UNKNOWN`，不能把该案例计作已证明的 D1 适用性。快照 ID 同时绑定案例元数据摘要；错误 `WRITE` 版本的旧集合未被改写，当前激活指针仅指向上述 `CALL` 版本。

本轮 `mvn clean verify` 的 41 项 Java 测试通过、`BUILD SUCCESS`，见[Maven 日志](evidence/S3/d1-kb-v1-maven.log)；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` 的 106 项 Python 测试通过，见[Python 日志](evidence/S3/d1-kb-v1-python.log)。新增回归覆盖错误防护字段、重入顺序、模型权重摘要、报告版本、许可证摘要和候选向量正文摘要。所有自动测试离线；真实 Milvus 仅作单独人工环境集成校验，未调用付费 API。完整重放命令见[知识库记录](research/S3_D1_KB_READINESS.md)。D1 的独立目标—案例价值标签、真实开发先导、完整提示 token 公平尚未完成，故 G1 的**知识来源部分**可审，G1 对研究先导整体仍未通过；D1 效果保持 `UNVERIFIED`，D2 未变。

日期：2026-09-24。范围：来源准入、谱系隔离与 D1 离线证伪流水线，以及 D2 固定候选最小契约。开发在当前主目录完成；真实模型未调用。工程交付与研究效果分别验收，后者仍受 G1–G3 门禁约束。

### 2026-10-04 首批原件增量复核

对首批十项固定源码和既有划分重新执行离线谱系审计。新增固定 Basin、Gondi、Maia、AI Arena 四份原始 finding 正文，Basin 修复审查版与 Maia 维护者修复提交；PoolTogether 原有报告和补丁保持摘要不变。八项未剔除样本中，已登记原始报告 5，修复源码或修复版本 3，缺完整原件或独立标签的样本仍为 8。新登记材料均继承事件组，更新的[泄漏报告](evidence/S3/first-batch-leakage-report.json)给出 `ok=true`、跨划分错误 0、近克隆候选 0、知识 2／开发 4／验证 2、`readyForFormalSnapshot=false`。原件 SHA-256、来源、逐项限制及重放命令见[原件复核](REVIEW.md#s3-first-batch-evidence-review)。

正式准入未通过：AI Arena 的维护者修复仓库返回 404；SCRUBD 三项缺逐事件报告和修复；所有八项均缺独立的漏洞位置、类别和适用性标签。未把修复源码自动标成安全负例，也未打开锁定测试。现有 `mvp_` 集合保持 `ENGINEERING_MVP`；本轮未创建或激活正式 `s1b_` 集合，正式 `active.json` 不存在。下一步需补知识侧重入真实修复对与独立标签，再按 S1b 完整回读流程激活正式快照。

本轮执行 `mvn clean verify`，Java 40 项全部通过、`BUILD SUCCESS`，见[Maven 日志](evidence/S3/first-batch-20261004-maven.log)；执行 `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`，Python 90 项全部通过，见[Python 日志](evidence/S3/first-batch-20261004-python.log)。清单更新改变工程演示快照的谱系摘要，已重建当前 `mvp_ec838f133828429f8b9fc0f53a1b2948` 集合，完整回读后页面状态接口返回 `ready=true`、`researchEligible=false`、3 条文档；旧 `mvp_b51c012b788548a6bca40e3ca91d67ae` 集合保留。Milvus 集合列表仅含上述两个 `mvp_`，没有 `s1b_`。
工程代码与证据已提交到远程 `origin/main`；同步不改变下文的研究门禁状态。2026-09-25 的第一批真实案例核验增量见文末；下面原有工程验证数据保留其当时口径。

### 按需求核验

| 需求 | 当前结果 | 证据与未满足部分 |
|---|---|---|
| S3-01 来源准入 | 部分完成 | 来源登记初始固定四个仓库提交，2026-09-25 增列 Proof-of-Patch 修复线索；机器门禁要求真实样本的源码、报告、补丁、漏洞位置和审核引用齐备。逐事件真实性与许可仍待人工核对，真实准入数为 0。 |
| S3-02 谱系隔离 | 工程门禁通过，真实数据未审 | 合成泄漏报告与离线回归覆盖项目、事件、补丁、精确重复、近克隆候选和衍生材料；锁定集拒绝打开。 |
| S3-03 独立标签 | 契约通过，真实标签缺失 | 判断格式与 UNKNOWN 分母有回归；没有独立审核员对真实目标—案例出具标签。 |
| S3-04 同池同预算对照 | 合成机制通过，真实 token 公平未验证 | 七策略复用同一候选池；字段过滤基线保留可用反证，避免人为削弱。合成码点适配器不能替代真实模型 tokenizer 与消息模板。 |
| S3-05 D1 消融与指标 | 合成机制通过，研究效果未验证 | 两项消融、逐样本指标和错误分解可重放；真实开发样本为 0。 |
| S3-06 D2 固定候选 | 最小契约通过 | guard 两项基线与 UNKNOWN 分母可重放；真实真假候选尚无独立证据。 |
| S3-07 付费运行控制 | 本轮无需付费运行 | 未选择真实运行，未调用付费 API；后续真实实验仍需请求及 token 上界 dry-run。 |
| S3-08 研究裁决 | 暂停效果结论 | G1 未通过；D1 仅保留离线证伪方案，D2 停留在挑战契约。 |

因此本次只能确认 S3 的工程部分可重放，不能将 S3 整体标为研究验收通过或 `READY_TO_SHIP`。

### 来源审核与 G1 状态

[来源登记](data/SOURCE_REGISTRY.json)初始保存四个仓库的固定提交，2026-09-25 增列 Proof-of-Patch；记录许可状态、公开材料入口及未核实字段。首轮依据各项目原始 GitHub 仓库和论文入口核对，未下载数据集到本项目，也没有给真实样本编造源码摘要或人工真值。后续十项待审名单记录从固定上游源码计算的真实字节摘要，仍未准入人工真值。

| 来源 | 仓库许可 | 已见原始材料 | 仍需人工核实 |
|---|---|---|---|
| SCRUBD | 未核实；仓库 API 未报告许可 | `SCRUBD-CD/data`、重入标签及注释入口 | 每条合约源码版本、报告/评论对应、补丁谱系、RE=0 的保护语义 |
| SmartBugs Curated | 仓库 Apache-2.0 | 类别目录、源码注释、`vulnerabilities.json` | 原项目谱系、逐事件报告、真实修复对；库中漏洞样本不自动产生安全负例 |
| ASE 2025 AC 基准 | 仓库 MIT | `datasets.xlsx`、DeFiHackLabsCVEs、Code4rena | 各行原始报告、准确源码/修复提交、负例定义与项目/克隆关联 |
| ACFix | 未核实；仓库 API 未报告许可 | `data`、README 中 original/modified 与测试日志入口 | 真实人工补丁与模型输出区分、原始报告、源码提交、许可及修复正确性 |
| Proof-of-Patch | 未核实；仓库 API 未报告许可 | 元数据、原始审计与修复链接 | 仅按线索回到原项目核实；类别误配与失效链接不能直接入真值 |

仓库许可证仅说明仓库声明，不代替对上游第三方合约/报告再分发范围的逐项核对。G1 **未通过**：当前没有逐事件经审查的真实目标—案例标签、可靠补丁对和安全负例。因此未执行真实开发集先导，未打开锁定测试，D1 科研效果状态为 **UNVERIFIED**。

### 工程门禁与数据契约

`tools/experiment/s3.py lineage` 检查源码和衍生材料 SHA-256、来源/版本、项目、漏洞事件、补丁对、精确字节、人工克隆组与跨划分关联边。报告产生连通组 ID 和近克隆候选；跨划分近克隆候选也阻断。源码、报告、摘要、知识块和模板的 `groupId` 必须继承样本补丁对组。真实补丁样本只有在来源四项状态均已核实、漏洞类别和行号有效、SOURCE/REPORT/PATCH 原件均已校验且报告和补丁材料由 `truthEvidence` 指向、独立审核员及版本有记录时，才会退出 `pendingSamples`。这些字段的真实性仍需人在原始仓库与报告中核查，程序不能仅凭填写 `INDEPENDENT` 字符串证明审核独立性。锁定测试源码在先导进程中从不打开。本切片无法验证外部封存证明的真实性，因此只要清单包含锁定测试样本便拒绝运行；锁定集的近克隆隔离仍需后续独立审核方案，不能宣称已完成。近克隆规范化指纹只是候选发现器，不能证明不存在其他克隆。

`judgments.json` 对每个目标—案例给出 0–3 级适用性、支持/反证价值、审查角色、标签版本、证据引用和 `REVIEWED/PENDING/DISPUTED`。支持与反证必须来自同一审核配对的不同案例。待审必须保持 UNKNOWN，评价要求覆盖整个候选池；只要池中尚有待审案例，Recall@K/nDCG 为 null，并显式报告未知总数及入选数。无已审核正例、无已知入选分母也为 null。按项目作为聚合单位；真实补丁、人工改造、合成样本分别计数。合成夹具作者的标签仅用于机制测试，`researchEligible=false`。

`tools/experiment/s3_pilot.py` 每个目标只调用一次 S2 `compare`，固定知识快照和候选池，再做字段条件过滤与两项消融：字段过滤保留条件已支持与已反证的案例，只排除 UNKNOWN，防止人为削弱反证基线；D1_NO_BINDING 使用配对元数据但不使用目标条件绑定，D1_NO_COMPLEMENT 保留适用候选但不选互补反例。检索超时与解析失败逐样本记 `FAILED`，不从分母消失。S2 字节/数量预算必须足以容纳全部候选，之后由同一显式 tokenizer 适配器对 **系统提示＋目标源码＋问题＋工具摘要＋输出格式＋已选证据** 完整计数；适配器文件、版本、模板和最大 token 数绑定计划。现有 UTF-8 字节数不作为 token 数。真实模型试验前还需独立核实 tokenizer 与指定模型版本、chat 消息序列化格式及全部提示字段一致；现有纯文本拼接尚未证明与真实 API 提示等价。示例使用码点计数，仅可验证流水线控制流，不能作为 token 公平的科研证据。固定提示本身超预算会拒绝运行。

D2 路径可行性过滤和双向错误曲线留待后续阶段；本切片只验固定候选、覆盖义务与 guard 两项简单基线。D2 的 [失败/未知分母](evidence/S3/demo/d2-summary.json)显示合成固定候选计划 2、弃权 UNKNOWN 2、未知真值上的确定性判断 0、失败 0；没有可裁决结果，错误接受/拒绝率为 null。D2 的 `validate_d2_challenges` 要求固定候选源码摘要、风险行、声称路径、真值出处及六类保护义务。TRUE/FALSE 必须有审核证据，UNKNOWN 保留未知；真值 UNKNOWN 上的 TRUE/FALSE 输出另计 `unknownTruthDecisions`，不计正确。当前两个合成候选的 guard 存在性/具体行基线输出在 [D2 夹具](evidence/S3/demo/d2-baselines.json)；基线的漏洞裁决始终 UNKNOWN，不把 guard 字样当安全。

### 可重放命令

在项目根目录执行：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/s3.py lineage \
  --ledger docs/vibe/releases/R1/evidence/S3/demo/ledger.json --root .

PYTHONPATH=tools/experiment python3 tools/experiment/s3_pilot.py \
  --ledger docs/vibe/releases/R1/evidence/S3/demo/ledger.json --root . \
  --plan docs/vibe/releases/R1/evidence/S3/demo/plan.json \
  --labels docs/vibe/releases/R1/evidence/S3/demo/judgments.json \
  --tokenizer docs/vibe/releases/R1/evidence/S3/demo/codepoint_tokenizer.py \
  --jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar \
  --worker tools/experiment/program_facts.py --output /tmp/s3-pilot-new.json

mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
```

`--output` 必须是不存在的文件，避免覆盖前次实验。源数据只是 [S2 合成机制夹具](evidence/S2/demo/bundle.json)，重新标为 development/knowledge 的 S3 演示划分；[谱系清单](evidence/S3/demo/ledger.json)、[人工标签示例](evidence/S3/demo/judgments.json)、[计划](evidence/S3/demo/plan.json)、[逐样本输出](evidence/S3/demo/pilot.json)均可复查。修正字段过滤基线后，合成示例中 D1 与字段过滤的 Recall@2 **均为 1**；D1 的 nDCG@2 为 1，字段过滤为 0.834。两者在作者构造案例上的差异**不是方法提升证据**。

### 最新验证证据

- [Maven 日志](evidence/S3/maven-clean-verify.log)：`mvn clean verify`，35 项，0 失败/错误/跳过，BUILD SUCCESS。
- [Python 日志](evidence/S3/python-unittest.log)：`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`，72 项，OK。新增回归先观察到报告/补丁待审样本被遗漏、空材料准入、来源材料错绑、反证基线缺失、超时丢分母、未知真值漏计及旧源码硬编码凭证，再修正相应行为。
- 旧模块仅执行 `mvn -o -f legacy/pom.xml -DskipTests compile`，离线编译成功；未运行旧集成测试，因其可能调用真实服务。
- [失败回归](evidence/S3/review-red.log)与独立复审确认：共享报告跨划分、锁定证明伪造、候选正文注入、超预算、注释伪 guard 和标签伪配对均已阻断；[空清单失败回归](evidence/S3/empty-ledger-red.log)及[修复后回归](evidence/S3/empty-ledger-green.log)证明空来源/样本不会通过门禁。独立复审结论限于首切片工程门禁，无剩余已知阻断。
- [泄漏报告](evidence/S3/demo/leakage-report.json)：合成 knowledge 2、development 1、跨划分错误 0；两个知识案例同一连通组。`pendingSamples=3`，因为合成夹具无真实来源许可/报告/补丁，科研准入仍为 0。
- [逐样本结果](evidence/S3/demo/pilot.json)：七种检索/消融策略共享同一个 S2 `poolHash` 与快照，统一提示上限 600 个**合成码点计数单位**；实际完整提示 312 或 445 单位。原始输出包含每策略入选案例、Recall@K、nDCG、错误入选、互补覆盖、逐条件错误分解与 UNKNOWN 分母。真实模型 token 公平尚未验证。
- 本次在主目录重新执行谱系命令，结果为 3 个合成样本、跨划分错误 0、待审 3；重新执行先导后，分母为计划 1、完成 1、失败 0、科研准入 0，输出与仓库逐样本证据逐字段一致。四个来源仓库的远程 HEAD 与来源登记中的固定提交一致。

### 失败、UNKNOWN 与研究裁决

合成演示：计划 1、完成 1、失败 0、研究合格 0；UNKNOWN 判断 0。真实开发样本：0，真实研究指标全部未计算。近克隆门禁、锁定测试拒绝、待审标签 null 分母、token 总提示预算和 D2 UNKNOWN 均有确定性离线回归。

D1 裁决：**谨慎保留离线证伪方案，暂停效果结论**。下一步要先完成许可、来源、补丁、项目组及人工判断审核；再锁定真实 tokenizer 与完整提示预算，比较 D1 与最强非 D1 基线的项目级结果。若简单字段过滤解释全部收益，应收窄 D1；若可靠样本/标签无法取得，应暂停该科研主张。D2 继续停留在挑战数据契约，不进入多智能体或深度符号执行实现。锁定测试只在方法、阈值和预算冻结后由独立审核者开启。

旧 `src/` 中曾有形似真实的硬编码供应商密钥，本轮改为读取 `DASHSCOPE_API_KEY` 环境变量并加入源码扫描回归；该旧值已存在于此前提交历史，**源码修改不能撤销已暴露的凭证**，需在供应商控制台撤销或轮换。未尝试使用该凭证，也未改写 Git 历史。

### 2026-09-25 第一批真实案例核验增量

用户批准访问控制／重入范围与 10～15 项上限。当前[核验记录](research/S3_FIRST_BATCH_AUDIT.md)和[十项待审名单](evidence/S3/first-batch-intake.json)由 ASE 基准、SCRUBD V6.0 固定提交及 Proof-of-Patch 原始修复线索形成；[重新下载复核](evidence/S3/first-batch-source-check.json)确认十项源码 SHA-256 一致、三项 SCRUBD `RE=1` 且 `is_student=0` 行定位一致，五个访问控制、五个重入项目暂不重复。此检查不证明标签正确。原始报告／许可／补丁仍有缺口，因此 **待审 10、准入 0、安全负例 0**。用户尚未审核逐事件标签，未运行真实隔离门禁、快照激活、D1 真实对照或付费模型。Yaxis finding 编号和 Proof-of-Patch 两项类别的疑点均已排除，不能用候选数替代高质量准入数。

### 2026-09-26 候选审核与本地报告闭环

用户回复「全部审核通过」，已记为对首批十项候选选择的确认；这不代替逐事件的原始许可、报告、补丁和独立标签凭据。十项继续标为待审，科研准入 0，正式 Milvus 快照未激活，锁定测试集未打开，D1 真实效果未计算。

本地实验台的固定合成对照运行现在生成独立报告目录：每个样本一行写入 `samples.jsonl`，并保存 `summary.json` 与完整运行记录。页面展示报告目录，提供 JSONL 下载入口；历史回看读取已存结果，不重跑实验。若执行器返回无效逐样本结构，接口报错且不发布运行记录。此闭环仍只运行合成夹具，不读取 API Key，也不调用真实模型或 Milvus；它不是正式实验的断点续跑入口。

验证：`mvn clean verify` 成功，Java 测试 36 项；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` 成功，Python 离线测试 80 项，其中本地页面测试 8 项。浏览器实际打开 `http://127.0.0.1:8766/` 并回看运行 `33abfca768aa4b458c89ac00adb213bd`，页面显示报告链接及目录；报告接口返回 HTTP 200、`application/x-ndjson` 和下载文件名 `samples.jsonl`。本次运行分母：计划 1、完成 1、失败 0、科研合格 0；报告位于 `.local/experiment-ui/reports/33abfca768aa4b458c89ac00adb213bd/`，只在本机保存。

### 2026-09-26 真实候选预分配与源码隔离

[分配表](evidence/S3/first-batch-assignment.json)覆盖十项固定候选；[分组说明](research/S3_FIRST_BATCH_SPLIT.md)记录来源角色、两项经原始报告核对后剔除的类别误配，以及知识 2／开发 4／验证 2 的项目级分配。十份固定源码再次下载，SHA-256 均与原名单一致。八项未剔除源码运行 `first_batch.py audit` 和 S3 `lineage`，两者均返回 `ok=true`、跨划分错误 0、已发现近克隆候选 0；[机器报告](evidence/S3/first-batch-leakage-report.json)保留分组 ID、清单摘要及待审分母。PoolTogether 的原始 finding 396 和修复提交 `50bd158` 源码已在本机按 SHA-256 固定为 REPORT/PATCH 原件，并与源文件继承同一事件组；改动后原件摘要不匹配会拒绝运行。

此结论只覆盖已取得的源码及一对报告／补丁。八项仍为 `pendingSamples`，真实安全负例 0，锁定测试 0，正式知识快照和 Milvus 激活 0；近克隆扫描不能证明不存在语义克隆。D1 两个方向尚无足够的经独立审核的真实正反例对，不报告真实效果。新的离线回归覆盖源码漂移、分配缺失、同项目跨划分、近克隆跨划分与原件摘要／组继承。完整重放命令见[分组说明](research/S3_FIRST_BATCH_SPLIT.md)。

本轮重新运行 `mvn clean verify`：Java 36 项通过，BUILD SUCCESS；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`：Python 85 项通过，OK，其中首批数据门禁新增 5 项。首批本机目录没有 `active.json`，没有创建或激活 Milvus 集合，也未调用付费模型。

### 2026-09-26 本机 Milvus 与真实 API 工程 MVP 增量

用户明确要求先建立一版向量数据库并接入真实 API，跑通 MVP。此增量使用独立的 `mvp_` Milvus 集合和 `ENGINEERING_MVP` 指针，与上述尚未激活的**正式科研知识快照**区分。知识 2 个项目组、3 个片段；检测目标是开发划分固定样本 `AC-ASE-006`。构建前复核本机固定原件与首批隔离，写入后完整读回才激活；页面状态接口和每次运行重新校验快照。详细启动与边界见 [工程试跑说明](operations/S3_MVP_MILVUS_RUN.md)。该词法哈希向量库只为联调，不是正式知识库，也不产生 D1 研究证据。

最新离线验证：[Maven 日志](evidence/S3/mvp-maven-clean-verify.log)记录 `mvn clean verify` 成功、Java 38 项通过，新增本地 HTTP 回归核对 DeepSeek 请求只发送 `max_completion_tokens`；[Python 日志](evidence/S3/mvp-python-unittest.log)记录 `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` 共 89 项，全部通过。Milvus v2.6.4 本机容器健康检查通过；快照 `beeb199c96ff11df6fe7416b02e2d327cc8bdc76da00df61a7eead5772ef8806`，集合 `mvp_b51c012b788548a6bca40e3ca91d67ae`，片段 3 条。浏览器实际打开 `http://127.0.0.1:8767/mvp.html`，看到快照就绪、四条运行历史，并点开最后一次成功结果；页面显示模型结论、证据片段、用量和报告目录。每个报告在本机 `.local/mvp-runs/<runId>/` 保存计划、启动标记与结果；上述本机路径被 Git 忽略。

本轮真实请求记录如下，均固定同一开发样本、同一快照、一次请求、无自动重试；另有一次 16-token 短提示诊断请求确认 Agent Plan 端点、密钥和型号可用，返回 HTTP 200、输入 86、输出 8 token。

| 运行编号 | 请求边界 | 结果 | 实际用量 |
|---|---|---|---|
| `7c29aa76c84247cfa2d460e63c584952` | 旧 `max_tokens=512`，等待 60 秒 | 约 60 秒调用失败，`UNRESOLVED` | usage 缺失，保持 null |
| `d5208d517e2642d7b52317aa8771fc52` | 旧 `max_tokens=512`，等待 180 秒 | 完成；报告了未授权升级疑点 | 输入 1945、输出 917；输出超过 512，原因是该字段不包含全部推理 token |
| `c285f720b3b94aa8931a8548852a8262` | `max_completion_tokens=1024` | 输出到达 1024 后 JSON 不完整，`UNRESOLVED` | 输入 1945、输出 1024 |
| `9dc58487b1ad458386d72ccc516b7f78` | `max_completion_tokens=2048`，等待 180 秒；当前实现 | 完成；报告了初始化权限疑点 | 输入 1945、输出 1770 |

`max_completion_tokens` 同时限制回答与推理内容，依据[火山方舟 Chat API 文档](https://docs.volcengine.com/docs/ark/chat-api?lang=zh)。最后一次实际用量低于请求上限。固定源码用户消息 7250 UTF-8 字节；真实 token 上限仍未由独立 tokenizer 锁定，故不把该字节数宣称为科研预算公平。两次成功结果对同一目标给出不同解释，且目标标签、知识适用性仍待独立审核：本次仅证明工程链路可运行，**没有检测准确率、D1 增益或安全负例结论**。失败两次、完成两次；失败均保持 `UNRESOLVED`，不存在自动重试或“失败即安全”。

### 2026-10-04 结构化输出稳定性修正

用户指出页面中 `AC-ASE-006` 的运行 `1b5b52e352154857974b763e9aa2880b` 失败且输出 token 恰为 2048。排查确认：原请求只在提示词里要求 JSON，没有设置服务端 `response_format`。增加严格 JSON Schema 后，Java 本地 HTTP 测试核对请求包含三个必填字段、`additionalProperties=false`、`strict=true`；解析器继续拒绝缺字段、空理由及非 JSON，不能把失败转成“安全”。另用供应商文档核对 [JSON Schema 与最大输出字段](https://docs.volcengine.com/docs/ark/chat-api?lang=zh) 和 [DeepSeek V4 思考开关](https://docs.volcengine.com/docs/ark/deep-thinking?lang=zh)。

本次显式试跑的四个新运行均只发一次请求、没有自动重试。`6043e1496bbc4341a82e429d478fa60d` 使用严格 Schema＋关闭思考，输出 103 token 但字段校验未通过；该次尚未启用原文诊断，具体字段无法追溯。`3d2ab656d0e54534bf966d6aa75273b0` 使用同配置，输出 26 token 且结构化解析完成，但结论为“未发现”，与早前同一源码的其他回答不一致，不能证明检测正确。低强度思考的 `ff03d009e2054fa588eb40d1d2d2b72b` 与 `d65ddce0c5e749be86bd1c49271fc980` 分别耗尽 2048、4096 输出 token，均没有生成任何最终回答；前者的本机 `raw-response.txt` 为 0 字节。增加总预算不能可靠解决该型号的思考耗尽问题，因此最终工程配置回到关闭显式思考和 2048 上限。最终修改后没有再发起付费请求，**不能把一次成功当作已测得低失败率**。

最终离线验证：[Maven 日志](evidence/S3/mvp-structured-maven.log)的 `mvn clean verify` 通过 Java 40 项，[Python 日志](evidence/S3/mvp-structured-python.log)的离线测试 90 项通过。新增测试覆盖显式配置时发送的 JSON Schema/思考参数、普通 DeepSeek 请求不继承 MVP 开关、`finish_reason=LENGTH` 的未决映射、无效原文仅写本机诊断文件以及失败时不重试。工程页面保留原失败历史，新运行的输出截断会显示为明确原因；已保存的旧记录不会被改写。科研标签、D1 效果和检测准确率仍未验证。

### 2026-10-04 D1 正式知识候选与构建门禁

[D1 知识库准入记录](research/S3_D1_KB_READINESS.md)固定 Atomic Loans 原始审计、真实修复 PR、修复前后源码与 MIT 许可证，替换不可读取修复源码的 AI Arena 正式知识位置；原工程 `mvp_` 集合和划分未改。正式候选 11，排除 3，参与隔离的八项为知识 2、开发 4、验证 2。[机器泄漏报告](evidence/S3/d1-kb-leakage-report.json)显示 `ok=true`、跨划分错误 0、近克隆候选 0、`pendingSamples=8`。Atomic Loans 审计报告所列整文件 SHA-1 与 PR 修复前文件不同，已记录为独立复核点。

新增 `d1_kb.py` 从经过 S3 完整审核的清单生成两种角色的知识片段、S1b 快照和 D1 catalog；不自动激活。离线测试先验证缺失实现失败，再验证待审标签、待审配对、补丁篡改、缺失配对、重复补丁和无效结构均拒绝；完整审核的夹具可生成两条内容寻址文档且没有 `active.json`。实际首批清单执行构建命令返回 `正式知识快照构建拒绝：谱系冲突或真实标签待审`，没有创建 `.local/d1-kb-snapshots/active.json` 或 `s1b_` Milvus 集合。所用空向量文件只为验证拒绝发生在向量处理前，**并非正式 embedding**。

本轮重新执行 `mvn clean verify`：`BUILD SUCCESS`，Java 40 项测试，失败 0、错误 0；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`：Python 99 项，全部通过。复查发现同一快照 ID 的 catalog 若被本地篡改会被静默覆盖，已增加拒绝覆盖的回归测试和修复。候选向量工具另以注入的确定性编码器验证两份片段输出、缺补丁拒绝和模型权重不可读时的明确错误；真实 BGE 模型依赖已安装并锁定，但权重下载在 `huggingface.co/.../modules.json` 的 HTTPS 请求遇到 `SSL: UNEXPECTED_EOF_WHILE_READING`，没有产生真实向量。本轮没有调用付费 API、没有运行 D1 真实效果实验、没有打开锁定测试集。正式知识快照准入 0，错误／失败样本不映射为安全，未知分母 8。

<a id="s4-verification"></a>

## R1-S4 验证记录

状态：实施中；本文件只记录已执行检查，不把单项通过当作整链交付或科研效果。

### 目标登记与隔离（S4-01、S4-02 的输入部分）

2026-10-05：先运行新测试，因 `formal_targets` 模块不存在而失败；实现后执行 `PYTHONPATH=tools/experiment python3 -m unittest tools/experiment/tests/test_formal_targets.py -v`，2 项通过。测试以临时目录内的固定源码和谱系夹具验证四目标列表、函数原始行号、源码／片段双摘要、源码篡改和同项目跨划分拒绝。额外只读检查本机现有原件：`AC-ASE-006/009` 为整份试跑，`RE-SCRUBD-001` 为第 574–660 行函数级试跑，`RE-SCRUBD-002` 因提示上限阻塞。本项不调用模型、Milvus 或工具；研究真值仍待审。

同日正式检索冒烟发现 `RE-SCRUBD-001` 原始文件含 CRLF；`Path.read_text` 把它规范化为 LF，导致事实摘要不等于登记摘要。新增 CRLF 回归测试先失败，再改为按原始字节解码，2 项测试恢复通过。原始源码摘要与函数片段摘要现分别绑定，未修改原件。

### 正式快照与 D1 预览（S4-01、S4-02）

2026-10-05：新 `formal_recall` 测试先因模块不存在失败；实现后 `PYTHONPATH=tools/experiment:tools/experiment/tests python3 -m unittest tools/experiment/tests/test_formal_recall.py tools/experiment/tests/test_recall.py -v` 的 8 项通过，`mvn -pl audit-mvp -Dtest=RetrievalCliTest test -q` 退出码 0。离线夹具验证正式快照与 catalog 绑定、四条候选配对、未知条件、短目标无风险事实、错误 ID／分数、模型维度和指针变化拒绝。另加 Java 结果快照不匹配回归，先失败后通过。

本机只读冒烟使用已固定 BGE 权重、本机 Milvus `127.0.0.1:29531` 和当前 Java JAR：`AC-ASE-006` 在正式快照召回 4 条候选，D1 返回 `NO_RISK_FACT`；`RE-SCRUBD-001` 召回同一 4 条，D1 入选 0，记录“没有经审核且条件适用的完整对比配对”及 Atomic 防御片段条件未知。两者均未调用付费模型；这验证接线和诚实缺口，不是 D1 效果证据。

### 结构化假设与本机工具（S4-03、S4-04）

2026-10-05：先运行新 `HypothesisServiceTest`、`HypothesisCliTest`、`ToolCliTest`，因新类型不存在而编译失败；实现后用本机假网关、假 HTTP 和子进程脚本验证空假设、最多三条的严格 JSON Schema、额外字段／错行号／错证据引用、截断与模型异常。失败始终为 `FAILED/UNRESOLVED`，缺失 usage 为 `null`。网关新 schema 仅用于 `--hypotheses`，原三字段 `AuditService` 未修改。`ToolCli` 将空告警、解析错误分开，支持固定本机配置的 Slither 与可选 Mythril；空告警不输出 SAFE。`mvn -pl audit-mvp -Dtest=HypothesisServiceTest,HypothesisCliTest,ToolCliTest,GatewayTest,AuditServiceTest,AuditCliTest test -q` 退出码 0；后续加入可选 Mythril 回归后定向测试仍为 0。未请求真实付费 API。

### D2、持久化与本机页面（S4-05、S4-06、S4-07）

2026-10-05：新 D2 测试先因模块不存在失败，随后覆盖工具空告警、工具超时为 UNKNOWN，以及与风险行匹配的显式重入告警可反驳旁路义务。D2 六项义务在证据不足时都保持 UNKNOWN，不把未发现告警当作防护覆盖。新运行器测试先因模块不存在失败，随后覆盖目标与片段双摘要、模型调用前源码变化拒绝、完整提示字节超限不调用模型、计划／事件先持久化、无 usage、模型异常保持未决、只读重放及计划篡改拒绝。HTTP 测试先因新接口参数不存在失败，随后验证页面与状态／预览／历史读取零模型调用，额外字段、重复 JSON 键、未知样本、超大请求和跨源请求拒绝；原离线实验台与 MVP 页面测试均通过。

本机 `127.0.0.1:29531` 正式 Milvus 和固定 BGE 权重的只读离线演练：`AC-ASE-006` 检索 4 条候选，D1 为 `NO_RISK_FACT`，运行 `0c24b53de78c44dbae34b6cb79b51838` 得 `COMPLETED/NO_CONFIRMED_FINDINGS`、D2 `UNKNOWN`、计划 1／失败 0／未知 1，重放与内存结果一致。`RE-SCRUBD-001` 函数级运行 `1e376569d2964c4c8c89810d813108de` 得第 574–660 行、D1 `COMPLETED` 但未选中可审核的完整对比配对、D2 `UNKNOWN`。两次离线运行均为明确的空假设夹具，不是模型审计结论；未运行真实 Slither、Mythril 或付费 API。

本机 HTTP 页面 `http://127.0.0.1:8769/agent.html` 经实际请求核对：`/agent.html`、状态、目标和历史均返回 200；`POST /api/agent/runs` 对 `AC-ASE-006` 离线演练返回 201，运行编号 `c479ded84b3147deb207656f3510607e`；后续新版本对 `RE-SCRUBD-001` 函数级演练返回 201，编号 `6f79bab499e644208653a1615d0e934c`，只读回放和 JSONL 下载均返回 200，报告恰好一行。新版本给结束事件加入结果摘要，早先两个工程演练记录因版本升级不进入新页面历史；磁盘原件仍保留，不能混称为当前可回放版本。页面只将既有阶段数据可视化，不证明 D1 提升或 D2 准确率。

### 本轮限制与分母

- 正式知识快照仍为 `9fc63d0e8828a8caa78145e133b8f954f9fedaf79469ea0927434d7dbef725c8`，集合 `s1b_612ad26b068c4b64842463a633d6d1ba`，四条向量对应两组真实补丁对；本轮只读，不激活新集合。
- 完成的当前版本 HTTP 离线演练 2 次，失败 0，D2 UNKNOWN 2；模型假设由固定空夹具给出，usage 输入／输出均为 `null`。更早两个运行只用于开发中的持久化检查，不并入当前版本分母。真实模型请求 0，真实工具运行 0。
- 两份短访问控制目标没有可绑定正式知识的同类风险事实；重入目标的条件匹配仍有 UNKNOWN，不能由四条知识向量或工程链路推导 D1 的论文效果。函数级试跑上下文不完整；`RE-SCRUBD-002` 仍被提示上限阻塞。
- D2 初版只从已有源码事实和工具行级告警判定显式反驳，其余保护义务维持 UNKNOWN；未运行深度路径求解。真实模型质量、工具可用性和真实提示 token 公平本轮未验证。锁定测试未打开。

### 最终离线回归与待同步状态（S4-08）

2026-10-05 15:46（Asia/Shanghai），当前主目录 `main`、实施起点 `163bd8d`：`mvn clean verify` 退出码 0，Java 47 项全部通过；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` 退出码 0，Python 120 项全部通过。新测试均使用假网关、本机假 HTTP、假索引或固定子进程夹具；默认测试不依赖真实 Milvus、Slither、Mythril 和付费 API。实际本机 Milvus/BGE 离线烟测单列在上文，不计入确定性测试。

`git diff --check` 对整个工作树返回 2，唯一报告为用户在本轮前已有的 `docs/vibe/releases/R1/research/S3_DATASET_SELECTION_PROPOSAL.md` 末尾空行；本轮未修改该文件，也不会将它纳入本版本提交。本轮已暂存文件的差异检查退出码 0；实际提交与远程同步以 Git 历史为准。

最终 JAR 与运行器重启后，页面再以 `AC-ASE-006` 发起一次离线 HTTP 运行：运行编号 `44baf45837064295800b48ff51574af0`，POST 201，`COMPLETED`、D2 `UNKNOWN`；状态、目标、历史、页面均返回 200，GET 回放 200 且运行编号一致。该次已计入上方当前版本 2 次分母。

<a id="s5-verification"></a>

## R1-S5 真实知识库与页面试跑验证

2026-10-07。本轮完成真实案例的来源固定、谱系合并、新版知识快照和页面单样本三策略入口。下述离线运行仅验证工程链路，**没有调用付费模型，也不能证明 D1 提升了检测效果**。

### 数据来源与隔离

新增 [原件核对](evidence/S5/source-review.json) 将 [RabbitHole 原始高危报告](https://github.com/code-423n4/2023-01-rabbithole-findings/issues/608)及[已合并修复](https://github.com/rabbitholegg/quest-protocol/pull/86)放入知识侧；[JPEG’d 原始报告](https://github.com/code-423n4/2022-04-jpegd-findings/issues/81)及[已合并修复](https://github.com/jpegd/core/pull/19)、[Infinity 原始报告](https://github.com/code-423n4/2022-06-infinity-findings/issues/184)及[项目方修复提交](https://github.com/infinitydotxyz/exchange-contracts-v2/commit/b90e746fa7af13037e7300b58df46457a026c1ac)放入独立验证侧。RabbitHole 原修复前文件与审计版本一致；JPEG’d 的审计版与补丁父提交仅目标函数一致，不能宣称整文件相同；Infinity 的修复是目标函数增加 `nonReentrant`。新增九份源码、原始报告正文与修复源码已按原字节保存于 [原件镜像](evidence/S5/originals)，九份 SHA-256 全部与[登记](evidence/S5/assignment.json)吻合。源码 SPDX 分别为 MIT、GPL-3.0、MIT；RabbitHole 仓库与文件许可声明不一致，来源记录保留该事实。

合并既有 Maia、Atomic Loans 知识案例及 PoolTogether 验证案例后，[正式清单](evidence/S5/formal-v2-ledger.json)为知识 3 组、验证 3 组；知识对应[三组真实补丁对](evidence/S5/formal-v2-pairs.json)。[泄漏报告](evidence/S5/formal-v2-leakage-report.json)摘要为 `581a083047ba2a8d8eefe8b34f2e32d219d170544941116d8ec0101b7e622df6`，`errors=[]`、`nearCloneCandidates=[]`、`pendingSamples=[]`。开发样本另外与正式清单联合检查，不能借开发目标反向污染知识和验证。验证目标均以函数级源码进入页面；修复版仅作为报告证据，不作为“整份合约安全”的负例。

### 快照与页面证据

[快照收据](evidence/S5/snapshot-receipt.json)：固定本地 BGE 模型离线编码，生成 6 条 384 维知识向量；内容寻址快照 `5381e15f60729bf4e475572f0717e911d316e4754a17f9d0cf74cf341a3d76c3`。Milvus 新集合 `s1b_a6741615b74240909978e25ae2264476` 的六条正文和向量完整读回后才激活。旧集合没有删除。本机 `active_snapshot` 再读回通过。

页面 [单样本工作台](http://127.0.0.1:8769/agent.html)展示三个独立验证目标和三种策略：向量召回、简单条件字段过滤、D1 对比检索。每个目标的三种策略来自相同快照与同一候选池；入选上下文上限同为 2048 UTF-8 字节，每次显式真实点击最多一次模型请求、2048 输出 token、零自动重试。**字节上限不是完整提示的真实 token 公平**，当前缺少经独立复核的目标—案例适用性标签，因此页面始终 `researchEligible=false`。真实模型选择由本地凭证配置读取，本轮未调用。

实际经 HTTP 页面接口做九次离线试跑并用 `audit_run.replay` 逐项核验 `plan.json`、`events.jsonl`、`sample.jsonl` 和 `result.json`。[逐次运行收据](evidence/S5/ui-offline-smoke.json)列出各运行编号和报告路径。三个目标各三种策略，共 9 项；完成 9、失败 0、D2 未知 9、真实模型请求 0。逐目标候选池摘要在三种策略间一致。按向量／字段过滤／D1 顺序，入选片段数为：PoolTogether `1/2/0`，JPEG’d `2/1/0`，Infinity `1/0/0`。所有离线模型假设都是固定空夹具，结论为 `UNRESOLVED`。这组结果显示当前 D1 的条件绑定**覆盖不足**，尤其 JPEG’d 的 `_mint` 内部状态变化和 Infinity 的跨函数路径不能被轻量事实提取完整表示；不能从中推断真实审计准确率或优势。

### 重放命令

在本机已有 R1-S3 固定原件、固定 BGE 权重和本机 Milvus 时，可以重建并校验：

```bash
mkdir -p .local/r1-s5/sources .local/r1-s5/reports .local/r1-s5/patches
cp docs/vibe/releases/R1/evidence/S5/originals/sources/* .local/r1-s5/sources/
cp docs/vibe/releases/R1/evidence/S5/originals/reports/* .local/r1-s5/reports/
cp docs/vibe/releases/R1/evidence/S5/originals/patches/* .local/r1-s5/patches/
PYTHONPATH=tools/experiment python3 tools/experiment/first_batch.py audit --intake docs/vibe/releases/R1/evidence/S5/intake.json --assignment docs/vibe/releases/R1/evidence/S5/assignment.json --root . --source-dir .local/r1-s5/sources --output-dir .local/r1-s5/candidate
PYTHONPATH=tools/experiment python3 tools/experiment/d1_admission.py --candidate-ledger .local/r1-s5/candidate/ledger.json --decisions docs/vibe/releases/R1/evidence/S5/decisions.json --root . --base-ledger .local/d1-kb-v1/ledger.json --base-pairs .local/d1-kb-v1/pairs.json --output-dir .local/r1-s5/formal-v2
PYTHONPATH=tools/experiment HF_HUB_OFFLINE=1 .local/d1-embed-venv/bin/python tools/experiment/d1_embed.py --ledger .local/r1-s5/formal-v2/ledger.json --pairs .local/r1-s5/formal-v2/pairs.json --root . --output-dir .local/r1-s5/formal-v2 --model-dir .local/d1-embedding-model
PYTHONPATH=tools/experiment python3 tools/experiment/d1_kb.py --ledger .local/r1-s5/formal-v2/ledger.json --pairs .local/r1-s5/formal-v2/pairs.json --vector-bundle .local/r1-s5/formal-v2/candidate-vectors.json --root . --snapshot-root .local/d1-kb-snapshots
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from milvus_rest import MilvusRestIndex; from snapshots import active_snapshot; print(active_snapshot(Path(".local/d1-kb-snapshots"), MilvusRestIndex("http://127.0.0.1:29531")))'
PYTHONPATH=tools/experiment HF_HUB_OFFLINE=1 .local/d1-embed-venv/bin/python tools/experiment/local_ui.py --port 8769
```

新环境首次激活新快照才需要调用 `activate_snapshot`；若已有[快照收据](evidence/S5/snapshot-receipt.json)所列集合，只运行 `active_snapshot` 读回，不重复创建。旧基础原件与模型准备方法见 [R1-S3 知识库记录](research/S3_D1_KB_READINESS.md)。页面每次点击结果保存在 `.local/audit-runs/<运行编号>/`，历史读取不重新调用模型。

离线验证：`mvn clean verify` 成功，Java 47 项；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` 成功，Python 127 项。测试不依赖真实 API、Milvus 或未锁定工具环境。本机 Milvus 和 HTTP 页面冒烟单独列为集成验证。

### 下一步研究判断

当前仅能保留 D1 作为待证伪方法，**不能报告提升**。知识侧重入只有一组，真实验证侧函数级事实无法覆盖跨函数状态和修饰器防护；先补充独立项目的合格重入知识／验证案例并扩大到原定 10～15 个候选事件内，再请独立人员逐目标标注适用性、支持及反证价值。冻结真实 tokenizer、完整聊天模板与项目级评分口径后，才能在同池和完整 token 预算下比较三种策略；锁定测试集仍不得用于调参。

<a id="s6-verification"></a>

## R1-S6 批量对照与数据规模调研验证

### 2026-10-07 真实运行授权后的补充验收

用户明确授权真实模型批量试跑并取消预算前置限制。真实入口现可在页面预览计划后启动，固定每组合一次请求、零自动重试；已开始但未落盘的组合续跑时仍记为失败且未知，不自动重发。完整输入 token 与费用上界保留 `null`，UTF-8 字节上限不作为 token 公平依据。

排查近期单次 `FAILED` 发现两个原因：已登记验证源码包含原项目导入路径且要求特定 Solidity 编译器版本，临时单文件 Slither 运行返回 `PROCESS_ERROR`；真实模型有时无视 API 的严格结构要求，返回 Markdown 顶层数组，或在函数级源码缺少合约声明时填入 `Unknown`。本次为模型提示加入精确对象字段、固定空数组格式、绝对行号和从完整源码读取的所属合约名；无效输出仍是失败与未决，新增具体校验原因及仅保存在 `.local/audit-runs/<运行编号>/raw-response.txt` 的原文诊断。对需要项目依赖的源码，Slither 明确记为 `SKIPPED`，没有将工具缺失、无告警或 D2 未知解释为安全，也没有伪造工具结果。

真实单次复测 `RE-INFINITY-001`：运行 `f99d443b5ce543c085b323fb75bff881`，状态 `COMPLETED`、模型用量 1415/12 token、Slither `SKIPPED`、D2 `UNKNOWN`。真实 HTTP 批量编号 `454ae9bd0efc4cb8afe2a68c033b3725`，三验证目标 × 三策略共九次计划请求，完成 8、失败 1、未知 9；失败项为 `AC-ASE-040 × D1` 的 `MODEL_OUTPUT_INVALID`（356/292 token），并未重试或计作安全。补充改进后，`AC-ASE-040 × D1` 的单次运行 `68911004ad154215b3061bb358e2046e` 通过结构校验并产生一条初步假设，D2 仍为 `UNKNOWN`。这些结果仅证明真实调用和报告链路可运行，不能证明 D1 检测增益或审计结论正确。

补充验收的离线回归：`mvn clean verify` 通过，Java 51 项；Python 137 项全部通过；`node --check tools/experiment/local_ui/agent.js` 通过。自动化测试均未调用真实 API 或 Milvus；上述真实调用属于单独的人工授权冒烟。

重放命令：

```bash
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from batch_compare import replay_batch; print(replay_batch(Path(".local/audit-batches"), "454ae9bd0efc4cb8afe2a68c033b3725")["denominators"])'
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from audit_run import replay; r=replay(Path.cwd(), "68911004ad154215b3061bb358e2046e"); print(r["status"], r["model"]["conclusion"], r["d2"]["verdict"])'
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
node --check tools/experiment/local_ui/agent.js
```

以下原始 S6 验收段落记录变更前状态，保留供追溯；当前运行入口以本补充段落为准。

日期：2026-10-07。所有新增自动化测试完全离线；本机 Milvus 与 HTTP 冒烟另列。**本轮没有调用真实付费 API，也没有产生 D1 效果提升结论。**

### Milvus 清理与当前知识

清理前核对正式指针 `.local/d1-kb-snapshots/active.json` 与工程指针 `.local/mvp-kb/active.json`，只删除无活动指针引用的三个旧集合：`mvp_b51c012b788548a6bca40e3ca91d67ae`、`s1b_2f8522116d6b43e693092c303947be6a`、`s1b_612ad26b068c4b64842463a633d6d1ba`。历史本机运行报告没有删除；旧集合的数据库查询不能再回放。

再次经 Milvus REST `collections/list` 查询，仅剩：

- `s1b_a6741615b74240909978e25ae2264476`：当前正式知识，快照 `5381e15f60729bf4e475572f0717e911d316e4754a17f9d0cf74cf341a3d76c3`，`active_snapshot` 完整读回通过，六条向量对应三个真实补丁对。
- `mvp_ec838f133828429f8b9fc0f53a1b2948`：仍被工程 MVP 活动指针引用的演示集合，三条工程片段，不能当作正式科研知识。

当前正式清单依旧是三个知识组与三个独立验证组；[S5 来源与泄漏报告](VERIFICATION.md#s5-verification)给出项目、事件、补丁对和近克隆隔离证据。本轮没有将验证源码、合成演示库或未经核对的数据批量导入 Milvus。

### 批量对照与页面

[批量编排](../../../../tools/experiment/batch_compare.py)在开始前持久化计划，按目标与策略逐项写入 `samples.jsonl`；每项调用前先持久化 `STARTED`。续跑跳过已完成项，将“曾开始但未落结果”的项记为失败且未知，不自动重发。断裂的末尾 JSONL 行可恢复，完整损坏记录不静默放行。计划固定快照、来源摘要、组合与提供方；单次结果若绑定不同快照或源码则拒收。

本机 [批量审计工作台](http://127.0.0.1:8769/agent.html)支持选择三个独立验证目标和三种策略、预览上界、运行离线批量对照、查看按策略对比及下载 JSONL；单样本预览与显式真实运行入口保留。真实批量计划可展示端点、模型、最多九次请求、18432 输出 token、90000 输入 UTF-8 字节，但输入 token 与费用上界仍为 `null`，因此 HTTP 返回 422，页面不允许启动。字节数不充作完整提示 token 公平。

最新实际本机 HTTP 冒烟编号：`f9ca2a32f8fb4a6abc1ac4b005cba092`，逐样本报告位于 `.local/audit-batches/f9ca2a32f8fb4a6abc1ac4b005cba092/samples.jsonl`，对应单次审计详情在 `.local/audit-runs/<运行编号>/`。目标为 `AC-ASE-040`、`RE-INFINITY-001`、`RE-JPEGD-001`，策略为 `DENSE`、`FIELD_FILTER`、`D1`，全部绑定同一正式快照。同目标三策略的候选池摘要无冲突。九项完成、失败 0、未知 9；入选证据计数分别为向量召回 4、字段过滤 3、D1 0。输入／输出 usage 均为 `null`，检测召回、检索 Recall@K、nDCG 等均为 `null`。这是固定空假设的工程报告，不能作为模型检测性能。

UI 浏览器验收已确认：页面显示三个验证目标、三策略选择、批量计划上界、历史报告，以及“完成 9／未知 9”的策略对比表和 JSONL 下载链接。真实运行未点击。

### 离线验证与重放

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
node --check tools/experiment/local_ui/agent.js
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from batch_compare import replay_batch; import json; print(json.dumps(replay_batch(Path(".local/audit-batches"), "f9ca2a32f8fb4a6abc1ac4b005cba092")["denominators"], ensure_ascii=False))'
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from milvus_rest import MilvusRestIndex; from snapshots import active_snapshot; index=MilvusRestIndex("http://127.0.0.1:29531"); print(index.request("collections/list", {})); print(active_snapshot(Path(".local/d1-kb-snapshots"), index))'
```

结果：Maven 构建成功，Java 47 项；Python 136 项；JavaScript 语法检查通过。新测试覆盖计划上界、批量逐项落盘、真实批量拦截、接口读回、来源漂移、断点续跑防重复和残缺 JSONL 尾行恢复。Milvus 与页面冒烟需本机服务及既有模型权重，未纳入离线自动测试。

### 研究判断

经 [文献规模与实验设计](research/S6_RESEARCH_DESIGN.md)核对，当前知识只有三组项目事件，重入知识仅一组；三个验证目标上 D1 尚未选出适用完整对比配对。人工目标—案例标签、可靠安全负例、真实 tokenizer 和完整提示预算仍缺。**D1 只能保留为待证伪方法，当前不具备宣称增益或开展付费批量效果实验的条件。**下一步按项目事件扩充经审真实补丁对，先解决条件事实覆盖，再冻结标签与 token 公平方案。

<a id="s7-verification"></a>

## R1-S7 公开语料候选采集与隔离入库

日期：2026-10-07。此步骤完成数百级**待审候选**的本地采集和 Milvus 入库；尚未完成数百级**正式 D1 知识案例**。集合名称、页面入口及计数单位必须分开理解。

### 来源与筛选

| 来源 | 固定版本与本地位置 | 本轮实际使用 | 准入限制 |
| --- | --- | --- | --- |
| [AutoMESC 原始仓库](https://github.com/majdsoud/AutoMESC-Framework) | `a143612ca5bfa52109367750a034ae4c9b66803d`；`.local/dataset-candidates/automesc/` | 2,379 个提交、6,821 条 Solidity 文件改动；其中 5,588 条有前后片段。按改动行关键词、文件类型和项目去重选取 300 个项目的 300 组成对片段，访问控制／重入各 150 组。 | 这是自动挖掘的改动片段，不是完整合约；关键词类别是候选提示，不是漏洞真值；提交的“已检查”字段不等于独立安全修复审核。 |
| [FORGE-Curated 原始仓库](https://github.com/shenyimings/FORGE-Curated) | `bace532526e5a978a5b175964d1ce769c577362c`；`.local/dataset-candidates/forge-curated/flatten/vfp-vuln/` | 固定的 302 条中高危漏洞—文件条目中，筛出 142 条与访问控制／重入关键词相关的条目，涉及 94 份报告名称、225 份受影响源码文件。 | 条目含提取后的审计描述和源码，未提供逐条真实修复对；项目方仍在人工核对漏洞与代码位置。不能把源码条目当作安全防御案例。 |

AutoMESC 四份 CSV 的 SHA-256 固定在 [候选采集脚本](../../../../tools/experiment/r1_candidate_corpus.py) 中。FORGE-Curated 的 Git 修订在运行时校验。本机原始数据与候选结果保存在被 Git 忽略的 `.local/dataset-candidates/`；提交的代码和文档不含原始数据或模型密钥。选取后的逐案记录在 `r1-pending/automesc-selected.json`、`forge-selected.json`，嵌入向量在 `vectors.json`。

新机器上可按固定修订重新取得原件；下载后由脚本再次校验 CSV 摘要与 FORGE Git 工作目录：

```bash
mkdir -p .local/dataset-candidates/automesc
for name in commits_exported_data_.csv file_change_exported_data_.csv fixes_exported_data_.csv repository_exported_data_.csv; do curl -fL "https://raw.githubusercontent.com/majdsoud/AutoMESC-Framework/a143612ca5bfa52109367750a034ae4c9b66803d/AutoMESC%20data/20188256/$name" -o ".local/dataset-candidates/automesc/$name"; done
git clone --filter=blob:none --sparse https://github.com/shenyimings/FORGE-Curated.git .local/dataset-candidates/forge-curated
git -C .local/dataset-candidates/forge-curated checkout bace532526e5a978a5b175964d1ce769c577362c
git -C .local/dataset-candidates/forge-curated sparse-checkout set flatten/vfp-vuln
```

### Milvus 实际写入

本地固定模型 `BAAI/bge-small-en-v1.5` 修订 `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` 离线生成 384 维向量。AutoMESC 每组保留改动前和改动后两条，共 600 条；FORGE 每个筛选条目一条，共 142 条。独立集合 `r1pending_3ba8dd13979d18e0087177521ce5583e` 共 **742 条向量**；逐条读取正文、向量和 ID 与本地输入完全一致，唯一 ID 742 个。[本机收据](../../../../.local/dataset-candidates/r1-pending/receipt.json)记录完整身份和计数。二次运行按内容身份识别已写入条目，完整读回，不产生重复项。

每条记录均为 `reviewStatus=PENDING`，AutoMESC 的 `patchStatus=UNVERIFIED`，FORGE 的 `patchStatus=MISSING`。这个集合**不是正式知识快照**，未写入 D1 案例目录，也没有替换 `.local/d1-kb-snapshots/active.json`。正式活动集合仍是 `s1b_a6741615b74240909978e25ae2264476`，内容是已审的三个补丁对、六条向量。当前页面只使用正式集合；742 条待审向量不会悄悄进入实验。

### 谱系与测试集检查

本轮没有把仓库中的 SmartBugs Curated 或 SolidiFI-benchmark 输入候选知识集合。两套原始测试来源本机共有 493 份 `.sol` 文件、486 个不同字节摘要；候选 742 条文本与正式六份原件、上述测试文件的完全字节碰撞均为 0。对 FORGE 的 225 份完整受影响源码与这 493 份测试源码再做归一化五元 token 集合 Jaccard `≥0.85` 筛查，命中 0。AutoMESC 仅有局部 diff，**不能**据此完成近克隆、漏洞事件与项目级隔离证明；FORGE 的报告名也不能独立证明项目组不重合。两套原始数据作为正式验证／测试集还需按漏洞事件和补丁分组、核对标签，锁定集不得用于调参。

### 验证与页面操作

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from milvus_rest import MilvusRestIndex; from snapshots import active_snapshot; print(active_snapshot(Path(".local/d1-kb-snapshots"), MilvusRestIndex("http://127.0.0.1:29531")))'
PYTHONPATH=tools/experiment HF_HUB_OFFLINE=1 .local/d1-embed-venv/bin/python tools/experiment/r1_candidate_corpus.py --automesc-dir .local/dataset-candidates/automesc --forge-dir .local/dataset-candidates/forge-curated/flatten/vfp-vuln --output-dir .local/dataset-candidates/r1-pending --model-dir .local/d1-embedding-model --milvus-url http://127.0.0.1:29531
```

验证结果：Maven 51 项 Java 测试、Python 141 项离线测试通过；Milvus 对待审集合 742 条全量读回通过，正式活动指针和六条正式知识读回通过。自动化测试使用内存 Milvus 夹具，不依赖真实数据库、模型 API 或付费服务。本轮真实模型请求为 0。

浏览器打开 [Attu](http://127.0.0.1:3000) 可以在 `r1pending_...` 查看 742 条待审向量；`s1b_...` 才是页面正在使用的正式知识。[审计工作台](http://127.0.0.1:8769/agent.html)现在直接显示“正式知识 6 条向量／待审 742 条向量”的区别。先选择三个独立验证目标和三种检索策略，运行模式选“离线工程演练”，点击“查看运行计划”后再点“开始批量对照”；页面会显示逐策略结果和 JSONL 下载。离线模式仅验证检索、保存与回放，模型结论为固定空假设。要检查真实模型工程链路，可明确选择“真实模型批量运行”并再次查看计划；这会调用付费 API，结果仍只能作为当前六条正式知识的工程观察，不能解释为这 742 条待审资料带来的 D1 增益。

本机 HTTP 实际离线对照编号 `4bafd8746da74a128c16a0ec36c75056`；结果在 `.local/audit-batches/4bafd8746da74a128c16a0ec36c75056/samples.jsonl`。九项完成、失败 0、未知 9；DENSE／FIELD_FILTER／D1 入选证据数为 4／3／0，候选池冲突为 0。输入及输出 token、检测召回、检索 Recall@K 和 nDCG 保持 `null`，不报告效果提升。

### 尚未完成的研究准入

本轮目标中的“数百级正式知识库、足以验证 D1 效果”仍未达成。下一步优先从这些候选中核对真实审计报告、精确修复前后源码和实际补丁，逐事件独立标注目标—案例适用性与正反证据，并将同项目、同事件和近克隆与测试集分开。还须修复 D1 对函数级事实和跨函数时序的覆盖不足、冻结完整提示 token 预算。正式快照构建器当前会拒绝这批 `PENDING` 条目；不能通过把候选数量或代码块数量说成“已审核安全案例”来绕过门禁。

<a id="s8-auto-experiment-verification"></a>

## 自动标注知识快照与批量对照验收

### 数据与快照

本轮复用本机固定的 AutoMESC 原始候选收据，按项目保留 300 组改动前后片段：访问控制 150 组、重入 150 组，共 600 条 384 维向量。自动差异规则识别 49 组有明确保护特征的改动；其余 251 组仅能证明代码发生变化，供带有显式缺口提示的软对比检索使用。`review_status=AUTO_LABELED`、`evidence_tier=HEURISTIC`、来源提交、源码摘要和规则版本写入快照清单，未把自动标签伪装成逐案人工审核。

活动快照 `4566ccb54e07d7a4fec54e5dadfe0d0ae9b508b5565c1022154598d7b94e1820`，Milvus 集合 `s1b_5e2e9fa91d2d4433b0a7ddf12cffb256`。发布前已对 600 条 ID、正文和向量逐页完整读回，之后才原子切换 `.local/d1-kb-snapshots/active.json`。旧快照和独立 `r1pending_` 候选集合仍保留；FORGE 142 条单侧资料没有明确修复对应项，本轮未转作正反例。

验证目标是 SmartBugs Curated 的 49 条公开漏洞样本（访问控制 18、重入 31），加本机 OpenZeppelin 衍生安全函数 4 条，共 53 条。目标与 AutoMESC 知识的项目交集为 0；完整源码最大近克隆相似度为 0.815789，低于当前 0.85 排除阈值。安全对照只覆盖 4 个访问控制函数，类别明显不平衡。漏洞类型作为**已知定向审计任务**传给三种策略，是否有漏洞只在评估器中使用；因此这里不能代表未知类别的通用合约审计。

### 三策略与指标口径

三策略复用同一快照、同一个按目标固定的候选池及 2048 字节证据上下文。向量基线按分数入选；字段基线仅按已知目标漏洞类别字段过滤，不依赖 D1 条件绑定；D1 优先选择显式条件配对，缺失时按同一改动对两侧的向量分数与差异重排，软配对明确标注未经修复证据核验。输出报告逐项保存候选池摘要、入选 ID、模型结论、错误类别、用量和耗时。

`TP/FP/FN/TN` 只统计实际结构化模型的“报告漏洞／未报告发现”，后者不表示源码已被证明安全。失败、超时、解析错误和离线空假设为 `UNKNOWN`，不进入混淆矩阵，但始终保留分母。缺失 usage 为 `null`。`类别命中@K` 与 `类别召回@K` 只检查入选知识的漏洞类别与目标标签是否一致，**不是**人工标注的目标—案例相关性，也不是论文级检索 Recall@K。完整提示的 tokenizer 公平尚未验证，报告显示各策略实际 token，不能仅凭 UTF-8 字节上限宣称等 token 对照。

### 工程复现

在仓库根目录运行：

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
PYTHONPATH=tools/experiment python3 tools/experiment/auto_d1_snapshot.py --activate
HF_HUB_OFFLINE=1 PYTHONPATH=tools/experiment .local/d1-embed-venv/bin/python tools/experiment/benchmark_cli.py --mode offline
HF_HUB_OFFLINE=1 PYTHONPATH=tools/experiment .local/d1-embed-venv/bin/python tools/experiment/local_ui.py --port 8769
```

在 `http://127.0.0.1:8769/agent.html` 的“公开数据集批量审计”中选目标、三策略和运行模式，先查看计划，再启动。页面逐项刷新进度大表；结束后在“三策略评测报告”查看混淆矩阵、检索类别命中、token 与耗时，并下载完整 JSONL 和含模型结果、证据 ID 的 CSV；同一文件也保存在 `.local/auto-benchmark-runs/<批次编号>/`。重新执行相同批次编号时，已开始的模型请求不会自动重发。

离线完整批次 `25a630abae6141959a8ac789e812474e`：53 目标 × 3 策略，完成 159、失败 0、UNKNOWN 159、同池冲突 0；类别命中率向量 43/49、字段过滤 49/49、D1 49/49。离线模式没有真实审计结论，Precision/Recall/F1 保留空值。真实模型的完整批次结果另在下方记录。

`mvn clean verify` 通过，Java 56 项；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` 通过，Python 166 项；`node --check tools/experiment/local_ui/agent.js` 通过。另通过本机 HTTP 对页面目标、计划、启动、进度回放以及 JSONL/CSV 下载做了离线冒烟：单个安全函数 × 三策略，完成 3、失败 0、UNKNOWN 3。

### 真实模型批次

本机真实模型完整批次为 `e2d55443e02549a386bdd93f222998c6`，同一快照与每目标同一候选池，计划 159 项、有效结构化结果 147、失败/UNKNOWN 12、未执行 0、候选池冲突 0。失败中结构化输出无效 10 项、模型调用错误 2 项，均未折算安全结论。逐项 `samples.jsonl`、`samples.csv`、`summary.json` 位于 `.local/auto-benchmark-runs/e2d55443e02549a386bdd93f222998c6/`；页面历史列表也可打开与下载。

| 策略 | 有效／计划 | TP | FP | FN | TN | Precision | Recall | F1 | 平均输入／输出 token | 平均模型耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 向量召回 | 48／53 | 40 | 1 | 5 | 2 | 0.976 | 0.889 | 0.930 | 1363.6／150.8 | 4635 ms |
| 简单字段过滤 | 50／53 | 41 | 3 | 5 | 1 | 0.932 | 0.891 | 0.911 | 1303.4／170.5 | 4927 ms |
| D1 对比检索 | 49／53 | 40 | 1 | 7 | 1 | 0.976 | 0.851 | 0.909 | 1186.8／155.6 | 4593 ms |

各行有效分母不同，因此主要参考**三策略共同有效的 43 个目标**：向量召回 TP 37、FP 1、FN 4、TN 1，F1 0.937；字段过滤 TP 36、FP 2、FN 5、TN 0，F1 0.911；D1 TP 37、FP 1、FN 4、TN 1，F1 0.937。D1 相对向量召回在 3 个目标上纠正结果，同时在另外 3 个目标上变错，整体没有净提升；相对字段过滤为 4 个目标纠正、2 个目标变错。这是单轮、类别已知、标签未独立复核且安全对照仅 4 个的探索结果，**不能宣称 D1 真实改进合约审计**。下一步应扩充独立安全对照、补人工目标—案例相关性标签、固定完整提示 tokenizer 预算并做多次重复，再决定 D1 保留或收窄。

运行期间曾有两轮被主动中止的批次，其中一轮与 Maven 清理 JAR 重叠，造成局部启动失败；它们保留原始日志但未混入上表。上表只来自重新固定构建产物后的完整批次。

<a id="s8-nomic-verification"></a>

## Nomic 对照与结构化输出修复验收

2026-10-09。工程验证完成，已执行本机真实模型实验。最终 Nomic 原文重放报告为 159 项有效、失败／UNKNOWN 0；旧 BGE 原始记录保留。D1 在本轮仍未超过向量召回，不能宣布研究改进。

### 知识、模型与来源

- 同一 AutoMESC 300 组改动对、600 条文本，源目录 `.local/dataset-candidates/r1-pending`；原表、提交与来源摘要沿用 [自动知识验收](VERIFICATION.md#s8-auto-experiment-verification)。49 组明确防御差异、251 组软配对；全部为自动标注，未伪装成逐案证实的安全修复。
- BGE 活动快照 `4566ccb54e07d7a4fec54e5dadfe0d0ae9b508b5565c1022154598d7b94e1820`，集合 `s1b_5e2e9fa91d2d4433b0a7ddf12cffb256`，384 维；原目录 `.local/d1-kb-snapshots` 保持不变。
- Nomic 活动快照 `a6d70058bb93a26505def7878553d01e7667248d387f41a101a4ff2f71bd36db`，集合 `s1b_nomic_bddddf9a77d34aa1b898409789453ec8`，768 维，独立目录 `.local/d1-nomic-snapshots`。两个集合均完整读回 600 条且内容校验一致。
- Ollama：`http://127.0.0.1:11434/api/embeddings`，`nomic-embed-text:latest`，摘要 `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`。文档用 `search_document: `，查询用 `search_query: `，向量经有限数值、维度、非零和归一化检查。
- 编码断点 `.local/d1-nomic-embeddings/vectors.jsonl` 持久化 600 项；已完成项再次构建不重复编码。完整文本仍存快照，截取记录在回执。
- 目标仍为独立 SmartBugs 49 个公开漏洞源码与本机 4 个 OpenZeppelin 安全对照函数：53 目标 × DENSE／FIELD_FILTER／D1。知识—测试源码摘要、项目和近克隆检查沿用原登记，跨项目重叠 0，最大近克隆相似度 0.815789，小于 0.85。目标类别对所有策略公开，布尔真值仅进入评估。

#### 窗口事实

本机 Nomic 元数据与实际拒绝行为显示有效窗口为 **2048 token**；即使请求配置 `num_ctx=8192`，长输入仍返回窗口超限。本轮不是 8192 token 实验。[Ollama 官方模型页](https://ollama.com/library/nomic-embed-text)同样标为 2K；[Nomic 原模型说明](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)说明文档／查询应使用各自任务前缀。
本地 BGE tokenizer 实测：600 条中 250 条超过 512 token，最长 2891 token；Nomic 本机编码回执：17 条文档被截取，53 个查询均未截取。因两模型分词器不同，不能把字符截取回执当作相同 tokenizer 的精确 token 数。更少截取说明输入覆盖变广，不单独证明审计提升。

### 结构化输出与重试

- Jackson 前提取首尾最外层对象，接受 Markdown 围栏／前后说明；仍拒绝重复键、多对象和不可解析正文。必需语义字段存在即可，附加标题／严重程度不造成失败。
- 整数行号或可解析数字字符串均可；溢出、范围错误仍拒绝。`evidenceIds` 缺失或 null 视为无引用，未知／重复 ID 仍拒绝。
- 合约名按源码声明归一化，函数支持末尾括号、大小写、实际构造函数别名与无名回退函数。先核对真实声明及其行范围，避免把 `Missing.missing` 普通函数误当作构造函数。完整合约允许真实声明的不同函数；函数片段仍限制在目标范围。
- 每条假设分别核对。保留通过校验的真实发现，被拒绝项另记 `rejectedHypotheses`；部分拒绝显示 `PARTIAL_HYPOTHESES_REJECTED`。全部拒绝仍 FAILED／UNRESOLVED，不能变成安全。
- 网关对 HTTP 429、连接闪断／EOF 仅重试一次，等待 1 秒；SDK 重试关闭。认证／永久错误不重试，解析错误不重新调用模型。实际 `requestAttempts` 落盘，完整真实批次实测 159 次尝试，无重试触发。
- CLI 原文诊断保留；自动批次原文另存 `.local/auto-benchmark-diagnostics/`，记录路径与权限。`--replay-response` 完全离线；派生结果记录原始批次、正文摘要、解析 JAR 摘要和追加请求 0。原用量／耗时不会被重放清零，缺失 usage 仍为 null。

### 运行证据与分母

- Nomic 离线批次 `aee62962864c45e5816b364f08272f28`：159 完成、失败 0、UNKNOWN 159、池冲突 0。离线空假设不作为安全预测。
- 最近 BGE 真实基线 `69cc13d23d34414a85f8536769728c4f`：159 单元、149 有效、10 解析失败／UNKNOWN。之前的 `e2d55443e02549a386bdd93f222998c6` 等记录也未覆盖。
- Nomic 原始真实批次 `c2df251864914b3eb84f5038b08f4ef1`：159 次 HTTP 尝试，154 有效、5 解析失败／UNKNOWN。原始 JSONL 不修改。
- 最终原文重放 `5e7a69b3a18f4cfa8b3f75a9f17d8a42`：恢复 5 个解析失败，159 有效、失败 0、UNKNOWN 0、池冲突 0，追加模型请求 0；其中一项保留有效 withdrawBalance 假设，拒绝无目标声明的攻击者 fallback 附加假设。
- 修复前停止的试跑 `d7039f1e5124449184f755e29ffe2b7e` 保留：持久化 11 个结果，12 个 STARTED，其中最后一个调用未落盘，供应商是否接受及用量未知；不计入正式对照。不能将总调试开销写成只有正式批次 159 次。

### 横向描述性对比

下面全量指标只对各策略有效预测计算，失败单列；BGE 与 Nomic 的有效分母不同。耗时为逐单元模型 CLI 墙钟时长，含 Java 启动与调用，未计入预先缓存的嵌入／检索时间。Token 均来自供应商 usage。

| 嵌入 | 策略 | TP/FP/FN/TN | Precision | Recall | F1 | 平均输入/输出 token | 平均审计秒 | 失败 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| bge | DENSE | 44/1/3/3 | 0.9778 | 0.9362 | 0.9565 | 1343.0/162.6 | 4.660 | 2 |
| bge | FIELD_FILTER | 41/0/5/2 | 1.0000 | 0.8913 | 0.9425 | 1318.8/152.0 | 4.499 | 5 |
| bge | D1 | 40/1/6/3 | 0.9756 | 0.8696 | 0.9195 | 1191.3/156.6 | 4.561 | 3 |
| nomic | DENSE | 48/0/1/4 | 1.0000 | 0.9796 | 0.9897 | 1381.3/165.0 | 4.742 | 0 |
| nomic | FIELD_FILTER | 48/0/1/4 | 1.0000 | 0.9796 | 0.9897 | 1363.1/164.4 | 4.881 | 0 |
| nomic | D1 | 45/0/4/4 | 1.0000 | 0.9184 | 0.9574 | 1276.7/146.6 | 4.212 | 0 |

六路共同有效目标为 44 个（42 个漏洞、2 个安全对照）：

| 嵌入 | DENSE F1 | FIELD_FILTER F1 | D1 F1 |
|---|---:|---:|---:|
| bge | 0.9756 | 0.9500 | 0.9250 |
| nomic | 1.0000 | 0.9880 | 0.9756 |

总 token：BGE 输入 204215／输出 24974，Nomic 输入 213120／输出 25229。Nomic 类别代理命中 DENSE 44/49、FIELD_FILTER 49/49、D1 49/49；没有人工相关性标签，不能将代理命中写成真实相关性 Recall 或 nDCG。

相对 BGE，Nomic 的入选片段在 DENSE 的 53/53、FIELD_FILTER 的 52/53、D1 的 38/53 目标上变化；嵌入模型改变了实际检索上下文。Nomic 全量 D1 F1 0.9574，低于 DENSE／FIELD_FILTER 的 0.9897；六路共同分母下仍低于 DENSE。**D1 保留为工程对比策略，科研主张继续收窄，当前无其相对强基线改善的证据。**
旧 BGE 与新 Nomic 同时存在解析器／提示修复差异，且仅一次重复、4 个安全样本、启发式补丁标签、完整提示 token 未等额固定；即使 Nomic 表面指标更高，也不能将变化单独归因于长上下文嵌入。这些事实影响结论，不阻止页面试跑。

### 验收与重放命令

全量验证：Java 66 项通过；Python 175 项通过；`node --check` 通过。测试均为离线夹具，无真实 API／Milvus 依赖；真实实验独立执行。日志 `.local/nomic-maven-verify.log`、`.local/nomic-python-tests.log`、`.local/nomic-real-final.log`、`.local/nomic-reparse.log`。

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
node --check tools/experiment/local_ui/agent.js
# 构建重放已有 600 向量，不覆盖 BGE；已完成项跳过
PYTHONPATH=tools/experiment python3 tools/experiment/nomic_snapshot.py --activate
# 离线原文重放；指定已有输出编号时结果一致则跳过
PYTHONPATH=tools/experiment python3 tools/experiment/reparse_benchmark.py --batch-id c2df251864914b3eb84f5038b08f4ef1 --output-id 5e7a69b3a18f4cfa8b3f75a9f17d8a42
# 重算对比表，不调用模型
PYTHONPATH=tools/experiment python3 tools/experiment/embedding_compare.py --bge-batch 69cc13d23d34414a85f8536769728c4f --nomic-batch 5e7a69b3a18f4cfa8b3f75a9f17d8a42
# 启动本机工作台
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=tools/experiment .local/d1-embed-venv/bin/python tools/experiment/local_ui.py --port 8769
```

真正新增一组调用的命令为 `PYTHONPATH=tools/experiment python3 tools/experiment/benchmark_cli.py --embedding-profile nomic --mode real`；仅显式选择真实模式才付费，正常 159 次、限流／断连情况下最多 318 次尝试。不要在调用过程中运行 Maven clean 或替换 JAR。

页面 `http://127.0.0.1:8769/agent.html`：公开数据集区域选 Nomic → 53 目标 → 三策略 → 运行模式 → 查看计划 → 启动。只查看现有结果时，在历史中选择 `5e7a69b3`（nomic／原文重放），可见三策略指标、53 目标共同有效对比、逐项记录和 JSONL／CSV 下载。原始批次 `c2df2518` 显示 5 个失败，与派生恢复结果分别保留。

本机最终逐样本目录 `.local/auto-benchmark-runs/5e7a69b3a18f4cfa8b3f75a9f17d8a42/`；横向大表 `.local/embedding-comparison/comparison.csv`，完整横向 JSON 为同目录 `comparison.json`。文档与代码可同步，原始本机报告和模型文件继续留在本机。

<a id="s8-verification"></a>

## R1-S8 批量准入与正式对照阶段记录

后续已按用户新增授权将 300 组 AutoMESC 改动对作为**自动标注**知识层激活，并打通数据集标签下的三策略批量审计。当前状态与重放证据见[自动标注知识快照与批量对照验收](VERIFICATION.md#s8-auto-experiment-verification)；以下段落保留此前探索阶段的历史状态。

### 2026-10-08 探索性数百条知识检索补充

按用户要求，已在**不激活正式快照**的前提下，对 `r1pending_3ba8dd13979d18e0087177521ce5583e` 中的 742 条待审向量完成 Milvus 全量读回，并将其作为探索性 D1 候选库。来源为 AutoMESC 300 组改动前后片段（600 条）和 FORGE-Curated 142 条审计参考。两者原始准入状态均仍为 `PENDING`。对 AutoMESC 仅用可复核的句法差异暂定出 12 组可对照条件（重入修饰器 6 组、调用者检查 6 组）；其余 288 组和 FORGE 条目不伪装成安全反例。

从本机 SmartBugs Curated 文档提取访问控制 18、重入 31 个公开源码作为**探索目标**。按来源项目、源码字节和归一化 5-gram 的 Jaccard／片段包含度筛查；入选目标对待审库的最大相似度为 0.815789，低于预设 0.85 排除阈值。它们只有文档头给出的漏洞行标签，未取得独立盲审的目标—案例适用性标签；不能作为锁定测试或真实安全负例。SolidiFI 注入样本本轮没有混入这一组。

三策略在每个目标上共用固定候选集合、查询向量和候选池；Milvus 返回分数与本地固定向量余弦逐条核对，召回暂定配对时补齐另一侧。每条候选统一截取前 700 字符作为检索展示片段，检索上下文统一限制为 2048 UTF-8 字节、最多 4 条案例；这**仍不是完整提示 token 公平**。逐样本写入 JSONL，重启会跳过已有完成、未知和失败项；失败不会映射为安全。`FIELD_FILTER` 不会把无条件、未定性的参考条目计作适用证据。

本机批次 `ae7c3a073454646ea1a0701dfca5b097`：计划 49、完成检索 32、失败 0、事实无法唯一绑定而未知 17。已完成目标中，向量召回 32 个目标有入选片段，简单条件过滤 3 个，D1 仅 1 个目标得到暂定正反配对（访问控制）；D1 重入配对入选为 0。逐样本记录、目标来源/摘要/隔离字段和三策略入选 ID 位于 `.local/d1-exploratory-runs/ae7c3a073454646ea1a0701dfca5b097/` 的 `plan.json`、`results.jsonl`、`report.json`。检测召回率、精确率、D1 改进均为 `null`，因为本轮**没有运行大模型审计，也没有可靠的独立适用性真值**。这轮直接说明目前的 742 条虽达到数量级，但可绑定的对比知识过少，不能据此声称 D1 改善审计。

重放命令（固定本机 BGE 权重与 Milvus；只读向量库、零付费模型请求）：

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
node --check tools/experiment/local_ui/agent.js
HF_HUB_OFFLINE=1 PYTHONPATH=tools/experiment .local/d1-embed-venv/bin/python tools/experiment/exploratory_probe.py
PYTHONPATH=tools/experiment python3 tools/experiment/local_ui.py --port 8771
curl --noproxy '*' -fsS http://127.0.0.1:8771/api/agent/exploratory
```

验证结果：Maven 54 项、Python 155 项、JavaScript 语法检查通过；实际批次 49 项逐样本保存、失败 0；页面 API 已读回同一批次与 `null` 效果指标。页面地址为 `http://127.0.0.1:8771/agent.html`，顶部“公开样本的三策略检索对照”可查看记录或点击重跑。正式活动快照仍为 `5381e15f60729bf4e475572f0717e911d316e4754a17f9d0cf74cf341a3d76c3`，对应 3 组／6 条经审知识；探索结果不改变正式研究结论。

更新：2026-10-08。本阶段**未完成批量转正或正式 D1 效果实验**。当前活动知识快照仍为 3 个已审事件、6 条向量，独立验证仍为 3 个事件。以下是已完成的工程准备和可复核阻塞。

### 候选逐项核对

执行：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/candidate_admission_queue.py --candidate-dir .local/dataset-candidates/r1-pending --output .local/dataset-candidates/r1-pending/admission-queue.json
```

逐项清单的摘要为 `951b953ab5912580db3d7d01898b1e32ac162e3d4ec879d53492a0b2595f8b4c`。442 组候选对应 742 条向量：AutoMESC 300 组，FORGE-Curated 142 条。准入 0 组，待审 442 组；标签提示中访问控制 279 组、重入 163 组，**只是关键词候选，不是真值**。清单逐项记录来源版本、定位链接、正文摘要和缺失证据，不复制完整源码；收据数量与清单不符会拒绝生成。AutoMESC 仅有前后局部片段，缺独立漏洞报告、完整前后源码、安全修复审核与近克隆组；FORGE 有报告／源码条目，但缺可核实修复补丁。它们不能直接复制到 `s1b_` 集合。

另抽查 [Proof-of-Patch 固定版本](https://github.com/ASSERT-KTH/Proof-of-Patch/tree/eca2a566326d7636665c45c670698e05ea12a3ac) 的 [AI Arena 077](https://github.com/ASSERT-KTH/Proof-of-Patch/tree/eca2a566326d7636665c45c670698e05ea12a3ac/findings/077)：本机原版 `MergingPool.sol` SHA-256 为 `b0c5b90a1f1ec659047238063433f52cc69fa95091df9af76d155f69a75ab5dd`，补丁版为 `3469e4a579bb2435b33a65bb592c34f4402d4720e05bb089944f11fc86faa7c8`。原始 `claimRewards` 未带重入锁，补丁增加 `ReentrancyGuard` 与 `nonReentrant`。这是真实修复线索，但当前 D1 成对知识契约仅支持重入的“状态写入移到外部调用之前”；该补丁采取重入锁，不能伪造成现有条件见证。本项保留待审，不作为新增正式知识。Proof-of-Patch 的 001、041、042、054、070、098 等条目虽然有访问控制或重入元数据提示，原始文字描述分别涉及上限、不正确索引、预言机更新、转账／无代码地址和暂停问题；不能凭类别字段转正。

进一步核对 [Proof-of-Patch Cooler 049](https://github.com/ASSERT-KTH/Proof-of-Patch/tree/eca2a566326d7636665c45c670698e05ea12a3ac/patches/049)：其本地补丁确实给 `rollLoan` 增加调用者检查；[Sherlock 原始问题 #200](https://github.com/sherlock-audit/2023-08-cooler-judging/issues/200) 被标为重复报告，[主问题 #243](https://github.com/sherlock-audit/2023-08-cooler-judging/issues/243) 还描述贷款方抢跑更换条款的路径。而元数据指向的[维护者 PR #54](https://github.com/ohmzeus/Cooler/pull/54) 将 `rollLoan` 整体替换为另一套延长贷款流程，不能把数据集中的单行检查称为该 PR 的原样修复。因此它也只保留为待审修复线索。

另下载 [CoinFabrik Solidity RnD](https://github.com/CoinFabrik/solidity-rnd/tree/efd709441987a28bd7220d79b2d872f8c7cfa8d9) 的固定修订，仅读取 15 份 `findings.json` 后统计为 171 条 finding、15 个项目组。其中大小写合并后的重入类别只有 4 条、分属 4 个项目；报告中有“最佳实践”而非已证实可利用事件。抽查 Venus `PegStability.sol` 的前后文件，补丁同时升级编译器并重写大段业务逻辑，无法直接把整份差异归因于单个重入 finding。该来源可继续逐项筛选，不能凭 171 条 finding 将向量库扩成正式配对知识。

### 批量入口与本机重放

批量计划不再限制最多 3 个目标，但服务端只接受正式谱系清单中 `validation` 且 `runnable` 的样本；未知、开发或锁定目标仍拒绝。新验证目标可在已审谱系记录中指定 `evaluationFunction`，由源码解析确认函数唯一且满足提示大小限制。页面每策略增加“报告漏洞／未决”原始运行计数，失败、未知、缺失 usage 保持独立。它们不是准确率或 D1 改进指标。

本机活动快照 `5381e15f60729bf4e475572f0717e911d316e4754a17f9d0cf74cf341a3d76c3`、集合 `s1b_a6741615b74240909978e25ae2264476`。通过页面同一 HTTP 接口完成离线批次 `fc014f17f5dc47e3ba16687b7398ecdd`：3 个独立验证目标 × 3 种策略，计划 9、完成 9、失败 0、未知 9、待处理 0，候选池冲突 0；DENSE 入选证据 4、字段过滤 3、D1 0。逐项记录在 `.local/audit-batches/fc014f17f5dc47e3ba16687b7398ecdd/samples.jsonl`，汇总在同目录 `summary.json`，页面“批量历史”可重放。离线模式是固定空假设，不能从这些数值推断检测效果。未提供独立目标—案例适用性标签、真实完整提示 token 公平和经核实安全负例，所以 Recall@K、nDCG、误选率与检测指标继续为 `null`。

验证命令：

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
node --check tools/experiment/local_ui/agent.js
curl -fsS http://127.0.0.1:8769/api/agent/batches/fc014f17f5dc47e3ba16687b7398ecdd
```

结果：Maven 51 项、Python 146 项、JavaScript 语法检查通过。该批次零真实模型请求。D1 当前判断为**暂停效果主张，继续完善数据与适用性标注**；不得把 742 条待审向量转正或称作提升证据。

<a id="s9-verification"></a>

## R1-S9 工程验收记录

日期：2026-10-10。需求来源与范围见 [SPEC](SPEC.md#s9-spec)，实施边界见 [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md#s9-implementation-plan)。工程验证通过；独立复核与 Git 同步状态以 [PROGRESS](../../PROGRESS.md) 为准。科研效果仍未验证，正式发布授权为 NOT_REQUESTED。

### 自动验证

| 命令 | 最新结果 | 原始证据 |
|---|---|---|
| `mvn clean verify` | Java 75 项通过，失败/错误/跳过均 0 | [.evidence/R1-S9/maven.log](../../../../.evidence/R1-S9/maven.log) |
| `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` | Python 245 项通过，无跳过；包含真实 Java 模型与工具网关 | [python.log](../../../../.evidence/R1-S9/python.log) |
| `node --check tools/experiment/local_ui/workbench.js`、`node --check tools/experiment/local_ui/agent.js` | 均退出 0 | 本轮终端运行记录 |
| `java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help` | 退出 0，显示模型/假设/工具/检索入口 | [cli-help.log](../../../../.evidence/R1-S9/cli-help.log) |

全部模型测试仅访问 loopback HTTP，工具使用子进程夹具；没有外部付费模型调用。知识检索冒烟复用已有本机 Ollama/Milvus，不下载模型、不重建知识。

### 逐项验收

| 条件 | 证据与结果 | 状态 |
|---|---|---|
| S9-01：预置与粘贴、结构和事实 | 输入范围/CRLF/同名/同行歧义回归；Chromium 两条输入路径；展示解析限制、CALL/WRITE/CEI | VERIFIED |
| S9-02：固定 Nomic 与 D1 预算 | 复用快照 `a6d70058bb93a26505def7878553d01e7667248d387f41a101a4ff2f71bd36db`，768 维/600 向量；两个上下文 1627/1559 字节；4096 字节边界回归 | VERIFIED |
| S9-03：Java 结构化假设 | 本机 HTTP 实际返回非空 schemaVersion=2；usage 120/40；精确名称优先、歧义拒绝、原始行号、拒绝项未决聚合回归 | VERIFIED |
| S9-04：工具状态与失败 | Java Slither 子进程夹具实际执行，返回 `local-fixture`、源码摘要与 Contract.sol；超时/异常/缺配置/导入依赖回归，失败保留模型结果 | VERIFIED |
| S9-05：六义务与保守裁决 | D2 39 项正反例、来源绑定、类别/位置、权限覆盖和消费入口路径回归；完整保护反驳对应假设，缺证据保留 UNKNOWN | VERIFIED |
| S9-06：透视、报告、历史 | Chromium 六阶段、D1 对照、源码与六项表；下载真实 JSONL，历史仅 GET；原中断记录未重写、重启不重发 | VERIFIED |
| S9-07：同池批量 | 最新单目标×三策略离线运行完成 3、失败 0、未知 3；同池摘要一致；原模型指标、D2 与流水线失败分别展示 | VERIFIED |
| S9-08：本机与输入门禁 | HTTP Host/Origin/重复字段/大小/票据/并发回归；配置重序列化、冻结消费、空白凭证、清理回归；实际响应禁止框架嵌入；文本注入无图片节点 | VERIFIED |

### Chromium 与本机冒烟

当前入口：`http://127.0.0.1:8771/workbench.html`。最后重启的服务加载当前代码；原有 8769 服务保留。

- 预置 EtherStore：`245bea7409f848288ea820b2f87d894a`，六阶段、COMPLETED/UNRESOLVED；[桌面截图](../../../../.evidence/R1-S9/preset-desktop.png)、[浏览器下载报告](../../../../.evidence/R1-S9/preset-report.jsonl)。
- 粘贴权限合约：`3b3d0bdf0b8647be863e86bc0321ca95`，FUNCTION 范围、COMPLETED/UNRESOLVED；注释含 `<img src=x onerror=alert(1)>`，DOM 图片数为 0；六项未知表实测 6 行。[桌面](../../../../.evidence/R1-S9/pasted-desktop.png)、[390px 移动截图](../../../../.evidence/R1-S9/pasted-mobile.png)；页面宽度与窗口同为 390。
- [浏览器控制台](../../../../.evidence/R1-S9/browser-console.log) 无错误；[网络记录](../../../../.evidence/R1-S9/browser-network.log)、[历史读取网络](../../../../.evidence/R1-S9/history-network.log)和[结构化检查](../../../../.evidence/R1-S9/browser-summary.json)保存原始核对结果。历史读取无 POST。
- 最新本机三策略批量：`a132733766974dcb88ddde439a8d686b`；[结果](../../../../.evidence/R1-S9/batch-smoke.json)保留分母、usage 空值和 D2 未知，不计算模型 F1。

### 结论限制

受限结构语法树不是完整 Solidity 编译器 AST，D2 仅核验能够明确绑定的简单直线路径。权限接管的支持要求存在完整公开消费入口，且只有同权限检查及其后的敏感操作；附加检查、权限覆盖、额外调用或不完整入口保留未知。真实工具仍依赖已有编译器与项目依赖，含 import 的单文件目标跳过工具，不自行下载依赖。

六项保护全部支持只反驳相应漏洞假设；HYPOTHESES_REFUTED 和 NO_CONFIRMED_FINDINGS 均不表示合约安全。自动标注补丁不是逐案审核的安全负例，4096 字节不是等 token 预算。本轮完成工程闭环，不产生 D1 改进或 D2 准确率的科研结论。
