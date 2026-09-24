# S1a 验证记录

日期：2026-09-20。S1a 本地验收通过；S1b 尚未实现；没有研究性能结果。

- Python 测试：`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`，7 项通过。见 [日志](evidence/unittest.log)。初次缺模块红测后实现，宏平均问题另有失败回归后修复。
- Maven 回归：`mvn clean verify`，19 项通过，无失败或跳过；见 [日志](../R1-S0/evidence/maven-clean-verify.log)。Python 测试需要单独执行，不声称 Maven 包含它们。
- 实际执行 inventory：400 个样本，7 组完全重复，共 14 个成员。见 [待审核清单](evidence/legacy-inventory.json)。所有 labels / split / project_group 保留 null，未改原文件。
- 独立审查：只读审查并独立运行初始 6 项测试；指出 macro_f1 忽略未定义类别会改变分母。已添加“部分类别无定义”回归，先失败后通过。
- 修正后的 macro_f1 对预定义类别整体计算，任一类别无定义则整体 null；条件平均单独命名 macro_f1_defined_only，不能混用作跨方法主指标。

## 限制

字节重复不是近似克隆或项目级治理。清单不构成正式划分；没有把未经审核的目录标签用于计分。S0 自然语言类型尚未映射到规范类型，未实现实例级定位匹配、知识快照激活、阶段日志、checkpoint/resume/replay 或正式实验运行器。这些仍属于 S1b。

## S1b 本地验收（2026-09-21）

范围：本轮已授权的知识快照、隔离检查、持久记录与恢复工程行为。Verification Status：`VERIFIED`（离线工程范围）；Shipping Authorization：`NOT_REQUESTED`。不代表真实实验或研究数据已验收。

环境：主目录 `/Users/daiyifei/Documents/code/SmartContract-agent`；分支 `main`；基点 `66161d5b74a6df980425f37c913e63591d246d2a`，未提交。Python 3.14.7，Corretto Java 21.0.8。代码版本绑定见 [S1b 产物摘要](evidence/s1b-artifact-hashes.json)。

| 验收行为 | 验证证据 | 结果 |
|---|---|---|
| 逐个样本 START/RESULT 持久化、自动跳过已有结果 | `test_restart_skips_completed_and_replay_is_read_only`、CLI run/resume 子进程计数 | 通过 |
| 调用中断或 RESULT 落盘失败后不自动重复调用 | `test_interrupted_call_is_unresolved_and_only_unstarted_is_called`、`test_result_write_interruption_does_not_repeat_paid_call` | 通过；不确定项需显式 retry-id |
| 尾部残行可恢复，完整行损坏与重复事件拒绝 | `test_partial_tail_recovered_but_replay_does_not_truncate`、`test_full_line_corruption_and_duplicate_event_rejected` | 通过 |
| 单写者、落盘失败时不发起调用 | `test_concurrent_writer_rejected`、`test_fsync_failure_before_start_prevents_external_call` | 通过 |
| 源码/配置/产物/类型映射/知识快照绑定 | binding、source drift、bound snapshot、冻结 JAR/配置测试 | 通过 |
| Replay 只读、失败不能当安全、usage 缺失为 null | replay、failed negative、unknown type、usage 回归及原 S1a 测试 | 通过 |
| 完整知识快照构建与原子发布/激活 | 构建中断、摘要篡改、维度/非有限向量、旧指针保留测试 | 通过 |
| Milvus 半集合不能激活，全部分页读回核对 | 缺项、错误向量、重复 ID、多页末项篡改测试 | 离线客户端契约通过；未连接真实 Milvus |
| 测试与检索库同组隔离 | 字节/项目/克隆跨划分，缺审核来源，知识文档引用测试样本拒绝 | 通过；不替代人工谱系审核 |

实际执行：

- `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`：**35 项通过，0 失败**；[完整日志](evidence/s1b-unittest.log)。其中原 S1a 7 项保留。
- `mvn clean verify`：**19 项通过，0 失败/错误/跳过，BUILD SUCCESS**；[完整日志](evidence/s1b-maven-clean-verify.log)。
- Java CLI 帮助与 S1b CLI 帮助：退出码均为 0；[Java](evidence/s1b-java-help.log)、[S1b](evidence/s1b-cli-help.log)。
- `git diff --check` 及本轮未跟踪文本文件的逐文件空白检查：通过；[检查摘要](evidence/s1b-workspace-check.json)。
- 按 `requesting-code-review` 完成只读独立复审；初次 30 项、增量 32 项通过，均无阻断问题。其后补齐 3 项边界测试，最终主流程全套 35 项通过。见 [复审记录](S1B_REVIEW.md)。

限制：未调用真实模型、embedding、Milvus 或真实漏洞工具；Milvus 适配器只验证注入客户端的契约行为，真实 SDK/服务兼容性未验证。文件原子重命名与 fsync 在本地 macOS 文件系统验收；网络文件系统及 Windows 未验收。旧 legacy RAG 启动导入未接入新快照。实际数据的项目谱系、克隆关联、标签和正式划分仍待审核，本轮不输出正式研究成绩。
