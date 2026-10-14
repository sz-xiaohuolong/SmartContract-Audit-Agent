# 同编译证据重放：最新候选开始获得支持依据

复用发现阶段的编译证据后，最新 163 条候选为 82 支持、0 反驳、81 未知（49.69%）。旧 133 条和历史 151 条仍为 75／0／58、80／0／71。真实维护者修复仍未知，新增模板与复核的模型增益尚未测得。

这是按原日期保存的探索性记录。状态含义见 [概念速查](../attachments/CONCEPTS_AND_WALKTHROUGH.md)，跨批比较与当前结论见 [实验看板](../attachments/EXPERIMENT_DASHBOARD.md)。

## 实现与行为边界

| 任务 | 已实现行为 | 验收边界 |
| --- | --- | --- |
| SYN-01 | `compilation_runtime.py`重验并复用发现阶段input／output／binding，显式投影各候选合约；批量、单次、工作台、保存候选与派生入口贯通 | 原收据缺失拒绝，源码／设置／编译器漂移失败；fact ID格式及原候选不改 |
| SYN-02 | `real_fix_check.py`核验真实before／after独立源码、工具完成状态及最终SUPPORTED→REFUTED关系 | 当前两组真实修复仍UNKNOWN→UNKNOWN，不能用局部BLOCKED或义务REFUTED替代最终裁决 |
| SYN-03 | `focus_context.py`生成ff／fm／fi／fv原字节索引，登记全部合约入口与内部调用、资源写入及缺口；编译失败提供SYNTAX_ONLY | FULL模型源码不变；语法回退不宣称完整；间接函数指针、递归、assembly、动态／外部调用等明确未决 |
| SYN-04 | `check_templates.py`与10条AC／RE模板，核对知识划分、pair／chunk／来源及两个文档SHA，保守实例化并保存呈现回执 | 来源身份10／10，语义独立审核0；未绑定状态版本或路径不猜配；预算不足整条拒绝；默认仍消费原D1配对 |
| SYN-05 | `evidence_review.py`从重验AST独立核对引用、身份、入口操作、资源、闭包与正常提交，工作台展示PASS／CONFLICT／UNRESOLVED | 只读侧报告，gateApplied=false；不改D2三态；缺独立候选真值时精确率及混淆矩阵null |
| SYN-06 | `synapse_protocol.py`版本化一次三策略授权和RQ-A／B／C因素协议，绑定代码、来源与输入身份 | 多因素三次、双模型、重嵌入未授权；独立标签、来源谱系审核、精确token公平及真实双向闭环缺任一则researchEligible=false |

候选执行的实际`compilationManifest`独立持久化，冻结target保持原字节；工作台历史回读能恢复多合约实际清单。最终补上公开案例离线演练包装的导出字段，专项失败回归转为通过。该补丁仅影响local_ui输出包装；三批重放的证明器、Java源码和JAR逐文件一致，无须重新执行同候选工具重放。

## 固定候选重放

三批各159个目标／策略单元，原模型、候选、usage及标签只读。最新批通过权威单元索引物化读取视图，原三段模型批次不改；输入视图与其`original-unit-index.json`保留用于复核。

| 候选组 | 候选分母 | 最终支持／反驳／未知 | 未知率 | 原件与派生 |
| --- | ---: | --- | ---: | --- |
| 最新163 | 163 | 82／0／81 | 49.69% | 原逻辑视图`7422032756dd4cbcb1ba2861df17c3d9`；派生`761f5071074c4646a8679e860b97ab18` |
| 旧133 | 133 | 75／0／58 | 43.61% | 原`119b4862f8a14818b62848ce709c3ee6`；派生`f099df96bfd946b68a6792c7f35a6f64` |
| 历史151 | 151 | 80／0／71 | 47.02% | 原`6cae40677b104152bd92efedc5bbc479`；派生`fefe1e051eb843de8bce07d3528e68dd` |

