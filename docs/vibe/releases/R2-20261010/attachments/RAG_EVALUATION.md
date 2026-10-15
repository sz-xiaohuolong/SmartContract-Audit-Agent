# 怎样评估检索改进：Ragas 接入与实验口径

我们需要知道 D1 为什么有效或无效：它有没有把有用的修复案例排在前面，模型的解释有没有证据支撑，以及最后有没有找对漏洞。只看漏洞发现 F1，无法分清检索和生成各自的贡献。

本次采用 Ragas 作为**可选的语义评估工具**，同时新增不调用模型的人工相关性排序评估。两者从保存的实验批次读取当时真正消费的文本，生成独立报告，不改变审计流程和 D2 裁决。接入工程已完成本机验证；真实相关性标注和真实评判模型实验尚未完成，因此目前不能宣布 D1 的检索增益。

## 对 Gemini 调研的判断

选择 Ragas 合理，但不能沿用调研中的所有论断。

| 原建议 | 核对后的结论 |
| --- | --- |
| Ragas 有学术依据 | 有。Es 等人的工具论文发表于 EACL 2024 系统演示论文集，可准确引用；没有证据支持“顶会几乎全部使用”或“导师直接认可” |
| DeepEval 必须上云，不能灵活用本地模型 | 不准确。其文档明确说明云端平台是可选项，也提供模型适配能力；本次选择 Ragas 的原因是其指标接口适合现有 Python 分析流程 |
| 接入 Ragas 只需复制几行示例 | 示例没有处理版本、实际消费文本、失败、用量和评判成本。当前接入固定 Ragas 0.4.3，使用 `ragas.metrics.collections` 接口 |
| Context Relevance 与 Context Precision 是同一指标 | 不是。前者评估上下文对问题的相关程度；后者还使用参考答案并考虑排序。相关性、检索准确性和漏洞正确性不能互相替代 |
| Answer Correctness 可以衡量 riskLine 命中率 | 不能直接替代。语义正确性不等于行号或函数匹配，定位评价仍需独立的漏洞位置标注和明确匹配规则 |
| 忠实度高说明抑制了漏洞幻觉 | 只能说评判模型认为回答得到给定材料支撑。检索案例本身可能错误，且待审代码与历史代码不是同一合约；应另外抽样审核 |
| Ragas 与 D2 结合就能提供数学安全保证 | 当前系统不具备这种全局保证。D2 是有限范围的证据核验，未知和证明范围仍需保留，不能让高分绕过核验 |

Ragas 官方还提供其他指标，并不存在必须照搬的一组“三元组标准”。工具本身也不是本项目的算法创新；创新仍需通过独立标注、可比基线和消融实验来检验。

## 三层结果分别回答什么

以 `withdraw` 为例：系统检索到“先更新余额再付款”的历史修复，模型提出当前函数可能存在重入。这时应分开回答以下问题。

1. **检索排序：参考案例选得好吗？** 人工查看固定候选池，给每个片段标注 0（无关）、1（部分相关）、2（直接相关）。离线计算 P@k、候选池 Recall@k、MRR@k 和 nDCG@k。
2. **语义诊断：材料有用、解释有依据吗？** Ragas 用显式指定的评判模型计算上下文相关性、参考答案精度／召回与忠实度。它们是辅助分数，需要人工校准。
3. **最终效果：漏洞找对、证据充分吗？** 沿用现有模型发现统计及 D2 的支持／反驳／未知报告。位置级正确率需要额外审核，不能从 Ragas 分数推算。

论文可以描述为“检索质量、生成依据和程序证据分层评估”。不要写成“语义评分加形式证明已彻底解决幻觉”。

### 离线排序指标

| 指标 | 含义与边界 |
| --- | --- |
| P@k（前 k 项精确率） | 前 k 个片段中相关项的数量除以固定 k。返回不足 k 项时仍除以 k，避免少返回就抬高分数 |
| 候选池 Recall@k（召回率） | 找回的相关片段除以人工审核的候选池全部相关片段；**不代表整个知识库的召回率** |
| MRR@k（首个相关结果的倒数排名） | 第一个相关片段位于第 2 名时为 1/2；没有命中且池中有相关片段时为 0 |
| nDCG@k（考虑等级和顺序的排序质量） | 直接相关比部分相关贡献更高，靠前比靠后贡献更高；与同一池的理想排序比较 |

无检索的 VANILLA 不参与检索评分。完整审核后池内没有相关片段时，召回率、MRR 和 nDCG 为未定义；未审核和缺失不能当作 0。两种检索算法只有在源码、快照、候选池一致且均可评分时，才进入共同目标比较。

