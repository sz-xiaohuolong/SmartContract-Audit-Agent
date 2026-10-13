# 2026-10-13 阶段1～5零模型工程实现与重放报告

本轮接通了身份账本、D1提示消费记录、编译／SlithIR／有限EVM见证、四臂报告和工作台读取链路。**整体验收仍为PARTIAL：旧133候选UNKNOWN低于10%、真实维护者修复的AC／RE双向闭环、独立候选真值与精确token公平尚未全部满足。** 新增模型请求和嵌入请求均为0；不将局部工程通过写成五阶段全部完成。

依据为[研究差距报告](../RESEARCH_GAP_REVIEW_20261013.md)、[有效规格](../SPEC.md)及[统一计划](../IMPLEMENTATION_PLAN.md)。本轮基点为 `fa4c9f40a8b671fbd324343218044eedca68ccc9`，在当前主目录整合已有相关改动；原有R1提案、三份脚本删除及`.aris/`不纳入本轮提交。

## 冻结分母与最终结果

两批最终重放均为COMPLETED、159/159单元。独立脚本逐项核对稳定候选ID、原件SHA、源码／JAR身份、四臂分母及裁决，均一致；新增模型和嵌入请求为0。

| 原批次 | 候选数 | 保存SUPPORTED／UNKNOWN | 本轮SUPPORTED | 本轮REFUTED | 本轮UNKNOWN | UNKNOWN比例 | D2累计单元耗时 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 旧119b4862… | 133 | 12／121 | 75 | 0 | 58 | 43.61% | 242.719秒 |
| 新6cae4067… | 151 | 12／139 | 80 | 0 | 71 | 47.02% | 282.133秒 |

旧批次63条UNKNOWN转为SUPPORTED，原12条SUPPORTED保持不变；未知比例从90.98%降至43.61%，下降47.37个百分点。**58条仍超过≤13门槛，也不满足更严格的<13表述，冻结数值验收失败。** 新批次68条UNKNOWN转为SUPPORTED，仅单独报告覆盖，不替换133分母。REFUTED为0，不能宣称完成真实正反闭环。

| 四臂（接受／拒绝／未知） | 旧133 | 新151 |
|---|---:|---:|
| 无验证RAW_ACCEPTANCE | 133／0／0 | 151／0／0 |
| 修饰符GUARD_NAME_EXISTS | 123／10／0 | 143／8／0 |
| 行号LINE_CHECK | 112／21／0 | 118／33／0 |
| 完整FULL_D2 | 75／0／58 | 80／0／71 |

弱基线的接受／拒绝只表示对应规则决策，不是SUPPORTED／REFUTED证明。旧批次532行、新批次604行四臂结果均包含全部冻结候选；未有独立候选真值，所有混淆矩阵为null，禁止据此计算准确率或比较方法优劣。

旧58条未知按最终原因互斥分为：27条风险操作／跨度／调用上下文未唯一绑定，24条局部路径／入口／工具证明不足，6条机制／合约／源码身份未绑定，1条终止访问义务不足。新71条对应32条风险绑定、32条局部证明不足、7条有效编译收据缺失。明细与原始gaps均保留；这些是引擎诊断类别，不是人工错误候选标签。

最终派生目录：

- 旧133：`research-artifacts/runs/derived/5ee375133c084d6586ff8b8f43b4e009/`。
- 新151：`research-artifacts/runs/derived/5ee375151c084d6586ff8b8f43b4e010/`。

原始批次分别为 `119b4862f8a14818b62848ce709c3ee6` 和 `6cae40677b104152bd92efedc5bbc479`，均保留159单元。旧批次保存口径12支持／121未知；账本另列失败单元保守口径11／122，两者不能混用。新批次保存12支持／139未知，其中9条没有原assessment。所有原候选、原行号、模型对象、usage与原始字节保持不变；本轮仅写新派生批次。

每个最终目录包含 `manifest.json`、`samples.jsonl`、`assessments.jsonl`、`summary.json`、`four-arm-summary.json`、`four-arm-results.jsonl` 和 `REPORT.md`。大原件允许gzip无损归档，逻辑路径和原始SHA-256通过 `storage.read_artifact()` 回读。四臂候选ID与冻结账本相同；共享单元耗时不得按候选重复求和。

## 阶段完成边界