最新163原为全部UNKNOWN；本次82条得到SUPPORTED，减少50.31个百分点。剩余81条分别为：风险操作／跨度／调用上下文无法唯一绑定30条，路径／入口／工具不足40条，缺有效合约编译收据8条，合约／函数／源码范围不匹配3条。身份修复没有保证每条候选都能得到最终裁决。

最新163的独立复核为PASS 9、UNRESOLVED 143、缺失11；其中73条D2支持仍有复核未决，多数缺主体／资源／状态版本的完整对照。复核没有自动覆盖现行证明，也不把未决计作错误接受。三批四臂均使用同候选分母；弱臂接受不表示证明，没有独立候选真值则混淆矩阵null。

## 真实修复对

RabbitHole与Atomic分别消费维护者before／after自身的源码、编译与工具收据。最终均为UNKNOWN→UNKNOWN，双向验收false。

- RabbitHole：公开初始化后的权限状态、继承库receiver、动态调用、TryStatement和正常返回语义尚未闭合。
- Atomic：跨合约token转账与回调状态超出现行msg.sender余额／uint转账证明范围；两侧Slither运行成功不补足该语义。

真实补丁原件、局部路径差异及缺口保留，不改候选标签或假装维护者修复无效。旧133未知≤13、AC／RE各一组真实漏洞SUPPORTED与维护者修复REFUTED仍是原验收条件。


## 复现与运行记录

下列原段落、表格和数值保留当时口径。凭证、用量缺失、运行锁与证据规范的统一解释见 [运行审计附录](../attachments/OPERATIONS_AND_REPRODUCIBILITY.md)。

<details>
<summary>展开原实验身份、执行经过与详细限制</summary>

# SYNAPSE 启发的工程实施与零模型验证

本轮根据用户授权实施统一计划 SYN-01～06。发现与候选核验现在消费同一份重验编译收据；焦点源码索引、10条知识来源检查模板、六项确定性证据复核及单次采集协议已接通。真实维护者修复双向裁决和旧133候选UNKNOWN≤13仍未通过，整体研究保持PARTIAL／UNVERIFIED。

工程在当前主目录 `main` 完成，保留已有R1文档改动、三个脚本删除及`.aris/`。工程验证新增模型／嵌入请求0；用户另行授权的一次真实API采集在工程提交后执行，结果独立记录，不能与固定候选重放混为一批。

## 验证、审查与原件

最终自动验证为758项Python通过（120.619秒）、111项Java通过及CLI帮助退出0。实际浏览器公开SimpleDAO演练得到SUPPORTED；焦点、模板与独立复核可见，JSON下载保留实际候选编译清单，模型请求0、usage=null。最后导出包装补丁有失败→通过回归，全量随后重跑通过。

独立整轮审查发现两项重要问题：候选实际清单没有持久化、复核的入口／操作／资源身份漏检；均先失败回归后修复。多合约入口遗漏与间接内部调用误报完整也已修复。无待延期Minor；不再用第二轮审查代替失败回归和全量验证。

原件与摘要位于`.evidence/R2-20261010/synapse-implementation-20261014/`：`execution-ledger.md`、`python-final.log`、`maven.log`、`replays-final.json`、`template-verification.json`、`browser-verification.json`及真实修复对。Atomic较大JSON已gzip无损归档，`atomic-pair-storage.json`登记原字节SHA和往返核验。重放原件位于`research-artifacts/runs/derived/<编号>/`，以`manifest.json`的输出SHA及provenance复核，不覆盖历史结果。

真实API沿用deepseek-v4-flash、Ark Agent Plan和Nomic快照，53目标×三策略、最多159正式＋2冒烟、零自动重试，每请求最多16384完成token。代码／JAR／配置／HEAD冻结后执行；单次采集不能评价尚未被模型消费的焦点或模板因素，金额及精确token公平缺依据时保留null／UNVERIFIED。

</details>

返回 [唯一文档地图](../../../PROJECT.md)。
