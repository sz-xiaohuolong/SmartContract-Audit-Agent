# D1/D2 毕设工程统一验收矩阵

| 当前事实 | 状态 |
|---|---|
| R2-20261010 | 整体验证 UNVERIFIED；S11 有限引擎／双收据与 S12 页面接缝工程 VERIFIED，完整学术正反与方法效果仍未验收 |
| 研究效果 | UNVERIFIED；最新思考与全文输入批次共同51目标F1：VANILLA 0.9783、DENSE 1.0000、D1 0.9783，D1仍未超过最强对照；历史采集D2为139／151未知；2026-10-13零模型重放旧133为75／0／58、新151为80／0／71；冻结UNKNOWN门槛未达 |
| 证据入口 | `.evidence/R2-20261010/`；历史证据仍按 PROJECT 导航 |

基线：[SPEC](SPEC.md)；任务：[统一计划](IMPLEMENTATION_PLAN.md)。历史 S9 的局部验证保留在原文件，不扩展为本轮完成证据。

| REQ | 本轮证据 | 结果与缺口 |
|---|---|---|
| 01 输入 | 输入清理、原件摘要及行号回归；真实 Chromium 粘贴、预览、离线运行和下载 | S10 输入局部 VERIFIED；S11 事实与 S12 展示接续 |
| 02 工具环境与53目标 | 53 环境预检；53 次真实 Slither，51 成功、2 失败；逐目标固定版本/二进制/参数/退出/耗时/诊断 | VERIFIED（工具运行与失败处理）；失败不能当安全 |
| 03 真值隔离 | 模型与检索消费清理输入；发现与给定候选分开；真值变异、字符串保护及来源回归 | VERIFIED（工程）；历史模型输出仍有污染限制 |
| 04 D1离线/预算方案 | 同原Nomic保存池47目标重选、冻结600文档对账、94完整配对、Java／Python一致及零模型报告；最新真实批次另见本页末节 | PARTIAL；消费工程VERIFIED，新F1已采集；独立标签与完整提示token公平未验 |
| 05 假设绑定 | Java schemaVersion=2 回归与 loopback 网关通过；位置、机制、源码和完整函数签名错绑拒绝，usage=null 保留 | VERIFIED（工程绑定）；编译证据完整性由 06／07 单列 |
| 06 编译事实 | 六环境真实 standard-json 对照及新版单文件／依赖模板编译；声明、UTF-8 跨度、源码闭包和 ABI 入口；官方 Slither 独立双收据 | VERIFIED（有限工程）；超出已支持初始化和入口语义的候选保留缺口 |
| 07 D2真实正反 | 权限闭包、有限 CEI／统一锁、相关入口、正常退出及资金建态；真实 SimpleDAO／Reentrance 正裁决和严格 CEI 机制对照反驳 | PARTIAL（研究）；有限引擎 VERIFIED，真实维护者修复正反与广泛效果未验收 |
| 08 派生重放 | 2026-10-13两批159×2单元／133+151原候选，四臂身份、原件、模型／usage和源码／JAR摘要全部匹配；下载原始字节一致 | VERIFIED（工程）；旧UNKNOWN 121→58，仍未达到≤13，研究未通过；历史派生保持原口径 |
| 09 真实先导与四基线 | 双账本、10事件盘点；6正式事件18原件SHA一致；四臂完整532／604行 | PARTIAL；4事件及独立候选审核缺失，混淆矩阵null，真实维护者修复闭环未达 |
| 10 工作台 | 预置公开案例、真实演练、预览后离线执行、动态六义务、单候选切换、只读派生历史及下载；实际 Chromium 三屏宽与控制台通过 | VERIFIED（本轮界面工程）；正式付费模型运行未执行 |
| 11 毕设材料 | 本轮[工程报告](S11_S12_ENGINE_REPORT.md)已由保存结果生成；完整来源审核、预注册与四基线另列 | PARTIAL |
| 12 验证/提交同步 | 2026-10-13全量734项Python、111项Java与CLI通过；最后时间漂移修复独立复审通过；浏览器错误0，身份见本轮git-sync | VERIFIED（本机工程）；跨机恢复与整体研究仍未完成 |

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

## S11／S12 防御静态核验闭环

2026-10-11 本轮有限引擎、双收据、保存候选重放及页面联动工程验收通过。详细数字、规则和限制见[工程报告](S11_S12_ENGINE_REPORT.md)，原始证据 `.evidence/R2-20261010/S11-S12-final/`。整个 R2 研究有效性仍 UNVERIFIED。

