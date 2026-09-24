# 本轮调查与文档验证记录 — R0-20260918

## 控制

- 时间：2026-09-18，Asia/Shanghai。
- 交付范围：源码调查和待审核文档。
- Requirement Status：`DRAFT`；Effective SPEC：尚未建立。
- Release Verification Status：`UNVERIFIED`；Shipping Authorization：`NOT_REQUESTED`。
- 文档核查与软件 Release 验证分开：文档完整不能将未实现需求标记通过。

## 实际执行的检查

| 检查 | 结果 | 证据与范围 |
|---|---|---|
| Git 当前分支与基点 | main / 66161d5b74a6df980425f37c913e63591d246d2a | [源码清单](review-evidence/source-manifest.json)；不代表此提交运行稳定 |
| 核心源码与调用入口审查 | 完成静态调查 | [TECH_DESIGN](../../TECH_DESIGN.md) 22 项记录；非主线演示类未逐项安全审计 |
| 数据数量与字节重复检查 | 400 文件、393 唯一字节哈希、7 重复组 | [数据清单](review-evidence/data-inventory.json) |
| KB/测试完全匹配检查 | 143 KB 代码块提取；首尾空白标准化后相同项为 0 | 只限精确匹配；近似克隆和项目污染仍未验证 |
| Java/Maven 环境检查 | java 命令为 21.0.8；Maven 实际 JDK 为 23.0.2 | [环境记录](review-evidence/environment.txt)；编译目标仍为 21 |
| `mvn -o -DskipTests test-compile` | exit 0，BUILD SUCCESS；本地 protobuf POM 警告 | [原始日志](review-evidence/offline-test-compile.log)；主类为增量 up-to-date，测试类编译 8 个；未运行测试 |
| 源码与 pom 是否被改动 | 按 SHA-256 对照初始 manifest | [文档检查](review-evidence/document-check.json)；数据另以只读检查为限 |
| 文档路径、需求与 AC 唯一性、需求在阶段建议中的覆盖 | 自动检查和主 Agent 自审 | [文档检查](review-evidence/document-check.json)；不能替代用户决定或独立科研审查 |
| diff 边界 | 原有 `.gitignore` 修改仍保留，新增 docs/vibe | 未提交、未推送；未将本地凭证写入文档 |

## 需求验证矩阵

所有需求的实施验证均未开始。下表的阶段是未来计划，不是通过证据。

| REQ | AC | 计划验证阶段 | 实际结果 |
|---|---|---|---|
| REQ-01 | AC-01 | S0 状态夹具 | UNVERIFIED |
| REQ-02 | AC-02 | S1 标识与快照 | UNVERIFIED |
| REQ-03 | AC-03 | S0 断网测试 | UNVERIFIED |
| REQ-04 | AC-04 | S0 进程夹具 | UNVERIFIED |
| REQ-05 | AC-05 | S1 半构建恢复 | UNVERIFIED |
| REQ-06 | AC-06 | S2 条件配对 | UNVERIFIED |
| REQ-07 | AC-07 | S2/S3 实例引用 | UNVERIFIED |
| REQ-08 | AC-08 | S3 裁决表 | UNVERIFIED |
| REQ-09 | AC-09 | S3 预算及停止 | UNVERIFIED |
| REQ-10 | AC-10 | S1/S4 恢复重放 | UNVERIFIED |
| REQ-11 | AC-11 | S1 跨组阻断 | UNVERIFIED |
| REQ-12 | AC-12 | S1/S4 指标算例 | UNVERIFIED |
| REQ-13 | AC-13 | S2/S3/S4 消融 | UNVERIFIED |
| REQ-14 | AC-14 | S0 模型故障注入 | UNVERIFIED |
| REQ-15 | AC-15 | S0/S4 引用与日志 | UNVERIFIED |
| REQ-16 | AC-16 | S0/S4 旧新口径 | UNVERIFIED |

## 尚未验证事项

真实 Slither/Mythril 版本与编译覆盖、挂起进程动态复现、云模型额度/限流和 model ID、Milvus 当前数据、近似克隆与谱系隔离、真实负例标注、D1/D2 方法效果，全部不能写为已验证。

不执行 `mvn test` 的原因是当前测试入口可能触发全 Spring 装配、知识导入和付费调用；本轮任务仅是方案调查。该决定不是测试通过的替代证据。

## 交付结论

本轮提交的是可审核方案包。不是功能完成、不是需求冻结、不是 READY_TO_SHIP。两项并行只读任务因服务限额未完成，本轮仅有主 Agent 源码调查与自审证据，不声称独立审查通过。
