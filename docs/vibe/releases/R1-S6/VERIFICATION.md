# R1-S6 批量对照与数据规模调研验证

## 2026-10-07 真实运行授权后的补充验收

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

## Milvus 清理与当前知识

清理前核对正式指针 `.local/d1-kb-snapshots/active.json` 与工程指针 `.local/mvp-kb/active.json`，只删除无活动指针引用的三个旧集合：`mvp_b51c012b788548a6bca40e3ca91d67ae`、`s1b_2f8522116d6b43e693092c303947be6a`、`s1b_612ad26b068c4b64842463a633d6d1ba`。历史本机运行报告没有删除；旧集合的数据库查询不能再回放。

再次经 Milvus REST `collections/list` 查询，仅剩：

- `s1b_a6741615b74240909978e25ae2264476`：当前正式知识，快照 `5381e15f60729bf4e475572f0717e911d316e4754a17f9d0cf74cf341a3d76c3`，`active_snapshot` 完整读回通过，六条向量对应三个真实补丁对。
- `mvp_ec838f133828429f8b9fc0f53a1b2948`：仍被工程 MVP 活动指针引用的演示集合，三条工程片段，不能当作正式科研知识。

当前正式清单依旧是三个知识组与三个独立验证组；[S5 来源与泄漏报告](../R1-S5/VERIFICATION.md)给出项目、事件、补丁对和近克隆隔离证据。本轮没有将验证源码、合成演示库或未经核对的数据批量导入 Milvus。

## 批量对照与页面

[批量编排](../../../../tools/experiment/batch_compare.py)在开始前持久化计划，按目标与策略逐项写入 `samples.jsonl`；每项调用前先持久化 `STARTED`。续跑跳过已完成项，将“曾开始但未落结果”的项记为失败且未知，不自动重发。断裂的末尾 JSONL 行可恢复，完整损坏记录不静默放行。计划固定快照、来源摘要、组合与提供方；单次结果若绑定不同快照或源码则拒收。

本机 [批量审计工作台](http://127.0.0.1:8769/agent.html)支持选择三个独立验证目标和三种策略、预览上界、运行离线批量对照、查看按策略对比及下载 JSONL；单样本预览与显式真实运行入口保留。真实批量计划可展示端点、模型、最多九次请求、18432 输出 token、90000 输入 UTF-8 字节，但输入 token 与费用上界仍为 `null`，因此 HTTP 返回 422，页面不允许启动。字节数不充作完整提示 token 公平。

最新实际本机 HTTP 冒烟编号：`f9ca2a32f8fb4a6abc1ac4b005cba092`，逐样本报告位于 `.local/audit-batches/f9ca2a32f8fb4a6abc1ac4b005cba092/samples.jsonl`，对应单次审计详情在 `.local/audit-runs/<运行编号>/`。目标为 `AC-ASE-040`、`RE-INFINITY-001`、`RE-JPEGD-001`，策略为 `DENSE`、`FIELD_FILTER`、`D1`，全部绑定同一正式快照。同目标三策略的候选池摘要无冲突。九项完成、失败 0、未知 9；入选证据计数分别为向量召回 4、字段过滤 3、D1 0。输入／输出 usage 均为 `null`，检测召回、检索 Recall@K、nDCG 等均为 `null`。这是固定空假设的工程报告，不能作为模型检测性能。

UI 浏览器验收已确认：页面显示三个验证目标、三策略选择、批量计划上界、历史报告，以及“完成 9／未知 9”的策略对比表和 JSONL 下载链接。真实运行未点击。

## 离线验证与重放

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
node --check tools/experiment/local_ui/agent.js
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from batch_compare import replay_batch; import json; print(json.dumps(replay_batch(Path(".local/audit-batches"), "f9ca2a32f8fb4a6abc1ac4b005cba092")["denominators"], ensure_ascii=False))'
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from milvus_rest import MilvusRestIndex; from snapshots import active_snapshot; index=MilvusRestIndex("http://127.0.0.1:29531"); print(index.request("collections/list", {})); print(active_snapshot(Path(".local/d1-kb-snapshots"), index))'
```

结果：Maven 构建成功，Java 47 项；Python 136 项；JavaScript 语法检查通过。新测试覆盖计划上界、批量逐项落盘、真实批量拦截、接口读回、来源漂移、断点续跑防重复和残缺 JSONL 尾行恢复。Milvus 与页面冒烟需本机服务及既有模型权重，未纳入离线自动测试。

## 研究判断

经 [文献规模与实验设计](RESEARCH_DESIGN.md)核对，当前知识只有三组项目事件，重入知识仅一组；三个验证目标上 D1 尚未选出适用完整对比配对。人工目标—案例标签、可靠安全负例、真实 tokenizer 和完整提示预算仍缺。**D1 只能保留为待证伪方法，当前不具备宣称增益或开展付费批量效果实验的条件。**下一步按项目事件扩充经审真实补丁对，先解决条件事实覆盖，再冻结标签与 token 公平方案。
