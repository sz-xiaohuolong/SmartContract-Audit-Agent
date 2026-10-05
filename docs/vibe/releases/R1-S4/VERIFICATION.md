# R1-S4 验证记录

状态：实施中；本文件只记录已执行检查，不把单项通过当作整链交付或科研效果。

## 目标登记与隔离（S4-01、S4-02 的输入部分）

2026-10-05：先运行新测试，因 `formal_targets` 模块不存在而失败；实现后执行 `PYTHONPATH=tools/experiment python3 -m unittest tools/experiment/tests/test_formal_targets.py -v`，2 项通过。测试以临时目录内的固定源码和谱系夹具验证四目标列表、函数原始行号、源码／片段双摘要、源码篡改和同项目跨划分拒绝。额外只读检查本机现有原件：`AC-ASE-006/009` 为整份试跑，`RE-SCRUBD-001` 为第 574–660 行函数级试跑，`RE-SCRUBD-002` 因提示上限阻塞。本项不调用模型、Milvus 或工具；研究真值仍待审。

同日正式检索冒烟发现 `RE-SCRUBD-001` 原始文件含 CRLF；`Path.read_text` 把它规范化为 LF，导致事实摘要不等于登记摘要。新增 CRLF 回归测试先失败，再改为按原始字节解码，2 项测试恢复通过。原始源码摘要与函数片段摘要现分别绑定，未修改原件。

## 正式快照与 D1 预览（S4-01、S4-02）

2026-10-05：新 `formal_recall` 测试先因模块不存在失败；实现后 `PYTHONPATH=tools/experiment:tools/experiment/tests python3 -m unittest tools/experiment/tests/test_formal_recall.py tools/experiment/tests/test_recall.py -v` 的 8 项通过，`mvn -pl audit-mvp -Dtest=RetrievalCliTest test -q` 退出码 0。离线夹具验证正式快照与 catalog 绑定、四条候选配对、未知条件、短目标无风险事实、错误 ID／分数、模型维度和指针变化拒绝。另加 Java 结果快照不匹配回归，先失败后通过。

本机只读冒烟使用已固定 BGE 权重、本机 Milvus `127.0.0.1:29531` 和当前 Java JAR：`AC-ASE-006` 在正式快照召回 4 条候选，D1 返回 `NO_RISK_FACT`；`RE-SCRUBD-001` 召回同一 4 条，D1 入选 0，记录“没有经审核且条件适用的完整对比配对”及 Atomic 防御片段条件未知。两者均未调用付费模型；这验证接线和诚实缺口，不是 D1 效果证据。

## 结构化假设与本机工具（S4-03、S4-04）

2026-10-05：先运行新 `HypothesisServiceTest`、`HypothesisCliTest`、`ToolCliTest`，因新类型不存在而编译失败；实现后用本机假网关、假 HTTP 和子进程脚本验证空假设、最多三条的严格 JSON Schema、额外字段／错行号／错证据引用、截断与模型异常。失败始终为 `FAILED/UNRESOLVED`，缺失 usage 为 `null`。网关新 schema 仅用于 `--hypotheses`，原三字段 `AuditService` 未修改。`ToolCli` 将空告警、解析错误分开，支持固定本机配置的 Slither 与可选 Mythril；空告警不输出 SAFE。`mvn -pl audit-mvp -Dtest=HypothesisServiceTest,HypothesisCliTest,ToolCliTest,GatewayTest,AuditServiceTest,AuditCliTest test -q` 退出码 0；后续加入可选 Mythril 回归后定向测试仍为 0。未请求真实付费 API。

## D2、持久化与本机页面（S4-05、S4-06、S4-07）

2026-10-05：新 D2 测试先因模块不存在失败，随后覆盖工具空告警、工具超时为 UNKNOWN，以及与风险行匹配的显式重入告警可反驳旁路义务。D2 六项义务在证据不足时都保持 UNKNOWN，不把未发现告警当作防护覆盖。新运行器测试先因模块不存在失败，随后覆盖目标与片段双摘要、模型调用前源码变化拒绝、完整提示字节超限不调用模型、计划／事件先持久化、无 usage、模型异常保持未决、只读重放及计划篡改拒绝。HTTP 测试先因新接口参数不存在失败，随后验证页面与状态／预览／历史读取零模型调用，额外字段、重复 JSON 键、未知样本、超大请求和跨源请求拒绝；原离线实验台与 MVP 页面测试均通过。