当前单位是**片段**：一组漏洞／修复对包含两个片段，不能把 D1 的一对与 DENSE 的一片当成相同 k。完整提示 token 预算仍待核验，本工具不自动宣称原三策略已经公平。

### 接入的 Ragas 指标

| 配置名称 | 输入 | 解释 |
| --- | --- | --- |
| `context_relevance` | 待审源码与任务、实际检索文本 | 不依赖参考答案；Ragas 使用同一评判模型的两套提示，不是两名独立审核者 |
| `context_precision` | 上述输入、人工参考答案 | 按顺序累计的语义精度，不能与离线 P@k 混为同一数值 |
| `context_recall` | 上述输入、人工参考答案 | 参考答案中的陈述被检索材料覆盖的程度，不是知识库相关文档召回率 |
| `faithfulness` | 待审源码、历史案例、模型原候选 | 回答在给定证据范围内的支撑程度；本项目范围标为 `TARGET_SOURCE_AND_RETRIEVED_CONTEXTS` |

参考答案应由独立审核人描述该任务需要的机制知识和依据，例如“需要检查余额写入与外部调用顺序，并考虑其他入口是否使用同一保护”。历史案例通常无法证明待审合约的具体行号。若参考答案包含目标特有事实，Context Recall 低分未必表示检索质量差，必须结合人工审核解释。不能直接把 `hasVulnerability=true` 或模型自己的答案改写成参考真值。

未报告漏洞的回答不计算忠实度，不能记为满分。模型失败不生成“安全”回答。定位准确率、Answer Correctness、Answer Relevancy 和嵌入评估没有在本次自动接入，以免引入额外模型／嵌入成本或混淆评价对象。

## 怎样使用

以下命令在项目根目录执行。输出目录必须不存在，历史结果不覆盖。普通导出和排序只用 Python 标准库；语义评估单独安装依赖。

### 第一步：从一个保存批次导出

```bash
python3 tools/experiment/eval_ragas.py prepare \
  --batch research-artifacts/runs/benchmarks/9ec220e9e03c485c8871703ec4711b27 \
  --output research-artifacts/runs/derived/ragas-new-input
```

输出 `dataset.json` 与 `qrels.template.json`。前者是冻结评估输入，带原批次、行摘要、源码／快照／候选池身份、真实上下文和模型原候选；后者是相关性审核表，所有等级初始为 `null`，即尚未标注。

首次做真实评判时，在上面的命令中加 `--sample-id 样本编号`，只导出一个目标及其原计划策略；该选项可重复。未知或重复编号会被拒绝。不要修改已导出的文本后继续沿用旧的输入摘要。

导出读取原件或 gzip 归档，在批次写锁内固定读取。只有实际文本与输入收据、证据 ID 和摘要匹配才可评估。旧函数范围如果没有保存确切消费文本，保留为输入缺失（MISSING_INPUT）；身份冲突标为输入无效（INVALID_INPUT）。不会调用当前检索器重建旧上下文。

**本次只读检查：** 上述初始批次有 159 个计划单元，29 个输入完整，130 个缺少可评分输入。这是分段采集中的初始批次，不能代表 2026-10-14 全部正式请求；其续采原件仍在各自批次内。本入口一次分析一个批次，不自动合并不同计划、构建阶段或重复请求。没有独立审核时，29 个输入完整单元也不能产生人工排序分数。

### 第二步：人工审核，再算排序

复制模板到自己的审核文件。对每个待评估查询，核对 `sourceHash`、`snapshotId` 和 `poolHash`；沿 `origin.batchPath` 找到对应 `samples.jsonl` 的 `retrieval.pool.candidates`，查看全部候选内容和来源。压缩原件用 `storage.read_artifact()` 读取。

将 `grades` 中全部候选填为 0、1 或 2，填写 `reviewer`（审核人）和 `rationale`（审核依据），完成后才把 `reviewStatus` 改为 `REVIEWED`。参考答案 `reference` 可留空；只有前述两项依赖参考答案的 Ragas 指标需要它。审核表必须覆盖候选池，不允许只标注入选案例。

```bash
python3 tools/experiment/eval_ragas.py offline \
  --dataset research-artifacts/runs/derived/ragas-new-input/dataset.json \
  --qrels /绝对路径/人工审核后的相关性表.json \
  --k 4 \
  --output research-artifacts/runs/derived/ragas-new-ranking
```

输出中文 `report.md` 和逐项 `report.json`。省略 `--qrels` 可检查可评估覆盖，分数保留空值。JSON 同时保存各策略有效分母和 `paired` 共同目标结果，论文比较应使用后者。

### 第三步：按需启用评判模型

本机已验证 Python 3.12、Ragas 0.4.3。固定依赖包括兼容的 `langchain-community==0.3.31`；仅安装最新传递依赖可能在导入阶段失败。

