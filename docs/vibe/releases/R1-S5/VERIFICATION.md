# R1-S5 真实知识库与页面试跑验证

2026-10-07。本轮完成真实案例的来源固定、谱系合并、新版知识快照和页面单样本三策略入口。下述离线运行仅验证工程链路，**没有调用付费模型，也不能证明 D1 提升了检测效果**。

## 数据来源与隔离

新增 [原件核对](evidence/source-review.json) 将 [RabbitHole 原始高危报告](https://github.com/code-423n4/2023-01-rabbithole-findings/issues/608)及[已合并修复](https://github.com/rabbitholegg/quest-protocol/pull/86)放入知识侧；[JPEG’d 原始报告](https://github.com/code-423n4/2022-04-jpegd-findings/issues/81)及[已合并修复](https://github.com/jpegd/core/pull/19)、[Infinity 原始报告](https://github.com/code-423n4/2022-06-infinity-findings/issues/184)及[项目方修复提交](https://github.com/infinitydotxyz/exchange-contracts-v2/commit/b90e746fa7af13037e7300b58df46457a026c1ac)放入独立验证侧。RabbitHole 原修复前文件与审计版本一致；JPEG’d 的审计版与补丁父提交仅目标函数一致，不能宣称整文件相同；Infinity 的修复是目标函数增加 `nonReentrant`。新增九份源码、原始报告正文与修复源码已按原字节保存于 [原件镜像](evidence/originals/)，九份 SHA-256 全部与[登记](evidence/assignment.json)吻合。源码 SPDX 分别为 MIT、GPL-3.0、MIT；RabbitHole 仓库与文件许可声明不一致，来源记录保留该事实。

合并既有 Maia、Atomic Loans 知识案例及 PoolTogether 验证案例后，[正式清单](evidence/formal-v2-ledger.json)为知识 3 组、验证 3 组；知识对应[三组真实补丁对](evidence/formal-v2-pairs.json)。[泄漏报告](evidence/formal-v2-leakage-report.json)摘要为 `581a083047ba2a8d8eefe8b34f2e32d219d170544941116d8ec0101b7e622df6`，`errors=[]`、`nearCloneCandidates=[]`、`pendingSamples=[]`。开发样本另外与正式清单联合检查，不能借开发目标反向污染知识和验证。验证目标均以函数级源码进入页面；修复版仅作为报告证据，不作为“整份合约安全”的负例。

## 快照与页面证据

[快照收据](evidence/snapshot-receipt.json)：固定本地 BGE 模型离线编码，生成 6 条 384 维知识向量；内容寻址快照 `5381e15f60729bf4e475572f0717e911d316e4754a17f9d0cf74cf341a3d76c3`。Milvus 新集合 `s1b_a6741615b74240909978e25ae2264476` 的六条正文和向量完整读回后才激活。旧集合没有删除。本机 `active_snapshot` 再读回通过。

页面 [单样本工作台](http://127.0.0.1:8769/agent.html)展示三个独立验证目标和三种策略：向量召回、简单条件字段过滤、D1 对比检索。每个目标的三种策略来自相同快照与同一候选池；入选上下文上限同为 2048 UTF-8 字节，每次显式真实点击最多一次模型请求、2048 输出 token、零自动重试。**字节上限不是完整提示的真实 token 公平**，当前缺少经独立复核的目标—案例适用性标签，因此页面始终 `researchEligible=false`。真实模型选择由本地凭证配置读取，本轮未调用。

实际经 HTTP 页面接口做九次离线试跑并用 `audit_run.replay` 逐项核验 `plan.json`、`events.jsonl`、`sample.jsonl` 和 `result.json`。[逐次运行收据](evidence/ui-offline-smoke.json)列出各运行编号和报告路径。三个目标各三种策略，共 9 项；完成 9、失败 0、D2 未知 9、真实模型请求 0。逐目标候选池摘要在三种策略间一致。按向量／字段过滤／D1 顺序，入选片段数为：PoolTogether `1/2/0`，JPEG’d `2/1/0`，Infinity `1/0/0`。所有离线模型假设都是固定空夹具，结论为 `UNRESOLVED`。这组结果显示当前 D1 的条件绑定**覆盖不足**，尤其 JPEG’d 的 `_mint` 内部状态变化和 Infinity 的跨函数路径不能被轻量事实提取完整表示；不能从中推断真实审计准确率或优势。

## 重放命令

在本机已有 R1-S3 固定原件、固定 BGE 权重和本机 Milvus 时，可以重建并校验：

```bash
mkdir -p .local/r1-s5/sources .local/r1-s5/reports .local/r1-s5/patches
cp docs/vibe/releases/R1-S5/evidence/originals/sources/* .local/r1-s5/sources/
cp docs/vibe/releases/R1-S5/evidence/originals/reports/* .local/r1-s5/reports/
cp docs/vibe/releases/R1-S5/evidence/originals/patches/* .local/r1-s5/patches/
PYTHONPATH=tools/experiment python3 tools/experiment/first_batch.py audit --intake docs/vibe/releases/R1-S5/evidence/intake.json --assignment docs/vibe/releases/R1-S5/evidence/assignment.json --root . --source-dir .local/r1-s5/sources --output-dir .local/r1-s5/candidate
PYTHONPATH=tools/experiment python3 tools/experiment/d1_admission.py --candidate-ledger .local/r1-s5/candidate/ledger.json --decisions docs/vibe/releases/R1-S5/evidence/decisions.json --root . --base-ledger .local/d1-kb-v1/ledger.json --base-pairs .local/d1-kb-v1/pairs.json --output-dir .local/r1-s5/formal-v2
PYTHONPATH=tools/experiment HF_HUB_OFFLINE=1 .local/d1-embed-venv/bin/python tools/experiment/d1_embed.py --ledger .local/r1-s5/formal-v2/ledger.json --pairs .local/r1-s5/formal-v2/pairs.json --root . --output-dir .local/r1-s5/formal-v2 --model-dir .local/d1-embedding-model
PYTHONPATH=tools/experiment python3 tools/experiment/d1_kb.py --ledger .local/r1-s5/formal-v2/ledger.json --pairs .local/r1-s5/formal-v2/pairs.json --vector-bundle .local/r1-s5/formal-v2/candidate-vectors.json --root . --snapshot-root .local/d1-kb-snapshots
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from milvus_rest import MilvusRestIndex; from snapshots import active_snapshot; print(active_snapshot(Path(".local/d1-kb-snapshots"), MilvusRestIndex("http://127.0.0.1:29531")))'
PYTHONPATH=tools/experiment HF_HUB_OFFLINE=1 .local/d1-embed-venv/bin/python tools/experiment/local_ui.py --port 8769
```

新环境首次激活新快照才需要调用 `activate_snapshot`；若已有[快照收据](evidence/snapshot-receipt.json)所列集合，只运行 `active_snapshot` 读回，不重复创建。旧基础原件与模型准备方法见 [R1-S3 知识库记录](../R1-S3/D1_KB_READINESS.md)。页面每次点击结果保存在 `.local/audit-runs/<运行编号>/`，历史读取不重新调用模型。

离线验证：`mvn clean verify` 成功，Java 47 项；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v` 成功，Python 127 项。测试不依赖真实 API、Milvus 或未锁定工具环境。本机 Milvus 和 HTTP 页面冒烟单独列为集成验证。

## 下一步研究判断

当前仅能保留 D1 作为待证伪方法，**不能报告提升**。知识侧重入只有一组，真实验证侧函数级事实无法覆盖跨函数状态和修饰器防护；先补充独立项目的合格重入知识／验证案例并扩大到原定 10～15 个候选事件内，再请独立人员逐目标标注适用性、支持及反证价值。冻结真实 tokenizer、完整聊天模板与项目级评分口径后，才能在同池和完整 token 预算下比较三种策略；锁定测试集仍不得用于调参。