| 阶段 | 本轮已实现并核验 | 尚未完成的验收项 |
|---|---|---|
| 1 身份与来源 | 两批账本、稳定候选ID、159单元与284条候选回读、原件前后摘要；10个事件／项目的来源盘点 | 只有6个正式事件的18份来源／报告／补丁原件完整；4事件待审，Gondi补丁和Cooler完整报告缺失。独立候选真值未审核 |
| 2 D1准入 | 159上下文消费核对，300配对／22入选对窗口回读；Java最终system／user摘要与差分引导；六臂消融预注册 | 历史159单元缺最终请求回执；tokenizer未核实，精确token公平UNVERIFIED；212个自动条件仍UNKNOWN，不能由提示文字升级为正式ConditionBinder证明 |
| 3 D2证明 | 编译风险目录、唯一AST语句／±2行绑定、结构别名与时间；双收据接入有限EVM；真实U_BANK、PERSONAL_BANK、PRIVATE_ETH_CELL、Missing正裁决 | solc0.4.9的standard-json不兼容仍阻断Parity；复杂动态／代理／ERC20语义未覆盖；RabbitHole与Atomic维护者修复尚未形成SUPPORTED／REFUTED闭环 |
| 4 四臂 | 全部原候选逐项输出，固定身份、前后变化、UNKNOWN原因、耗时、四臂分布及下载 | UNKNOWN门槛未达；独立真值缺失，混淆矩阵为null，不能用样本来源标签替代候选真值 |
| 5 工程与工作台 | 全量离线测试、Java构建与CLI；浅色工作台SimpleDAO真实离线演练、六义务、行定位、JSON导出、派生报告 | 原始研究材料和工具二进制只在本机保存，远程备份未配置；单独Git克隆不能实现历史运行身份100%恢复 |

### 本轮关键修复

1. `compiled_d2` 将候选已绑定、工具双收据MATCH、同资源的UNKNOWN接入本机执行；正常业务独立执行两次一致后才能形成有限反例。`complete=false`及原静态缺口继续保留，有限执行不能用于完整反驳。
2. 辅助调用按源码跨度、声明、部署地址和返回栈核验，不因`Log`或`AddMessage`名称认定良性。子调用回滚、耗尽gas、未绑定实现与深层外部调用不能作为正常返回。
3. 修复SlithIR实际`mode`字段消费，以及旧Slither将局部storage初始化表示为AssignmentOperation、跨度却指向右侧索引的问题；仅由唯一局部声明、initializer AST、精确字节跨度、同根／key／字段共同准入。Index与Assignment同跨度分开核验，避免相互制造歧义。
4. 权限正裁决必须证明实际权限资源由敏感入口消费；候选SSTORE须改变紧前权限且正常持久提交，后续其他写入不能拼接归因。消费者必须读取同权限槽并实际执行不同状态资源写入或非零数值CALL；STATICCALL、零额调用和未建模深层回调保持UNKNOWN。
5. 本机Anvil固定Istanbul及传统交易费用字段，显式开启steps tracing。稀疏存储trace从实际同槽SLOAD后的栈恢复读取值，不以账户快照假装窗口读取证据。原字节码／ABI／AST不变，实际收款与合法时间推进构造初态；不使用直接改写storage、balance或code的方法。
6. 修复独立执行的区块时间漂移：原先固定时间先被空块消耗，日志器实际TIMESTAMP出现1秒差异；现在固定时间直接由业务交易消费，完整trace和双执行对账规则不变。红绿测试及修复前原件均保留。
7. 四臂汇总沿用候选独立裁决，其他合约工具失败不改写该候选已匹配的结果；失败候选自身、缺失assessment和UNKNOWN仍在分母中。弱基线只产生接受／拒绝决策，不冒充形式化证明。派生顶层记录当前编译清单／错误／诊断，旧失败单独放provenance；Spank本轮重编译成功，Parity三单元仍缺原固定版本的兼容协议，不能写成四单元均修复。

评审采用只读子代理，已修复候选前写入归因、packed address、消费者实际执行、错辅助部署、无关工具失败降级及深层回调等问题。相应失败／修复对照保留在下列证据目录；最终审查范围内无剩余阻断，不代表超出支持范围的程序语义已获证明。

## D1预算与研究解释

`hypotheses-v4-diff-guidance` 只引导比较修复变化窗口中的调用者断言、同资源写入与调用顺序；修复片段不替换待审源码。最终请求回执分列system、源码、上下文、其他指令／风险目录、消息封装和输出；实际字节可回读，但没有真实tokenizer的token数仍为null。历史usage也不补造。

`.evidence/R2-20261010/stage2-d1-20261013/latest/` 保存 `check.json`、`pair-review.json`、`protocol.json`。53个D1单元中33个AUTO_JAVA_SOFT、20个AUTO_PYTHON_SOFT；它们不是正式条件证明。本轮零模型重放不能回答改变提示是否提高模型发现率，也不能把历史212条自动条件改为SUPPORTED。

## 复现与执行身份

环境使用Java21、Spring Boot4.1.1、Spring AI2.0.1、Python3.14.7，以及按本机配置和源码pragma选择的固定solc、Slither、Anvil和cast。最终manifest记录每个生产Python／Java源码摘要、JAR摘要、工具配置及原件摘要；每个实际工具／EVM收据另记录二进制身份、源码闭包和执行证据。收据自身与输入文件应一起恢复。

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help

PYTHONPATH=tools/experiment python3 tools/experiment/tool_replay.py --compiled \
  --original-run research-artifacts/runs/benchmarks/119b4862f8a14818b62848ce709c3ee6 \
  --output-run research-artifacts/runs/derived/$(python3 -c 'import uuid; print(uuid.uuid4().hex)')

