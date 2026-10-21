# 研究差距：从工程可用走向可信实验

这份报告记录 2026-10-13 当时的差距、投入估计和研究路线。其中“尚未接通”“尚未重放”属于当时状态；之后的工程进展请结合当前进度阅读。它区分数据来源、模型发现、候选核验与论文主张，避免把程序可运行直接当作研究目标达成。

先读 [概念与案例](attachments/CONCEPTS_AND_WALKTHROUGH.md) 理解术语，再对照 [当前实验看板](attachments/EXPERIMENT_DASHBOARD.md)。

<details>
<summary>展开原技术分析、表格与可复核记录</summary>

# VeriRAG：官方实现对标、最终目标差距与剩余阶段审查

审查日期：2026-10-13。范围：研究、只读核查与规划。当前仓库 HEAD 为 `fa4c9f40a8b671fbd324343218044eedca68ccc9`，同时存在未提交实现；本报告不以 HEAD 冒充完整工作区身份。未修改业务源码、标签、冻结知识、历史原件、规格、计划或验收状态；未提交、推送、创建工作树或启动真实模型实验。

标记约定：**事实**表示本轮读到的源码、原件或执行结果；**推断**表示由这些证据支持但尚未用独立实验验证的解释；**建议**表示未来方案；**待验证**表示缺少相应证据。本文的“通过”均限定到具体接缝，不代表学校毕业资格或论文发表资格。

## 1. 直接回答：还剩六个必要验收关口

**建议把冻结目标剩余工作收敛为六个必要阶段：数据与身份封口、D1机制与预算准入、D2真实正反闭环、固定候选重放与四基线、完整工程复现与演示、论文主张与材料结项。** 这是根据当前缺口的依赖和不同验收对象归并出的六个关口，并非六套新 Release 或新 Slice。全部映射到现有 S11／S12；阶段二和三可在阶段一完成对应输入后并行，文稿可提前起草。

当前已经具备可工作的审计系统骨架：输入清理、固定快照检索、结构化候选、编译器事实、Slither 双收据、有限路径、三态结果、派生重放及工作台。**尚未完成的是从这些局部工程能力到可信研究结论的闭环。** 不能用页面完成度、通过测试数量或一次高 F1 代替该闭环。

本轮最重要的事实如下。

1. 最新批次 `6cae40677b104152bd92efedc5bbc479` 的保存原件重算一致：53目标×三策略，共159单元；共同有效51目标的 F1 为 VANILLA 0.9783、DENSE 1.0000、D1 0.9783。D1没有超过最强对照；本批212个D1入选片段的适用性全部为 UNKNOWN，不能据此验证条件适用性的独立作用。
2. D2的151条保存假设中，12 SUPPORTED、0 REFUTED、139 UNKNOWN，未知率92.05%。12条支持仅来自4个重入目标在三策略下的重复，不是12个独立事件；访问控制尚无支持，真实维护者修复的正反闭环仍缺失。
3. 当前源码含风险目录和有限EVM见证，但批量请求未传递风险目录，EVM见证尚未进入生产裁决链。它们属于局部实现／夹具证据，不能提前计入端到端完成项。
4. 独立标签、足够且多项目的安全对照、完整提示token公平、真实案例四基线和完整同候选重放仍未验收。研究资格保持 `researchEligible=false`，整体研究状态保持 UNVERIFIED。

**工作量建议为24～43开发人日，另需约3～6审核人日及外部材料等待时间。** 假设一名熟悉项目的开发者、现有本机工具可用、仅扩展与两类机制直接有关的有限语义、不新增付费模型请求。此区间是实施与审查的投入估计，**不保证达到D2未知率目标**；语义覆盖困难可能导致冻结验收继续不通过。没有毕业截止日期、学校论文要求和可用人力，不能换算为确定完成日期。

必须保留的数值约束：现行[SPEC][spec]增补要求原批次 `119b4862f8a14818b62848ce709c3ee6` 的133条原假设、159单元保持不变，UNKNOWN低于10%。本轮只读核对该批次为12支持、121未知。因此严格 `<10%` 意味着最多13条未知，至少要将原121条未知中的108条转为有充分证据的裁决，且不能引入错误裁决。**最新151条候选不能替代这个分母；目前没有完整重放证明该目标已满足。** 若诚实的有限验证无法达到，应提交目标变更建议，不能自行删难例、放宽证明语义或改写验收状态。

三条路线的边界：

| 路线 | 内容 | 本轮判断 |
|---|---|---|
| A：冻结毕设必要路线 | 六个关口；D1离线机制检查及正式方案；D2真实AC／RE各一组维护者修复正反、原候选重放、四基线、工程和材料 | 必须补齐；数值目标未满足就保持对应验收未完成 |
| B：论文可信度增强 | 经独立审核的分组数据、同完整提示预算的发现实验、重复测量、机制消融、跨项目置信区间 | 优先投入，但新付费模型批次需要另立可审查预算；不得自动复用历史授权 |
| C：接近顶会顶刊的额外研究 | 更大规模独立项目、外部复现、现代EVM语义覆盖或形式保证、跨模型／时间外推、多工具可比基准 | 不自动加入毕设承诺；有成本且没有发表保证 |

## 2. 最终目标—当前证据—剩余缺口

### 2.1 对冻结要求逐项核对

以下编号直接沿用[SPEC][spec]的R2-01～12及其同一行AC，不另造验收编号。历史工程证据见[VERIFICATION][verification]；本轮185项选择性离线测试见[验证日志][tests]，并非全量新验收。

| 最终要求 | 当前证据与状态 | 剩余缺口／限制 | 对应阶段 |
|---|---|---|---|
| R2-01 输入、原始位置和展示 | **已实现且有历史验证证据**：输入掩码保行列，工作台输入、定位和下载 | 本轮未重跑浏览器；新增端到端数据需复核展示与下载身份 | 五 |
| R2-02 固定工具环境 | **已实现且有验证证据**：编译闭包、固定solc及配置摘要、工具失败保留；最新保存工具159项OK | 工具OK不保证编译绑定OK；4单元绑定失败；跨机环境仍需复核 | 三、五 |
| R2-03 真值隔离 | **局部实现**：发现不按真值行号选函数，注释答案被清理；真值变异有测试 | 仍把来源机制类别传入发现与检索，当前应描述为“给定机制类别的发现”；不能宣称完全无标签先验盲测或消除训练污染 | 一、二 |
| R2-04 D1 | **局部实现**：同冻结候选池、全文变化窗口、配对消费已接通 | 自动配对不等于真实修复；212片段适用性全未知；完整提示token公平、独立标签和消融方案待验 | 一、二 |
| R2-05 结构化假设 | **已实现且有验证证据**：schemaVersion=2、签名／位置／机制绑定、拒绝与usage缺失保留 | 最新3模型单元结构失败；风险目录可选字段未在批量生产请求接入 | 三、五 |
| R2-06 AST／IR事实 | **已实现且有有限验证证据**：编译器AST、Slither IR、源码／工具双收据、资源与入口事实 | 不支持语义、别名和外部调用仍有缺口；不能视为完整Solidity／EVM解释器 | 三 |
| R2-07 D2 | **局部实现**：六义务、绑定、有限正例及严格CEI合成对照 | 0反驳；AC／RE真实维护者修复正反未完成；有限反例不等于完整资金损失证明；133候选<10%未验 | 三、四 |
| R2-08 派生重放 | **已实现且有历史验证证据**：原模型保留、派生目录、原件摘要、只读下载 | 不同历史批次不能混用；要求的133条完整重放尚缺最终证据 | 四、五 |
| R2-09 真实先导与四基线 | **局部盘点／证据不足**：十项目清单，六准入、四待审；六事件18原件摘要匹配 | 十项目不等于十组完整正反；独立审核、项目谱系、安全负例、四基线未完成 | 一、四 |
| R2-10 工作台 | **已实现且有历史验证证据**：六义务、编译诊断、原始／派生区分、响应式浏览器记录 | 本轮没有新浏览器验收；须以最终引擎真实样本复核，避免以模拟页面代替真实证明 | 五 |
| R2-11 毕设材料 | **局部实现**：工程报告、来源盘点、实验报告已存在 | 缺统一方法边界、全部对照、可生成数字和论文主张映射 | 六 |
| R2-12 工程交付 | **历史局部工程通过；当前整体证据不足**：已有663 Python／109 Java历史记录，本轮185离线通过 | 当前未提交改动不能由旧构建背书；最终全量、CLI、真实工具、浏览器和可恢复身份需重新封口 | 五、六 |