```bash
# 已存在该环境时跳过创建步骤。
uv venv --python 3.12 .local/ragas-venv
uv pip sync --python .local/ragas-venv/bin/python tools/experiment/ragas-requirements.lock
cp config/ragas.example.json .local/ragas-judge.json
```

编辑本地配置，填写实际 `baseUrl`、`model`、`apiKeyEnv`、请求上限和指标。凭证通过配置指定的环境变量提供；本机无鉴权服务也显式设置非秘密占位值。配置不会自动读取既有审计模型或切换 Ark 计费端点。支持 OpenAI 兼容的 Chat Completions 结构化响应；本机夹具已验证，实际 Ark／vLLM 模型是否遵循 JSON Schema 仍需单独冒烟。明确只支持 JSON Object 的服务可将 `responseFormat` 设置为 `json_object`，没有自动降级。

**下面的命令会向所配置的服务发送源码、历史案例和模型候选。** 运行前确认已选择目标样本、端点、模型和请求上限；接入本身不代表授权新的付费批量实验。

```bash
.local/ragas-venv/bin/python tools/experiment/eval_ragas.py judge \
  --dataset research-artifacts/runs/derived/ragas-new-input/dataset.json \
  --config .local/ragas-judge.json \
  --allow-model-requests \
  --output research-artifacts/runs/benchmarks/ragas/new-judge
```

需要 Context Precision／Recall 时，在配置中加入对应指标，并提供 `--qrels`。缺参考答案会明确跳过，不会悄悄用待评估模型答案代替。

一次指标计算可能包含多次请求：Context Precision 通常每片段一次，Context Recall 一次，Context Relevance 两次，Faithfulness 通常两次。`maxRequests` 限制整个运行的请求尝试，指标内部同样受限；SDK 与评估层零自动重试。超时、格式错误、无效评分、预算耗尽都保留空分数。Ragas 相关性指标内置的部分失败回退也被适配层识别，不冒充完整成功。忠实度还会核对生成陈述与逐条判断完整对应；漏项、重复或改写不能缩小分母来抬高分数。

输出包含中文报告、逐指标状态、共同目标比较、请求体、原始响应和收据。每次请求前保存开始记录，中断后不自动续发；输出目录不能复用。凭证不写入文件，用量缺失保留 `null`；没有可靠价格信息时不估算费用。关闭 Ragas 遥测与 LangSmith 跟踪，不默认上传云端看板。

## 论文实验还需要完成什么

先从独立于调参的目标集中抽取访问控制、重入与无漏洞对照；冻结知识库、同池候选和相关性审核。参考标签应由独立审核人建立，报告审核人数、分歧处理及一致性。审核人看到算法名称可能产生偏差，宜隐藏策略后再打相关性等级。

固定相同的源码范围、k、完整提示 token 预算与生成模型，比较 DENSE、字段筛选与 D1；VANILLA 只参与最终发现效果对照。先报告离线排序，再用固定评判模型做语义诊断，抽样与人工判断对照。重复实验、置信区间和统计显著性尚未在本工具中计算，不能从单次均值推导。

所有结果继续标为研究效果尚未验证（UNVERIFIED），直到独立标注、正式协议和真实评判完成。高忠实度不作为进入 D2 的筛选门槛，也不改变未知状态。

## 来源与实现

以下来源于 2026-10-15 核对：

- Es 等：[RAGAs: Automated Evaluation of Retrieval Augmented Generation，EACL 2024 系统演示论文](https://aclanthology.org/2024.eacl-demo.16/)，页 150–158，DOI：10.18653/v1/2024.eacl-demo.16。
- Ragas 官方：[Context Precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)、[Context Recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)、[Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)、[Context Relevance](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/nvidia_metrics/)、[0.3 到 0.4 迁移](https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/)。具体运行以依赖锁的 0.4.3 为准。
- DeepEval 官方文档源：[RAG 指标](https://github.com/confident-ai/deepeval/blob/main/docs/content/docs/(use-cases)/getting-started-rag.mdx)、[云平台可选的说明](https://github.com/confident-ai/deepeval/blob/main/docs/content/integrations/frameworks/anthropic.mdx)。

实现入口：[eval_ragas.py](../../../../../tools/experiment/eval_ragas.py)、[ragas_judge.py](../../../../../tools/experiment/ragas_judge.py)、[依赖锁](../../../../../tools/experiment/ragas-requirements.lock)、[无凭证配置示例](../../../../../config/ragas.example.json)。验收统一记录在 [VERIFICATION](../VERIFICATION.md)，任务位于 [统一计划](../IMPLEMENTATION_PLAN.md)。