本机 `127.0.0.1:29531` 正式 Milvus 和固定 BGE 权重的只读离线演练：`AC-ASE-006` 检索 4 条候选，D1 为 `NO_RISK_FACT`，运行 `0c24b53de78c44dbae34b6cb79b51838` 得 `COMPLETED/NO_CONFIRMED_FINDINGS`、D2 `UNKNOWN`、计划 1／失败 0／未知 1，重放与内存结果一致。`RE-SCRUBD-001` 函数级运行 `1e376569d2964c4c8c89810d813108de` 得第 574–660 行、D1 `COMPLETED` 但未选中可审核的完整对比配对、D2 `UNKNOWN`。两次离线运行均为明确的空假设夹具，不是模型审计结论；未运行真实 Slither、Mythril 或付费 API。

本机 HTTP 页面 `http://127.0.0.1:8769/agent.html` 经实际请求核对：`/agent.html`、状态、目标和历史均返回 200；`POST /api/agent/runs` 对 `AC-ASE-006` 离线演练返回 201，运行编号 `c479ded84b3147deb207656f3510607e`；后续新版本对 `RE-SCRUBD-001` 函数级演练返回 201，编号 `6f79bab499e644208653a1615d0e934c`，只读回放和 JSONL 下载均返回 200，报告恰好一行。新版本给结束事件加入结果摘要，早先两个工程演练记录因版本升级不进入新页面历史；磁盘原件仍保留，不能混称为当前可回放版本。页面只将既有阶段数据可视化，不证明 D1 提升或 D2 准确率。

## 本轮限制与分母

- 正式知识快照仍为 `9fc63d0e8828a8caa78145e133b8f954f9fedaf79469ea0927434d7dbef725c8`，集合 `s1b_612ad26b068c4b64842463a633d6d1ba`，四条向量对应两组真实补丁对；本轮只读，不激活新集合。
- 完成的当前版本 HTTP 离线演练 2 次，失败 0，D2 UNKNOWN 2；模型假设由固定空夹具给出，usage 输入／输出均为 `null`。更早两个运行只用于开发中的持久化检查，不并入当前版本分母。真实模型请求 0，真实工具运行 0。
- 两份短访问控制目标没有可绑定正式知识的同类风险事实；重入目标的条件匹配仍有 UNKNOWN，不能由四条知识向量或工程链路推导 D1 的论文效果。函数级试跑上下文不完整；`RE-SCRUBD-002` 仍被提示上限阻塞。
- D2 初版只从已有源码事实和工具行级告警判定显式反驳，其余保护义务维持 UNKNOWN；未运行深度路径求解。真实模型质量、工具可用性和真实提示 token 公平本轮未验证。锁定测试未打开。

## 最终离线回归与待同步状态（S4-08）

2026-10-05 15:46（Asia/Shanghai），当前主目录 `main`、实施起点 `163bd8d`：`mvn clean verify` 退出码 0，Java 47 项全部通过；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` 退出码 0，Python 120 项全部通过。新测试均使用假网关、本机假 HTTP、假索引或固定子进程夹具；默认测试不依赖真实 Milvus、Slither、Mythril 和付费 API。实际本机 Milvus/BGE 离线烟测单列在上文，不计入确定性测试。

`git diff --check` 对整个工作树返回 2，唯一报告为用户在本轮前已有的 `docs/vibe/releases/R1-S3/DATASET_SELECTION_PROPOSAL.md` 末尾空行；本轮未修改该文件，也不会将它纳入本版本提交。本轮已暂存文件的差异检查退出码 0；实际提交与远程同步以 Git 历史为准。

最终 JAR 与运行器重启后，页面再以 `AC-ASE-006` 发起一次离线 HTTP 运行：运行编号 `44baf45837064295800b48ff51574af0`，POST 201，`COMPLETED`、D2 `UNKNOWN`；状态、目标、历史、页面均返回 200，GET 回放 200 且运行编号一致。该次已计入上方当前版本 2 次分母。
