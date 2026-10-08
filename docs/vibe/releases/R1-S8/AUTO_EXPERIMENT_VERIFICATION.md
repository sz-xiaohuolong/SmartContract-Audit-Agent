# 自动标注知识快照与批量对照验收

## 数据与快照

本轮复用本机固定的 AutoMESC 原始候选收据，按项目保留 300 组改动前后片段：访问控制 150 组、重入 150 组，共 600 条 384 维向量。自动差异规则识别 49 组有明确保护特征的改动；其余 251 组仅能证明代码发生变化，供带有显式缺口提示的软对比检索使用。`review_status=AUTO_LABELED`、`evidence_tier=HEURISTIC`、来源提交、源码摘要和规则版本写入快照清单，未把自动标签伪装成逐案人工审核。

活动快照 `4566ccb54e07d7a4fec54e5dadfe0d0ae9b508b5565c1022154598d7b94e1820`，Milvus 集合 `s1b_5e2e9fa91d2d4433b0a7ddf12cffb256`。发布前已对 600 条 ID、正文和向量逐页完整读回，之后才原子切换 `.local/d1-kb-snapshots/active.json`。旧快照和独立 `r1pending_` 候选集合仍保留；FORGE 142 条单侧资料没有明确修复对应项，本轮未转作正反例。

验证目标是 SmartBugs Curated 的 49 条公开漏洞样本（访问控制 18、重入 31），加本机 OpenZeppelin 衍生安全函数 4 条，共 53 条。目标与 AutoMESC 知识的项目交集为 0；完整源码最大近克隆相似度为 0.815789，低于当前 0.85 排除阈值。安全对照只覆盖 4 个访问控制函数，类别明显不平衡。漏洞类型作为**已知定向审计任务**传给三种策略，是否有漏洞只在评估器中使用；因此这里不能代表未知类别的通用合约审计。

## 三策略与指标口径

三策略复用同一快照、同一个按目标固定的候选池及 2048 字节证据上下文。向量基线按分数入选；字段基线仅按已知目标漏洞类别字段过滤，不依赖 D1 条件绑定；D1 优先选择显式条件配对，缺失时按同一改动对两侧的向量分数与差异重排，软配对明确标注未经修复证据核验。输出报告逐项保存候选池摘要、入选 ID、模型结论、错误类别、用量和耗时。

`TP/FP/FN/TN` 只统计实际结构化模型的“报告漏洞／未报告发现”，后者不表示源码已被证明安全。失败、超时、解析错误和离线空假设为 `UNKNOWN`，不进入混淆矩阵，但始终保留分母。缺失 usage 为 `null`。`类别命中@K` 与 `类别召回@K` 只检查入选知识的漏洞类别与目标标签是否一致，**不是**人工标注的目标—案例相关性，也不是论文级检索 Recall@K。完整提示的 tokenizer 公平尚未验证，报告显示各策略实际 token，不能仅凭 UTF-8 字节上限宣称等 token 对照。

## 工程复现

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

## 真实模型批次

本机真实模型完整批次为 `e2d55443e02549a386bdd93f222998c6`，同一快照与每目标同一候选池，计划 159 项、有效结构化结果 147、失败/UNKNOWN 12、未执行 0、候选池冲突 0。失败中结构化输出无效 10 项、模型调用错误 2 项，均未折算安全结论。逐项 `samples.jsonl`、`samples.csv`、`summary.json` 位于 `.local/auto-benchmark-runs/e2d55443e02549a386bdd93f222998c6/`；页面历史列表也可打开与下载。

| 策略 | 有效／计划 | TP | FP | FN | TN | Precision | Recall | F1 | 平均输入／输出 token | 平均模型耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 向量召回 | 48／53 | 40 | 1 | 5 | 2 | 0.976 | 0.889 | 0.930 | 1363.6／150.8 | 4635 ms |
| 简单字段过滤 | 50／53 | 41 | 3 | 5 | 1 | 0.932 | 0.891 | 0.911 | 1303.4／170.5 | 4927 ms |
| D1 对比检索 | 49／53 | 40 | 1 | 7 | 1 | 0.976 | 0.851 | 0.909 | 1186.8／155.6 | 4593 ms |

各行有效分母不同，因此主要参考**三策略共同有效的 43 个目标**：向量召回 TP 37、FP 1、FN 4、TN 1，F1 0.937；字段过滤 TP 36、FP 2、FN 5、TN 0，F1 0.911；D1 TP 37、FP 1、FN 4、TN 1，F1 0.937。D1 相对向量召回在 3 个目标上纠正结果，同时在另外 3 个目标上变错，整体没有净提升；相对字段过滤为 4 个目标纠正、2 个目标变错。这是单轮、类别已知、标签未独立复核且安全对照仅 4 个的探索结果，**不能宣称 D1 真实改进合约审计**。下一步应扩充独立安全对照、补人工目标—案例相关性标签、固定完整提示 tokenizer 预算并做多次重复，再决定 D1 保留或收窄。

运行期间曾有两轮被主动中止的批次，其中一轮与 Maven 清理 JAR 重叠，造成局部启动失败；它们保留原始日志但未混入上表。上表只来自重新固定构建产物后的完整批次。
