# 真实 API 批量实验报告（2026-10-10）

状态：**已结束**；批次 `546fe566368e4b0ea7b6aeb58b235939`。

已落盘 159/159 个单元，模型有效判断 159 个，模型失败 0 个；流水线完成 12 个、失败 147 个。D2 支持／反驳／未知为 0／0／159。

本批共同目标上 D1 的 F1 比最强基线低 0.0115，未观察到 D1 的净改进。

## 批次与配置

| 项目 | 记录 |
| --- | --- |
| 开始时间 | 2026-10-10 13:51:11（北京时间） |
| 结束时间 | 2026-10-10 14:06:45（北京时间） |
| 墙钟时长 | 15.57 分钟 |
| 目标与策略 | 53 个目标（漏洞标签 49，安全函数对照 4）× DENSE／FIELD_FILTER／D1 |
| 标签来源 | 49 个 SMARTBUGS_CURATED_HEADER；4 个 LEGACY_SAFE_CONTRACTS，本轮未另做独立真值标注 |
| 模型 | deepseek-v4-flash |
| 端点 | https://ark.cn-beijing.volces.com/api/plan/v3 |
| 输出设置 | 每次最多 2048 token；显式思考关闭；JSON Schema；配置超时 60 秒 |
| 检索 | 本机 Nomic 768 维，有效窗口 2048 token；同目标共用候选池；上下文最多 4096 字节 |
| 嵌入模型摘要 | 0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f |
| 知识 | 自动标注的 300 组／600 向量；未逐案核验 |
| 快照 | a6d70058bb93a26505def7878553d01e7667248d387f41a101a4ff2f71bd36db |
| 计划摘要 | b34fa1ed88eb6fa896450e9a3ae7f2368dd29436f02a8e9e3c8776d96794a147 |
| 流水线版本 | s9-v1 |
| 提交基点 | 4dfc7e19584af8840c3cde5402dac9ee2533f31c |
| 构建产物 SHA-256 | 7471ad8373abad68888d838cfa83d0ad66f20cae7c59f7149e41dd23d15c2fad |
| 本轮请求边界 | 159 个单元；瞬时限流／断连最多重试一次；总请求上限 318；总输出 token 上限 651264 |
| 实际请求尝试 | 已记录 159 次；0 个单元缺少请求次数 |
| 完整 usage 记录 | 159/159 个已落盘单元 |
| 候选池冲突 | 0 |

批次经用户明确授权后启动一次，未更换端点、重建知识、改动源码或重试历史批次。原有未提交修改保留；实际运行产物由上述 JAR 摘要固定。

## 模型标签对照

此表评价模型“报告漏洞／未报告漏洞”，使用原数据集标签。工具失败另列，模型指标不代表 D2 验证成功。模型失败及未知不并入 TN。

| 策略 | 模型完成 | 模型失败 | 模型未知 | TP | FP | FN | TN | 精确率 | 召回率 | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DENSE | 53 | 0 | 0 | 44 | 0 | 5 | 4 | 1.0000 | 0.8980 | 0.9462 |
| FIELD_FILTER | 53 | 0 | 0 | 44 | 1 | 5 | 3 | 0.9778 | 0.8980 | 0.9362 |
| D1 | 53 | 0 | 0 | 43 | 0 | 6 | 4 | 1.0000 | 0.8776 | 0.9348 |

三策略共同有效目标数：53。对照表使用相同目标分母：

| 策略 | 共同目标 | TP | FP | FN | TN | 精确率 | 召回率 | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DENSE | 53 | 44 | 0 | 5 | 4 | 1.0000 | 0.8980 | 0.9462 |
| FIELD_FILTER | 53 | 44 | 1 | 5 | 3 | 0.9778 | 0.8980 | 0.9362 |
| D1 | 53 | 43 | 0 | 6 | 4 | 1.0000 | 0.8776 | 0.9348 |

按类别展开：访问控制包含 18 个漏洞目标与 4 个安全函数对照；重入包含 31 个漏洞目标。