### 2.2 从输入到统计的源码证据链

| 接缝与源码定位 | 本轮核实内容 | 支撑与适用边界 |
|---|---|---|
| [evaluation_input.py:5][input]；[benchmark_targets.py:42][targets] `_record`；[benchmark_runtime.py:29][riskfact] `_risk_fact` | 注释答案掩码保留位置；全文作为发现输入；风险选择不读真值riskLine | `test_evaluation_input`通过；字符串内容保留，不能保证全部语义线索或模型记忆被消除 |
| [exploratory_targets.py:22][exploratory] `load_targets`；[audit_run.py:190][auditrun]；[HypothesisService.java:65][hypothesis] | 来源类别筛选AC／RE并作为机制先验进入提示与检索 | 用户预先给定审计范围时合理；源数据标签决定范围时不属于完全盲测。需要协议澄清，不能偷偷改历史输入 |
| [benchmark_runtime.py:114][runtime] `preview/_recall_candidates`；[d1_consumption.py:38][d1consume] `mechanism_events/pair_snippets/soft_pairs` | 固定快照最多80候选；选择全文变化窗口；同机制配对、相似分差及最多4片段／4096字节 | 本轮D1测试通过；识别语法可见变化不证明修复语义正确；字节上限不等于token公平 |
| [D1Retriever.java:10][retriever]；[AutomaticContrast.java:28][automatic]；[ConditionBinder.java][binder] | `auto-1`走自动软配对，绑定UNKNOWN；正式分支另有主体、资源、顺序、状态约束 | 最新53条D1中33走Java自动路径、20走Python软配对；不可用正式分支能力代替本批实际执行能力 |
| [compiler_facts.py:365][compiler]；[bound_slither.py:200][slitherbound] `analyze_bound/verify_bound_tool` | 重验solc输入闭包、版本、配置及stdout；工具以独立收据关联编译环境，提取IR事实 | 本轮编译D2测试及历史真实双收据；本轮未重新调用真实solc／Slither |
| [risk_binding.py:50][binding] `bind_risks`；[compiled_d2.py:81][graph] `_Graph` | 原候选行→语句跨度→±2行唯一关联；限制同入口／机制／真实操作，不重写候选 | 唯一绑定测试通过；操作类型错误、多义、超范围仍未知，不能自动归为模型错报 |
| [candidate_proofs.py:268][candidateproof] `prove_candidate`；[reentrancy_proofs.py:1000][reproof] `prove_reentrancy` | 有限权限／重入路径、相关入口和状态建态；统一锁与严格CEI完整性检查 | 图节点1800、调用深度24；有限见证路径128、符号6、数值候选16、赋值8192等预算存在；未找到见证不推导安全 |
| [compiled_d2.py:669][verdict] `_apply_proof`；[d2_verify.py:11][obligations] | 六义务为actor、resource、pre_risk_guard、entry_coverage、state_version、bypass；裁决有显式证据门槛 | 本轮 `test_candidate_proofs/test_reentrancy_proofs/test_compiled_d2`；真实维护者修复仍未通过完整正反验收 |
| [evm_witness.py:572][evm] `execute_bound_witness`；[risk_catalog.py:42][catalog]；[audit_run.py:208][auditrequest] | 本机EVM见证及风险目录有实现／测试，生产批量链未接通 | **仅局部实现／夹具**；本轮未执行这些新模块的全量验收，不能声称其解决了真实139条未知 |
| [tool_replay.py:111][replay] `replay`；[benchmark_report.py:11][reportcode] `summarize_d2` | 同原候选派生，缺失assessment仍UNKNOWN；模型usage保留 | 185测试含批次／报告；若未来usage缺失，只能称已观察小计，完整总成本保持null |

其中正裁决要求有限反例FEASIBLE、正常退出、资金或运行初始化证据以及同类原工具佐证；反驳要求PROVED、完整范围、BLOCKED、六义务全部SUPPORTED及工具身份MATCH。工具告警佐证并不独立证明交易可行。当前RE见证是 `SATISFIABLE_ABSTRACTION` 下的CEI防御断言反例，源码明确不宣称完整攻击可利用性。相关结论应限制为“在记录的模型与初态范围内支持该候选”。

另一个直接影响访问控制覆盖的事实是：当前 `_apply_proof` 的AC正裁决分支只接受 `ACCESS_CONTROL_TERMINATION`，没有通用权限WRITE正裁决入口。因此14条权限写入候选不仅缺正常提交见证，还需要先定义并验证对应的裁决接缝；不能假设补一个动态回执就会自动成为SUPPORTED。

### 2.3 最新批次的独立复核

原件位于[最新原始批次][run]，通过 `storage.read_artifact()` 解压并核对原始字节。项目汇总函数重算后，又以独立循环直接计算共同样本混淆矩阵；结果见[批次重算][recompute]和[独立指标][independent]。原plan、events、samples、summary的前后SHA-256相同，保存汇总与重算的计划、分母、共同样本、指标和候选池冲突项全部一致。

| 层级 | 数量 | 正确解释 |
|---|---:|---|
| 计划单元／实际正式HTTP尝试 | 159／159 | 三策略各53，各一次；不含其他目录的5个冒烟 |
| 模型结构有效／结构失败 | 156／3 | 每策略52有效；失败保留，不补成安全 |
| 完整流水线完成／失败 | 152／7 | 7包括3模型结构失败及4模型有效后的编译绑定失败 |
| 保存工具状态OK | 159 | 与完整流水线成功是不同分母 |
| 共同模型有效目标 | 51 | 47漏洞来源标签＋4安全来源对照；非51个人工独立审核项目 |
| 全部目标 | 53 | 49漏洞来源标签＋4安全来源对照 |

| 策略 | 共同51：TP／FP／FN／TN | 共同F1 | 各自52有效F1 | 全53模型成功覆盖 |
|---|---|---:|---:|---:|
| VANILLA | 45／0／2／4 | 0.97826087 | 0.97872340 | 52/53 |
| DENSE | 47／0／0／4 | 1.00000000 | 1.00000000 | 52/53 |
| D1 | 45／0／2／4 | 0.97826087 | 0.96774194 | 52/53 |

以上F1只衡量来源标签下样本“有无报告”，不保证位置、危险操作或理由正确；D2支持率也不能替代其候选真值。不得拿不同有效子集的F1直接做配对因果比较。

| 策略 | 输入token | 输出token | 正式请求 | 金额 |
|---|---:|---:|---:|---|
| VANILLA | 67,651 | 28,736 | 53 | null |
| DENSE | 120,156 | 48,567 | 53 | null |
| D1 | 109,321 | 42,369 | 53 | null |
| 合计 | 297,128 | 119,672 | 159 | null |

本批usage缺失0，金额未核实。相同片段数／字节上限没有形成相同完整提示token预算；D1较Dense少输入token不等于已经完成公平试验。模型思考和全文输入同时变化的跨批次结果，也不能分离单因素效果。

历史执行JAR SHA-256为 `febef6ae3e8e1d1e5a57b3ffe66ba7e7b079972091bb3f34b505f67dff344bf6`，关联提交 `5d6b50b`，但当时还含未提交Java改动。84项历史执行文件摘要与当前工作区比对为55相同、29不同，详见[身份比对][identity]。差异包括后续数据／存储迁移与工具修改，**不能据此指控原件变更，也不能声称当前HEAD能完整重建当时执行程序**。未来需保存可达提交加必要补丁／文件清单的复现闭包。

## 3. 顶会顶刊论文与官方源码对标

### 3.1 检索、筛选与证据等级

已按orx内置指南运行关键词、语义及OpenAlex检索，围绕智能合约、LLM/RAG、静态验证及基准四个方向筛选；正文通过 `orx paper --full` 或正式出版页面读取，代码通过官方Git仓库检查。13份检索结果的标识与摘要身份、固定代码版本、已读文件SHA见[来源登记][sources]。下表保留12项候选，深入检查其中4个官方实现；**全部外部实验均未实际运行复现**。

