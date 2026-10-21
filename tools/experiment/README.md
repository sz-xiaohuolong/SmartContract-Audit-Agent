# 数据与实验工具（S1a / S1b）

## 阶段1～5零模型复现入口

当前工程进度、最终数字与未达事项见 [2026-10-13离线报告](../../docs/vibe/releases/R2-20261010/experiments/2026-10-13_STAGE1_5_OFFLINE_REPORT.md)。历史原件须按 [原件说明](../../research-artifacts/README.md) 恢复；Git 不包含全部原始响应、固定编译器和收据，单独克隆仓库不足以复现历史实验。

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
PYTHONPATH=tools/experiment python3 tools/experiment/tool_replay.py --compiled \
  --original-run research-artifacts/runs/benchmarks/119b4862f8a14818b62848ce709c3ee6 \
  --output-run research-artifacts/runs/derived/$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
python3 tools/experiment/local_ui.py --port 8773
```

重放目标目录必须不存在，批次编号采用32位小写十六进制。重放读取保存候选及usage，重新执行本机编译与Slither；`four-arm-summary.json` 和 `four-arm-results.jsonl` 保存四臂统计与逐候选结果。没有独立候选真值时混淆矩阵为null，失败与缺失保持UNKNOWN。两历史批次的候选账本在 `data/audit/r2/research-review/20261013/`。

有限EVM见证只在 `config/tools.local.properties` 显式启用，配置格式见 `config/tools.example.properties`。Anvil必须支持 `--steps-tracing`；以二进制SHA-256绑定anvil与cast，固定Istanbul、独立31337链和时间初态。只使用原编译字节码、正常业务调用与合法时间推进；不直接改写存储、余额或代码。双次独立执行、正常返回、实际资金建态和同资源源映射都匹配后才接纳有限反例；不能用有限执行反驳候选或证明整合约安全。

打开 `http://127.0.0.1:8773/agent.html`，选择SimpleDAO并点击“离线演练”，查看六项义务及原行号；运行历史中可展开派生报告并下载四臂JSON。该路径新增模型请求为0，缺失usage继续显示null。