| 类别 | 策略 | 有效目标 | TP | FP | FN | TN | 漏洞召回率 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 访问控制 | DENSE | 22 | 15 | 0 | 3 | 4 | 0.8333 |
| 访问控制 | FIELD_FILTER | 22 | 15 | 1 | 3 | 3 | 0.8333 |
| 访问控制 | D1 | 22 | 14 | 0 | 4 | 4 | 0.7778 |
| 重入 | DENSE | 31 | 29 | 0 | 2 | 0 | 0.9355 |
| 重入 | FIELD_FILTER | 31 | 29 | 0 | 2 | 0 | 0.9355 |
| 重入 | D1 | 31 | 29 | 0 | 2 | 0 | 0.9355 |

## 工具与 D2

| 策略 | 流水线失败 | D2 支持 | D2 反驳 | D2 未知 | D2 未运行 |
| --- | --- | --- | --- | --- | --- |
| DENSE | 49 | 0 | 0 | 53 | 0 |
| FIELD_FILTER | 49 | 0 | 0 | 53 | 0 |
| D1 | 49 | 0 | 0 | 53 | 0 |

| Slither 状态 | 单元数 |
| --- | --- |
| OK | 12 |
| PROCESS_ERROR | 147 |

默认 Slither 版本为 0.11.3，默认 solc 为 0.8.30。49 个漏洞目标的编译约束属于 0.4.x／0.5.x；首个 FibonacciBalance 样本的独立 solc 诊断已明确返回编译版本不兼容。其余工具错误按保存的分类汇总；本轮没有逐条 stderr，不能把所有进程错误都当作已逐条核验同一原因。未切换或安装编译器，未重跑付费模型。

另对兼容 0.8.x 的最小合约执行了一次零付费 Slither 检查，工具返回 success=true；工具本身可以在匹配的编译环境下运行。诊断原件保存在本批目录。

程序事实提取状态按唯一目标统计；PARTIAL 或 FAILED 会限制路径证明与 D2 裁决：

| 程序事实状态 | 唯一目标数 |
| --- | --- |
| COMPLETE | 1 |
| FAILED | 2 |
| PARTIAL | 50 |

D2 共评估 172 条模型假设；无假设时仍保持 D2 未知。下表的单位是“假设中的义务”，不是合约数。义务支持表示保护义务已获证据支持，不能直接读成漏洞支持。

| 保护义务 | SUPPORTED | REFUTED | UNKNOWN |
| --- | --- | --- | --- |
| actor | 0 | 4 | 168 |
| resource | 4 | 0 | 168 |
| pre_risk_guard | 0 | 4 | 168 |
| entry_coverage | 0 | 0 | 172 |
| state_version | 0 | 0 | 172 |
| bypass | 0 | 0 | 172 |

| D2 说明 | 假设数 |
| --- | --- |
| 六项保护义务未获完整证明时不得推断安全 | 95 |
| 合约、函数、风险行与操作无法唯一绑定事实 | 48 |
| 机制或风险操作未明确绑定已支持的类别 | 25 |
| 程序证据保留；路径、六项覆盖或绑定工具证据不足，最终未知 | 4 |

| 路径证据状态 | 假设数 |
| --- | --- |
| UNKNOWN | 172 |

| 最终结论 | 单元数 |
| --- | --- |
| NO_CONFIRMED_FINDINGS | 11 |
| UNRESOLVED | 148 |

被严格校验拒绝的附加假设：2 条。D2 反驳仅针对绑定假设；未报告、未知或工具错误均不构成全合约安全结论。

## 用量与耗时

| 策略 | 请求尝试 | 已知输入 token | 已知输出 token | 平均模型耗时 ms | 中位模型耗时 ms | P90 模型耗时 ms | 平均流水线耗时 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DENSE | 53 | 96067 | 9284 | 5024 | 4743 | 7991 | 6301 |
| FIELD_FILTER | 53 | 98493 | 9774 | 4995 | 4600 | 7352 | 5603 |
| D1 | 53 | 81092 | 9820 | 5027 | 4784 | 7322 | 5642 |

