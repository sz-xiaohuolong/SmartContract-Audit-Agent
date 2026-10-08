# R1-S8 批量准入与正式对照阶段记录

## 2026-10-08 探索性数百条知识检索补充

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

## 候选逐项核对

执行：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/candidate_admission_queue.py --candidate-dir .local/dataset-candidates/r1-pending --output .local/dataset-candidates/r1-pending/admission-queue.json
```

逐项清单的摘要为 `951b953ab5912580db3d7d01898b1e32ac162e3d4ec879d53492a0b2595f8b4c`。442 组候选对应 742 条向量：AutoMESC 300 组，FORGE-Curated 142 条。准入 0 组，待审 442 组；标签提示中访问控制 279 组、重入 163 组，**只是关键词候选，不是真值**。清单逐项记录来源版本、定位链接、正文摘要和缺失证据，不复制完整源码；收据数量与清单不符会拒绝生成。AutoMESC 仅有前后局部片段，缺独立漏洞报告、完整前后源码、安全修复审核与近克隆组；FORGE 有报告／源码条目，但缺可核实修复补丁。它们不能直接复制到 `s1b_` 集合。

另抽查 [Proof-of-Patch 固定版本](https://github.com/ASSERT-KTH/Proof-of-Patch/tree/eca2a566326d7636665c45c670698e05ea12a3ac) 的 [AI Arena 077](https://github.com/ASSERT-KTH/Proof-of-Patch/tree/eca2a566326d7636665c45c670698e05ea12a3ac/findings/077)：本机原版 `MergingPool.sol` SHA-256 为 `b0c5b90a1f1ec659047238063433f52cc69fa95091df9af76d155f69a75ab5dd`，补丁版为 `3469e4a579bb2435b33a65bb592c34f4402d4720e05bb089944f11fc86faa7c8`。原始 `claimRewards` 未带重入锁，补丁增加 `ReentrancyGuard` 与 `nonReentrant`。这是真实修复线索，但当前 D1 成对知识契约仅支持重入的“状态写入移到外部调用之前”；该补丁采取重入锁，不能伪造成现有条件见证。本项保留待审，不作为新增正式知识。Proof-of-Patch 的 001、041、042、054、070、098 等条目虽然有访问控制或重入元数据提示，原始文字描述分别涉及上限、不正确索引、预言机更新、转账／无代码地址和暂停问题；不能凭类别字段转正。

进一步核对 [Proof-of-Patch Cooler 049](https://github.com/ASSERT-KTH/Proof-of-Patch/tree/eca2a566326d7636665c45c670698e05ea12a3ac/patches/049)：其本地补丁确实给 `rollLoan` 增加调用者检查；[Sherlock 原始问题 #200](https://github.com/sherlock-audit/2023-08-cooler-judging/issues/200) 被标为重复报告，[主问题 #243](https://github.com/sherlock-audit/2023-08-cooler-judging/issues/243) 还描述贷款方抢跑更换条款的路径。而元数据指向的[维护者 PR #54](https://github.com/ohmzeus/Cooler/pull/54) 将 `rollLoan` 整体替换为另一套延长贷款流程，不能把数据集中的单行检查称为该 PR 的原样修复。因此它也只保留为待审修复线索。

另下载 [CoinFabrik Solidity RnD](https://github.com/CoinFabrik/solidity-rnd/tree/efd709441987a28bd7220d79b2d872f8c7cfa8d9) 的固定修订，仅读取 15 份 `findings.json` 后统计为 171 条 finding、15 个项目组。其中大小写合并后的重入类别只有 4 条、分属 4 个项目；报告中有“最佳实践”而非已证实可利用事件。抽查 Venus `PegStability.sol` 的前后文件，补丁同时升级编译器并重写大段业务逻辑，无法直接把整份差异归因于单个重入 finding。该来源可继续逐项筛选，不能凭 171 条 finding 将向量库扩成正式配对知识。

## 批量入口与本机重放

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
