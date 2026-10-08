# R1-S7 公开语料候选采集与隔离入库

日期：2026-10-07。此步骤完成数百级**待审候选**的本地采集和 Milvus 入库；尚未完成数百级**正式 D1 知识案例**。集合名称、页面入口及计数单位必须分开理解。

## 来源与筛选

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

## Milvus 实际写入

本地固定模型 `BAAI/bge-small-en-v1.5` 修订 `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` 离线生成 384 维向量。AutoMESC 每组保留改动前和改动后两条，共 600 条；FORGE 每个筛选条目一条，共 142 条。独立集合 `r1pending_3ba8dd13979d18e0087177521ce5583e` 共 **742 条向量**；逐条读取正文、向量和 ID 与本地输入完全一致，唯一 ID 742 个。[本机收据](../../../../.local/dataset-candidates/r1-pending/receipt.json)记录完整身份和计数。二次运行按内容身份识别已写入条目，完整读回，不产生重复项。

每条记录均为 `reviewStatus=PENDING`，AutoMESC 的 `patchStatus=UNVERIFIED`，FORGE 的 `patchStatus=MISSING`。这个集合**不是正式知识快照**，未写入 D1 案例目录，也没有替换 `.local/d1-kb-snapshots/active.json`。正式活动集合仍是 `s1b_a6741615b74240909978e25ae2264476`，内容是已审的三个补丁对、六条向量。当前页面只使用正式集合；742 条待审向量不会悄悄进入实验。

## 谱系与测试集检查

本轮没有把仓库中的 SmartBugs Curated 或 SolidiFI-benchmark 输入候选知识集合。两套原始测试来源本机共有 493 份 `.sol` 文件、486 个不同字节摘要；候选 742 条文本与正式六份原件、上述测试文件的完全字节碰撞均为 0。对 FORGE 的 225 份完整受影响源码与这 493 份测试源码再做归一化五元 token 集合 Jaccard `≥0.85` 筛查，命中 0。AutoMESC 仅有局部 diff，**不能**据此完成近克隆、漏洞事件与项目级隔离证明；FORGE 的报告名也不能独立证明项目组不重合。两套原始数据作为正式验证／测试集还需按漏洞事件和补丁分组、核对标签，锁定集不得用于调参。

## 验证与页面操作

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
PYTHONPATH=tools/experiment python3 -c 'from pathlib import Path; from milvus_rest import MilvusRestIndex; from snapshots import active_snapshot; print(active_snapshot(Path(".local/d1-kb-snapshots"), MilvusRestIndex("http://127.0.0.1:29531")))'
PYTHONPATH=tools/experiment HF_HUB_OFFLINE=1 .local/d1-embed-venv/bin/python tools/experiment/r1_candidate_corpus.py --automesc-dir .local/dataset-candidates/automesc --forge-dir .local/dataset-candidates/forge-curated/flatten/vfp-vuln --output-dir .local/dataset-candidates/r1-pending --model-dir .local/d1-embedding-model --milvus-url http://127.0.0.1:29531
```

验证结果：Maven 51 项 Java 测试、Python 141 项离线测试通过；Milvus 对待审集合 742 条全量读回通过，正式活动指针和六条正式知识读回通过。自动化测试使用内存 Milvus 夹具，不依赖真实数据库、模型 API 或付费服务。本轮真实模型请求为 0。

浏览器打开 [Attu](http://127.0.0.1:3000) 可以在 `r1pending_...` 查看 742 条待审向量；`s1b_...` 才是页面正在使用的正式知识。[审计工作台](http://127.0.0.1:8769/agent.html)现在直接显示“正式知识 6 条向量／待审 742 条向量”的区别。先选择三个独立验证目标和三种检索策略，运行模式选“离线工程演练”，点击“查看运行计划”后再点“开始批量对照”；页面会显示逐策略结果和 JSONL 下载。离线模式仅验证检索、保存与回放，模型结论为固定空假设。要检查真实模型工程链路，可明确选择“真实模型批量运行”并再次查看计划；这会调用付费 API，结果仍只能作为当前六条正式知识的工程观察，不能解释为这 742 条待审资料带来的 D1 增益。

本机 HTTP 实际离线对照编号 `4bafd8746da74a128c16a0ec36c75056`；结果在 `.local/audit-batches/4bafd8746da74a128c16a0ec36c75056/samples.jsonl`。九项完成、失败 0、未知 9；DENSE／FIELD_FILTER／D1 入选证据数为 4／3／0，候选池冲突为 0。输入及输出 token、检测召回、检索 Recall@K 和 nDCG 保持 `null`，不报告效果提升。

## 尚未完成的研究准入

本轮目标中的“数百级正式知识库、足以验证 D1 效果”仍未达成。下一步优先从这些候选中核对真实审计报告、精确修复前后源码和实际补丁，逐事件独立标注目标—案例适用性与正反证据，并将同项目、同事件和近克隆与测试集分开。还须修复 D1 对函数级事实和跨函数时序的覆盖不足、冻结完整提示 token 预算。正式快照构建器当前会拒绝这批 `PENDING` 条目；不能通过把候选数量或代码块数量说成“已审核安全案例”来绕过门禁。
