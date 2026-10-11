# D1/D2 毕设工程统一验收矩阵

| 当前事实 | 状态 |
|---|---|
| R2-20261010 | 整体验证 UNVERIFIED；S10 局部工程完成，S11 绑定事实与有限路径工程接入局部 VERIFIED，真实整体正反仍未验收 |
| 研究效果 | UNVERIFIED；新增模型请求预算 0 |
| 证据入口 | `.evidence/R2-20261010/`；历史证据仍按 PROJECT 导航 |

基线：[SPEC](SPEC.md)；任务：[统一计划](IMPLEMENTATION_PLAN.md)。历史 S9 的局部验证保留在原文件，不扩展为本轮完成证据。

| REQ | 本轮证据 | 结果与缺口 |
|---|---|---|
| 01 输入 | 输入清理、原件摘要及行号回归；真实 Chromium 粘贴、预览、离线运行和下载 | S10 输入局部 VERIFIED；S11 事实与 S12 展示接续 |
| 02 工具环境与53目标 | 53 环境预检；53 次真实 Slither，51 成功、2 失败；逐目标固定版本/二进制/参数/退出/耗时/诊断 | VERIFIED（工具运行与失败处理）；失败不能当安全 |
| 03 真值隔离 | 模型与检索消费清理输入；发现与给定候选分开；真值变异、字符串保护及来源回归 | VERIFIED（工程）；历史模型输出仍有污染限制 |
| 04 D1离线/预算方案 | 53 目标保存池同池核对、600 文档对账、零模型离线报告；正式方案 PREPARATION | PARTIAL；独立标签与完整提示 token 预算未冻结 |
| 05 假设绑定 | Java schemaVersion=2 回归与 loopback 网关通过；位置、机制、源码和完整函数签名错绑拒绝，usage=null 保留 | VERIFIED（工程绑定）；编译证据完整性由 06／07 单列 |
| 06 编译事实 | 六环境真实 standard-json 逐字节重编译对照；声明、UTF-8 跨度、完整源码闭包与 ABI 入口绑定 | PARTIAL；绑定事实已有本机证据，构造／初始化及全入口语义尚未完整证明 |
| 07 D2真实正反 | 六环境九固定候选的类型化 CFG；权限／锁版本局部差异及更早 CALL 显式保存 | PARTIAL（局部静态证据）；全部整候选 UNKNOWN，真实正反验收 UNVERIFIED |
| 08 派生重放 | 159 单元、53 目标、172 假设零模型重放；原件全文件和代码/JAR 摘要封口复核 | S10 CLI VERIFIED；S12 派生 HTTP／页面展示待验收 |
| 09 真实先导与四基线 | 原件盘点中，独立审核尚缺 | UNVERIFIED |
| 10 工作台 | Apple 工作台已有实际 Chromium 验收；显式登记的编译清单贯通预览、执行、导出与只读回放，离线编译夹具 Chromium 通过 | PARTIAL；完整真实路径与派生页面交付由 S12 接续 |
| 11 毕设材料 | 待从保存结果生成 | UNVERIFIED |
| 12 验证/提交同步 | S10 `dd7eb97` 已同步；S11 PASS-003 无阻断，新鲜 Maven 88 项、Python 397 项和 CLI 通过，无跳过；编译接缝 Chromium 控制台错误 0；同步身份见下方记录 | S10 与 S11 本机工程接入局部 VERIFIED；整体 UNVERIFIED |

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

S10 提交为 `dd7eb97`，已按精确文件范围检查凭证并同步 `origin/main`。执行期间另外出现的页面改动及启动时的无关修改均留在工作区，未纳入本提交；被测生产源码摘要与该提交逐项核对一致。

## Apple 工作台界面局部验收

本次只完成用户指定的四个工作台实现文件及其接口回归；S11 事实提供器、派生报告接入和研究效果仍按原矩阵追踪。原始证据 `.evidence/R2-20261010/apple-workspace/` 默认 Git 忽略。

