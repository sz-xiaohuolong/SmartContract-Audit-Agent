# 交给另一 Codex 任务的实施提示词

请在本地项目 /Users/daiyifei/Documents/code/SmartContract-agent 实施 R1-S3 的**首个可验收切片**。直接在当前目录开发，保留全部未提交改动，不新建 worktree，不提交或推送。所有回复、文档和新增注释使用简体中文。

先读 AGENTS.md、docs/vibe/PROJECT.md、docs/vibe/PROGRESS.md、docs/vibe/releases/R1-S2/{SPEC,DESIGN,VERIFICATION}.md、docs/vibe/releases/R1-S3/{SPEC,DESIGN,IMPLEMENTATION_PLAN}.md、thesis/D1_D2第二轮查新与立题裁决_20260924.md，并检查现有 tools/experiment、audit-mvp 与数据。按本仓库 vibe-workflow 恢复项目状态后实施。用户已授权工程调整；不必重复询问实施许可。

本任务的首要交付是**数据来源、谱系隔离与 D1 离线证伪流水线**，不是宣称 D1/D2 创新已成立。先核对 SCRUBD 重入、SmartBugs Curated 知识、ASE 2025 AC 基准及 ACFix 样本的公开性、许可证、源码版本、原始报告/补丁和标签；无法核实的来源记录待审，不制造安全负例。建立原始/衍生材料 provenance、项目/事件/补丁/完全重复/近克隆关联组与 knowledge/development/validation/locked-test 泄漏阻断。不得把现有旧知识库与测试答案混用。设计可人工复核的目标—案例适用性、支持/反证价值和 UNKNOWN 标签格式；真实、人工改造与合成样本分别记录。

复用 S2 同候选池四策略，增加“简单条件字段过滤”强基线，保证比较时同 pool、同知识快照、同完整下游提示 token 上限；现有 UTF-8 字节预算不可冒充 token 公平。先做完全离线的适用性 Recall@K/nDCG、错误案例入选、互补证据覆盖及逐样本错误分析，加入目标绑定和互补选择消融。没有经过审查的真实标签时只交付可信流水线与阻塞说明，不报告虚构效果。D2 仅建立固定真假候选及 guard 存在/具体防护行等基线数据契约，不做完整多智能体或深度符号执行。

遵守 Java 21、Spring Boot 4.1.1、Spring AI 2.0.1、Python 离线工具契约；离线测试不得需要真实 API、Milvus 或工具环境。异常、超时、解析错误、证据不足不能映射为安全，usage 缺失保留 null。未经显式真实运行选择，不调用火山付费 API。若后续建议小批 deepseek-v4.1-flash 实验，先提交模型/端点/样本×策略×重复×调用次数/token/重试上界 dry-run；Agent Plan Small 于 2026-10-18 23:59 到期，但套餐额度要实测。

先实现最小数据/检索先导并完成对应测试，运行 mvn clean verify 与 PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v。更新 R1-S3 VERIFICATION.md、docs/vibe/PROGRESS.md 与必要的操作文档，给出可重放命令、样本谱系、泄漏报告、逐样本原始结果、失败/unknown 分母、与强基线的负/正结果及下一门禁建议。若数据许可或可靠标签不足，请把真正完成的工程部分交付并明确阻塞，不扩大为未经验证的“研究创新”。不得打开锁定测试集调参。
