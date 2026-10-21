# VeriRAG：可复核的智能合约审计研究系统

VeriRAG 让大模型先提出漏洞猜想，再由程序分析和有限的本机执行检查依据。D1 提供漏洞与修复的对照参考，D2 围绕调用者、资产、检查顺序和相关路径逐项核验，报告给出支持、反驳或未知。

截至 **2026-10-21**，项目已进入 **phase 5：对照查询与证据区分度重排**，离线设施和一次真实模型比较已完成。本机工作台、结构化模型网关、固定候选重放及有限核验能够运行；权限事实提示、机制卡片和新排序仍通过显式研究入口使用。工程部分完成，研究增益尚未验证：phase 3、phase 4 与 phase 5 的探索均未观察到分类增益，真实维护者修复前后仍未形成完整正反证据。

从 [项目总览与唯一文档地图](docs/vibe/PROJECT.md) 开始。该页提供 5 分钟概览和 15 分钟阅读路线，继续连接方法、实现、实验及论文材料。当前事实见[进度](docs/vibe/PROGRESS.md)，最新阶段的实施和限制见[phase 5 验收](docs/vibe/releases/phase5-20261021/VERIFICATION.md)。

## 构建与离线演示

在仓库根目录执行：

```bash
mvn clean verify
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
```

默认模块为 `audit-mvp`，使用 Java 21、Spring Boot 4.1.1 依赖体系与 Spring AI 2.0.1。命令行不启动 Spring 容器；Python 提供本机网页并编排分析。默认测试使用本机 HTTP 与子进程夹具，不要求真实模型或 Milvus；首次构建需要下载 Maven 依赖。

[快速上手](docs/vibe/releases/R2-20261010/attachments/GETTING_STARTED.md) 提供三条启动命令、合成演示和 SimpleDAO 离线核验。合成演示读取夹具；离线核验使用保存候选；真实模型模式会向显式选择的供应商发送源码。这三种模式验证的内容不同。

## 开发与研究资料

- [技术设计](docs/vibe/TECH_DESIGN.md)：Java/Python 分工、默认流程、研究开关及证明边界。
- [实验总览](docs/vibe/releases/R2-20261010/attachments/EXPERIMENT_DASHBOARD.md)：按批次分开呈现模型 F1、候选覆盖、执行失败和真实修复结果。
- [数据入口](data/README.md)：直接使用根目录 `smartbugs-curated/`、`SolidiFI-benchmark/`，额外对照在 `data/controls/openzeppelin/`，版本与摘要由 `data/datasets.json` 登记。
- [离线工具说明](tools/experiment/README.md)：命令、输入与统计重放；Python 测试命令为 `PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`。
- [运行与复现规范](docs/vibe/releases/R2-20261010/attachments/OPERATIONS_AND_REPRODUCIBILITY.md)：凭证、调用范围、证据身份及本机原件恢复。

论文材料沿用 `thesis/` 本机保存约定，可用入口和缺失材料由唯一文档地图说明。已有查新裁决尚未冻结两个独立创新点，不能把工程接入直接写成方法有效或首创。

旧 Java 应用与独立构建已退役，历史代码可从迁移前提交 `4ba5750` 恢复；当前实现以技术设计和源码为准。