R1-S8 的 742 条待审向量可用 `candidate_admission_queue.py` 生成逐项证据缺口清单。它只写审核队列，不建立或激活正式知识快照；本机命令与准入状态见 [R1-S8 阶段验证](../../docs/vibe/releases/R1/VERIFICATION.md#r1-model-comparison)。

本地可视化验收：先运行 `mvn clean verify` 生成 Java 检索 JAR，再运行 `python3 tools/experiment/local_ui.py --port 8765`，打开 `http://127.0.0.1:8765/`。前后端由同一服务提供，仅运行固定合成样例，不读取模型密钥。界面、历史结果与研究限制见 [本地页面说明](../../docs/vibe/releases/R1/attachments/LOCAL_UI.md)。

离线清单、评估、快照和重放使用 Python 3 标准库，无额外依赖。真实采集和可选 Ragas 语义评判必须显式选择模型配置与请求范围；单写者锁和进程组控制面向本项目的 macOS/Linux 环境。

检索调优入口为 `python3 tools/experiment/eval_ragas.py --help`：`prepare` 导出冻结批次的实际消费文本与人工相关性模板，`offline` 零请求计算排序指标，`judge` 使用独立安装的 Ragas 0.4.3 和显式评判配置。缺失和未审核不计成零分，语义评分不改变 D2。完整命令、依赖安装与论文口径见 [Ragas 接入说明](../../docs/vibe/releases/R2-20261010/attachments/RAG_EVALUATION.md)。

```bash
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
python3 tools/experiment/offline.py inventory --root SolidiFI-benchmark/buggy_contracts --output /tmp/manifest-new.json
python3 tools/experiment/offline.py evaluate --labels /路径/labels.json --predictions /路径/predictions.json --output /路径/metrics-new.json
```

公开数据源与版本见 [数据入口](../../data/README.md)和 [datasets.json](../../data/datasets.json)。SmartBugs 目标直接读取根目录原始源码与 `vulnerabilities.json`，额外阴性对照读取 `data/controls/openzeppelin/`；缺少 SmartBugs 原始数据时显式报错。探索命令的 `--target-dir` 指向含 JSON 标注和 `dataset/` 的原始仓库，默认 `smartbugs-curated`。

SmartBugs 沿用原加工文档的样本编号；新记录保留原始空白、源码路径和标注摘要。已保存实验使用其固定输入回放，新输入摘要变化时不能直接续写旧计划。离线测试使用本地夹具，无需原始数据集或真实 API。

输出路径必须尚不存在。清单中的 `types`、`project_group`、`split` 均待审核。稳定 ID 同时绑定相对路径与源码字节；移动路径或修改代码会产生不同 ID。`exact_group` 只证明字节相同，不代表已完成项目级泄漏治理。

标签文件契约：

```json
{"categories":["reentrancy","access_control"],"samples":[{"id":"sample-1","types":["reentrancy"]},{"id":"sample-2","types":[]}]}
```

预测文件契约：

```json
[{"id":"sample-1","status":"COMPLETED","types":["access_control"]},{"id":"sample-2","status":"FAILED","types":[]}]
```

样本 ID 必须与标签清单一致；类型名称必须来自预定义类别，不做模糊字符串匹配。上述预测让重入类增加 FN、访问控制类增加 FP；第二条失败不计为正确完成的负例。重复样本 ID、计划外样本、未知类型以及失败结果附带类型均被拒绝。未出现在预测中的计划样本记为 missing。

该格式是独立的类型评估输入，不直接接受 S0 CLI 的自然语言单类型结果。S1b 的批处理入口负责精确类型映射、sourceHash/样本 ID 绑定及阶段记录；报告通过 replay 从已保存结果重算。

类型预测按集合去重；这里不是实例级匹配。零分母为 null；`macro_f1` 固定采用全部预定义类别，任一类别无定义时整体为 null；另给 `macro_f1_defined_only` 作为有定义类别的条件平均，并输出类别列表。后者的分母可能随预测变化，不能直接作为跨方法主指标。负例误报率以全部计划负例为分母，必须同时报告 unresolved_negative 和 completion_rate，不能用大量失败换取“低误报”。

标签是否经审核无法由程序自动证明：空列表只应用于目标漏洞范围已审核的负例。当前仓库数据清单只生成待审核条目，不直接转换成此标签文件。

## 存储分类与一键整理

真实批次、派生报告、快照和工具收据保存到 `research-artifacts/`，分类与恢复见[原件说明](../../research-artifacts/README.md)。`.local/` 维护本机环境、模型、服务、固定 Solidity 工具及恢复材料；下载仓库位于 `data/external/`。可读报告进入版本实验目录，`.evidence/` 按 AGENTS 预算只留关键验证材料。

```bash
python3 tools/experiment/organize_storage.py --apply --restart-ui
```

省略 `--apply` 只预览。已封口原件支持 gzip，逻辑文件名和原始 SHA-256 由 `storage.read_artifact()` 还原；模型、候选与 usage 不删减。新摘要不复制完整样本，CSV 按需导出。旧目录的相对兼容链接保留历史清单与虚拟环境入口，不能作为重复副本删除。体积与验收见[整理报告](../../docs/vibe/releases/R2-20261010/STORAGE_LAYOUT_REPORT.md)。

## S1b：审核与隔离

`inventory` 仍保持 S1a 的待审核输出，不替用户确定来源、谱系、标签或划分。将其补充为审核清单后，运行：

```bash
python3 tools/experiment/s1b.py validate-splits --manifest /路径/manifest-reviewed.json
```

审核清单的最小格式如下。`source_hash` 和 `exact_group` 必须填写真实源码字节的 SHA-256；省略号不是合法摘要。

```json
{
  "schema_version": "1",
  "categories": ["reentrancy", "access_control"],
  "samples": [{
    "id": "sample-1", "path": "contracts/a.sol",
    "source_hash": "填写64位小写SHA256", "exact_group": "与source_hash相同",
    "origin": "来源仓库及版本、原始路径", "project_group": "项目谱系或基础合约组",
    "clone_groups": ["经审核的克隆或漏洞补丁关联组"],
    "types": ["reentrancy"], "split": "test", "review_status": "REVIEWED"
  }]
}
```

`split` 仅允许 `knowledge/train/validation/test`。同一字节组、项目组或任一克隆组不得跨划分；跨多种关联的传递关系也受这些约束覆盖。没有已知克隆关联时明确填 `[]`；程序无法证明人工审查是否全面，不能据此宣称已完成近似克隆发现。知识快照使用同一份全量审核清单，包含测试侧元信息，防止只校验知识子集而遗漏跨库关联。

## S1b：知识快照与激活

向量由用户显式准备；构建命令不会调用 embedding 服务。每份文档表示已经切好的知识块，必须带原样本 ID；SmartBugs 的说明、补丁、摘要也必须继承原合约谱系。输入 bundle：

```json
{
  "manifest": {"schema_version": "1", "categories": ["reentrancy"], "samples": []},
  "documents": [{"id": "chunk-1", "sample_id": "knowledge-sample-1", "text": "知识块正文"}],
  "embedding": {"model": "所用模型", "dimension": 2, "revision": "明确版本"},
  "chunking": {"version": "manual-v1", "说明": "实际分块与文本规范化规则"},
  "vectors": {"chunk-1": [0.1, 0.2]}
}
```

示例中的 `manifest.samples` 需替换为完整审核条目，空清单会被拒绝。`documents` 只允许引用 `knowledge` 条目。每个块必须恰好有一个有限、非零、维度匹配的向量；按 Milvus FLOAT_VECTOR 的 float32 精度保存。快照 ID 绑定完整清单、文档、分块版本、embedding 配置与向量。

```bash
python3 tools/experiment/s1b.py snapshot-build --root /路径/kb --bundle /路径/bundle.json
python3 tools/experiment/s1b.py snapshot-verify --root /路径/kb --id 生成的快照ID
python3 tools/experiment/s1b.py snapshot-activate --root /路径/kb --id 生成的快照ID
```

先在临时目录写入并 fsync，读回全部内容校验后原子重命名。激活再次检查完整性，并原子替换 `active.json`；构建中断不会产生可激活目录，失败不会覆盖已有指针。已发布快照目录不得人工编辑；读取必须使用 `verify_snapshot` / `active_snapshot`，不能只检查目录或集合存在。

Milvus 通过 `snapshots.MilvusIndex(client)` 注入同步 `MilvusClient`，再调用 `activate_snapshot(root, snapshot_id, index)`。适配器创建唯一 `s1b_...` 集合，分批插入、flush，并通过 Strong 一致性分页读回每个 ID、向量和文档；完整匹配才替换本地激活指针。应用使用 `active_snapshot(root, index)` 获取经过再次校验的集合名。它不修改旧集合或全局别名，不自动清除构建失败留下的孤立集合。旧 legacy RAG 的启动导入逻辑没有接入此入口。

R1-S3 的 D1 正式知识候选使用 `d1_kb.py` 从完整审核的谱系清单、逐案审核的补丁对片段、同一固定模型的向量构建上述 S1b 快照和 D1 catalog。构建命令不自动激活；待审标签、未审配对、摘要不符、知识样本覆盖不全或跨划分泄漏都会拒绝。`d1_embed.py` 可先用本地固定模型为待审案例生成候选向量，输出明确标记 `candidateOnly=true`，不绕过正式准入；离线测试用注入的确定性编码器，不下载权重。当前首批材料仍待审，具体原件、候选划分及模型下载阻塞见 [D1 知识库准入记录](../../docs/vibe/releases/R1/attachments/D1_KB_READINESS.md)。现有 `mvp_` 工程演示集合不属于此入口。

默认 CLI 只激活本地快照。真实 Milvus 接入须在明确配置、凭证来自环境变量的调用方创建客户端；本轮不安装 SDK、不建立真实连接。适配接口依据 [PyMilvus 官方客户端文档](https://github.com/milvus-io/pymilvus/blob/master/_autodocs/api-reference/milvus-client.md) 实现，离线客户端夹具验证完整性与激活行为，真实 SDK/服务版本兼容性仍须部署时验证。

## S1b：逐样本日志、恢复与重放

计划 JSON：

```json
{
  "schema_version": "1",
  "manifest": {"schema_version": "1", "categories": ["reentrancy"], "samples": []},
  "sample_ids": ["sample-1"],
  "type_mapping": {"重入漏洞": ["reentrancy"], "reentrancy": ["reentrancy"]},
  "mode": "Vanilla",
  "kb_snapshot": null
}
```

填入完整审核清单后才能执行。类型映射按模型输出的完整字符串精确匹配，不做猜测或模糊匹配；未映射类型记 `FAILED/TYPE_UNMAPPED`，保留原始结果及已有 usage。调用/解析异常不会成为负例，缺失 usage 保留 `null`。当前执行器复用 S0 Vanilla CLI；`kb_snapshot` 可以绑定对照实验的知识快照，需同时传 `--snapshot-root` 并验证它使用相同审核清单，这不表示 Vanilla 已执行检索。

以下命令会调用选定供应商，只有准备实际实验时才执行。源码根目录对应清单内的相对路径，配置文件复用现有 providers properties，密钥仅从环境变量读取：

```bash
python3 tools/experiment/s1b.py run \
  --plan /路径/plan.json --root /路径/源码根目录 --journal /路径/run.jsonl \
  --jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar \
  --config /路径/providers.properties --provider ark
```

再次使用完全相同参数运行 `run`，或将子命令替换为 `resume`，会自动跳过已记录的完成、失败和不确定项，只调用尚未开始的样本。`resume` 要求日志已存在。配置、JAR、Java 启动程序、批处理实现、类型映射、完整计划或源码变化均拒绝混入旧运行；修改配置后必须另建日志。JAR 与配置使用冻结字节的临时副本，避免运行途中读取变化。`--timeout` 默认 660 秒；`--java` 可明确选择 Java 路径。

JSONL 本身就是 checkpoint：首行保存绑定计划，之后每次调用前追加 `START` 并 fsync，调用后追加规范 `RESULT` 并 fsync。事件按序号与前项摘要构成校验链。每次运行持有单写者锁；完整日志行损坏、重复事件或绑定漂移均拒绝继续。仅末尾没有换行的残行允许恢复时截断；实验头本身不完整则拒绝自动恢复，因没有已确认实验头，需检查后另建日志。

有 `START` 没有 `RESULT` 时，无法判断外部调用是否已计费，恢复将其记录为 `UNRESOLVED/CALL_INTERRUPTED`，不会自动再次调用。确需重试时，在完整 run/resume 命令上追加 `--retry-id sample-1`；可以重复此参数指定多个失败或不确定项，已完成项不允许重试。外部 API 与本地文件无法形成同一事务，本实现不声称 exactly-once；保守恢复避免盲目重复计费。

```bash
python3 tools/experiment/s1b.py replay --journal /路径/run.jsonl > /路径/report-new.json
```

Replay 不加载模型、配置、源码或 Milvus，不改写原日志。报告含最后一次尝试的规范结果与 S1a 指标；完整尝试历史保留在 JSONL，重试后的报告 usage 只代表最后一次尝试，不能代替所有尝试的总费用。遇到残行会标记 `incomplete_tail=true`；未开始项仍计入 missing 分母。CLI 退出码：0 命令完成（run/resume 时所有计划项完成），1 批次仍有失败或不确定项，2 输入、绑定或存储无效。

## S2：程序事实与 D1 独立对照

事实提供器只做受限结构分析，未知控制流、动态别名和未支持语法保留 PARTIAL/UNKNOWN。状态变量、检查主体、修饰器顺序和调用/写入位置均保留来源；不因为出现 require 或 onlyOwner 就认定安全。

```bash
python3 tools/experiment/program_facts.py --source /路径/target.sol > /路径/facts.json
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --retrieval --help
```

S1b 的知识块可加一份审核 catalog。其格式为 `{"snapshotId":"快照摘要","cases":{"知识块ID":{...}}}`；每个块的元数据必须包含 `caseId/pairId/role/mechanism/riskKind/conditions/reviewed`，不包含目标真值。`role` 为 VULNERABLE 或 DEFENSE，机制为 REENTRANCY 或 ACCESS_CONTROL；初始条件为 CHECK_BEFORE 或 STATE_WRITE_BEFORE，角色变量用 `$actor/$resource/$authority`。具体可运行示例见 [S2 合成夹具](fixtures/retrieval/catalog.json)。

查询 JSON 包含已准备的 `vector`、查询文本 `text` 和目标源码 `sourceHash`，不得偷偷调用 embedding。目标源码必须属于快照全量审核清单的非 knowledge 划分。

```bash
python3 tools/experiment/recall.py \
  --root /路径/kb --snapshot 快照摘要 --catalog /路径/catalog.json \
  --query /路径/query.json --limit 20 --output /路径/pool-new.json
```

输出含 `pool` 与召回元信息，后者记录向量/文本查询摘要、catalog 摘要、embedding 型号和算法版本。默认本地计算 cosine；加 `--milvus-url http://127.0.0.1:29530` 时要求该根目录已有经完整读回验证的 Milvus active 指针，再对搜索返回的 ID 和分数做本地核对。所有对照消费同一个导出的 pool，不能为 D1 额外免费补候选。

Java 请求包括 `target`（机制、风险事实 ID、角色绑定）、`pool`、`budget`。风险事实 ID 从事实提供器输出选择，角色由调用方明确指定；完整样例为 [request.json](fixtures/retrieval/request.json)。独立对照入口：

```bash
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --retrieval \
  --source tools/experiment/fixtures/retrieval/target.sol \
  --request tools/experiment/fixtures/retrieval/request.json \
  --worker tools/experiment/program_facts.py --strategy compare
```

可选策略：`dense/hybrid/contrastive/d1/compare`。`compare` 固定输出四种策略、相同池摘要及预算、选中上下文和全部候选的条件解释；不读取配置密钥、不调用模型、与 D2 无耦合。预算单位为实际上下文 UTF-8 字节，包含标识与正文；额外诊断解释不属于允许下游免费拼入的上下文。

示例是人工构造的机制夹具，包含有意接近的条件变体，仅供测试，不可作为跨项目实验、正式测试划分或论文性能数据。工程语义及已知覆盖边界见 [S2 设计](../../docs/vibe/releases/R1/PROPOSED_DESIGN.md#r1-design)。

## S3：来源隔离与离线证伪先导

S3 的完整契约、来源待审状态和可重放命令见 [R1-S3 验证](../../docs/vibe/releases/R1/VERIFICATION.md#r1-data-evidence)。`s3.py lineage` 只读取开发、知识与验证源码；本切片对任何包含锁定测试的清单直接拒绝，程序不打开其源码。`s3_pilot.py` 共用 S2 候选池运行四原策略、字段过滤和两项消融，要求完整提示 tokenizer 适配器与版本摘要；示例码点计数器只用于机制测试。失败和未知保持单独分母，未核验真实标签时不计算科研收益。

本机 Milvus 与单次真实模型工程试跑采用独立的 `mvp_` 集合和 `/mvp.html` 页面，完整命令、费用边界及报告目录见 [工程 MVP 说明](../../docs/vibe/releases/R1/attachments/MVP_MILVUS_RUN.md)。该入口只处理固定开发样本，不作为 S3 研究先导或 D1 效果评估。

## R1-S4：正式知识快照的单样本审计工作台

本机已登记的四个开发目标中，`AC-ASE-006` 与 `AC-ASE-009` 可作整份源码工程试跑；`RE-SCRUBD-001` 仅允许 `matchOrderWithReserve` 第 574–660 行函数级试跑，必须同时展示完整源码与片段摘要；`RE-SCRUBD-002` 因提示上限暂不可运行。全部目标均非论文测试结果，标签仍按原谱系审核状态处理。

先执行 `mvn clean verify` 构建当前 Java JAR。页面使用本机固定 BGE 权重，需要项目已有的 `.local/envs/embedding`，从仓库根目录启动：

```bash
.local/envs/embedding/bin/python tools/experiment/local_ui.py --port 8769
```

浏览器打开 `http://127.0.0.1:8769/agent.html`。目标列表、状态、正式检索预览、历史与下载为只读操作。离线演练不调用付费模型，也不运行真实 Slither；它会检查本机正式 `s1b_` Milvus 快照、使用固定 BGE 生成 D1 候选、经过 Java D1，并以明确标记的空假设及跳过工具状态检验编排和报告。离线结果的“未发现已报告问题”不构成安全结论，D2 仍为 UNKNOWN。Milvus 需在 `127.0.0.1:29531` 可用，当前正式指针与六条向量须完整读回，不回退到旧 `mvp_` 集合。

只有在页面显式选择真实运行才使用 `config/providers.local.properties` 中已核实的火山 Agent Plan 端点和模型；单样本最多 1 次请求，批量每种目标与策略组合最多 1 次请求，2048 输出 token，零自动重试。运行器在临时配置中启用严格 JSON Schema 并关闭显式思考，提示同时写明精确 JSON 字段、已核实的所属合约和绝对行号；模型仍可能违约，失败保持未决，原始响应仅存于被 Git 忽略的本机诊断文件。这种模型配置不能直接当作科研对照配置。完整消息只有 UTF-8 字节硬上限，尚无指定模型的精确 token 公平保证。Slither 路径填写在被 Git 忽略的 `config/tools.local.properties`，格式见 `config/tools.example.properties`；Mythril 可选，增加 `tools.mythril.executable` 即可。对依赖原项目导入路径的验证源码，单文件 Slither 无法可靠编译，当前明确记为 `SKIPPED`，D2 保持 `UNKNOWN`；工具未安装、失败、空告警均不证明安全。

每次运行写入 `research-artifacts/runs/audits/<运行编号>/plan.json`、`events.jsonl`、`sample.jsonl` 与 `result.json`。模型请求前先将启动事件 fsync；中断后已有记录只读回放，不自动重发。`replay(root, run_id)` 会核对计划摘要、逐样本结果和结束事件摘要。页面下载的 JSONL 与本机逐样本文件相同。若需要人工检查，可对照页面运行编号和该目录中的快照 ID、两个源码摘要、阶段状态、usage 与 UNKNOWN/失败分母。真实付费运行须由操作者自行点击；默认离线测试命令不发网络 API 请求。

```bash
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
```

该工作台只证明单样本工程链路可执行。D1 的真实效果仍需独立审核目标—案例适用性标签、锁定真实 tokenizer 和同池强基线后另行实验；D2 初版只有已有证据的六项义务检查，不是完整路径求解。

## R1-S9：单合约深度审计与 D2 证据核验

构建 `audit-mvp` 后，沿用本机离线嵌入环境启动服务：

```bash
mvn clean verify
.local/envs/embedding/bin/python tools/experiment/local_ui.py --port 8771
```

打开 `http://127.0.0.1:8771/workbench.html`，选择已登记样本或粘贴完整 Solidity。默认查询固定 Nomic 768 维快照；BGE 可显式选择。先预览源码范围、受限语法树、调用/写入/CEI、D1 前后配对及条件绑定，再启动离线演练或明确选择当前配置的真实模型。一次预览只能使用一次，输入、策略、模式、配置或快照改变后必须重新预览。粘贴输入最多 128 KiB，模型源码最多 16 KiB；较长源码必须明确定位函数或风险行。D1 上下文最多 4096 UTF-8 字节，此限制不是 token 公平。

六阶段报告包含程序事实、D1、schemaVersion=2 模型假设、固定本机 Slither/Mythril 状态、D2 义务矩阵和最终裁决。源码与工具/D2 引用可以互相定位。D2 的 `verdict` 针对漏洞假设，`protectionVerdict` 针对保护覆盖；六项保护均获支持且该路径确已阻断才可反驳特定假设，具体可行反例和同源工具佐证才能支持漏洞。缺工具、空告警、partial 事实和异常均不能证明安全。受限语法树不等于完整编译器 AST，当前只支持访问控制和重入的有限证据核验。

真实配置在预览中绑定摘要，启动时捕获不可变内容和环境凭证，再重建为权限 600 的临时配置，结束后清理。本机供应商配置支持单行 `key=value`、空行与注释；为避免 Python/Java 解析分歧，拒绝冒号键、转义键和反斜杠续行，含特殊字符的凭证可通过环境变量提供。函数范围的假设严格匹配所选合约与函数；全文范围允许核验其他实际声明的函数。被拒绝或位置校验失败的假设使反驳汇总保持未决。

报告保存到被 Git 忽略的 `research-artifacts/runs/workbench/<运行编号>/`，含绑定源码、预览、计划、阶段事件、完整结果和单行 JSONL；下载与历史回放不调用模型或工具。服务重启后的未封口记录标为 `INTERRUPTED`，不自动续发。单样本与批量共享运行锁。自定义源码不会进入正式知识或研究标签。自动知识仍为自动标注待核验层；没有科研效果结论。

`/agent.html` 保留三策略批量入口，新报告添加工具、D2、最终裁决和流水线失败。模型状态、预测及模型耗时维持原统计口径，D2 未知和流水线失败另列；历史报告没有执行 D2 时显示未核验，不重写旧报告。真实模型单次最多两次请求（瞬时错误仅重试一次），输出上限 2048 token；本次工程验收不发起外部付费调用。真实编译工具按全部有效 pragma 选择预先配置的固定编译器；含 import 的目标须提供明确依赖路径，缺失依赖或工具故障保留未知。

## R2-S10：输入治理与零模型派生重放

评测原件与清理输入分别保存摘要；注释答案用空白遮蔽并保留行列，字符串内容原样保留。发现任务不使用评分真值选择函数、风险或检索；历史固定目标按给定候选核验记录。清理后输入用于查询与模型，评分标签单独消费。

在被 Git 忽略的 `config/tools.local.properties` 中指定 Slither 的绝对可执行路径和 `tools.compiler.directory`（已备齐版本的本机目录）。工具结果保存实际编译器版本／摘要、参数、退出、耗时和脱敏诊断；环境、源码或依赖改变后不复用成功缓存。

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 tools/experiment/tool_replay.py \
  --original-run research-artifacts/runs/benchmarks/546fe566368e4b0ea7b6aeb58b235939 \
  --output-run research-artifacts/runs/derived/新的派生目录
```

输出目录必须不存在。重放仅重新执行工具和 D2，新增模型请求为 0；原模型、usage 与全部原文件摘要保持。派生结果绑定源码、完整工具环境、当前代码与 JAR，并封口保存 manifest、summary、逐单元 JSONL 和报告。历史输入的答案污染限制仍保留，不能把派生核验当作清理后模型发现实验。S10 局部验收与真实工具兼容缺口见 [R2 验收矩阵](../../docs/vibe/releases/R2-20261010/VERIFICATION.md)。

原批次缺源码的输入阻断只有在冻结计划、源码摘要、失败／UNKNOWN、零请求及usage=null身份一致时才可重放。此类单元保持原D2并计入完整分母，跳过编译与工具。加 `--compiled` 使用绑定编译事实与独立Slither双收据；工作台默认读取 `research-artifacts/runs/derived/<32位编号>`，输出须使用新目录。

## R2-S11：真实编译事实与有限路径

`compiler_facts.py` 每次读取显式 manifest，核对完整源码闭包、固定 solc 与版本、settings、输入输出、声明及 UTF-8 跨度，随后实际重新编译并比较完整 JSON。执行前后编译器摘要必须一致。ABI 函数、继承入口、自动 getter、fallback／receive 分别盘点；构造与初始化语义仍单独保留缺口。编译对照成功为 `RECOMPILED_MATCH`，结构事实整体保持 `PARTIAL`。

```bash
python3 tools/experiment/compiler_facts.py \
  --manifest data/audit/r2/compiler-manifests/rabbit-after.json --root .
python3 tools/experiment/d2_verify.py \
  --manifest data/audit/r2/compiler-manifests/atomic-after.json \
  --hypothesis data/audit/r2/path-candidates/atomic-after.json --root .
```

六份清单登记本机 `.local/r2/` 中的原始编译产物和固定二进制。换机器须按相同来源恢复原件及环境；路径或摘要不匹配时失败，不生成替代 AST。保存假设和可选 `--tools` 工具 JSON 仅用于 `CLAIM_VALIDATION`，新增模型请求为 0；命令退出 0 表示核验已运行，不能从最终 `UNKNOWN` 推断安全。非法输入或编译绑定失败退出 1，裁决仍为未知。

编译 D2 从 AST 构造有限 CFG，展开内部调用和单占位符修饰器，按实际支配与声明／映射 key／struct 字段／状态版本计算义务。`localPathEvidence` 记录局部命题、范围及条件前提；`pathEvidence` 和 `proofScope` 保留全候选、全入口与早期调用缺口。Rabbit 修复后的权限检查、Atomic 首付款前置锁只提供相应局部证据；Atomic 三版仍有置锁前的 `ACEXT()` 调用。静态可达与工具告警不足以支持可行漏洞。

共享接口 `d2_verify.evaluate`、`audit_workbench.assess` 支持显式 `compilation_manifest` 和 `root`。本机登记目标可携带 `compilerManifest`；单样本预览保存 `compiledFacts` 和计划身份，执行前重核验；批量也在模型前核验绑定。页面请求不能任意指定清单路径。清理后的消费源码须与编译输入字节一致，旧报告只读。配置 `tools.compiler.directory` 时，发现阶段先生成重验编译收据，模型之后复用原input／output／binding并按候选合约投影；缺发现收据的兼容入口独立生成候选清单；仅配置 `tools.slither.solc` 的旧网关仍沿用原入口。含导入的源码须使用完整依赖模板，缺依赖、固定编译器或工具收据时保持未知。

`bound_slither.py` 使用固定 solc 和官方 Slither 编译适配器生成独立收据，重新核对源码闭包、设置、AST、ABI、字节码及工具输出。两个摘要各自保存，通过实际对账建立 `MATCH`，不复制摘要。`candidate_proofs.py` 证明访问控制的权限委派和相关写入口闭包；`reentrancy_proofs.py` 证明有限 CEI 或统一互斥锁覆盖。保护完整且双收据匹配才能 `REFUTED`；合法入账建态、正常退出的 CEI 顺序反例及同源同类告警共同成立才能 `SUPPORTED`。局部保护、工具无告警及未建态路径仍为 `UNKNOWN`。

保存候选可通过统一入口零模型核验：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/audit_runner.py \
  --source /本机/已登记源码.sol --hypotheses /本机/保存假设数组.json --root .
PYTHONPATH=tools/experiment python3 tools/experiment/tool_replay.py --compiled --root . \
  --original-run research-artifacts/runs/benchmarks/546fe566368e4b0ea7b6aeb58b235939 \
  --output-run research-artifacts/runs/derived/新的32位十六进制运行编号
```

`audit_runner.py` 的假设文件是 JSON 数组；含导入时增加 `--manifest`。重放不改变原假设或 usage，导出 `assessments.jsonl`、`summary.json` 和 `REPORT.md`；UNKNOWN 对照分母包含全部保存假设，缺失 assessment 仍计为未知。输出目录必须不存在；用于页面展示的运行编号须为 32 位十六进制，不能直接复制示例占位文字。先构建 Java，再重放；期间修改生产实现或 JAR 会拒绝封口。

`agent.html` 下拉菜单预置 Unprotected、SimpleDAO，以及本机原件可用时的 RabbitHole／Atomic Loans 修复前后版本。点击「离线演练」会实际运行固定编译器、Slither 和 D2，仅复用登记候选，零模型请求；绿色表示该项保护成立，红色表示被反证，灰色表示缺证据。预览后「开始审计」亦支持该离线流程。合成机制模拟继续单独标明 D2 未执行。运行历史展示已封口派生报告、逐样本矩阵与原字节下载；登记候选不参与模型发现效果指标，离线总审计结论保留未决。实际结果和证明边界见 [R2 验收矩阵](../../docs/vibe/releases/R2-20261010/VERIFICATION.md)。

## R1-S6：独立验证样本批量对照

同一 `/agent.html` 页面新增批量区域。勾选已登记的独立验证目标和 `DENSE`、`FIELD_FILTER`、`D1` 策略，先点击“查看运行计划”，再开始批量对照。每项结果同步写入 `research-artifacts/runs/batches/<批量编号>/samples.jsonl`，页面显示按策略的完成、失败、未知、入选证据、usage 和待核验指标；下载链接直接返回逐样本 JSONL。重新打开历史不会发起模型请求；异常中断的计划可在历史中续跑，已启动但没有结果的项记为未决，不自动重发。

“真实模型批量运行”可查看当前端点、模型、样本数 × 策略数 × 重复次数 × 模型阶段 × 尝试次数以及请求和输出 token 上界。用户已授权显式启动真实批量；完整输入 token 与费用上界仍为 `null`，输入 UTF-8 字节上限不是 token 公平。页面的检测召回、检索 Recall@K 和 nDCG 只有取得独立审核的目标—案例标签后才能计算，当前显示“待核验”。数据规模依据和后续实验方案见 [R1-S6 研究设计](../../docs/vibe/releases/R1/attachments/RESEARCH_DESIGN.md)。

## 真实 API 的 Vanilla／Dense／D1 对照与离线报告

`benchmark_cli.py` 默认策略为 `VANILLA DENSE D1`。Vanilla 的模型上下文与证据 ID 为空；固定候选池仅用于对照身份和 Dense／D1 共池，模型不消费该池。`FIELD_FILTER` 仍可显式选择，历史计划和结果不改写。

自动知识使用 `mechanism-window-unknown-v1` 消费契约：从冻结全文选择可见机制变化窗口，过滤仅改名、注释／字符串及多义配对，窗口不足时不配对；Java／Python均最多两对且完整上下文≤4096 UTF-8字节。自动入选绑定与评估全部UNKNOWN，“改动后”不表示有效修复。CALL资源关联只用于检索的语法提示，不能作为D2数据流证明。当前修复与零模型复验见[根因报告](../../docs/vibe/releases/R2-20261010/experiments/2026-10-12_D1_D2_REPAIR_REPORT.md)；没有新模型请求时不提供新F1。

真实运行沿用本机已核实供应商配置、Nomic 768 维活动快照及固定工具。启动前检查凭证、本地服务、模型摘要，并先对单一样本执行真实冒烟；未通过路由、usage 与结构化解析时不启动正式批次。以下真实命令仅在已有对应批次授权时执行，自动测试继续使用本地夹具。

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/benchmark_cli.py \
  --mode real --embedding-profile nomic \
  --sample-ids access_control__dataset_access_control_FibonacciBalance__4b0dfd1088 \
  --strategies DENSE D1

PYTHONPATH=tools/experiment python3 tools/experiment/benchmark_cli.py \
  --mode real --embedding-profile nomic --include-blocked \
  --strategies VANILLA DENSE D1
```

默认只选择可运行目标；`--include-blocked` 将已登记的阻断目标保留在计划分母中，输出 `EVALUATION_INPUT_BLOCKED`、失败／UNKNOWN、请求次数 0 和 usage=null，绝不按评分真值裁剪源码或调用模型。请求边界仅按可运行目标计算。正式运行的逐单元结果还保存编译清单及编译失败分类，便于回读双收据与 D2 引用。

仅从保存文件重算中文报告和逐假设明细，不再调用模型或工具：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/benchmark_report.py \
  --run research-artifacts/runs/benchmarks/dcf98eef6475433f80f228c9ab5a29fb \
  --output .evidence/R2-20261010/API-batch-20261011/重算报告.md \
  --detail-output .evidence/R2-20261010/API-batch-20261011/重算明细.json \
  --metadata .evidence/R2-20261010/API-batch-20261011/report-metadata.json
```

模型 Precision／Recall／F1 与 D2 裁决独立统计。D2 反驳率为 REFUTED／有效保存假设数；UNKNOWN 不当作误报或安全，缺失核验仍计入未知。自动知识和数据集标签使当前报告属于探索性评测，完整 token 公平、独立适用性真值与研究效果验收仍需单列。

## SYNAPSE 首期证据与上下文接入

这次改动让模型提出的疑似漏洞与工具核验使用同一份编译记录，避免“代码一样、编号不同”导致无法定位。工作台还增加相关源码索引、检查模板和证据复核，帮助人回查结论。2026-10-14工程入口继续使用原工作台和三策略批量。默认模型仍读取完整清理源码（FULL）和原有漏洞／修复参考配对（D1）；新增索引和模板用于展示、回查与保存使用记录，尚未放入模型提示，记录为`consumedByModel=false`。因此，这次三策略实验的F1分数不能证明模板提示提高了效果。

- `compilation_runtime.py`消费`discoveryCompilation`时重验原输入、输出和binding，显式投影候选合约；缺原收据不重新编译掩盖。实际候选`compilationManifest`随报告独立保存，冻结target保持原字节。
- `focus_context.py`为目标函数（ff）、修饰器（fm）、内部调用（fi）和状态变量（fv）建立原字节索引，列出全部合约入口；间接调用、内联汇编、递归与未知外部实现分别列缺口。编译失败时只提供语法索引（SYNTAX_ONLY），不据此宣称完整或安全。
- `check_templates.py`读取`data/audit/r2/check-templates.json`，核对知识划分和来源身份，为已入选pair保守实例化；未绑定状态版本或路径不猜配，预算不足整条拒绝。10条来源身份已核验，语义独立审核仍未完成。
- `evidence_review.py`从重验的编译语法树（AST）独立核对六项接缝，输出通过（PASS）、冲突（CONFLICT）或未决（UNRESOLVED）。`gateApplied=false`表示只生成侧报告，不覆盖D2漏洞三态；缺独立候选真值时精确率保持未知（null）。
- `real_fix_check.py --help`提供真实before／after最终裁决核验；两侧独立源码、工具COMPLETED、before SUPPORTED与after REFUTED同时成立才通过，局部BLOCKED或义务REFUTED不算最终验收。
- `synapse_protocol.py`隔离一次三策略采集与待审RQ-A／B／C协议，不覆盖历史六臂协议；缺独立标签、来源谱系审核、精确token公平或真实双向闭环时研究资格false。

当前真实修复与旧133未知门槛仍为部分完成（PARTIAL）；工程结果、完整163／133／151重放、原件指针和研究限制见[实施报告](../../docs/vibe/releases/R2-20261010/experiments/2026-10-14_SYNAPSE_IMPLEMENTATION_REPORT.md)。本次一次真实批量已完成，159正式请求、158模型有效，新163条候选为83支持／0反驳／80未知；三个构建产物阶段及失败限制见[真实报告](../../docs/vibe/releases/R2-20261010/experiments/2026-10-14_SYNAPSE_REAL_API_REPORT.md)。原件继续通过`storage.read_artifact()`读取并核对原始字节身份。

## R3 卡片与多路检索实验

R3 在原代码对之外保存可回读的机制卡片，并让代码向量、代码词法、函数名目的代理和行为词法分别召回。它记录资源背景冲突、保护差异的新增覆盖和重复惩罚，方便核对为什么选了这几对参考。当前卡片均未独立语义审核，研究资格为未验证；默认工作台与原批量入口保持原策略。

先完成 `mvn clean verify`，确保本机 Nomic、Milvus 和已有模型／工具配置可用，再执行无付费预检：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/r3_cli.py --allow-unreviewed
```

缺省选择八个已登记目标，按无检索、原代码对、同案例卡片、并集向量排序、并集融合排序五个条件构造实际 Java 请求，并在本机重放空回答。预检不访问付费模型，检查完整提示是否超过 32768 UTF-8 字节；该字节上限不代表精确 token 公平。

已获对应一次批量授权时，增加 `--execute --batch-id <32位十六进制编号>` 执行五条件采集。重复批次编号会拒绝，任何模型失败或身份变化会停止后续付费请求，禁止自动换端点或追加请求。原件保存到 `research-artifacts/runs/benchmarks/`，卡片唯一原件保存在 `research-artifacts/snapshots/r3/`。运行期间不得重建共享 JAR 或提交源码。

评估仍使用 `eval_ragas.py`：R3 代码对与卡片统一按案例计数（CASE_PAIR），原片段 ID 继续保存。卡片评估会回读冻结卡片原件并核对实际正文；原实验仍按代码片段计数（SNIPPET）。R3 每次最多两案例，计算案例排序时显式选择 `--k 2`；没有独立相关性标注时分数留空。实施边界与批量预算见 [R3 统一计划](../../docs/vibe/releases/R3-20261015/IMPLEMENTATION_PLAN.md#8-2026-10-16-首期实施决定与状态)。

2026-10-16 的一次真实采集已完成：40/40 模型请求有效、零重试，五条件分类 F1 均为 1.0；完整流程 33 项完成、7 项风险绑定失败。22 条新候选为 10 支持、0 反驳、12 未知。该次授权已消费，结果及原件身份见 [R3 实施与真实实验报告](../../docs/vibe/releases/R3-20261015/experiments/2026-10-16_R3_IMPLEMENTATION_AND_REAL_API_REPORT.md)。

## phase 5：离线对照查询与同池重排

这个入口检查参考案例是否能区分调用主体或余额写入顺序。它从重验的编译事实生成问题，让同一份完整前后材料分别与原问题和对照问题比较。`P5_RELEVANCE` 按原相似度排序；`P5_MARGIN` 按“原相似度减去最大对照相似度”排序。过滤、完整配对、最多两案例及 4096 UTF-8 字节预算共用，只改变排序依据。默认工作台和 D2 继续使用原路径。

下面所有命令在项目根目录运行。输出目录必须不存在，不能覆盖已冻结结果。先登记历史输入，再准备查询及盲审模板；准备时会调用原编译器重验保存的收据，不需要 Milvus 或模型 API。

```bash
python3 tools/experiment/phase5_cli.py inventory \
  --batch-id 9ec220e9e03c485c8871703ec4711b27 \
  --batch-id be23621ebe4f404e956a5f4261d5810d \
  --batch-id 6beeb4553a30422e883fdefcdc085073 \
  --unit-index .evidence/R2-20261010/API-synapse-20261014/effective-unit-index.json \
  --output research-artifacts/runs/benchmarks/phase5-复现/inventory

python3 tools/experiment/phase5_cli.py prepare \
  --batch-id be23621ebe4f404e956a5f4261d5810d \
  --output research-artifacts/runs/benchmarks/phase5-复现/prepared
```

第一步按原批次保留计划目标和候选数量；权威分段索引必须与原件行、源码及完整计划一致。第二步导出 `dataset.json`、`reviews.template.json`、`lineage.template.json`，分别保存冻结输入、隐藏方法分数与排名的审核材料、项目／事件／补丁来源表。没有事实、没有对照、入口不支持和超预算都保留原因，不当成零分。

编码必须显式选择已登记本机 BGE 权重和对应 Python 环境；不会下载或调用外部嵌入服务。`--allow-unreviewed` 表示允许工程演练，不表示独立审核通过。

```bash
.local/envs/embedding/bin/python tools/experiment/phase5_cli.py compare \
  --dataset research-artifacts/runs/benchmarks/phase5-复现/prepared/dataset.json \
  --model-dir .local/models/bge --allow-unreviewed \
  --output research-artifacts/runs/benchmarks/phase5-复现/comparison

python3 tools/experiment/phase5_cli.py replay \
  --run research-artifacts/runs/benchmarks/phase5-复现/comparison/run.json

python3 tools/experiment/phase5_cli.py evaluate \
  --run research-artifacts/runs/benchmarks/phase5-复现/comparison/run.json \
  --reviews research-artifacts/runs/benchmarks/phase5-复现/prepared/reviews.template.json \
  --output research-artifacts/runs/benchmarks/phase5-复现/evaluation

python3 tools/experiment/phase5_cli.py lineage \
  --ledger research-artifacts/runs/benchmarks/phase5-复现/prepared/lineage.template.json \
  --output research-artifacts/runs/benchmarks/phase5-复现/lineage
```

`compare` 在运行前从原件重建输入，拒绝改正文后重新封摘要的替换。`run.json` 保存每个操作的完整分数、向量、选中配对、消费文本及失败。`replay` 使用保存向量复算，不重新编码；输入全部失败时，它核对失败与空排序的记录是否一致。命令退出 0 只表示报告完整保存，仍需查看各操作的 `status`。

`evaluate` 以完整配对计分，先在目标内平均，再跨目标平均。独立人工应在审核模板副本中分别填写：查询的 `status=ACCEPTED/REJECTED`，材料相关性的 `relevance.status=REVIEWED`，以及覆盖完整候选池的 `pairGrades`（0 无关、1 部分有用、2 直接有用）。两种审核都需填写 `reviewerType=INDEPENDENT_HUMAN`、`reviewer` 与 `rationale`；源码、问题、引用和材料正文保持冻结版本。未审核、AI 诊断或不完整池不能产生正式成绩。逐目标覆盖表保留零操作目标和入口缺口。

`lineage` 检查已填写的字节摘要、项目、事件和补丁是否跨知识／开发／评价划分；缺字段保持需要审核（REVIEW_REQUIRED）。它只检查登记的一致性，不代替独立来源审核。

2026-10-21 首期 BGE 本机集成保留 8 个目标、46 个操作；13 个结构有效，33 个未支持。13 个有效单元均因池内完整材料超过固定模型的 512 token 上限而失败，未执行向量推理；排序指标为空，零真实模型请求。来源登记见 [data/audit/phase5](../../data/audit/phase5/)，测试、技术说明与限制见[统一验收](../../docs/vibe/releases/phase5-20261021/VERIFICATION.md)。这批结果尚不能说明检索质量或漏洞发现效果提高。


### phase 5 的真实开发集探索

`phase5_experiment.py` 读取上述冻结输入，显式使用本机 Nomic 完整编码，并复用 Java 模型网关与原 D2。默认只做预检；以下命令不发付费请求：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/phase5_experiment.py \
  --dataset research-artifacts/runs/benchmarks/phase5-20261021/prepared/dataset.json \
  --output research-artifacts/runs/benchmarks/phase5-新的预检目录 \
  --allow-unreviewed
```

新编码使用 `/api/embed`、`truncate=false`，逐文本保存实际 token 数；超限不裁剪重试，模型摘要漂移终止整轮。全部结构有效操作按材料等权平均，再分别按原分与差值排序。没有有效对照、评分不完整或资源键不一致时，目标三条件共同阻断，仍占计划分母。

真实执行需要 `--execute` 和本次唯一 `--batch-id`，并重新核对模型、端点、源码、JAR、配置和消费预检。最多 24 个计划单元；每次完整提示最多 32768 UTF-8 字节、输出最多 16384 token，零重试。`--comparison` 可复用保存的完整评分，输出只登记原件指针，不复制向量。单次授权在 `research-artifacts/runs/benchmarks/phase5-20261021/real-authorization.json` 持久登记，换编号也不能自动重跑。已有授权消费后，复核应使用 `benchmark_batch.replay_batch` 和 `phase5_cli.py replay`。

本入口只用于已授权的一次开发集探索。未审核查询、材料与来源仍不能产生正式检索成绩；共同字节上限也不等于精确 token 公平。默认工作台、Java 候选协议及 D2 规则沿用原实现。
