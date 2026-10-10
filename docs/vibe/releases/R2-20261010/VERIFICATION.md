# D1/D2 毕设工程统一验收矩阵

| 当前事实 | 状态 |
|---|---|
| R2-20261010 | 整体验证 UNVERIFIED；S10 局部工程验收已取得真实重放和浏览器证据，S11 接续 |
| 研究效果 | UNVERIFIED；新增模型请求预算 0 |
| 证据入口 | `.evidence/R2-20261010/`；历史证据仍按 PROJECT 导航 |

基线：[SPEC](SPEC.md)；任务：[统一计划](IMPLEMENTATION_PLAN.md)。历史 S9 的局部验证保留在原文件，不扩展为本轮完成证据。

| REQ | 本轮证据 | 结果与缺口 |
|---|---|---|
| 01 输入 | 输入清理、原件摘要及行号回归；真实 Chromium 粘贴、预览、离线运行和下载 | S10 输入局部 VERIFIED；S11 事实与 S12 展示接续 |
| 02 工具环境与53目标 | 53 环境预检；53 次真实 Slither，51 成功、2 失败；逐目标固定版本/二进制/参数/退出/耗时/诊断 | VERIFIED（工具运行与失败处理）；失败不能当安全 |
| 03 真值隔离 | 模型与检索消费清理输入；发现与给定候选分开；真值变异、字符串保护及来源回归 | VERIFIED（工程）；历史模型输出仍有污染限制 |
| 04 D1离线/预算方案 | 53 目标保存池同池核对、600 文档对账、零模型离线报告；正式方案 PREPARATION | PARTIAL；独立标签与完整提示 token 预算未冻结 |
| 05 假设绑定 | 历史 S9 有夹具；本轮待重验 | UNVERIFIED |
| 06 编译事实 | 待实现/真实验证 | UNVERIFIED |
| 07 D2真实正反 | 历史172假设路径未知；待补齐 | UNVERIFIED |
| 08 派生重放 | 159 单元、53 目标、172 假设零模型重放；原件全文件和代码/JAR 摘要封口复核 | S10 CLI VERIFIED；S12 派生 HTTP／页面展示待验收 |
| 09 真实先导与四基线 | 原件盘点中，独立审核尚缺 | UNVERIFIED |
| 10 工作台 | 待真实浏览器验收 | UNVERIFIED |
| 11 毕设材料 | 待从保存结果生成 | UNVERIFIED |
| 12 验证/提交同步 | S10 独立评审无阻断；新鲜 Maven 88 项、Python 333 项和 CLI 通过，无跳过；真实 Chromium 无控制台错误 | S10 提交同步待执行；整体 UNVERIFIED |

## S10 局部工程验收

真实原件与日志位于 `.evidence/R2-20261010/S10-acceptance/`，浏览器证据位于 `.evidence/R2-20261010/S10-browser/`；均为本机原始证据，默认 Git 忽略。恢复 diff 和初始源码摘要随验收记录保存，不覆盖启动时的无关修改。

| 项目 | 新鲜结果与证据 |
|---|---|
| 独立审查 | `review` 与 `deslop-shared-libs` 的规格、代码和消肿检查无阻断；报告 `review.md` |
| 根构建与 CLI | `maven-clean-verify.log`：Java 88 项通过，无跳过；`cli-help.log`：退出 0 |
| Python 离线 | `python-full.log`：333 项通过，无失败或跳过；测试不依赖真实模型、Milvus 或外部工具 |
| 历史派生重放 | `historical-derived/manifest.json` 已 COMPLETED；159/159 单元，53 次工具执行，172 条原候选，新增模型请求 0 |
| 工具结果 | 唯一目标 51 OK、2 PROCESS_ERROR；三策略单元 153 OK、6 PROCESS_ERROR。原批次仅 12 OK、147 PROCESS_ERROR |
| D2 与事实 | 159 单元 UNKNOWN，172 条路径 UNKNOWN；唯一目标事实 50 PARTIAL、1 COMPLETE、2 FAILED。工具修复不自动补足路径证明 |
| 两个剩余失败 | `reentrancy_bonus` 与 `reentrancy_cross_function`：固定 solc 0.4.26 实际编译退出 0，旧 tuple 赋值有警告；Slither 0.11.3 的 IR 转换在 `TupleVariable` 断言失败。直接库调用 trace 与独立 solc 诊断保存到 `failure-diagnostics/`，未修改原源码或伪造告警 |
| 浏览器 | 本机 `8776/workbench.html`，Nomic 固定快照；注释答案被清理，行号保留，源码注入仅为文本；离线演练、下载 JSONL、历史只读通过；控制台错误 0，390px 无水平溢出 |

重算入口：先执行根 `mvn clean verify`，再执行
`PYTHONPATH=tools/experiment python3 tools/experiment/tool_replay.py --original-run .local/auto-benchmark-runs/546fe566368e4b0ea7b6aeb58b235939 --output-run .evidence/R2-20261010/S10-acceptance/新的派生目录`。
必须使用新输出目录，并备齐原批次、固定编译器及本机工具配置。重放只评价保存候选核验，不代表清理输入后的模型发现实验；研究效果仍 UNVERIFIED。

## 完成审计规则

逐项检查当前源码、适用自动测试、真实程序及浏览器证据；没有支持某项的证据时保持未验证。指标由保存结果重算。UNKNOWN、故障与标签缺失单列分母。没有独立审核或新模型实验时，不把工程完成改写为方法已验证。