python3 tools/experiment/d1_research_check.py \
  --batch-dir research-artifacts/runs/benchmarks/6cae40677b104152bd92efedc5bbc479 \
  --snapshot-root research-artifacts/snapshots/nomic \
  --output .evidence/R2-20261010/d1-new-check

python3 tools/experiment/local_ui.py --port 8773
```

重放前恢复[原件清单](../../../../../research-artifacts/README.md)所指历史批次、快照、收据和二进制；不得续写旧计划。EVM配置参见[示例](../../../../../config/tools.example.properties)，实际路径与SHA填写到Git忽略的`config/tools.local.properties`。只启动独立回环节点，无模型端点请求。

浏览器打开 `http://127.0.0.1:8773/agent.html`，选择SimpleDAO，点击“离线演练”。结果为候选SUPPORTED，六义务中主体／资源／前置余额检查SUPPORTED，入口／状态版本／旁路REFUTED；义务反驳与最终候选反驳含义不同，不能把红卡计作修复案例REFUTED。点击第19行定位，导出JSON中`newModelRequests=0`、`modelCalls=0`，usage仍null。运行历史可查看最终派生报告与四臂下载。

## 验证与证据

全量Python **734项通过**（89.328秒），`mvn clean verify` **111项通过**（0失败／错误／跳过），CLI帮助退出0。最后的Python时间修复未改变Java或JAR，最终两批的生产源码和JAR摘要全部匹配。浏览器确认SimpleDAO六义务、19行定位、JSON导出与两批四臂报告；控制台错误0，下载原始字节与封口摘要一致。只读评审发现的问题均有修复与回归证据。

证据目录为 `.evidence/R2-20261010/stage1-5-final-20261013/`：

- `python-final.log`、`maven.log`、`cli.log`：全量测试与构建。
- `identity-verification.json`、`final-verification.json`：逐候选回读、原件保护、最终分布、身份与退出状态。
- `review2-red.log`／`review2-green.log`、`alias-*-red.log`／对应green、`deep-call-red.log`／`deep-call-green.log`：关键失败与修复对照。
- `workbench-simpledao.png`、`workbench-derived.png`、`browser-errors.json`、`browser-export-summary.json`、`browser-four-arm-downloads.json`：真实浏览器与下载核验。
- `timestamp-drift-comparison.json`、`timestamp-red.log`／`timestamp-green.log`：实际时间漂移原件指针与回归对照。
- `credential-scan.json`、`evidence-size.json`、`storage-retention.json`、`git-sync.json`：精确提交范围、凭证、体积、归档与同步身份。
- 完整执行trace只在 `research-artifacts/receipts/evm/` 保留一个权威版本；压缩后以原始SHA回读，不截断响应或执行步骤。

本任务证据约1.1MiB，整个`.evidence/`文件内容约47.2MiB，本任务无超过1MiB的单文件，符合10MiB任务／100MiB总预算。本轮40份派生文件无损压缩前519,014,885字节、压缩后72,143,914字节；各自仍由封口manifest的原始SHA验证，唯一原件未丢弃，研究原件远程备份仍未配置。

前四轮派生目录 `5ee371133c084d6586ff8b8f43b4e001`／`5ee371151c084d6586ff8b8f43b4e002`、`5ee372133c084d6586ff8b8f43b4e003`／`5ee372151c084d6586ff8b8f43b4e004`、`5ee373133c084d6586ff8b8f43b4e005`／`5ee373151c084d6586ff8b8f43b4e006`、`5ee374133c084d6586ff8b8f43b4e007`／`5ee374151c084d6586ff8b8f43b4e008` 是评审、元数据或时间修复前对照，不能代替最终版本验收。2026-10-13 用户要求清理无用旧结果后，保留时间漂移原件仍依赖的 `5ee374133c084d6586ff8b8f43b4e007`，其余7个中间重放及专属生成收据已删除；原目录和摘要登记在 `research-artifacts/migrations/obsolete-runs-cleanup-20261013.json.gz`。最终两批、真实模型原件及必要失败／修复对照仍可回读，本报告原统计不变。

## 保留的结论限制

当前正裁决证明有限CEI执行顺序违反或同资源调用者权限断言违反，不证明漏洞可利用性；没有生成攻击程序或载荷。没有独立候选真值，不能据接受数量计算精确率、召回率或宣称优于其他证明器。UNKNOWN包括候选操作类型不适配、多义位置、动态调用、无合法资金史、缺编译协议及未证明权限消费者，不能当作安全或错误候选自动扣除。

阶段3仍需支持原solc0.4.9对应的独立编译适配、真实代理／ERC20资源闭包与维护者修复双向验收；阶段1／4仍需独立来源与候选审核；阶段2仍需核实tokenizer后完成公平预算与正式消融。未达数值门槛如实保留，不修改冻结目标或分母。整个R2研究资格保持 `researchEligible=false`。