等级：M＝仅元数据／摘要；P＝读过论文正文或关键完整章节；C＝检查过官方关键源码；R＝实际运行并复现实验。本轮没有R。正式发表、工具演示和研讨会分别标记，不能互换。

| 工作与原文 | 发表核实 | 等级 | 与本项目的关系／选取结果 |
|---|---|---|---|
| [GPTScan: Detecting Logic Vulnerabilities in Smart Contracts by Combining GPT with Program Analysis](https://doi.org/10.1145/3597503.3639117) | ICSE 2024主会；[全文](https://arxiv.org/abs/2308.03314) | P+C | 最直接的LLM候选＋静态确认对照；深读 |
| [PropertyGPT: LLM-driven Formal Verification of Smart Contracts through Retrieval-Augmented Property Generation](https://doi.org/10.14722/ndss.2025.241357) | NDSS 2025正式论文 | P；辅助脚本C | 检索属性、编译反馈与验证；官方公开材料不包含完整核心prover，不能算完整源码对标 |
| [Securify: Practical Security Analysis of Smart Contracts](https://arxiv.org/abs/1806.01143) | CCS 2018；[作者机构原文](https://files.sri.inf.ethz.ch/website/papers/ccs18-securify.pdf) | P+C | 满足／违反充分条件与不确定结果，直接约束D2新颖性；深读原版 |
| [eThor: Practical and Provably Sound Static Analysis of Ethereum Smart Contracts](https://doi.org/10.1145/3372297.3417250) | CCS 2020；[全文](https://arxiv.org/abs/2005.06227) | P | Horn规则与EVM语义／single-entrancy；官方站源码迁移下载失效，未取得可核核心代码 |
| [SmartBugs 2.0: An Execution Framework for Weakness Detection in Ethereum Smart Contracts](https://doi.org/10.1109/ASE56229.2023.00060) | ASE 2023 **Tool Demonstrations**；[官方轨道条目](https://conf.researchr.org/details/ase-2023/ase-2023-tool-demonstrations/8/SmartBugs-2-0-An-Execution-Framework-for-Weakness-Detection-in-Ethereum-Smart-Contra) | P+C | 多工具执行、结果与失败归一化；深读，不当作新检测算法 |
| [Slither: A Static Analysis Framework for Smart Contracts](https://arxiv.org/abs/1908.09878) | **WETSEB 2019研讨会**，不是ICSE主会 | P+C | 项目已依赖的程序表示、依赖分析与检测器；深读，不能冒充顶会主会成果 |
| [Combining Fine-Tuning and LLM-Based Agents for Intuitive Smart Contract Auditing with Justifications](https://doi.org/10.1109/ICSE55347.2025.00027)（iAudit） | ICSE 2025；[全文](https://arxiv.org/abs/2403.16073) | P | 分类与解释分工、ranker／critic；官方页面指向匿名源码站，本轮未取得可检查代码正文 |
| [When ChatGPT Meets Smart Contract Vulnerability Detection: How Far Are We?](https://doi.org/10.1145/3702973) | TOSEM 34(4)，2025卷期；2024在线元数据 | M | LLM检测能力与评测威胁；不引用未读全文中的具体提升数字 |
| [Augmenting Multi-technique Static Analysis with Large Language Models: A Neuro-symbolic Approach to Smart Contract Vulnerability Detection](https://doi.org/10.1145/3832222)（ELSA） | PACMSE 3(ISSTA)，2026-10-01元数据 | M | 多技术静态分析与LLM融合的新近候选；未核源码，不能将摘要提升数字横比本项目 |
| [DeepDesc: integrating retrieval-augmented generation with large language models for smart contract vulnerability detection](https://doi.org/10.1007/s10664-025-10770-7) | Empirical Software Engineering 31(2)，在线2025-12-05；不列入本表顶会刊核心组 | M | RAG直接相关，待全文与官方代码复核；不能据标题认定D1已无新意或已有优势 |
| [EVMbench: Evaluating AI Agents on Smart Contract Security](https://arxiv.org/abs/2603.04915) | 2026预印本；本轮未核正式接收 | M | 真实任务和代理评测候选；未取得全文／代码证据，不计深度对标 |
| [Empirical review of automated analysis tools on 47,587 Ethereum smart contracts](https://doi.org/10.1145/3377811.3380364) | ICSE 2020元数据 | M | 多工具、大规模与标签局限的经典评测参照；本轮未复现其428,337次分析 |

文献筛选不是穷尽性查新：本轮足以指出“三态”“LLM＋静态”“普通RAG”不能单独作为新颖性，但不足以证明某个更精确的六义务方法从未出现。不能把没有检索到相同名称当作原创性证明。

### 3.2 四个官方实现的实际检查记录

#### GPTScan：可借鉴固定候选实验，不能照搬False的裁决含义

- **官方性／身份**：[MetaTrustLabs/GPTScan](https://github.com/MetaTrustLabs/GPTScan)的README指向完整源码仓库；所读为[GPTScan/GPTScan固定版本](https://github.com/GPTScan/GPTScan/tree/29a174773bd526c32ab7d6a8c78a63870330ccc7)，AGPL-3.0。许可和依赖均检查过。
- **入口与方法**：`src/main.py → tasks.simple_cli`；[analyze_pipeline.py](https://github.com/GPTScan/GPTScan/blob/29a174773bd526c32ab7d6a8c78a63870330ccc7/src/analyze_pipeline.py)的 `ask_whether_has_vul_with_scenario_v9`，以场景／属性规则请求LLM匹配并提取变量；[static_check.py](https://github.com/GPTScan/GPTScan/blob/29a174773bd526c32ab7d6a8c78a63870330ccc7/src/static_check.py)的 `run_static_check`，结合Falcon依赖及相等／不等／顺序检查；已读 `UnauthorizedTransfer.yml` 与 `falcon_adapter.py`。
- **数据／实验**：论文使用Web3Bugs、DeFiHacks及Top200等不同来源；§5.3固定中间候选647→221，移除426项同时丢掉3个真阳性，另有编译造成的漏检。§6承认路径不敏感和白名单局限。Top200的安全假设不等于逐项证明安全。README链接数据仓库，但本轮没有完整下载和执行统一论文评测／消融；当前小仓库根未发现清晰一键复现全部表格的入口。
- **关键实现边界**：[tasks.py](https://github.com/GPTScan/GPTScan/blob/29a174773bd526c32ab7d6a8c78a63870330ccc7/src/tasks.py)中编译失败可继续令Falcon为空，静态检查异常转False；部分适配器无数据也返回False。这个False不能直接映射为本项目REFUTED。README还说明部分依赖／路径可被跳过。
- **依赖／障碍**：Python3.10+、Java17+、solc、Falcon、旧OpenAI0.27.8；Falcon Git依赖没有固定到提交，模型端点和历史版本影响复现。未运行模型或作者实验。
- **本地差距与复用**：VeriRAG已经比简单布尔过滤更明确地保留失败和UNKNOWN，但尚缺GPTScan式固定候选前后对照与漏检审计。优先复用实验设计和规则描述；引入代码需核AGPL边界，不为“对标”重建整条旧依赖链。估计1～2人日完成规则／语义映射，真实适配另计。

#### Securify：三态有明确先例，必须核对性质及终止前提

- **官方性／身份**：[eth-sri/securify固定版本](https://github.com/eth-sri/securify/tree/51ba1240e60332b4a1e6ad02090da6fe57676354)README链接ETH作者论文并标记已弃用；Apache-2.0。本轮检查的是CCS2018对应原版，不用Securify2替代原论文。
- **入口与方法**：[Main.java](https://github.com/eth-sri/securify/blob/51ba1240e60332b4a1e6ad02090da6fe57676354/src/main/java/ch/securify/Main.java) `checkPatterns/checkInstructions`：EVM反编译、SSA／CFG和数据流不动点；[mustExplicit.dl](https://github.com/eth-sri/securify/blob/51ba1240e60332b4a1e6ad02090da6fe57676354/smt_files/mustExplicit.dl)给出must依赖、顺序和内存／存储传播；[AbstractInstructionPattern.java](https://github.com/eth-sri/securify/blob/51ba1240e60332b4a1e6ad02090da6fe57676354/src/main/java/ch/securify/patterns/AbstractInstructionPattern.java)分别调用 `isViolation/isCompliant`，输出violation、safe、warning及异常的conflict组合。
- **实际模式**：[DAO.java](https://github.com/eth-sri/securify/blob/51ba1240e60332b4a1e6ad02090da6fe57676354/src/main/java/ch/securify/patterns/DAO.java)检查调用、gas依赖及后续SSTORE；`UnrestrictedWrite`和`UnrestrictedEtherFlow`使用Caller依赖和must-precede分支。它们不是业务授权关系的通用证明；“某条件依赖caller”不等于“验证了正确角色”。
- **论文限制**：§5.3明确，违反模式假设相关指令处于某条可终止执行中；通用性质不能覆盖所有合约特定要求。此处与VeriRAG要求正常退出、初态及完整候选闭包的目标存在真实差异，值得验证，但并不自动证明VeriRAG更可靠。
- **数据／评测**：论文评测24,594个EVM合约和100个不超过200行的源码合约，比较Oyente／Mythril、人工检查、证明／警告覆盖及时间内存。分母常是call或sstore指令，不能和本地样本F1直接横比。已读 `DAOTest/UnrestrictedWriteTest` 及[test.py](https://github.com/eth-sri/securify/blob/51ba1240e60332b4a1e6ad02090da6fe57676354/test.py)；后者比较历史JSON的四类输出，是回归入口，不等于论文整套实验复现。未核到可直接复现论文全部表格的一键包。
- **依赖／障碍**：Java8、旧Gradle、Soufflé、匹配solc；README承认fallback未分析、库支持不足等限制。适合借鉴充分条件／未知／冲突设计和测量方法，不建议把弃用原版整体嵌入当前Java21项目。模式映射1～2人日；现代语义适配不在这个估计内。

#### Slither：复用表示和分析，不把检测器告警升级为证明

- **官方性／身份**：论文及[crytic/slither](https://github.com/crytic/slither)相互对应；所读tag **0.11.3**，提交[ f571b6b666d22045ae27dd1fc99024e3f951f1ee](https://github.com/crytic/slither/tree/f571b6b666d22045ae27dd1fc99024e3f951f1ee)，AGPL-3.0，与项目记录的工具版本一致。
- **关键实现**：[reentrancy.py](https://github.com/crytic/slither/blob/f571b6b666d22045ae27dd1fc99024e3f951f1ee/slither/detectors/reentrancy/reentrancy.py) `AbstractState/_explore`在CFG上传播读写／调用集合并求不动点；[reentrancy_eth.py](https://github.com/crytic/slither/blob/f571b6b666d22045ae27dd1fc99024e3f951f1ee/slither/detectors/reentrancy/reentrancy_eth.py) `find_reentrancies`聚合具体风险；`functions/suicidal.py`与SSA `data_dependency.py`已读。
- **数据／评测**：原论文人工审查常用合约；当前仓库的[检测器回归入口](https://github.com/crytic/slither/blob/f571b6b666d22045ae27dd1fc99024e3f951f1ee/tests/e2e/detectors/test_detectors.py)包含多个solc版本、预期输出与检测器测试。当前tag不能视为2019论文执行身份；本轮没有运行这些测试或重新完成论文评测，也没有独立消融复现。
- **依赖／边界**：Python、crytic-compile、兼容solc及完整源码依赖。局部is_protected、调用后状态写和集合依赖不证明所有路径可行，也不证明本项目六义务全满足。
- **复用建议**：继续复用SlithIR、SSA依赖、读写／调用事实及工具收据；自研部分集中在候选绑定、业务资源关系、证明范围和裁决契约。避免平行复制完整SSA／数据流引擎。新增1～2类事实适配估计2～4人日，复杂跨合约语义另计。

#### SmartBugs 2.0：对标执行与失败口径，不能替代真值审核

- **官方性／身份**：论文指向[smartbugs/smartbugs固定版本](https://github.com/smartbugs/smartbugs/tree/c8b7ddfff2584f07adc9ba82d12bf940c1d2af31)，Apache-2.0，样本许可另核。论文2023描述19工具，当前README为26工具，不能把当前支持数写成原论文实验数。
- **入口与实现**：[sb/analysis.py](https://github.com/smartbugs/smartbugs/blob/c8b7ddfff2584f07adc9ba82d12bf940c1d2af31/sb/analysis.py) `execute/run`管理Docker任务；[sb/parsing.py](https://github.com/smartbugs/smartbugs/blob/c8b7ddfff2584f07adc9ba82d12bf940c1d2af31/sb/parsing.py) `parse`保留findings、infos、errors、fails和parser版本；[Slither0.11.3解析器](https://github.com/smartbugs/smartbugs/blob/c8b7ddfff2584f07adc9ba82d12bf940c1d2af31/tools/slither-0.11.3/parser.py)保留解析失败、原工具success及源位置映射。
- **数据／评测**：`doc/datasets.md`链接Curated、Wild及其他数据，支持工具配置与结果重解析；这是工具执行框架，检测基线来自被调用工具，本身没有与D1对应的检索消融。数据目录链接CGT可作后续标签扩展候选，不能未经审核直接纳入正式知识或测试。
- **依赖／障碍**：Python、Docker、固定镜像及数据环境；本轮未启动Docker，未复现论文工具执行。现代仓库输出格式与原论文版本差异需要锁定。
- **本地差距与复用**：本项目原件归档、零模型重放已有优势接缝；缺的是更多工具的可比运行身份和跨机执行验证。可复用配置／解析协议，在适配层显式区分失败与阴性；预计2～3人日完成单工具适配与脱机回归，运行大基准另计。

### 3.3 方法参考的可比边界

PropertyGPT的[官方材料仓库](https://github.com/Pr0pertyGPT/PropertyGPT/tree/24a80982a6d3d69ad70a114490847d4cccc0609e)仅发现少量Python辅助脚本；已读 `certora_projects/extractor.py` 的正则提取及 `weight_calcu/linear_analysis.py` 的权重回归／划分，不是完整属性生成与prover源码。仓库根未核到许可证，不能默认自由复用。论文明确商业化及部分代码未来公开；同名第三方engine未证官方，已排除。

该论文的623个人工属性、23个Certora项目、9项目90属性测试，以及双人判等／第三人仲裁，提供了D1知识质量和人工评价的参考。其约80%属性匹配召回不是漏洞F1；筛选的CVE／真实事件也不等同于本地AC／RE来源集合。检索→编译反馈修复→相似度排序→验证的分层设计值得借鉴，不足以证明简单复制提示会有效。

[eThor官方站](https://secpriv.wien/ethor)明确源码下载迁移链接失效；本轮只读论文。其形式保证依赖EVM版本与指令限制，相关定理排除DELEGATECALL／CALLCODE情形；旧Constantinople语义不能自动覆盖现代opcode。论文F-measure采用sensitivity和specificity的调和平均，与本项目precision／recall的F1不同，禁止直接比较数字。

iAudit的[作者项目页](https://sites.google.com/view/iaudittool/home)指向匿名源码站，本轮只取得网页外壳。其微调detector／reasoner、ranker／critic是理由生成质量参考，不是形式验证；不建议将昂贵微调加入A路线。

### 3.4 统一维度的差距与必要性

| 维度 | 外部具体做法 | VeriRAG当前 | 差异影响与是否必需 | 优先复用／成本 |
|---|---|---|---|---|
| 研究问题 | GPTScan确认场景候选；Securify证明性质；PropertyGPT生成属性 | D1发现＋D2核验，目标混合 | 必须分别定义“发现准确”“候选可靠”“合约安全”，属A | 分层任务协议，1人日内可起草 |
| 威胁模型 | Securify明确可终止前提；eThor明确语义范围 | 已记录部分初态／外部调用前提，论文契约未统一 | 必须界定调用者、资源、部署、环境和支持语法，属A | 借鉴前提—性质—保证格式，1～2人日 |
| 检测范围 | Slither具体检测器；GPTScan规则类 | 两机制名较宽，实际AC CALL仅有限终止内置、RE仅子集 | 名称与可验证范围失配导致UNKNOWN；属A | 支持矩阵与已冻结全分母分开，1～2人日 |
| 程序表示 | SlithIR／SSA、Securify EVM不动点 | AST＋IR事实＋自研有限图 | 基础表示已具备；扩展应避免重复实现，属A有限补齐 | Slither事实适配2～4人日，非完整重写 |
| 检索知识 | PropertyGPT人工属性，编译反馈 | AutoMESC自动配对、全部自动标签 | 缺真实修复与条件相关性证据；属A离线、B效果 | 人工配对准入、条件标注3～5人日与审核 |
| 验证语义 | Securify独立充分条件；eThor形式边界 | 六义务、反例／保护闭包、三态 | 三态不是新贡献；缺真实双向可靠性，属A | 模式映射＋有限证明闭环8～15人日 |
| 数据标签 | PropertyGPT判等仲裁；Securify人工查100源码 | 来源标签、4个同上游安全对照、自动知识 | F1可高估泛化／理由正确；属A来源、B强统计 | 项目谱系、双审核，不以样本文件数当项目数 |
| 实验协议 | GPTScan固定中间候选＋漏检审计 | 新旧模型候选变化，完整四臂未跑 | 无法归因D2改进；属A | 原候选四臂同预算4～7人日 |
| 成本与复现 | SmartBugs容器／解析独立；工具版本化 | 本机原件、收据、gzip身份；历史JAR含未提交代码 | 本机可回读不等于跨机可复现；属A | 清单、最小输入闭包、零模型复现2～4人日 |

表中成本是模块级参考，与第五节阶段估计重叠，不能累加为另一套总工期。

## 4. D1／D2研究主张审查及最高优先阻塞

### 4.1 D1：当前能够主张什么

**事实**：本批D1使用300个自动标注知识样本形成的600文档向量，Nomic维度768；快照ID为 `a6d70058bb93a26505def7878553d01e7667248d387f41a101a4ff2f71bd36db`，本轮 `verify_snapshot`核对通过。300个登记project_group不是经独立谱系审查后的300项目，600文档也不是600漏洞。知识选择见[r1_candidate_corpus.py:50][corpus]，改动行关键词筛选不保证每对都是语义正确的漏洞—维护者修复。

本批D1两条自动路径最终都走软配对，212个入选片段的条件适用性全未知。正式ConditionBinder存在，并不意味着本次实验测到了它。`retrievalHitAtK/RecallAtK`在[benchmark_batch.py:176][proxy]中基于机制标签代理；D1先按机制过滤，代理为1具有循环性，不能当人工相关性Recall@K。

**可保留主张**：固定知识身份、成对上下文、真实消费记录和适用性缺口可审查的检索工程。**尚不支持的主张**：条件机制优于普通Dense／正反例提示；D1提高最终检测；检索召回率100%；自动条件约束已经有效执行。

**建议的机制检验**：

1. 固定模型、端点、提示骨架、知识池、项目／克隆划分和开发／独立测试；先完成人工判定的漏洞—修复配对及条件适用性子集。禁止在测试集失败后再回头修改规则并继续把它当独立测试。
2. 发现主对照为VANILLA／DENSE／D1；机制消融至少包括普通成对上下文、去条件、去修复。可采用分阶段设计控制费用，但比较组必须事先固定，不能看到结果后挑最有利组。
3. 统一完整提示token上限，并记录system、代码、检索、输出设置及实际输入／输出token；同上限不等于同实耗。VANILLA不补无关文字“凑等长”。tokenizer／供应商计数无法核实时，将精确公平标为待验，不以4096字节替代。
4. 分别测人工相关性P@K、完整有效pair率、条件绑定正确率、变化窗口是否包含关键机制，以及最终位置／危险操作／理由准确率。若没有穷尽相关项真值，不报告真正Recall@K。
5. B路线建议先预注册至少3次重复，但最终次数由预算与预期效应／功效讨论确定；按项目成组配对bootstrap或置换，报告效应区间和失败覆盖。159单元不能当159独立观测；项目少则只报告探索结果，不能把不显著说成等效。

**决策门槛**：阶段二在零模型条件下首先要求选入的审查配对100%来源可回读、条件结论与引用可核、反例／不支持条件不伪装SUPPORTED、token方案完整。B路线在解盲前约定有实际意义的最小效应δ和错误容忍度；只有独立集上D1对最强对照的改善及相应消融共同支持，才主张机制增益。区间跨零／效果不足表示证据不足；稳定无增益则删除独立增益主张，保留工程贡献，研究负结果照实写。不能为了保住D1名称迁移测试数据到知识库。

### 4.2 D2：139条UNKNOWN的逐项分流

[候选账本][triage]对151条原假设逐条保留sampleId、strategy、hypothesisIndex、candidateHash、原位置、proofKind、绑定、缺口与裁决。139条未知按固定优先规则互斥分流如下；原始gaps可重叠，**这不是逐项干预实验确定的唯一根因**。

| 保存证据中的首要缺口 | 条数 | 占139未知 | 下一步应证实什么 |
|---|---:|---:|---|
| AC CALL超出终止内置证明范围 | 21 | 15.11% | 是合理业务调用候选还是错误危险操作；需要哪类授权／调用语义，不能自动判候选错 |
| 风险未唯一绑定／操作类型未支持 | 9 | 6.47% | 原行、真实AST语句、签名和类型逐项审查；多义必须保持未知 |
| 其他AC写入资源／权限闭包不足 | 12 | 8.63% | 写入与受保护资产／权限关系、相关入口及旧状态 |
| 权限写入已关联敏感入口，但缺正常提交见证 | 14 | 10.07% | 合法初态和实际正常返回后持久状态，不能凭局部WRITE支持漏洞 |
| assessment缺失／编译绑定失败 | 9 | 6.47% | 4单元的编译收据和清理输入对应关系；首先恢复可评估性 |
| 辅助外部调用正常返回／无回调前提未核验 | 36 | 25.90% | 真实代码身份、部署和合法配置；可能同时缺初态，不能按Logger名称假定无害 |
| 重入主体余额／数值／存储别名未绑定 | 27 | 19.42% | 相同主体、mapping key、结构字段与支付数值是否一致 |
| 资金／构造初态建态未证实 | 8 | 5.76% | 用合法业务历史建态，并同时维护辅助总账和相关槽 |
| 路径或全入口保护闭包不足，仍待细查 | 3 | 2.16% | 路径可行性、相关入口和未支持结构，逐项保留不确定性 |
| 合计 | 139 | 100%（四舍五入） | 不能把全部未知解释成“模型候选质量差” |

4个编译绑定失败单元为Parity Wallet Bug1的三策略和Spank Chain Payment的DENSE，共9条假设缺核验。它们的模型输出可以仍计入发现指标，但不能算D2有效评估。

12条SUPPORTED全部是RE：Reentrance、reentrancy_dao、reentrancy_simple、SimpleDAO，每个目标三策略。0条REFUTED意味着**目前没有真实批次双向纠错效果的证据**。相同合约的多策略支持并不是独立重复证实，也不能证明AC能力。即使四目标人工判定都正确，样本量和相关性仍不足以支撑广泛的高精度主张。

### 4.3 D2的贡献定位及三种实现路线

成熟工具已覆盖语法树、IR、SSA、读写依赖、调用图、部分支配／顺序、检测模式和不确定结果。Securify还提供满足／违反充分条件框架；因此不能把这些能力的重新实现本身当作研究贡献。

**值得检验的D2贡献**应写为：针对LLM给定的具体候选，将源码与工具身份、主体／资源／时序／入口／状态版本／绕过六义务、可行的有限反例或完整保护范围，整合为可审查的裁决契约，并测量它相对弱验证基线是否减少错误支持与错误反驳。当前是有实现基础的候选主张，尚未经独立对照验证。

| 路线 | 收益 | 代价／风险 | 建议 |
|---|---|---|---|
| 继续扩大自研AST／有限EVM语义 | 可控制身份、证据结构与解释，针对当前缺口快修 | 容易长期追逐别名、代理、动态调用、循环和跨合约语义；夹具通过不保证健全性 | 只为冻结案例和明确子集补齐，建立预算上限；不默认重造完整验证器 |
| 接入成熟工具 | 复用Slither事实，SmartBugs统一执行；必要时引入独立EVM／符号工具对照 | 工具告警／空结果不能直接映射三态；版本、初态、许可与适配有成本 | **优先混合路线**：复用表示与执行，D2保留严格裁决层；新后端先做少量契约测试 |
| 明确收窄支持范围 | 降低过强主张风险，便于验证高可靠有限核验 | 可能无法满足133条<10%和广泛效果要求 | 支持范围可声明，历史全分母仍报；冻结目标改变必须单独提案，不能悄悄排除未支持候选 |

正反可靠性须分开验证：SUPPORTED使用来源报告、真实代码与可行性证据的独立审核；REFUTED使用真实维护者修复、完整相关入口和六义务，并核查修复是否只消除该候选。错误主体、错误资源、顺序、旧状态、旁路入口的合成扰动用于测试边界，**不能当真实项目负例**。维护者补丁也可能只处理部分问题，不能据一个候选被反驳宣布整合约安全。

真实先导中，RabbitHole修复将裸比较改为require，但代理初始化是必要前提；Atomic Loans将同loan的off写入前移，另一个早期 `ACEXT()` 调用仍在锁前；JPEG’d不是“把所有写入移到调用前”的通用CEI补丁。历史九个真实候选最终均UNKNOWN，局部BLOCKED／REACHABLE不能提升为完整裁决。来源与版本链见[真实先导][pilot]，历史局部证据见[九候选摘要][nine]。

### 4.4 数据、统计与优先阻塞

**事实**：53个清理后源码未发现完全相同字节；这不证明没有克隆、同项目谱系或模板相关性。探索目标的URL相等过滤与token集合相似度0.85见[load_targets][exploratory]，不是完整跨版本谱系／AST克隆审查。正式[isolation.py][isolation]对登记的project／clone／字节分组有约束，但探索数据不会因此自动变成经人工审核的正式独立集。

四个安全对照均来自OpenZeppelin同一上游，来源版本与安全性审核尚不充分；不能把四个文件当四个独立安全项目。正式六事件中，Maia／Atomic／RabbitHole是knowledge，PoolTogether／Infinity／JPEG’d是validation；不能拿知识侧成功案例充当最终独立泛化测试。六事件18份原件本轮hash全匹配，证明的是身份，不是新增人工标签审核。模型训练语料不可核，注释清理只降低显式答案泄漏，不消除预训练污染。

优先级按阻断研究解释的程度排序：

| 优先级 | 阻塞 | 为什么先处理 | 完成证据 |
|---|---|---|---|
| P0 | 固定分母、执行身份与人工裁决对象 | 否则后续改善无法归因，旧133目标可被新151悄悄替换 | 双批次账本、可回读原件、源码／JAR差异说明、逐候选人工审核字段 |
| P0 | 真实AC／RE维护者修复正反及有限语义边界 | 当前0反驳、AC无支持；继续加代码未必产生研究证据 | 各一真实正反组，六义务与初态可回读，未支持项保持UNKNOWN |
| P0 | D1真实配对与条件机制实际执行 | 当前全部自动绑定UNKNOWN，实验没有测试所声称机制 | 离线人工标注配对、绑定／消费检查、完整token方案 |
| P1 | 四基线同候选比较、独立标签和安全对照 | 防止把候选变化／弃权增加误当改善 | 全分母＋有效子集＋错误支持／反驳＋按项目统计 |
| P1 | 当前工作区完整复现、备份与材料 | 原件本机可读不等于第三方可复现 | 最小复现包、最终构建、真实工具及浏览器记录；备份状态如实标注 |

## 5. 带依赖、交付物与门槛的六阶段路线图

以下是**建议执行计划**，本轮不修改现有计划或状态。所有工程任务进入[S11／S12统一Slice Map][plan]。不按每个阶段新建规格、切片目录或验收体系。

关键路径为：**阶段一 → 阶段三 → 阶段四 → 阶段五 → 阶段六**。阶段二在阶段一对应数据冻结后与阶段三并行，在阶段六前完成；阶段五的环境准备、阶段六的文稿起草可以提前。独立审核、真实修复依赖和D2数值门槛是主要外部／研究等待点。

### 阶段一：数据、候选与执行身份封口（3～5开发人日）

- **问题／REQ**：R2-03、08、09、11；S11来源与固定候选、S12数据口径。前置仅为当前原件可读，可立即执行。
- **任务与模块**：为旧133和新151分别建立稳定候选ID、原始输入摘要及分母；核定knowledge／validation／test、项目／克隆谱系、四个安全来源；把十项目盘点补成至少十个可核原件独立事件登记，逐项列缺失、许可、源码和修复版本；给当前源码与历史执行JAR建立清晰身份映射。涉及 `benchmark_targets/exploratory_targets/isolation/storage` 及现有来源清单。借鉴PropertyGPT审核分工、SmartBugs数据登记，不直接导入未经审查的标签。
- **交付物**：双批次不可变候选清单、十至十五事件来源盘点、去重／谱系报告、人工审核表与争议表、执行身份清单。只新增派生记录，不改原候选。
- **工程验收**：159单元及133／151候选分别100%可定位；原件前后SHA不变；摘要、行号、策略、标签来源均可回读；所有缺失显式记录；登记的split交叉项目／克隆冲突为0，无法确认的分组标为待审，不伪称已无泄漏。
- **研究验收**：真正用于方法效果的标签须独立审核，候选位置／操作／性质与样本级漏洞标签分开。工程盘点可在审核未完成时交付，但 `researchEligible=false`，不宣布研究通过。
- **失败处置／资源**：原件不可得的条目保留缺口，不用合成样本补成真实项目；若可核事件不足10，R2-09保持未完成。需要独立审核者，预计本阶段1～2审核人日；新模型预算0。来源获取与许可争议不含在开发工时保证内。

### 阶段二：D1机制及完整提示预算的离线准入（3～5开发人日）

- **问题／REQ**：R2-03、04、05、11；S12 D1离线及预注册。依赖阶段一的知识／标签划分，可与阶段三并行。
- **任务与模块**：核定真实漏洞—修复窗口及条件关系；明确自动软配对与正式ConditionBinder的不同语义；做主体／资源／顺序错配与未知条件检查；验证最终模型请求确实消费所展示片段；形成完整提示token核算与VANILLA／DENSE／D1及消融的冻结方案。涉及 `d1_consumption/benchmark_runtime/formal_recall`、Java检索器与提示组装。
- **交付物**：可回读配对与条件审查记录、离线消费报告、预注册实验表和可审查预算表。借鉴PropertyGPT属性来源／人工判等与反馈分层；不声称取得其未开源prover。
- **工程门槛**：审查集入选配对来源和全文窗口回读100%；不存在将UNKNOWN条件展示为已支持的记录；错误绑定和未覆盖条件保留缺口；完整提示预算字段覆盖system／代码／上下文／输出及tokenizer身份。未核计数工具时公平项仍待验。
- **研究门槛**：A路线完成上述离线机制证据及正式方案即可；新真实模型实验不是自动必需。要主张独立增益，必须完成B路线的独立同预算消融并报告区间。无增益时删除增益主张，不影响诚实交付离线工程结果。
- **资源／失败处置**：0新增模型请求；约1审核人日，与阶段一共用审核材料。若知识配对语义不足，先修准入方案而非扩大上下文。B预算必须列模型、端点、目标×组数×重复数、重试上限、完整输入／输出上界；缺价格或token上界时金额保持null，不能给虚假总价。

### 阶段三：D2支持范围及真实正反闭环（8～15开发人日）

- **问题／REQ**：R2-02、05、06、07；S11事实与路径。依赖阶段一对应真实案例与原候选身份，是关键路径最大风险。
- **任务与模块**：先处理4单元编译绑定失败，逐类审查未知；明确AC CALL、权限写入、RE各自支持契约；复用Slither资源／读写事实，必要时将已有风险目录、合法业务EVM见证经过独立收据接入生产链；完成AC与RE各一组真实漏洞—维护者修复正反。RabbitHole／Atomic适合开发调试，验证侧保持独立，不为成功率跨split调换。主要模块为 `compiler_facts/bound_slither/risk_binding/candidate_proofs/reentrancy_proofs/compiled_d2`。
- **交付物**：支持范围矩阵、逐候选缺口与修复差分、真实正反证据、独立工具／EVM身份与正常退出记录、边界失败集；引擎变化必须可映射到一类具体证据缺口。
- **工程门槛**：新增支持路径的源位置、身份、资源、初态和工具引用100%可回读；失败／不支持／超时仍UNKNOWN；合成错主体／资源／顺序／旧状态／旁路入口中不出现错误反驳；不把有guard、无告警、局部BLOCKED当完整保护。
- **研究门槛**：至少1组真实AC与1组真实RE，漏洞版本获有可行性证据的支持、对应真实修复获满足完整范围的反驳；审核确认修复语义而不是只看版本名。有限正例与整合约安全声明严格分离。若做不到，R2-07继续PARTIAL；这不是用合成负例可替代的要求。
- **退出与失败处置**：8～15人日用于上述有界范围，不承诺覆盖全部133。每个新增语义先证明必要性和边界；若两组仍依赖无法取得的外部语义，输出明确阻塞与可选收窄提案，不无限自研。支持范围收窄不能自动改变冻结全分母或<10%门槛。
- **资源**：本机固定solc／Slither，必要时已有本机Anvil；不需要真实链或攻击部署；0模型预算。独立审核预计1～2人日；复杂代理初始化、依赖源缺失可能造成外部等待。

### 阶段四：全部原候选重放与四基线（4～7开发人日）

- **问题／REQ**：R2-07、08、09、11；S11来源／固定候选与S12报告。依赖阶段三引擎冻结及阶段一候选身份。新151用于描述当前覆盖，旧133单独承担冻结数值验收。
- **任务与模块**：对同一批候选运行四臂：无验证、guard存在、具体行检查、完整D2。将弱基线的规则、范围和输出含义预先定义，保留失败；四臂共享输入、候选及资源预算，不重跑模型发现。涉及 `tool_replay/benchmark_batch/benchmark_report` 与已有挑战契约，复用GPTScan固定候选／漏检审计、SmartBugs失败归一化思想。
- **交付物**：四臂完整派生结果、候选级配对变化、错误支持／错误反驳、覆盖、UNKNOWN、失败、耗时／已观察usage／null成本报告；真实、人工构造及合成对照分表。
- **工程门槛**：旧159单元／133候选100%被保留和尝试核验；模型候选hash、原usage及原件前后SHA不变；新增模型请求0；统计总和闭合。最新151另行完整报告，不能替换旧分母。
- **研究门槛**：全体分母和有效子集同时报告；独立审核裁决正确性；按项目成组统计，样本不足明确探索。冻结目标要求旧133中UNKNOWN≤13，且不得因错误裁决或放宽定义获得下降；未达到就保持该项未完成。若不验证臂直接接受候选为告警，其结果只能按同一候选真值解释，不冒称有证明。
- **失败处置／资源**：若结果无改善，保留负结果，收窄D2方法主张；若<10%无望，提供证据、仍未知类别、可信可达范围与目标调整建议，等待单独决定。0模型预算；1审核人日，可与阶段三审核重叠；本机工具可能耗时，但不等于开发人日。

### 阶段五：完整工程复现与演示（2～4开发人日）

- **问题／REQ**：R2-01、02、05、08、10、12；S12页面与交付。前置阶段三／四最终接口与结果，环境准备可提前。
- **任务／交付**：同一当前源码身份运行完整Maven、Python、CLI；本机真实工具与最终案例；浏览器查看六义务、未知原因、原始／派生、源码定位和下载。提供最小复现说明及源／依赖／工具清单，原件可获取性和远程备份状态明示；不复制整套数据或JAR到证据目录。
- **工程门槛**：`mvn clean verify`、`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`、CLI帮助成功；相关真实工具／浏览器无未解释失败；派生下载身份匹配；零模型历史回放；缺usage仍null。测试数随代码变化，不把历史663／109当新门槛。
- **研究门槛**：本阶段只验证复现和展示，不提升研究状态；有第二环境时执行零模型复现。未做第二环境验证就称“本机可复现”，不称跨机验证完成。
- **失败处置／资源**：构建失败或身份无法恢复先修复，不能用旧日志验新代码；1～2名实际演示观察者有帮助，但不等同独立标签审核；0模型预算。未来完成小版本后按AGENTS检查凭证与体积并提交同步，本轮禁止提交／推送仍有效。

### 阶段六：论文主张、材料和逐项结项（4～7开发人日）

- **问题／REQ**：R2-04、07、09、11、12；S12材料。前置前五阶段最终证据，系统实现和相关工作章节可提前写。
- **任务／交付**：形成问题定义、D1／D2方法边界、系统架构、真实案例、发现与核验两组实验、消融／失败分析、有效性威胁、启动演示／复现命令及逐项结项表；所有数字由保存原件生成。把“论文主张—定义—代码—实验—限制”逐一映射。
- **工程门槛**：报告中的分母、数字、链接和代码身份100%核对；模拟与真实、历史与本轮、开发与验证样本明确；必要证据不超预算，唯一原件保留且可回读。
- **研究门槛**：无增益可以诚实形成负结果／工程贡献；不能保留未获证据的“显著提升”“通用安全证明”。D2数值或真实正反未满足时，在结项表保持未通过并附目标变更建议，不以写完论文替代冻结验收。学校格式、最低工作要求和答辩时间须另行确认。
- **资源／不确定性**：0模型预算；导师／独立审核者对主张和学校要求的反馈属于外部等待。这里估算为已有材料基础的技术正文与证据整合，不含学校要求未知的额外实验或多轮大改。

## 6. 接下来三个工作包与可直接执行提示词

| 顺序 | 工作包 | 本次应收敛的产物 | 启动理由 |
|---|---|---|---|
| 1 | 双批次身份与候选审核准备（约1～2人日，阶段一的首部分） | 旧133／新151独立账本、原件摘要、未知分流、十事件缺口表、可给审核者使用的表单 | 完全零模型；先把目标、证据和分母固定，阻止后续“换题达标” |
| 2 | D2最小真实闭环与失效诊断（约3～5人日的首轮，属于阶段三） | 4编译失败诊断、AC／RE真实修复的缺失前提、一个可完整验收的有限子集及边界反例 | 先判断可靠裁决能否形成；不承诺这一包解决所有139未知 |
| 3 | D1条件机制与完整token准入（约2～3人日的首轮，属于阶段二） | 人工可审核pair、自动／正式路径区别、上下文消费检查、发现对照与消融的零请求预注册 | 防止再次付费测到“软配对”，却宣称条件机制增益 |

上述工作包工时包含在阶段估计中，不额外累加。工作包二、三在各自输入可用后可以并行，但不是本轮授权的实施动作。

**工作包一提示词：**

```text
请在 /Users/daiyifei/Documents/code/SmartContract-agent 执行“R2 双批次身份与候选审核准备”。

先遵守 AGENTS.md，读取 docs/vibe/PROJECT.md、PROGRESS.md，再读取
docs/vibe/releases/R2-20261010/RESEARCH_GAP_REVIEW_20261013.md 及当前 SPEC、统一计划。
全程简体中文，当前主目录工作，保留已有未提交改动，不创建worktree。

本工作包只读业务、原件、标签和冻结知识；仅新增审核报告、派生清单和必要证据。
不修改裁决引擎、原候选、原行号、历史标签、冻结目标或验收状态；不提交或推送；
不运行真实模型、不切换端点、不使用历史单批API授权。

以 storage.read_artifact() 读取并分别封口：
1. 119b4862f8a14818b62848ce709c3ee6：159单元、133原假设，保存12支持／121未知；
2. 6cae40677b104152bd92efedc5bbc479：159单元、151原假设，保存12支持／139未知。
旧批次承担UNKNOWN<10%的冻结目标，新批次仅单独报告当前覆盖，绝不混换分母。

复用 .evidence/R2-20261010/research-review-20261013/ 的已完成只读重算和候选账本，
先核对其输入摘要与本轮源码身份，避免无意义重做。补足旧133的逐候选稳定ID和原始hash。
每条保留批次、sampleId、策略、index、完整原候选指针、输入摘要、原位置／操作、
编译／工具身份、assessment是否缺失、裁决、所有原始gaps及互斥首要分流。
“模型候选错误”必须有逐项证据，不能从UNKNOWN反推。

核对最新4单元编译绑定失败及9条缺核验候选，只输出诊断证据，不改引擎。
核对现有十事件盘点的独立项目、源码／维护者修复版本、许可、原件可得性、
knowledge／validation划分、审核状态和缺口；不把六准入写成十组完整正反。
四个OpenZeppelin安全来源需保留同上游关系，未审核者保持待审。
输出独立审核表，区分样本级来源标签与候选位置／操作／性质真值，预留争议和仲裁字段。
未知的标签保持未知，不用自动标签或模型自评填成独立人工审核。

在现有R2目录新增一个工作包报告；Slice映射沿用S11来源／固定候选和S12材料，
不新建Slice独立目录或整套规格。必要证据仅放对应 .evidence 任务目录，
不复制完整模型响应、数据集、仓库或构建产物。

验收：两批候选与单元数准确；原件前后SHA一致；逐候选ID唯一且100%可回读；
缺失／失败／UNKNOWN未丢弃；新模型请求0；业务与冻结文件摘要不变；证据体积合规。
最终列明可立即交给审核者的材料、不可取得的证据，以及工作包二可启动的具体输入。
无法取得的证据明确留缺口，不反复提问替代调查，不宣称researchEligible=true。
```

## 7. 已核实来源、未核实事项与最少补充信息

### 7.1 本轮验证与保留证据

本轮运行的选择性离线测试命令为：

```bash
PYTHONPATH=tools/experiment:tools/experiment/tests python3 -m unittest \
  test_evaluation_input test_benchmark_report test_benchmark_batch \
  test_d1_consumption test_risk_binding test_reentrancy_proofs \
  test_compiled_d2 test_candidate_proofs -v
```

结果185项通过、无失败，耗时37.485秒，Python3.14.7。初次命令未包含tests目录，发生3个导入错误，纠正路径后通过；[失败记录][testfail]保留，不修改测试来掩盖问题。本轮**没有**运行全量Maven／Python、CLI、真实编译器／Slither／EVM、浏览器或外部论文复现实验；历史这些能力的通过情况只引用原记录。真实模型新增请求0。

| 本轮证据 | 内容 |
|---|---|
| [证据说明][evidence] | 命令、执行身份、结果、限制及体积检查 |
| [只读重算脚本][script]／[批次重算][recompute] | 最新指标、usage、D1实际路径、D2缺口和原件前后摘要 |
| [候选账本][triage] | 最新151候选逐项来源、裁决与分流 |
| [独立指标][independent] | 不调用项目指标函数的共同样本重算；字节重复检查 |
| [数据身份][dataidentity] | Nomic快照与六事件18份原件匹配 |
| [旧133口径核对][oldcheck]／[执行身份][identity]／[工作区读前摘要][workspaceidentity] | 旧批次数量与原件hash、历史84文件比较、本轮344文件保护基线 |
| [外部来源登记][sources] | 检索候选、论文缓存摘要、四官方仓库固定commit及关键文件hash |

研究原件仍在[research-artifacts][artifacts]，仅本机保存与远程备份未配置是现有限制；Git忽略不等于备份。报告和小型证据不复制全部付费响应或外部仓库。

### 7.2 仍未核实、不得写成完成的事项

- 学校毕业标准、最终截止日期、可用开发／审核人力；历史“2026年11月开题”不等于毕业截止日期。
- 所有候选的独立人工真值、完整项目谱系／克隆排查、四个安全对照的强负例资格，以及模型预训练污染。
- D1条件机制独立增益、同完整提示token公平、真正相关性Recall@K、重复试验稳定性。
- D2真实维护者修复的双向可靠性、跨合约／动态调用等超支持范围语义、旧133候选完整重放与<10%目标。
- 当前未提交源码的完整构建／生产集成，风险目录与EVM见证接入后的实际表现；当前HEAD不能自动代表历史JAR全部内容。
- PropertyGPT核心prover开源与许可、eThor可取得源码、iAudit可读官方代码；ELSA／DeepDesc等仅元数据候选的具体实现与可复现性。
- 本轮没有实际复现外部论文的效果数字，不能写成“复现一致”或“本系统优于这些工具”。

### 7.3 后续真正需要用户补充的最少信息

1. 学校最终提交／答辩时间，以及论文／系统必须满足的硬性要求；这会决定是否需要提出冻结范围调整。
2. 是否能安排至少一位未参与规则调参的审核者，以及可投入时间；没有独立审核仍可推进工程，但研究资格不能升级。
3. 只有准备执行B路线的新真实模型实验时，才需要确认具体模型、端点、请求／token／金额预算；当前A路线首先按零新增模型预算推进。

这些信息尚缺，不妨碍先执行第一个工作包。若D1无增益或D2达不到目标，报告应保留负结果、收窄论文主张，并将冻结目标变更作为单独决策提出；不能以“必须证明有效”为前提改动数据、分母或裁决语义。

[spec]: SPEC.md
[plan]: IMPLEMENTATION_PLAN.md
[verification]: VERIFICATION.md
[input]: ../../../../tools/experiment/evaluation_input.py
[targets]: ../../../../tools/experiment/benchmark_targets.py
[riskfact]: ../../../../tools/experiment/benchmark_runtime.py
[exploratory]: ../../../../tools/experiment/exploratory_targets.py
[auditrun]: ../../../../tools/experiment/audit_run.py
[auditrequest]: ../../../../tools/experiment/audit_run.py
[hypothesis]: ../../../../audit-mvp/src/main/java/com/xhl/audit/service/HypothesisService.java
[runtime]: ../../../../tools/experiment/benchmark_runtime.py
[d1consume]: ../../../../tools/experiment/d1_consumption.py
[retriever]: ../../../../audit-mvp/src/main/java/com/xhl/audit/retrieval/D1Retriever.java
[automatic]: ../../../../audit-mvp/src/main/java/com/xhl/audit/retrieval/AutomaticContrast.java
[binder]: ../../../../audit-mvp/src/main/java/com/xhl/audit/retrieval/ConditionBinder.java
[compiler]: ../../../../tools/experiment/compiler_facts.py
[slitherbound]: ../../../../tools/experiment/bound_slither.py
[binding]: ../../../../tools/experiment/risk_binding.py
[graph]: ../../../../tools/experiment/compiled_d2.py
[candidateproof]: ../../../../tools/experiment/candidate_proofs.py
[reproof]: ../../../../tools/experiment/reentrancy_proofs.py
[verdict]: ../../../../tools/experiment/compiled_d2.py
[obligations]: ../../../../tools/experiment/d2_verify.py
[evm]: ../../../../tools/experiment/evm_witness.py
[catalog]: ../../../../tools/experiment/risk_catalog.py
[replay]: ../../../../tools/experiment/tool_replay.py
[reportcode]: ../../../../tools/experiment/benchmark_report.py
[corpus]: ../../../../tools/experiment/r1_candidate_corpus.py
[proxy]: ../../../../tools/experiment/benchmark_batch.py
[isolation]: ../../../../tools/experiment/isolation.py
[pilot]: attachments/REAL_CASE_PILOT.md
[nine]: ../../../../.evidence/R2-20261010/S11-integration/cli-candidates/summary.json
[run]: ../../../../research-artifacts/runs/benchmarks/6cae40677b104152bd92efedc5bbc479
[artifacts]: ../../../../research-artifacts/README.md
[tests]: ../../../../.evidence/R2-20261010/research-review-20261013/targeted-tests.log
[testfail]: ../../../../.evidence/R2-20261010/research-review-20261013/targeted-tests-import-failure.log
[evidence]: ../../../../.evidence/R2-20261010/research-review-20261013/README.md
[script]: ../../../../.evidence/R2-20261010/research-review-20261013/recompute.py
[recompute]: ../../../../.evidence/R2-20261010/research-review-20261013/batch-recompute.json
[independent]: ../../../../.evidence/R2-20261010/research-review-20261013/independent-metrics.json
[triage]: ../../../../.evidence/R2-20261010/research-review-20261013/candidate-triage.json
[identity]: ../../../../.evidence/R2-20261010/research-review-20261013/execution-identity.json
[dataidentity]: ../../../../.evidence/R2-20261010/research-review-20261013/data-identity.json
[workspaceidentity]: ../../../../.evidence/R2-20261010/research-review-20261013/workspace-read-identity.json
[sources]: ../../../../.evidence/R2-20261010/research-review-20261013/source-registry.json
[oldcheck]: ../../../../.evidence/R2-20261010/research-review-20261013/old-batch-check.json

</details>

返回 [唯一文档地图](../../PROJECT.md)。