| 项目 | 本轮新鲜结果 |
|---|---|
| 回归 | Python 3.12：509项；Java 21：88项；均无失败或跳过；JAR帮助命令退出0 |
| 独立评审 | `REVIEW.md` 与增量复审无未解决阻断；工具错绑、建态、回退、无WRITE相关CALL入口与UI单候选裁决问题均已修复；CSO因源码规模超限未进入扫描 |
| 正反规则 | 真实SimpleDAO／Reentrance保存CALL候选获SUPPORTED；派生的严格CEI机制夹具获REFUTED、双收据MATCH、六义务SUPPORTED；只移动部分扣减仍UNKNOWN。机制夹具不计入研究样本 |
| 历史重放 | `cd592f4847454f939dfc75e87fecc9fd` COMPLETED；159单元、53目标、172假设；原件所有文件摘要未变，新增模型请求0 |
| 未知前后 | 172／172→166／172，即100%→96.51%，下降3.49个百分点；6条支持来自2目标的三策略，不能当作6个独立样本 |
| 失败与未知 | 150工具单元OK、9PROCESS_ERROR；113流水线完成、46失败；22条缺编译assessment仍计入未知分母；最终D2执行异常0 |
| 浏览器 | 真实演练、预览后离线审计、JSON导出、派生历史、逐样本矩阵、支持／未知假设切换与原字节下载通过；1440／834／390px无水平溢出；控制台错误与警告0 |
| 隔离与Git | 原批次、r1_candidate_corpus与Nomic快照未改；只精确提交相关源码／测试／文档，保留无关修改；身份与同步见本机`final-system-identity.json`、`git-sync.json` |

全量首轮失败、兼容夹具问题和旧AST空实参异常均留存原始日志；修复后再全量回归并生成新的派生运行。原有九真实候选的局部证据不被本轮机制对照覆盖；维护者修复的完整学术正反、四基线及显著未知率下降仍未达到验收。

## 完成审计规则

逐项检查当前源码、适用自动测试、真实程序及浏览器证据；没有支持某项的证据时保持未验证。指标由保存结果重算。UNKNOWN、故障与标签缺失单列分母。没有独立审核或新模型实验时，不把工程完成改写为方法已验证。

## 真实 API 三策略采集（2026-10-11）

本次仅完成用户授权的单次探索性采集；正式批次 `dcf98eef6475433f80f228c9ab5a29fb`、冒烟 `2a2097291b4242d98ce380167307f5d0`。原始证据 `.evidence/R2-20261010/API-batch-20261011/`，逐单元原件 `.local/auto-benchmark-runs/`；均保持本机留存，不提交凭证或新增原始日志。

| 验收事项 | 新鲜结果与证据 |
| --- | --- |
| 授权与范围 | 用户明确授权真实批次并确认全部53目标×三策略；发现六个超长输入后，用户确认保留18个阻断单元的失败／UNKNOWN且不发请求。未根据评分真值裁剪 |
| 前置检查 | 配置存在、凭证通过校验且未打印；Milvus 127.0.0.1:29531可读；Nomic 768d、摘要与活动快照一致，600向量读回。`preflight.json` |
| 冒烟 | 两个模型单元成功，JSON与usage均有效，输入3909／输出322 token。DENSE旧AST引用152无法解析，D2保持UNKNOWN；D1无假设、工具OK。无重复付费请求。`smoke-result.json`与`smoke-compilation-diagnostic.json` |
| 正式模型 | 159/159落盘；141次真实请求，139项有效，2项MODEL_OUTPUT_INVALID，18项输入阻断。零重试，usage完整141/141，输入185816／输出19984 token。`formal-execution.json`、原samples.jsonl |
| 策略与公平分母 | Vanilla上下文和证据ID为空；Dense／D1同池，冲突0。共同有效45目标上F1为0.8056／0.7887／0.7536；D1比最高基线低0.0519，未观察到增益。UTF-8上下文上限不等于token公平 |
| 静态工具与D2 | 工具执行135 OK／6 PROCESS_ERROR；流水线111完成／48失败。单元支持4／反驳0／未知155；135假设支持4／反驳0／未知131（97.04%），其中9条缺失核验仍占未知分母。支持来自Reentrance三策略及SimpleDAO的Dense；不生成利用代码 |
| 只读报告 | 新`benchmark_report.py`从保存计划、事件与样本重算，输出中文报告、六义务、逐假设、usage与未知原因；生成报告零模型与工具请求。`d2-detail.json`与[本次报告](experiments/2026-10-11_API_BATCH_REPORT.md) |
| 本机身份封存 | 配置执行前后、JAR与批次流水线Python源码摘要一致，原无关diff不变。JAR为`c49fbf20ab4423f3eee568bfef14586bb4ec8f9cfdc1d57e756f40459cc0d028`，其中含启动时未提交Java修改；以实测产物身份为准。`formal-system-identity.json`、`final-manifest.json` |
| 补丁与回归 | 原生规格／代码核对无本轮采集阻断，`review.md`。Python3.12全量518项通过、Java88项通过、CLI帮助退出0；`python-submission-regression.log`、`maven-verify.log`、`cli-help.log`。自动测试仍只用离线夹具 |
| Git边界 | 仅本次工具、测试、README和现行中文文档；原Java修改、R1提案修改、三项脚本删除、.aris和.local保留。凭证检查与同步身份留`git-sync.json` |

