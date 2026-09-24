# D1 工程设计与语义边界

日期：2026-09-22。落实用户已授权的 S2 工程需求；不表示论文创新效果已经成立。

## 实际调用链

`program_facts.py → PythonFactsExtractor → RetrievalStrategy → EvidenceBundle`。

另一路：`S1b 完整快照 → recall.py（本地余弦或 Milvus）→ 绑定目标 sourceHash 的 CandidatePool`。Java 检索接口只消费导出的知识候选与程序事实，不读取审核清单中的目标标签。目标源码必须匹配候选池绑定，召回导出前确认目标属于快照全量清单的非 knowledge 划分。源代码路径与 CLI 参数不会触发模型调用。

## 事实语义

事实提供器使用标准库词法与括号结构分析，记录合约状态变量、函数作用域、修饰器名称、CHECK/WRITE/CALL、源码行号及展开后的相对顺序。源码 SHA-256 和作用域内事实 ID 使引用可追溯；同一行重载函数使用独立作用域编号。

- `CHECK`：require/assert 中受支持的等值比较。它是检查的事实，不自动等于权限验证成功。
- `WRITE`：受支持的直接状态写语句；不推断具体数值是否完成资金扣减。
- `CALL`：受支持的低级外部调用、send/transfer；主体是源码中的接收方表达式。
- 无参数、单占位符的局部修饰器按嵌套顺序展开；仅有 onlyOwner 名称而无定义时保持未知。

分支、循环、继承、汇编、未知调用、内存/存储别名、复合赋值未支持形式、元组赋值、参数/局部遮蔽等产生 PARTIAL。这些作用域的条件判断返回 UNKNOWN。赋值右侧含外部调用也降级，避免把左值出现位置误当实际写入顺序。短路运算、多维索引、局部赋值、单语句多重赋值以及作为下标的状态变量发生写入，也降级为 PARTIAL；当前不追踪这些表达式的数据流。结构损坏返回 FAILED，不能解释成没有防护。

这不是完整 Solidity 解析器、编译器、CFG 或跨函数分析器。即使状态为 COMPLETE，也仅表示本提供器的受限结构处理完成，不证明源码能编译、可达性或保护有效性；正式研究数据还必须有独立编译与语义审核。

## 角色与条件

Target 明确给出 mechanism、riskFactId 和角色：actor 必须为当前调用者 `msg.sender`；resource 对应当前风险操作资源；authority 由调用方明确指定为权限状态槽，程序不从 `owner` 等名称猜测合法主体。状态写目标必须与 resource 一致。

两种初始条件：

| 谓词 | 检查对象 |
|---|---|
| CHECK_BEFORE | 同作用域内，在风险之前检查指定主体与指定权限槽相等 |
| STATE_WRITE_BEFORE | 同作用域内，在外部调用之前写入指定状态资源 |

条件使用 `$actor/$resource/$authority` 显式绑定。输出 SUPPORTED/CONTRADICTED/UNKNOWN，包含具体事实引用与原因。不同作用域、错误主体、明显不同的状态资源、检查过晚均不能提供前置支持；同一映射的不同动态下标不能直接认定资源不同，保留 UNKNOWN。等式正反写法使用相同的主体与权限槽别名规则。检查后同根权限槽被写入（包括可能别名的其他下标）或发生外部调用时，旧检查失效，保留 UNKNOWN。

STATE_WRITE_BEFORE 仅表达顺序，不说明更新值足以防止重入；案例适用性不是漏洞裁决。未知或矛盾案例可以出现在传统检索对照中，但 D1 不将其用作直接支持。

## 配对和强对照

CandidatePool 固定 snapshotId、sourceHash 和完整候选块；每个候选包含来源、已审核标识、配对 ID、机制、风险种类、角色和条件。候选池摘要保存进每份输出。

- Dense：按向量相似度排序。
- Hybrid：同一候选池按 cosine + 词集合 Jaccard 排序；这是明确固定的先导规则，不声称训练得到最优权重。
- 普通正反例：同机制分别选高分漏洞例和防御例，不使用条件过滤或配对差异。
- D1：只接受同审核配对、同机制、同风险种类且条件有差异的两侧；当前条件匹配的一侧作为 SUPPORT，另一侧作为 CONTRAST。按条件覆盖数、向量分数和稳定 ID 排序；去掉重复案例块、相同正文和无新增条件覆盖的配对。

所有策略使用相同 `Budget(maxBytes,maxCases)`。预算精确覆盖返回的 `context` UTF-8 字节（包含案例标识、角色和正文），不把无固定 tokenizer 的估算冒充模型 token。证据解释单独返回，不能在后续模型提示中免费追加解释或额外案例；正式模型实验必须冻结 tokenizer 与整个提示预算。

输出记录所有候选的逐条件评估，包括未被选择的 UNKNOWN/CONTRADICTED 项。没有有效防御案例、支持侧未知或预算不足时输出缺口，不拼造案例。案例 REVIEWED 与 pairId 是审核输入要求，程序不能替代对补丁真实有效性的人工审核。

## Milvus

本地镜像 `milvusdb/milvus:v2.6.4` 已实际验证。`MilvusRestIndex` 用标准库 REST 请求实现独立集合创建、完整读回和搜索，复用 S1b 的快照激活门禁；只允许 loopback URL 和 `s1b_` 随机集合，不修改旧集合或别名。凭证仅从 `MILVUS_TOKEN` 环境读取，HTTP 错误不输出服务端原文。

远端候选 ID、重复项、返回数量和 cosine 分数均对照本地快照核验，失败不回退为模型推测。当前分页读取使用 offset，超出服务器窗口会显式失败，未声称适用于无限规模知识库。

接口参考：[Milvus 向量搜索](https://milvus.io/docs/single-vector-search.md)。启动差异依据 [v2.6.4 配置源码](https://github.com/milvus-io/milvus/blob/v2.6.4/pkg/util/paramtable/service_param.go)：本地镜像须在进程初始化前设置 `DEPLOY_MODE=STANDALONE` 才能启用嵌入式 etcd。
