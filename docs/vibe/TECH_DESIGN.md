> 2026-09-19 实施更新：本文件后续内容保留原系统调查结论。当前 S0 通过独立 `audit-mvp` 模块实现，具体接口与边界以 [S0 SPEC](releases/R1-S0/SPEC.md)、[实施计划](releases/R1-S0/IMPLEMENTATION_PLAN.md)及 [README](../../README.md) 为准。原 `src/` 尚未迁移，本文件列出的旧代码缺陷不能视为全部已修复。

# 当前源码架构与重构依据

状态：当前事实记录，不是目标设计。核查日期：2026-09-18。代码基点：`66161d5b74a6df980425f37c913e63591d246d2a`。源码摘要见 [source-manifest.json](releases/R0-20260918/review-evidence/source-manifest.json)。

## 1. 核心结论

可以复用 Java 服务入口、模型兼容接口、Milvus 接口、Slither/Mythril 输出转换以及报告展示经验；不宜在现有 406 行审计服务与大规模 JUnit 实验类中继续叠加 D1/D2。首先需要拆分运行状态与安全判断，修正进程超时、建立数据清单与可重放实验，再验证方法。

现有实现是固定多阶段管线，并非能够按证据缺口自主规划的闭环 Agent。README 图中工具反馈回假设生成的箭头未对应 `auditFullAgent` 中的实际循环。D1/D2 当前都未实现。

## 2. 调查范围与方法

逐段核查 README、pom、AGENTS、SmartContractDetect、SafeQuestionAnswerAdvisor、文档加载与 Milvus 配置、分块工具、假设和结果模型、Slither/Mythril、JSON 规范化、模型配置、实验主类、SmartBugs 构造脚本及相关测试。另做全 Java 文件入口/调用扫描，检查遗留 RAG 工厂、工具注册、日志、配置边界及数据目录；非主线演示类未作业务级审计。

本轮的静态证据不等于运行故障复现。下文将源码可直接推导的问题标为“静态确认”，环境或具体输入下的结果标为“待运行验证”。没有启动 Spring 应用、Milvus，没有调用付费 API，没有执行可能覆盖数据的构造脚本。

## 3. 实际运行链路

```text
JUnit / Java 调用入口
  ├─ auditVanilla → LLM → JSON 规范化 → 三字段结果
  ├─ auditRAGOnly → 规则查询 / Milvus Top-3 → LLM → 三字段结果
  └─ auditFullAgent
       → retrieveContext
       → generateHypothesis（一次 LLM 调用 + 源码字符串兜底）
       → Slither（必运行）
       → shouldRunMythril（类别或 Slither High/Medium）
       → Mythril（满足条件才运行）
       → LLM 最终裁决（第二次 LLM 调用）
       → normalizeFinalResult
```

当前没有 REST Controller。Spring Web 依赖和 `/api` 配置不能视作已提供公开审计 API。`ToolRegistration.allTools` 生成回调数组，但 Full 直接调用 Java 工具对象，未依赖模型自主工具选择。创建了 FileBasedChatMemory 对象，但未将其装配为审计调用的记忆 Advisor，因此不能声称本模式利用了跨轮记忆。

## 4. 组件与边界

| 组件 | 当前职责与输入输出 | 重构判断 |
|---|---|---|
| SmartContractDetect | 源码字符串 → 三字段结果；内嵌提示、路由、类型规则、JSON 处理 | 保留旧入口作为兼容层，编排与策略拆分 |
| SafeQuestionAnswerAdvisor | 字符串规则构造查询；dataset 过滤；Top-3/0.5；每例前 700 字符 | 冻结为旧策略；新检索接口不依附聊天 Advisor |
| ContractAppDocumentLoader | 扫描所有 Markdown，手工逐行解析 Front Matter | 可复用读取思路，需清单、严格字段校验、逐文件失败记录 |
| MilvusVectorStoreConfig | Bean 初始化时探测并批量导入；6000 字符、400 重叠、batch=10 | 拆成显式离线构建流程；运行时只读冻结快照 |
| SlitherTool / MythrilTool | 单源码临时文件 → 整合约分析 → JSON 字符串 | 复用解析知识；重做进程执行、状态和完整证据保留 |
| ContractAuditHypothesis | suspected / candidateTypes / rationale / keySignals | 无实例位置、条件命题或证据关联 |
| SmartContractAnalysisResult | boolean + 类型字符串 + 理由字符串 | 无未决/运行错误语义，无多实例表达 |
| VeriRAGExperimentTest | 采样、调用、重试、计分、报告集中在 JUnit | 拆成命令入口、运行器、纯评估器与报告器 |
| CodingPlanConfig / EmbeddingConfig | Chat 为 OpenAI 兼容接口；Embedding 单独为 DashScope | 适配器可复用；调用额度、超时、成本应统一记录 |
| 遗留恋爱 RAG / 下载 / 文件 / PDF 工具 | 非审计主线；部分仍是 Spring Bean 或测试项 | 先隔离非核心装配，不先大规模删库式清理 |

