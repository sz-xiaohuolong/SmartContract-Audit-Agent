# 数据与实验工具（S1a / S1b）

R1-S8 的 742 条待审向量可用 `candidate_admission_queue.py` 生成逐项证据缺口清单。它只写审核队列，不建立或激活正式知识快照；本机命令与准入状态见 [R1-S8 阶段验证](../../docs/vibe/releases/R1/VERIFICATION.md#r1-model-comparison)。

本地可视化验收：先运行 `mvn clean verify` 生成 Java 检索 JAR，再运行 `python3 tools/experiment/local_ui.py --port 8765`，打开 `http://127.0.0.1:8765/`。前后端由同一服务提供，仅运行固定合成样例，不读取模型密钥。界面、历史结果与研究限制见 [本地页面说明](../../docs/vibe/releases/R1/attachments/LOCAL_UI.md)。

离线清单、评估、快照和重放使用 Python 3 标准库，无额外依赖。只有 S1b 的 run/resume 命令会显式调用所选模型；单写者锁和进程组控制面向本项目的 macOS/Linux 环境。

```bash
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
python3 tools/experiment/offline.py inventory --root src/main/resources/testset --output /tmp/manifest-new.json
python3 tools/experiment/offline.py evaluate --labels /路径/labels.json --predictions /路径/predictions.json --output /路径/metrics-new.json
```

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

先执行 `mvn clean verify` 构建当前 Java JAR。页面使用本机固定 BGE 权重，需要项目已有的 `.local/d1-embed-venv`，从仓库根目录启动：

```bash
.local/d1-embed-venv/bin/python tools/experiment/local_ui.py --port 8769
```

浏览器打开 `http://127.0.0.1:8769/agent.html`。目标列表、状态、正式检索预览、历史与下载为只读操作。离线演练不调用付费模型，也不运行真实 Slither；它会检查本机正式 `s1b_` Milvus 快照、使用固定 BGE 生成 D1 候选、经过 Java D1，并以明确标记的空假设及跳过工具状态检验编排和报告。离线结果的“未发现已报告问题”不构成安全结论，D2 仍为 UNKNOWN。Milvus 需在 `127.0.0.1:29531` 可用，当前正式指针与六条向量须完整读回，不回退到旧 `mvp_` 集合。

只有在页面显式选择真实运行才使用 `config/providers.local.properties` 中已核实的火山 Agent Plan 端点和模型；单样本最多 1 次请求，批量每种目标与策略组合最多 1 次请求，2048 输出 token，零自动重试。运行器在临时配置中启用严格 JSON Schema 并关闭显式思考，提示同时写明精确 JSON 字段、已核实的所属合约和绝对行号；模型仍可能违约，失败保持未决，原始响应仅存于被 Git 忽略的本机诊断文件。这种模型配置不能直接当作科研对照配置。完整消息只有 UTF-8 字节硬上限，尚无指定模型的精确 token 公平保证。Slither 路径填写在被 Git 忽略的 `config/tools.local.properties`，格式见 `config/tools.example.properties`；Mythril 可选，增加 `tools.mythril.executable` 即可。对依赖原项目导入路径的验证源码，单文件 Slither 无法可靠编译，当前明确记为 `SKIPPED`，D2 保持 `UNKNOWN`；工具未安装、失败、空告警均不证明安全。

每次运行写入 `.local/audit-runs/<运行编号>/plan.json`、`events.jsonl`、`sample.jsonl` 与 `result.json`。模型请求前先将启动事件 fsync；中断后已有记录只读回放，不自动重发。`replay(root, run_id)` 会核对计划摘要、逐样本结果和结束事件摘要。页面下载的 JSONL 与本机逐样本文件相同。若需要人工检查，可对照页面运行编号和该目录中的快照 ID、两个源码摘要、阶段状态、usage 与 UNKNOWN/失败分母。真实付费运行须由操作者自行点击；默认离线测试命令不发网络 API 请求。

```bash
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
```

该工作台只证明单样本工程链路可执行。D1 的真实效果仍需独立审核目标—案例适用性标签、锁定真实 tokenizer 和同池强基线后另行实验；D2 初版只有已有证据的六项义务检查，不是完整路径求解。

## R1-S9：单合约深度审计与 D2 证据核验

构建 `audit-mvp` 后，沿用本机离线嵌入环境启动服务：

```bash
mvn clean verify
.local/d1-embed-venv/bin/python tools/experiment/local_ui.py --port 8771
```

打开 `http://127.0.0.1:8771/workbench.html`，选择已登记样本或粘贴完整 Solidity。默认查询固定 Nomic 768 维快照；BGE 可显式选择。先预览源码范围、受限语法树、调用/写入/CEI、D1 前后配对及条件绑定，再启动离线演练或明确选择当前配置的真实模型。一次预览只能使用一次，输入、策略、模式、配置或快照改变后必须重新预览。粘贴输入最多 128 KiB，模型源码最多 16 KiB；较长源码必须明确定位函数或风险行。D1 上下文最多 4096 UTF-8 字节，此限制不是 token 公平。

六阶段报告包含程序事实、D1、schemaVersion=2 模型假设、固定本机 Slither/Mythril 状态、D2 义务矩阵和最终裁决。源码与工具/D2 引用可以互相定位。D2 的 `verdict` 针对漏洞假设，`protectionVerdict` 针对保护覆盖；六项保护均获支持且该路径确已阻断才可反驳特定假设，具体可行反例和同源工具佐证才能支持漏洞。缺工具、空告警、partial 事实和异常均不能证明安全。受限语法树不等于完整编译器 AST，当前只支持访问控制和重入的有限证据核验。

真实配置在预览中绑定摘要，启动时捕获不可变内容和环境凭证，再重建为权限 600 的临时配置，结束后清理。本机供应商配置支持单行 `key=value`、空行与注释；为避免 Python/Java 解析分歧，拒绝冒号键、转义键和反斜杠续行，含特殊字符的凭证可通过环境变量提供。函数范围的假设严格匹配所选合约与函数；全文范围允许核验其他实际声明的函数。被拒绝或位置校验失败的假设使反驳汇总保持未决。

报告保存到被 Git 忽略的 `.local/audit-workbench-runs/<运行编号>/`，含绑定源码、预览、计划、阶段事件、完整结果和单行 JSONL；下载与历史回放不调用模型或工具。服务重启后的未封口记录标为 `INTERRUPTED`，不自动续发。单样本与批量共享运行锁。自定义源码不会进入正式知识或研究标签。自动知识仍为自动标注待核验层；没有科研效果结论。

`/agent.html` 保留三策略批量入口，新报告添加工具、D2、最终裁决和流水线失败。模型状态、预测及模型耗时维持原统计口径，D2 未知和流水线失败另列；历史报告没有执行 D2 时显示未核验，不重写旧报告。真实模型单次最多两次请求（瞬时错误仅重试一次），输出上限 2048 token；本次工程验收不发起外部付费调用。真实编译工具依赖本机预先配置的环境，含 import 的单文件目标跳过工具并保留未知。

## R1-S6：独立验证样本批量对照

同一 `/agent.html` 页面新增批量区域。勾选已登记的独立验证目标和 `DENSE`、`FIELD_FILTER`、`D1` 策略，先点击“查看运行计划”，再开始批量对照。每项结果同步写入 `.local/audit-batches/<批量编号>/samples.jsonl`，页面显示按策略的完成、失败、未知、入选证据、usage 和待核验指标；下载链接直接返回逐样本 JSONL。重新打开历史不会发起模型请求；异常中断的计划可在历史中续跑，已启动但没有结果的项记为未决，不自动重发。

“真实模型批量运行”可查看当前端点、模型、样本数 × 策略数 × 重复次数 × 模型阶段 × 尝试次数以及请求和输出 token 上界。用户已授权显式启动真实批量；完整输入 token 与费用上界仍为 `null`，输入 UTF-8 字节上限不是 token 公平。页面的检测召回、检索 Recall@K 和 nDCG 只有取得独立审核的目标—案例标签后才能计算，当前显示“待核验”。数据规模依据和后续实验方案见 [R1-S6 研究设计](../../docs/vibe/releases/R1/attachments/RESEARCH_DESIGN.md)。