Token 汇总只覆盖供应商实际返回且已保存的 usage；重试前未返回 usage 的请求不计入此表。缺失值在原数据中保留 null，不补零。平均耗时包含模型调用适配过程；4096 字节预算不等于相等 token。

## 失败与模型误判

| 错误类别 | 单元数 |
| --- | --- |
| TOOLS_FAILED | 147 |

以下列出全部模型失败和与数据集标签不一致的模型判断；完整工具与 D2 证据见 JSONL。

| 目标 | 策略 | 数据集标签 | 模型判断 | 最终结论 | 错误类别 |
| --- | --- | --- | --- | --- | --- |
| access_control__dataset_access_control_FibonacciBalance__4b0dfd1088 | D1 | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_arbitrary_location_write_simple__4a0a499d22 | FIELD_FILTER | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_arbitrary_location_write_simple__4a0a499d22 | D1 | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_incorrect_constructor_name1__539cfe0360 | DENSE | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_mapping_write__487bf4968d | FIELD_FILTER | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_mycontract__409e3a2d57 | D1 | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_parity_wallet_bug_2__afba3ec7a5 | DENSE | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_phishable__32d30f14ab | D1 | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_unprotected0__fbc3cd8ad4 | DENSE | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| access_control__dataset_access_control_wallet_04_confused_sign__d538a9f685 | FIELD_FILTER | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| reentrancy__dataset_reentrancy_0xf015c35649c82f5467c9c74b7f28ee67665aad68__afcb83e7c0 | D1 | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| reentrancy__dataset_reentrancy_modifier_reentrancy__d36451620c | DENSE | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| reentrancy__dataset_reentrancy_reentrancy_bonus__1d476a6db0 | D1 | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| reentrancy__dataset_reentrancy_reentrancy_dao__4c02510f60 | FIELD_FILTER | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| reentrancy__dataset_reentrancy_spank_chain_payment__e2fd45cab2 | DENSE | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| reentrancy__dataset_reentrancy_spank_chain_payment__e2fd45cab2 | FIELD_FILTER | 漏洞 | NO_REPORT | UNRESOLVED | TOOLS_FAILED |
| safe_23_Ownable | FIELD_FILTER | 安全函数对照 | REPORT | UNRESOLVED | 无 |

## 解释边界与后续

本轮为公开数据集标签下的探索实验，researchEligible=false。安全对照只有四个函数，且与完整合约目标的输入范围不同；知识仍为自动标注，缺少逐案例适用性审核和独立 D2 真值。因此不能报告正式的 D2 准确率、合约安全率或方法创新成立，也不能用历史批次差异归因于单一算法变化。

下一步应固定与目标 pragma 匹配的工具编译环境，先做零付费工具验证；再对保存的模型假设开展独立人工核验和注明来源的派生裁决，保留本轮原始结果。

## 报告与原始数据

- [本机实验页面](http://127.0.0.1:8771/agent.html)：在自动知识批量历史中选择 `546fe566`。
- [批次 JSON 报告](http://127.0.0.1:8771/api/agent/auto-benchmark/runs/546fe566368e4b0ea7b6aeb58b235939)。
- [下载逐项 JSONL](http://127.0.0.1:8771/api/agent/auto-benchmark/runs/546fe566368e4b0ea7b6aeb58b235939/samples.jsonl)。
- [下载逐项 CSV](http://127.0.0.1:8771/api/agent/auto-benchmark/runs/546fe566368e4b0ea7b6aeb58b235939/samples.csv)。
- 本机目录：`.local/auto-benchmark-runs/546fe566368e4b0ea7b6aeb58b235939/`，保存计划、事件、模型／工具／D2、执行与目标清单、诊断、汇总和此报告。
- 历史报告保持原样；本报告直接重放本批落盘结果，没有追加模型请求。

仅重新生成汇总与中文报告（零模型请求）：

```bash
PYTHONPATH=tools/experiment .local/d1-embed-venv/bin/python .local/auto-benchmark-runs/546fe566368e4b0ea7b6aeb58b235939/finalize_report.py
```