## 5. 问题证据台账

完整路径相对仓库根目录；表中 app/、rag/、tools/、advisor/、config/、utils/ 前缀省略 `src/main/java/com/xhl/xhlaiagent/`，experiment/ 省略 `src/test/java/com/xhl/xhlaiagent/`。行号对应上述代码基点。P0 表示在可信实验前必须处理，不代表已动态复现所有风险。

| ID / 优先级 | 证据位置 | 问题及影响 | 判断与拟验收 |
|---|---|---|---|
| F01 / P0 | `src/main/java/com/xhl/xhlaiagent/advisor/JsonNormalizationAdvisor.java:35,103`；`app/SmartContractDetect.java:389` | 空/无对象响应或空结果可成为 hasVulnerability=false；格式失败与无漏洞混淆 | 静态确认；空、截断、缺字段分别保留错误，不产生安全判断 |
| F02 / P0 | `src/test/java/com/xhl/xhlaiagent/experiment/VeriRAGExperimentTest.java:328` | 捕获异常后构造 false/SystemError，再调用 computeOutcome；负样本异常被算 TN | 静态确认；独立错误维度及包含失败的总覆盖统计 |
| F03 / P0 | `src/main/java/com/xhl/xhlaiagent/tools/SlitherTool.java:67,70`；`tools/MythrilTool.java:66,70` | 同步读到 EOF 后才 waitFor；不关闭输出的子进程可使等待永不进入超时逻辑 | 静态确认；受控挂起子进程的墙钟超时与后代清理测试 |
| F04 / P0 | `tools/SlitherTool.java:108`；`tools/MythrilTool.java:107` | 缺少结果字段与空 issues 均被归为 ok；未综合退出码和顶层成功状态 | 静态确认；失败 JSON、非零退出及合法空结果分开测试 |
| F05 / P0 | `rag/MilvusVectorStoreConfig.java:35,88,119` | 查到一条就认为导入完成；探测异常变成重新导入；中断可能留部分数据 | 静态确认；构建 manifest、计数/哈希和原子激活快照 |
| F06 / P0 | `experiment/VeriRAGExperimentTest.java:222` | 目录直接推断 GT，safe 文件夹自动为安全；无标注范围与来源审核 | 静态确认；标签 manifest 显式记录 reviewed/unknown 与覆盖范围 |
| F07 / P0 | 测试源码 SHA-256 实测，见数据证据 | 7 组完全重复：各漏洞目录 buggy_22.sol 与 buggy_36.sol 相同 | 实测确认；同组只作一个独立单位，所有变体归组后划分 |
| F08 / P1 | `experiment/VeriRAGExperimentTest.java:517` | 类型误报只记 FN，不对错误预测类别记 FP；不可等同标准多类别 Macro-F1 | 静态确认；旧 VTA 仅作历史口径，新实例/类别混淆独立实现 |
| F09 / P1 | `experiment/VeriRAGExperimentTest.java:495` | 分类别 Recall 按二分类 outcome 计分，不要求类型正确 | 静态确认；报告区分检出率、类型召回与定位召回 |
| F10 / P1 | `experiment/VeriRAGExperimentTest.java:243,290` | 先按文件名字典序截取，再打乱；seed 不代表随机抽样 | 静态确认；冻结分组采样清单，所有模式读取同一清单 |
| F11 / P1 | `experiment/VeriRAGExperimentTest.java:377` | 重试整个 Full 审计，可能重复检索、假设和工具；没有阶段检查点 | 静态确认；仅对失败调用重试，尝试和累计成本全部留痕 |
| F12 / P1 | `experiment/VeriRAGExperimentTest.java:156,167,207` | 无效模式或空数据日志后正常返回；结果到结尾才写 Markdown | 静态确认；错误退出码、逐样本持久化、幂等恢复 |
| F13 / P1 | `rag/SafeQuestionAnswerAdvisor.java:22,78,105,161` | 查询依赖字符串，前 700 字符不保证包含漏洞/保护语义；同一文档块可能重复 | 静态确认；旧策略保留作为对照，D1 单独实验 |
| F14 / P1 | `app/SmartContractDetect.java:228,280` | 模型不怀疑时也可能因字符匹配被置 suspected=true；模型与规则来源未区分 | 静态确认；规则候选与模型候选记录来源，不伪称 LLM 判断 |
| F15 / P1 | `tools/MythrilTool.java:46`；工具仅写 `contract.sol` | 绝对路径绑定当前机器；缺多文件依赖/版本锁；整个合约运行不等于定向核验 | 静态确认；可配置工具、编译清单与能力范围 |
| F16 / P1 | `advisor/JsonNormalizationAdvisor.java:93` | 重建 ChatResponse 时未保留原 metadata/usage；难以可靠核算 Token | 静态确认；适配器先保存原始 usage 与请求元数据，缺失用 null |
| F17 / P1 | `advisor/MyLoggerAdvisor.java:27` | INFO 打印完整请求及响应，可能包含整个合约和知识正文 | 静态确认；普通日志仅 ID/状态，受控原始证据单独保留 |
| F18 / P1 | `scripts/flatten_oz.py:169,175,200,253` | 未解析 import 只警告后继续去掉 import；只保留入口 pragma；先删除全部旧输出 | 静态确认风险；不执行旧脚本，目标导入需依赖完整性与非覆盖构建 |
| F19 / P1 | `src/test/java/com/xhl/xhlaiagent/app/SmartContractDetectTest.java:17` 等 | Spring 测试依赖外部基础设施，多为非空断言；Mythril 测试用旧中文错误文本判定 | 静态确认；解析、状态、路由、计分应有离线确定性测试 |
| F20 / P2 | `rag/LoveAppRagCloudAdvisorConfig.java:19`；pom | 非主线云 RAG 配置仍注册，依赖多个 AI SDK；Vanilla 也受整应用装配影响 | 静态确认装配；实际各环境启动行为未运行验证 |
| F21 / P2 | `utils/SimpleLengthSplitter.java:35` | 未校验 maxLen/overlap；非法配置可导致不前进 | 静态推导；参数边界测试，字符预算与 Token 预算分开 |
| F22 / P1 | `config/CorsConfig.java:16` | 凭证跨域与任意来源模式并存；当前没有 Controller，不能称已发生远程漏洞 | 静态确认；本次不新增公网 API；若以后开放须单独审查 |

