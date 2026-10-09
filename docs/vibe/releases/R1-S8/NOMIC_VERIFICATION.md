# Nomic 对照与结构化输出修复验收

2026-10-09。工程验证完成，已执行本机真实模型实验。最终 Nomic 原文重放报告为 159 项有效、失败／UNKNOWN 0；旧 BGE 原始记录保留。D1 在本轮仍未超过向量召回，不能宣布研究改进。

## 知识、模型与来源

- 同一 AutoMESC 300 组改动对、600 条文本，源目录 `.local/dataset-candidates/r1-pending`；原表、提交与来源摘要沿用 [自动知识验收](AUTO_EXPERIMENT_VERIFICATION.md)。49 组明确防御差异、251 组软配对；全部为自动标注，未伪装成逐案证实的安全修复。
- BGE 活动快照 `4566ccb54e07d7a4fec54e5dadfe0d0ae9b508b5565c1022154598d7b94e1820`，集合 `s1b_5e2e9fa91d2d4433b0a7ddf12cffb256`，384 维；原目录 `.local/d1-kb-snapshots` 保持不变。
- Nomic 活动快照 `a6d70058bb93a26505def7878553d01e7667248d387f41a101a4ff2f71bd36db`，集合 `s1b_nomic_bddddf9a77d34aa1b898409789453ec8`，768 维，独立目录 `.local/d1-nomic-snapshots`。两个集合均完整读回 600 条且内容校验一致。
- Ollama：`http://127.0.0.1:11434/api/embeddings`，`nomic-embed-text:latest`，摘要 `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`。文档用 `search_document: `，查询用 `search_query: `，向量经有限数值、维度、非零和归一化检查。
- 编码断点 `.local/d1-nomic-embeddings/vectors.jsonl` 持久化 600 项；已完成项再次构建不重复编码。完整文本仍存快照，截取记录在回执。
- 目标仍为独立 SmartBugs 49 个公开漏洞源码与本机 4 个 OpenZeppelin 安全对照函数：53 目标 × DENSE／FIELD_FILTER／D1。知识—测试源码摘要、项目和近克隆检查沿用原登记，跨项目重叠 0，最大近克隆相似度 0.815789，小于 0.85。目标类别对所有策略公开，布尔真值仅进入评估。

### 窗口事实

本机 Nomic 元数据与实际拒绝行为显示有效窗口为 **2048 token**；即使请求配置 `num_ctx=8192`，长输入仍返回窗口超限。本轮不是 8192 token 实验。[Ollama 官方模型页](https://ollama.com/library/nomic-embed-text)同样标为 2K；[Nomic 原模型说明](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)说明文档／查询应使用各自任务前缀。
本地 BGE tokenizer 实测：600 条中 250 条超过 512 token，最长 2891 token；Nomic 本机编码回执：17 条文档被截取，53 个查询均未截取。因两模型分词器不同，不能把字符截取回执当作相同 tokenizer 的精确 token 数。更少截取说明输入覆盖变广，不单独证明审计提升。

## 结构化输出与重试

- Jackson 前提取首尾最外层对象，接受 Markdown 围栏／前后说明；仍拒绝重复键、多对象和不可解析正文。必需语义字段存在即可，附加标题／严重程度不造成失败。
- 整数行号或可解析数字字符串均可；溢出、范围错误仍拒绝。`evidenceIds` 缺失或 null 视为无引用，未知／重复 ID 仍拒绝。
- 合约名按源码声明归一化，函数支持末尾括号、大小写、实际构造函数别名与无名回退函数。先核对真实声明及其行范围，避免把 `Missing.missing` 普通函数误当作构造函数。完整合约允许真实声明的不同函数；函数片段仍限制在目标范围。
- 每条假设分别核对。保留通过校验的真实发现，被拒绝项另记 `rejectedHypotheses`；部分拒绝显示 `PARTIAL_HYPOTHESES_REJECTED`。全部拒绝仍 FAILED／UNRESOLVED，不能变成安全。
- 网关对 HTTP 429、连接闪断／EOF 仅重试一次，等待 1 秒；SDK 重试关闭。认证／永久错误不重试，解析错误不重新调用模型。实际 `requestAttempts` 落盘，完整真实批次实测 159 次尝试，无重试触发。
- CLI 原文诊断保留；自动批次原文另存 `.local/auto-benchmark-diagnostics/`，记录路径与权限。`--replay-response` 完全离线；派生结果记录原始批次、正文摘要、解析 JAR 摘要和追加请求 0。原用量／耗时不会被重放清零，缺失 usage 仍为 null。

## 运行证据与分母

- Nomic 离线批次 `aee62962864c45e5816b364f08272f28`：159 完成、失败 0、UNKNOWN 159、池冲突 0。离线空假设不作为安全预测。
- 最近 BGE 真实基线 `69cc13d23d34414a85f8536769728c4f`：159 单元、149 有效、10 解析失败／UNKNOWN。之前的 `e2d55443e02549a386bdd93f222998c6` 等记录也未覆盖。
- Nomic 原始真实批次 `c2df251864914b3eb84f5038b08f4ef1`：159 次 HTTP 尝试，154 有效、5 解析失败／UNKNOWN。原始 JSONL 不修改。
- 最终原文重放 `5e7a69b3a18f4cfa8b3f75a9f17d8a42`：恢复 5 个解析失败，159 有效、失败 0、UNKNOWN 0、池冲突 0，追加模型请求 0；其中一项保留有效 withdrawBalance 假设，拒绝无目标声明的攻击者 fallback 附加假设。
- 修复前停止的试跑 `d7039f1e5124449184f755e29ffe2b7e` 保留：持久化 11 个结果，12 个 STARTED，其中最后一个调用未落盘，供应商是否接受及用量未知；不计入正式对照。不能将总调试开销写成只有正式批次 159 次。

## 横向描述性对比

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

## 验收与重放命令

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