| 检查 | 观察结果与证据 |
|---|---|
| 视觉与依赖 | 用户给定的 Apple 令牌、系统字体、浅色三栏布局、响应式与打印样式；运行不需要 Node/npm 构建 |
| 完整 JSON | 新增 `/api/agent/workspace`、`/target`、`/simulation`、`/runs` 及单记录接口；预览补齐源码、六义务、阶段与统计，保留旧调用方兼容 |
| 语义边界 | 工具失败保持未决；usage 与费用缺失为 null；模拟明确为合成夹具且 D2 未执行；历史按保存的策略与运行模式展示 |
| Python | 当前共享工作区 352 项通过；本次新增接口回归 5 项；`python-final.log`。首轮其他任务模块未生成的错误保留在 `python.log` |
| Maven / CLI | `maven.log`：88 项通过；`cli.log`：帮助命令退出 0 |
| 实际 Chromium | 本机注入运行夹具：预览、显式离线运行、六义务、原始行号定位、策略变更使计划失效、历史回放不重发、源码字符串注入仅为文本；`browser-check.js` 与日志 |
| 下载 | `export.json` 包含完整证据且 token 为 null；`report.pdf` 由浏览器打印样式生成 |
| 响应式 | 1440px、834px、390px 截图；修复移动分段控件隐藏输入定位后，三个宽度均无页面水平溢出；`responsive-check.log` |
| 模型请求 | 新增真实模型请求 0；模拟不调用模型、工具或外部检索服务；真实运行仍需固定计划与明确选择 |

启动：`PYTHONPATH=tools/experiment python3 tools/experiment/local_ui.py --port 8765`，打开 `http://127.0.0.1:8765/agent.html`。点击「运行模拟」即可在没有知识服务时体验布局；真实审计使用现有已配置模型，必须先预览并勾选明确选择。PDF 按钮打开浏览器打印，可选择保存为 PDF。

## S11 绑定事实与有限路径接入

2026-10-11 本轮绑定事实与有限路径的本机工程接入为 VERIFIED，整个 S11 仍为 IN_PROGRESS、真实整体正反验收 UNVERIFIED。原始证据为 `.evidence/R2-20261010/S11-facts/`、`S11-paths/`、`S11-integration/`、`S11-review/`；原件与二进制只在本机备齐，不宣称已可跨机器取回。本轮新增模型请求为 0。