## 6. 文档与源码冲突

AGENTS 写每类 3、MAX_RETRIES=3、请求间隔 1 秒；当前代码实际为每类 50、安全 50、MAX_RETRIES=5（最多 6 次尝试）、间隔 2 秒。AGENTS 称 Slither 过滤 High/Medium，但解析循环保留所有 detector；High/Medium 用在 Mythril 路由。`CATEGORY_MAPPING` 用 Timestamp 键，实际目录为 Timestamp-Dependency；当前 getOrDefault 恰好返回标准标签，没有因此丢样本，不将它误报成现有分类错误。

README 的“可复现”尚欠环境锁、知识快照、调用参数及原始记录。README 所写 Safe 来源只是构造来源，不构成每份样本在指定威胁模型下安全的证明。不会把这些旧口径带入正式毕业论文。

## 7. 数据和环境实测

- 当前 35 个主 Java 文件、8 个测试 Java 文件；测试数据 350 正样本 + 50 名义安全样本，知识文档 143 份。
- 完全重复组 7，每组 2 份，400 文件对应 393 个字节级唯一源码；不意味着 393 个独立项目。
- 从 143 份 Markdown 提取代码后，与测试源码首尾空白标准化哈希比较，未发现相同项。该检查不覆盖近似克隆、共享基础合约、项目级关系、模型训练污染。
- `benchmark/testset` 不存在；实际入口为 `src/main/resources/testset`。
- `java -version` 为 Corretto 21.0.8；`mvn -version` 的实际运行 JDK 为 Homebrew 23.0.2。pom 的编译目标为 21，二者不可混为一谈。
- 离线 `test-compile` 成功，但主类增量检查显示 up to date，未证明干净构建；本地 protobuf POM 有非法依赖声明警告，未修复缓存或依赖。
- 本地两个非跟踪 profile 文件含非占位凭证字段，本轮未输出值；仅在本机保持现状。忽略文件不能自动证明 Git 历史从未含凭证，本轮未审计历史秘密。

## 8. 可复用与需要重做的边界

可复用：三模式作为研究对照概念、现有数据作为 legacy 冒烟集、部分工具解析映射、OpenAI 兼容模型接入结构、Milvus 存取方式、报告展示。

必须重新定义：状态/裁决契约、样本与标签模型、证据引用、知识快照、预算重试、实验指标与独立验证。

无需先做：全面换语言、升级全部依赖、Web UI、多 Agent 平台、Foundry 全链重放、改造符号执行内部搜索。这些都不是本轮重构前置条件。