重算命令：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/benchmark_report.py \
  --run .local/auto-benchmark-runs/dcf98eef6475433f80f228c9ab5a29fb \
  --output .evidence/R2-20261010/API-batch-20261011/重算报告.md \
  --detail-output .evidence/R2-20261010/API-batch-20261011/重算明细.json \
  --metadata .evidence/R2-20261010/API-batch-20261011/report-metadata.json
```

本次采集工程VERIFIED，研究效果仍UNVERIFIED。原模型标签指标与D2裁决独立；UNKNOWN、失败和无假设不构成安全。两个有效安全对照、自动知识／标签、有限证明范围及未锁定精确token预算限制了推广性；新旧批次输入治理与策略不同，不作同候选因果比较。不得用97.04%的未知弃权宣称误报拦截，也不自动启动第二批付费实验。

## D1／D2根因修复与零模型复验（2026-10-12）

本轮工程通过，完整结果及待授权模型复验方案见[根因修复报告](experiments/2026-10-12_D1_D2_REPAIR_REPORT.md)。原始证据位于 `.evidence/R2-20261010/D1-D2-root-cause-20261012/`，派生运行 `78c078d884e64cf69a65c54565824386` 已封口。整体R2研究效果仍UNVERIFIED。

| 检查 | 本轮证据与结果 |
|---|---|
| Python 3.12 | `python-full-final.log`：579项通过，0失败／错误／跳过；系统默认Python为3.14，验收显式使用3.12.13 |
| Java 21／CLI | `maven-final.log`：根 `mvn clean verify`，97项通过；`cli-final.log`：帮助命令退出0 |
| D1同池消费 | 47目标、4140原曝光、94对／188片段，1577–3235字节；91对包含旧700字符之后的变化；自动适用性全UNKNOWN；Java／Python一致，边界修复后选择不变 |
| D1独立审查 | 自动Dense入选状态矛盾、多义回退重配对及Java FULL范围矛盾已修；红绿／隔离driver及增量复审留证；CALL资源仅语法关联的限制保留 |
| D2独立整合 | 六项真实本地子进程整合回归通过：仅签名兼容、suicidal专属佐证、缺失／漂移第二收据、类／合约／函数／文件／跨度错绑拒绝、构造保护阻断；终止证明完整性始终false |
| 真实静态重放 | 159单元／53目标／135保存假设，47次工具执行；135工具单元OK、6PROCESS_ERROR；18阻断未执行；114流水线完成、45失败 |
| 裁决与迁移 | 假设11支持／0反驳／124未知；4支持保留、7未知→支持；未知率97.04%→91.85%，下降5.19个百分点；11支持来自5唯一目标，不能当作11独立样本 |
| 双收据与边界 | 全部支持均MATCH、正常退出并有同类工具佐证；终止调用只反证3项义务、其余UNKNOWN；26条原RE WRITE不改写，工具失败不当安全 |
| 原件与展示 | `integrity-final.json`：原批次全文件摘要、159原模型／usage／请求／预测、Nomic与catalog一致；工作台真实派生读取与原字节下载通过；本轮未重新执行Chromium验收 |
| 实现身份与同步 | 重放期间生产源码／JAR摘要不变；`verification-final.json`、`integrity-final.json`、`git-sync.json`记录测试、原件及提交同步身份；精确提交，启动时无关修改保留 |
| 新模型效果 | 本轮新增模型请求0，`newF1=null`；前次单次授权已消费，第二批须另行授权；独立标签、完整token公平及四基线仍待验 |

前一轮576项Python／94项Java通过记录及独立审查红证据均保留。最终579／97包含随后修正的接口边界；不能用中间 `after-binding.json` 或离线工具夹具结果替代本轮真实双收据派生。

### 剩余未知只读核对

工程提交205cf184后仅补充诊断与文档，未修改生产源码或重新执行工程回归。`.evidence/R2-20261010/D1-D2-residuals-20261012/audit.json` 的124个候选键与派生明细一一对应；互斥分类数为26／4／39／4／29／18／4，合计124。28个候选的每条相关正常退出图路径均包含日志外部调用，不能据此证明实际正常提交；四条权限写入位置正确，但原Slither没有同类佐证。独立读取重算及文档／凭证／Git范围检查见同目录 `verification.json`。原批次、派生全部文件、生产源码／JAR、Nomic／catalog摘要保持，新模型、编译器、工具执行0。此项只验证诊断口径，不改变11支持／0反驳／124未知或新F1=null。

### 真实复验准备与阻塞审计

`.evidence/R2-20261010/D1-D2-real-revalidation-ready/prepare.py` 只允许Milvus读回及Ollama模型元数据读取；没有触发模型、嵌入生成、编译器或静态工具。原53目标与源码摘要一致，47目标可运行，6目标×三策略阻断；冻结集合600向量及Nomic摘要匹配。`formal-plan.json`、`smoke-plan.json`、`readiness.json` 保存现行计划摘要、预留编号、286请求／585728输出token上限及授权后的命令。所有准备输入前后摘要一致，未建立正式或冒烟运行目录；配置凭证的远程有效性仍UNVERIFIED。

此处为授权前准备状态：当时新D1 F1没有真实调用证据，第二批授权缺口连续三个目标回合未解除，长目标标记BLOCKED，项目WAITING_HUMAN／UNVERIFIED。`goal-audit.json` 保留当时的阻塞审计。随后用户明确授权并完成单次复验，当前结果按下节更新；准备记录没有追写成已授权原件。

## 2026-10-12 第二次真实 API 复验

本次仅使用用户明确授权的同一 Ark Agent Plan 端点、`deepseek-v4-flash` 与原 Nomic 768 维快照。正式批次 `119b4862f8a14818b62848ce709c3ee6`、冒烟 `a68d70a324904c8db4635fcaa1d107df`；原始核对见 `.evidence/R2-20261010/API-revalidation-20261012/`，分析见[复验报告](experiments/2026-10-12_API_REVALIDATION_REPORT.md)。

| 检查 | 本轮新鲜结果 |
|---|---|
| 授权与预检 | 用户明确回复“授权该单次复验”；89个冻结输入和配置摘要执行前后相等，凭证不打印；Milvus 600向量读回、Nomic修订、正式／冒烟计划与预留编号匹配。`authorization.json`、`preflight.json`、`comparison.json` |
| 冒烟门禁 | FibonacciBalance 的DENSE／D1模型、JSON解析与usage均通过，各1次请求；输入3702／输出315 token。`smoke-verification.json`、原样本 |
| 正式封口 | 159／159单元落盘，139有效模型结果、20失败／UNKNOWN，其中18超长输入零请求，2结构化模型输出失败。正式142次请求尝试，其中一次受限重试；冒烟2次，合计144／286；已记录输出20497／585728 token。usage缺失0 |
| 三策略结果 | 新批次共同有效45目标：Vanilla 0.8219、Dense 0.8684、D1 0.9383；两个批次共同有效43目标：旧D1 0.7576→新D1 0.9487，新Dense 0.8611。自动标签探索性口径，候选池冲突0 |
| D2与工具 | 新133假设12支持／0反驳／121未知（90.98%），支持来自5唯一目标；工具137 OK／6 PROCESS_ERROR，流水线失败31。5个D2错误单元是候选身份绑定不匹配，其他候选记录仍保留 |
| 同候选口径 | 原135保存假设的严格派生重放仍为11支持／0反驳／124未知；新批次假设变化，90.98%与原97.04%不能解作同候选因果改善 |
| 新未知分流 | `unknown-classification.json`逐一覆盖121条未知：42入口／正常退出、33同主体余额数值、28风险操作绑定、6重入WRITE、6权限写入、5建态、1终止调用；75条重入CALL已绑定且双收据MATCH，仍不得无证明升级裁决 |
| 离线回归 | `python-full.log`：Python3.12全量579项通过；`maven-verify.log`：根 `mvn clean verify` 97项通过；`cli-help.log`：帮助命令退出0。构建在批次封口之后重新打包JAR，执行期JAR哈希以封口记录为准；`comparison-after-build.json`保留重建后只读重算结果 |
| 研究资格 | `researchEligible=false`；独立标签、充分安全对照、完整保护正反样本、精确token公平与四基线仍未验；整个R2研究效果UNVERIFIED |

只读重算：

```bash
PATH=/Users/daiyifei/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/bin:$PATH \
PYTHONPATH=tools/experiment python3 .evidence/R2-20261010/API-revalidation-20261012/analyze.py --allow-rebuilt-jar
```

原始批次与新批次各自保存在 `.local/auto-benchmark-runs/`；新原始日志、比较明细及下载输出留在被忽略的 `.evidence/`。本次真实采集工程已封口，D2高未知率与论文研究有效性继续追踪，不由本次API授权推导第三批请求。

## 2026-10-12 AST 容差与别名解析升级

用户本轮四项请求的局部工程验收为 VERIFIED。原始证据位于 `.evidence/R2-20261010/ast-tolerance-alias-20261012/`，不改写真实批次133条假设／121条未知的历史统计。

| 接缝 | 验证结果与限制 |
|---|---|
| 风险行与语句跨度 | 精确行、真实 UTF-8 语句跨度、±2 行窗口依次选择唯一操作；保留原候选与绑定位置，跨文件、错事实／跨度及多义拒绝；权限 WRITE 与重入 CALL 回归通过 |
| Storage 引用 | 编译 storage 指针、映射 key、实际结构字段与 SlithIR referenceBindings 交叉核验；仅 MATCH 收据传入证明及展示图；错根／key／字段、错跨度、多定义、memory 与重赋值保留未知 |
| 辅助退出路径 | 已绑定且无转账的只读查询／辅助日志生成带明确前提的正常 EXIT 见证；旧 view 的实际 IR CALL 保留无回调前提；未知返回值、未绑定日志及后置回滚不产生完整反例；顶层 CONDITIONAL 保持 UNKNOWN |
| 区块环境 | now／block.timestamp 同值，block.number 独立非负 uint256 求值；weeks 常量、矛盾条件、非法值与预算耗尽回归通过 |
| 当前工作区 | `python-static.log`：compileall 退出0；`python-full.log`：全部662项通过，无失败／跳过；`maven-verify.log`：109项通过；`cli-help.log`：退出0。包含启动时保留的其他工作 |
| 独立提交内容 | 导出拟提交源码并独立构建，未使用 Git 工作树；`python-commit-content-final.log`：635项全通过，无失败／跳过；`maven-commit-content.log`：97项通过；静态语法及CLI均退出0 |
| 范围与复核 | 启动快照、增量审查、凭证扫描及提交内容单独保存；保留未完成的Java、EVM、旧CALL兼容适配与其他无关修改。首轮顶层夹具多义定位失败已补齐factId，并保留失败日志后全量复验 |

本轮未调用真实API、编译真实目标、执行真实Slither或重放121条未知候选，不声称28／36／24／3各组全部解决或未知率实测下降。日志实现、部署地址、回调和正常返回缺少实际证据时继续UNKNOWN；整体R2研究验收仍UNVERIFIED。

## 2026-10-12 AST 升级后单次真实 API 复验

本轮真实采集及保存结果核对完成，详见[报告](experiments/2026-10-12_AST_API_REVALIDATION_REPORT.md)。正式 `9c480f3256884d5a90c1a6bb3e2d8095`，冒烟 `3ceaa993593146289246bb1bb0ff6b71`；证据 `.evidence/R2-20261010/API-ast-revalidation-20261012/`，新增原件仅本机留存。

| 检查 | 新鲜结果与限制 |
|---|---|
| 授权与预检 | 用户明确新请求；同模型／端点／Nomic，600向量读回；92项配置、源码、JAR和历史原件执行前后摘要相等，未打印凭证 |
| 冒烟 | 2单元解析与usage通过，各一次请求；Dense REPORT、D1 NO_REPORT，预测正确性不作为启动筛选条件；输入3716／输出341 token |
| 正式封口 | 159单元，139模型有效／20失败；18输入阻断零请求；正式141次尝试，含冒烟143／286，输出20898／585728 token，usage缺失0 |
| 公平分母 | 共同有效46目标F1：VANILLA 0.9000、DENSE 0.9136、D1 0.8718；D2 12支持／0反驳／115未知（90.55%）；两批三策略共同有效45目标的比较见报告；同池冲突0 |
| 程序证明 | 容差绑定4、别名记录0、辅助条件退出35条假设；可重叠且不等于全部原121条重放 |
| 工具与失败 | 工具状态 `{"OK": 143}`；模型失败 `{"EVALUATION_INPUT_BLOCKED": 18, "MODEL_OUTPUT_INVALID": 2}`；流水线失败 `{"EVALUATION_INPUT_BLOCKED": 18, "MODEL_OUTPUT_INVALID": 2}`，全部保留真实分类 |
| 身份与回归边界 | 工程基点 `f84dc218b868ac28e30685c2f668c7e53e5efdb3`；实际JAR `fa09524dd6788d783c8d9b7b7ccf966f205f48b056a1639a80dde2911096a127` 含启动时其他修改，不能仅由该提交复现。本轮不改生产代码，沿用上一节662项Python／109项Java验证；新增检查为只读重算、文档范围与凭证检查 |
| 研究与范围 | researchEligible=false；UNKNOWN不当安全，两批候选变化不作完整同候选因果归因；本次授权已消费，研究与更大未完成工作包继续UNVERIFIED |

只读重算命令见报告；comparison.json、d2-detail.json、proof-diagnostics.json和candidate-pairs.json分别保存身份／共同分母、逐假设、证明缺口与唯一保存候选子集配对。

## 数据迁移与旧应用退役

2026-10-12 用户明确授权迁移数据与清理旧应用。本次维护验收为 VERIFIED，不改变研究标签、既有实验或整个 R2 的验证状态。

| 核验项 | 结果 |
|---|---|
| 数据原件 | 898 份文件从旧资源迁至 `data/`；SHA-256 与 Git 对象逐份一致，CSV 标注与示例一并保留 |
| 实际批量目标 | 新入口仍加载原 53 目标，编号、保存源码摘要与标签与批次 `9c480f3256884d5a90c1a6bb3e2d8095` 一致 |
| 旧应用 | 当前目录移除旧 `src/`、`legacy/`，退役 48 份应用文件；历史可从迁移前 `4ba5750` 恢复 |
| 私有配置 | 两份被忽略的旧本机配置移至被忽略的私有恢复目录，目录权限 700、文件权限 600，不进入提交 |
| 工作区相关回归 | 目标、页面读取、探索提取和凭证扫描共 23 项通过 |
| 独立提交内容 | 在 `5d6b50b` 基础上核验本次变更：`mvn clean verify` 97 项 Java、Python 全量 636 项通过，CLI `--help` 退出 0；核验临时导出已清理 |
| Git 范围 | 仅迁移、退役和入口说明；既有 Java／EVM 与其他未提交开发内容保留 |

原始[迁移清单](../../../../.evidence/R2-20261010/legacy-retirement-20261012/migration-manifest.json)、[目标身份核对](../../../../.evidence/R2-20261010/legacy-retirement-20261012/target-check.json)、[验证摘要](../../../../.evidence/R2-20261010/legacy-retirement-20261012/verification.json)、[Maven 日志](../../../../.evidence/R2-20261010/legacy-retirement-20261012/maven-verify.log)与[Python 日志](../../../../.evidence/R2-20261010/legacy-retirement-20261012/python-full.log)为本机证据，默认不提交。数据原件与代码通过 Git 留存，本次新增真实模型请求为 0。

## 2026-10-12 思考模式与完整源码输入真实 API 复验

用户明确要求启用思考、取消样本模型输入的旧实验门槛并重跑实验。最新[报告](experiments/2026-10-12_THINKING_FULLSOURCE_API_REPORT.md)以正式 `6cae40677b104152bd92efedc5bbc479` 和五个单单元冒烟的保存原件为准；证据位于 `.evidence/R2-20261010/API-thinking-fullsource-20261012/`，原件位于被忽略的 `.local/auto-benchmark-runs/`。

| 核验项 | 新鲜结果与限制 |
| --- | --- |
| 工程回归 | Python 离线测试 663 项、Java `mvn clean verify` 109 项通过，CLI `--help` 退出 0；Loopback 请求体回归确认 `thinking=enabled`、`reasoning_effort=low` 与 16,384 完成 token |
| 输入与身份 | 53 个目标均以清理后的全文作为模型源码，原53份源码摘要、标签、模型／端点、Nomic 快照与旧正式计划一致；84项执行文件／JAR／配置／快照摘要前后相等；JAR SHA-256 `febef6ae3e8e1d1e5a57b3ffe66ba7e7b079972091bb3f34b505f67dff344bf6` |
| 冒烟决策 | 默认较长思考时短样本成功、最长样本在8192和16384完成token两次触顶；开启低思考长度后短样本与最长36,386字节源码均返回有效JSON与usage；共5次真实请求、3成功2失败，失败保留UNKNOWN |
| 正式请求 | 159计划单元全部落盘，各有一次真实请求；156模型有效、3结构校验失败，输入阻断0，零请求0，次数／usage缺失0；正式输入297,128／输出119,672 token。连同冒烟共164次请求、输入330,527／输出153,728 token |
| 旧阻断目标 | 先前6个超长目标本次各有3次请求，18个模型结果全部有效；最大单次模型输入10,762 token。Nomic查询嵌入另有3目标／9单元截取，检索上下文仍限4096字节，不等于模型源码截取 |
| 模型比较 | 本批三策略共同有效51目标F1：VANILLA 0.9783、DENSE 1.0000、D1 0.9783；D1低于Dense。与上批共同45目标的差值受思考设置、完成预算、输入资格与生成波动共同影响，不作单参数因果归因 |
| D2与失败 | 本批151假设：12支持／0反驳／139未知（92.05%）；3模型校验失败，另4模型有效单元因候选编译绑定失败使D2保持UNKNOWN。159项工具状态OK；研究效果仍UNVERIFIED |
| Git与范围 | 代码小版本 `5d6b50b` 已同步 `origin/main`；执行JAR还含启动前其他未提交工作，报告记录实际JAR与文件摘要。新增报告和本验收只记录已验证实验，不改写历史批次 |

计划摘要、逐样本请求、usage、共同目标指标和D2裁决由 `analyze_low.py` 只读重放；分析不会再次调用模型或工具。整个R2的独立真值、精确token公平与四基线继续为UNVERIFIED。

## 原始数据源去重与目录整理

2026-10-12 用户明确授权删除公开数据的重复副本并整理 `data/`。本次局部工程验证为 `VERIFIED`，R2 整体研究验证仍为 `UNVERIFIED`。

| 核验项 | 新鲜结果与限制 |
| --- | --- |
| 数据去重 | 143 份 SmartBugs Markdown 可从原始源码和标注重建；700 份 SolidiFI 副本及 `Overflow15.sol` 与原件逐字节相同，共删除 844 份文件、5,909,920 字节；50 份额外对照原样移动 |
| 唯一来源 | 加载器直接读取根目录 SmartBugs 的 Solidity 与 JSON；SolidiFI 离线清单直接读取原始 `buggy_contracts/`，350 份合约可枚举；两个数据集的 844 份源码、CSV 和 JSON 均与登记的 Git 版本一致 |
| 数据登记 | 上游、固定版本、文件数和聚合 SHA-256 保存于 `data/datasets.json`；额外 OpenZeppelin 对照的完整生成版本仍缺失，不因此升级安全真值 |
| 目标身份 | 53 个目标的编号、漏洞类型、标签值和漏洞行一致，全部原始字节摘要经核对；29 个目标仅因保留原始空白而改变输入摘要。新来源标签指出 JSON 或 OpenZeppelin，研究准入仍为 `false` |
| 历史兼容 | 已保存计划与实验不改写；原有保存目标可继续断点续跑，新 JSON 标注摘要进入新计划，标注变化不能续写原批次；两个离线回归覆盖上述边界 |
| 工程验证 | 本次提交内容的 `mvn clean verify` 97 项与 Python 离线测试 641 项通过，均无失败或跳过；CLI `--help` 退出 0；测试用原始数据集夹具与本机 HTTP／子进程，不需要下载原始仓库 |
| 范围与凭证 | 固定 `data/audit/` 输入、既有业务代码差异和三份脚本的已有删除均未混入；来源登记摘要、文档链接及待提交凭证扫描通过；新增真实模型请求 0 |

去重清单、目标比较、来源核验及 Java／Python／CLI 日志位于 `.evidence/R2-20261010/dataset-cleanup-20261012/`。当前数据树共 97 个文件，与两份原始数据集重复的 Solidity 副本为 0，入口见[数据说明](../../../../data/README.md)。验证使用准备提交内容的临时导出，主目录继续开发，已有主目录 JAR 不因本次数据整理而重建。

## 本机存储拆分与无损归档

2026-10-12 用户授权的本机存储维护验收已通过，详情见[整理报告](STORAGE_LAYOUT_REPORT.md)。迁移33目录、归档6,248文件，净减少704,518,776字节（约672 MiB）；工作区已有业务、EVM与脚本删除等修改保留。

| 核验项 | 新鲜结果与限制 |
| --- | --- |
| 研究身份 | 15,040份原件的还原SHA一致；30批次全部指标／候选／D2与3个派生报告保持一致 |
| 读取链路 | 6份快照完整性通过，6份编译绑定重编译通过；8个只读HTTP状态／下载检查通过，原字节不变 |
| 回归与幂等 | 工作区Python677项及存储专项10项通过；独立内容650项全量通过、网关1项构建后补验通过，Maven97项／CLI通过；最终整理迁移／归档／新增兼容入口均为0 |
| 证据与备份 | `.evidence/R2-20261010/storage-layout-20261012/` 保存日志与摘要；`research-artifacts/migrations/` 保存迁移清单及基线，均为本机证据，远程原件备份未配置 |
| 范围 | 新增模型请求0，失败、UNKNOWN与usage=null原值保留；R2整体研究验证仍UNVERIFIED |


## 2026-10-13 阶段1至5零模型工程与冻结目标验收

整体 **PARTIAL**，未通过五阶段全部验收。完整实现、四臂分布、复现命令与限制见[本轮工程报告](experiments/2026-10-13_STAGE1_5_OFFLINE_REPORT.md)。源码基点`fa4c9f4`，实际执行绑定工作区每份生产源码与JAR摘要；提交映射见下述`git-sync.json`。

| 验收项 | 实际结果 | 判定 |
|---|---|---|
| 数据与分母 | 双账本分别159单元／133候选与159单元／151候选，稳定ID唯一且100%可回读；原件前后SHA不变 | 工程通过 |
| 来源与独立真值 | 10事件盘点；6正式事件18原件齐全；4事件待审，独立候选真值尚缺 | 未完成 |
| D1消费 | 159上下文、300配对和22入选对回读；system差分引导、预算组件与最终摘要接通 | 工程通过；212自动条件、精确token公平未完成 |
| 编译修复 | 新派生使用当前清单／错误／诊断，历史失败留provenance；Spank成功重编译 | Parity三单元仍缺固定0.4.9协议，不称4单元全部通过 |
| D2有限反例 | 别名、同资源、实际权限消费者、合法建态、双独立执行及时间漂移修复；失败与超范围仍UNKNOWN | 有限引擎工程通过；维护者修复AC／RE双向闭环未完成 |
| 原133硬门槛 | 75 SUPPORTED／0 REFUTED／58 UNKNOWN，43.61%；原12支持保持，63未知转支持 | **未通过≤13及<10%门槛** |
| 新151单独结果 | 80 SUPPORTED／0 REFUTED／71 UNKNOWN，47.02% | 不替换133分母 |
| 四臂重放 | 原133产生532行，新151产生604行；稳定候选集、迁移和计时一致 | 工程通过；独立真值缺失，混淆矩阵null |
| 全量Python | 734项、89.328秒、退出0；不依赖真实API／Milvus／工具 | 通过 |
| 根构建／CLI | Maven 111项，0失败／错误／跳过；CLI帮助退出0 | 通过 |
| 浏览器 | 最新服务SimpleDAO六卡、19行高亮、JSON导出；两批四臂显示及四份下载SHA一致；控制台0错误 | 本机通过 |
| 模型费用 | 新增模型请求0、嵌入请求0；历史usage原样，演练缺失usage仍null | 通过 |
| 完整恢复 | 本机源码、输入、JAR、固定工具与收据身份可核对；原件和工具远程备份未配置 | 不宣称跨机100%恢复 |

最终派生为`5ee375133c084d6586ff8b8f43b4e009`及`5ee375151c084d6586ff8b8f43b4e010`，均在`research-artifacts/runs/derived/`，COMPLETED且159/159单元。原件通过`storage.read_artifact()`读取，归档不更改原始hash。

最小证据位于`.evidence/R2-20261010/stage1-5-final-20261013/`：`test-summary.json`与最终日志、`identity-verification.json`／`final-verification.json`、`timestamp-drift-comparison.json`、红绿回归、两张工作台截图、浏览器导出／下载摘要、凭证与体积检查、`git-sync.json`。执行trace仅保留于`research-artifacts/receipts/evm/`，无损压缩不截断。无关R1提案、原有脚本删除和`.aris/`未纳入本轮提交。

## 2026-10-13 无用实验结果退役清理

本次只清理本机产物并同步保留说明，生产代码与研究统计不变。7个零模型中间重放由最终版本替代，21个相同计划离线演练保留最新记录；传递依赖核对后删除2,092个只被退役运行引用的编译／Slither／EVM收据目录，合计22,823文件。文件内容减少420,878,254字节（401 MiB），按文件分配块计算磁盘占用减少461,250,560字节（440 MiB）。扣除新增清单与核对材料后，文件分配块净减少约438 MiB；清理后新增批次与收据保留，目录总占用仍会随运行增加。

26,222份保留文件SHA-256前后相等；30个原始模型批次及6个保留派生读取通过，9个HTTP JSONL／四臂下载与原字节一致。最终133／151候选的原件、源码／JAR、分母与裁决再次核对通过，仍为75支持／0反驳／58未知及80／0／71。时间漂移修复前旧133对照、关键失败原件、所有真实模型批次与正式报告保留。新增模型／嵌入请求均0，R2研究状态沿用PARTIAL／UNVERIFIED。

逐文件删除原因及摘要位于 `research-artifacts/migrations/obsolete-runs-cleanup-20261013.json.gz`，本机证据 `.evidence/R2-20261010/obsolete-runs-cleanup-20261013/` 保存清理、保留摘要、最终候选身份与下载核对。未修改生产代码，验证限定为受影响的实际读取／下载，不重复运行Java构建或全量测试。旧存储迁移基线记录当时身份，已退役中间结果不能再按该基线完整回读。

## 2026-10-13 阶段1～5升级后单次真实API采集

本次采集工程VERIFIED，研究保持PARTIAL／UNVERIFIED。见[真实报告](experiments/2026-10-13_STAGE1_5_REAL_API_REPORT.md)，本次证据 `.evidence/R2-20261010/API-stage1-5-20261013/`。

| 核验项 | 证据与结果 |
| --- | --- |
| 授权与预算 | 用户明确单次请求；159正式＋2冒烟共161次，每单元一次、零重试，完成token 160399／2637824；输入472841，金额未核实 |
| 输入与服务 | 53目标全部可运行；600个Nomic 768维向量实际读回；29份空白摘要变化，代码token、目标编号、漏洞类型与标签值相同；新输入独立计划 |
| 初始阻断与续采 | 文档整理提交使HEAD改变，初始4请求后155单元在runtime.run之前被保护阻断；生产源码／JAR未变，仅续采2＋153，原阻断requestAttempts=null及原件保留；159个实际请求单元精确索引，无重复 |
| 原件与执行身份 | 正式、冒烟、续采计划摘要及159唯一单元核对；生产Python／Java、JAR、配置与历史原件原始SHA前后相同，同池冲突0 |
| 模型标签 | 156有效、3失败；51共同目标F1 0.9892／1.0000／0.9783；失败不计TN、不重试；与历史两批共同49目标另表 |
| D2与失败 | 新163候选0支持／0反驳／163未知；148条风险绑定失败、5条assessment编译绑定失败；流水线失败140；工具162 OK／2 PROCESS_ERROR，未记为安全 |
| 零模型诊断 | SimpleDAO同源同跨度但发现／候选环境摘要与事实ID不同；复用同一发现收据后原候选SUPPORTED，候选未改、模型请求0；仅诊断，不并入正式结果或产品修复声明 |
| 回归复用 | 未修改生产代码，沿用相同源码／JAR的734项Python、111项Java与CLI通过证据；本轮执行及分析脚本语法、原件只读重放与独立账本核验通过 |

旧133的UNKNOWN≤13仍未达，历史151单独保留；本次新候选不能替代冻结分母。独立标签、精确token公平及完整保护闭包未验，本次付费授权已消费。原件无损归档、凭证与体积检查、精确提交同步身份见本轮证据。