| 范围 | 观察证据与限制 |
|---|---|
| 编译真实性 | 六组原 standard-json 输入用收据固定 solc 重编译，原始 stdout 字节、全部 AST、ABI、字节码及警告完全相同；`S11-facts/recompile/REPORT.md`。提供器每次再次对照，编译失败、超时、二进制漂移或重封的不同输出均拒绝 |
| 声明与入口 | Atomic 三组各 50 ABI 入口（11 getter），Rabbit 三组各 35（7 getter）；全部唯一匹配，entryGaps 为空；结构事实保持 PARTIAL，入口存在不等于相关语义覆盖完整 |
| Rabbit 局部 | audited／before 裸 `msg.sender` 比较不生成 CHECK；after 的真实 `require` 支配第 101 行绑定写入，局部 BLOCKED 为带明确前提的条件命题；计数器、内部库、初始化及其他入口缺口仍保留 |
| Atomic 局部 | audited／before 首 token 付款第 305 行未获前置锁版本；after 第 306 行同 loan／off 字段已置位，局部同入口同 key 回调 BLOCKED；三版第 85 行 `ACEXT()` 均在锁前，独立候选及 unlockedCallWindows 保留 REACHABLE 静态窗口 |
| 证据分层 | 九候选的最终 verdict 与整体 pathEvidence 均 UNKNOWN；局部 REACHABLE 不等于可行漏洞，局部 BLOCKED 不消除其他调用与入口。六义务、局部 scope／premises／conditional 与整候选 proofScope 分开保存 |
| 工具身份 | 现有工具 configHash／executionConfigHash 与编译 environmentHash 含义不同；未复制摘要或用空告警过门。当前 toolBinding 明确 TOOL_ENVIRONMENT_BINDING；编译／工具双收据桥仍待接入 |
| 编排 | 离线 D2 CLI 使用保存候选且零模型；登记目标的工作台预览绑定 compiledFacts／compilerBinding，模型之前重验；单样本及批量保留失败、未知和 usage=null，历史只读；清理源码与原件 AST 摘要不同不能混用 |
| 独立审查 | `S11-review/PASS-003.md` 无未修阻断；以标准库逐项比对九候选的完整绑定身份及 32 条 AST 原字节引用；同根潜在 key 别名、旧权限读取、未知调用、求值顺序及签名错绑均有红绿回归 |
| 自动检查 | `S11-integration/maven-clean-verify.log`：88 项通过；`python-full.log`：397 项通过，无失败或跳过，其中提供器 21 项、核心 26 项、集成 12 项；`cli-help.log` 退出 0 |
| 九候选 CLI | `S11-integration/verify_cli.py` 从版本控制的清单与候选逐项运行统一命令；`cli-candidates/summary.json` 保存命令、摘要、退出码及结果。全部退出 0、RECOMPILED_MATCH、整体 UNKNOWN，局部差异与核心输出相同 |
| 实际 Chromium | 本机 `8891/agent.html` 使用真实 solc 0.5.8 编译的合成合约及固定离线回复；编译事实、计划、D2、导出与只读回放贯通，六义务及 usage=null 保留，只有一次运行 POST；`browser-check.log` 通过、`browser-console.log` 错误 0、`browser/workbench.png` 截图。首次夹具版本写错导致编译失败的记录保留为 `*-fixture-error.log`，修正后重新完整验证 |

复核命令：`mvn clean verify`；`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`；`java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help`。统一候选 CLI 的命令见工具说明与 `cli-candidates/summary.json`。被测基点为 `27c3d56`，当前工作区的无关 Java 格式修改及 R1 提案保持初始摘要；Apple 四个实现文件与 `27c3d56` 一致。

| 已审且已测生产文件 | SHA-256 |
|---|---|
| `compiler_facts.py` | `cf07d980108d03878c1c75c24beb92e32507d5ec065da869bf9e773d2697c9f5` |
| `compiled_d2.py` | `6ac5640d3ba0de8a6f7ec4a0f3cf8c41f7f70f6fae83eafb2140bad723b8c901` |
| `d2_verify.py` | `313441d61e18a1dda27679c3a589df72558f256f53625fec4a1ebfff12926d80` |
| `audit_workbench.py` | `59d0d5bff1fc337eb08bf5c3290101a4f38f068972bea74cafe17540631094ae` |
| `benchmark_runtime.py` | `ee1f89aecb1493a1cb8e417a553d1123c7ddd60ee13d93d4402ac90dbeddc8fb` |

全量代码、测试和证据摘要保存于 `S11-integration/final-system-identity.json`；本轮只精确提交相关工具、清单、候选与文档，提交及远程同步身份保存于同目录 `git-sync.json`。以上为本机局部工程证据，测试夹具可从提交重跑；六原件及固定环境仍需另外恢复。

程序配置与固定候选分别在 `data/audit/r2/compiler-manifests/`、`data/audit/r2/path-candidates/`，运行方式见[工具说明](../../../../tools/experiment/README.md#r2-s11真实编译事实与有限路径)。完整交易可行性、编译／工具身份桥、相关入口覆盖和真实正反裁决继续按 REQ-07 追踪；没有据此完成整个 S11 或 R2。

## 完成审计规则

逐项检查当前源码、适用自动测试、真实程序及浏览器证据；没有支持某项的证据时保持未验证。指标由保存结果重算。UNKNOWN、故障与标签缺失单列分母。没有独立审核或新模型实验时，不把工程完成改写为方法已验证。
