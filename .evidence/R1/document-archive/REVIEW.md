# R1 历史评审归档

整理日期：2026-10-10。本文按原文来源合并历史记录，仅调整标题层级与路径。各章节的状态和“当前”均指原记录时点；归档不追加整体冻结、验收或发布结论。

| 原切片／记录 | 归档章节 |
|---|---|
| R1-S1 / `S1B_REVIEW.md` | [S1B_REVIEW.md](#s1-s1b-review) |
| R1-S2 / `REVIEW.md` | [REVIEW.md](#s2-review) |
| R1-S3 / `FIRST_BATCH_EVIDENCE_REVIEW.md` | [FIRST_BATCH_EVIDENCE_REVIEW.md](#s3-first-batch-evidence-review) |
| R1-S9 / `REVIEW.md` | [REVIEW.md](#s9-review) |

<a id="s1-s1b-review"></a>

## S1b 独立复审记录

日期：2026-09-21。按 `superpowers:requesting-code-review` 分派只读复审，审查 6 个新增实现模块、4 组新增测试及后续 usage 修复、文档增量。不依赖 git diff（本地新增目录仍未跟踪）。

初次复审实际运行 Python 全套 30 项通过；未发现 P1/P2 阻断问题。确认调用前 START fsync、不确定调用默认不重发、完整日志校验链、恢复绑定、隔离校验和索引完整读回的关键路径。

增量复核实际运行 32 项通过，确认 TYPE_UNMAPPED 仍为 FAILED、保留 raw 与实际 usage；知识快照必须匹配全量隔离清单；README/PROJECT 未将真实服务标为已验证。

建议补强的 RESULT 落盘中断、多页索引读回和冻结 JAR/配置三项测试已加入，主流程最终全套 35 项通过；这些新增测试没有改变实现代码。

未验证范围保持明确：真实 Milvus、SDK 版本、模型和 embedding 服务。本复审不授权提交、推送或发布。

<a id="s2-review"></a>

## S2 实现复查

日期：2026-09-22。独立复审状态：通过。09-21 的分派曾因账户额度失败；09-22 使用独立上下文的 `s2_final_review` 重新复审，复现问题后检查修复代码并执行离线回归，确认当前版本无剩余工程验收阻断。

本会话完成的本地复查与修复：

| 问题 | 证据与处理 |
|---|---|
| 同一行函数重载产生重复作用域/事实 ID | 新增回归，作用域加入成员序号，已通过 |
| 赋值右侧外部调用被源码位置误排为先写后调 | 复现后将相关作用域降级 PARTIAL，已通过 |
| 本地变量遮蔽、成员别名、存储别名、元组赋值与不支持的写入形式 | 回归测试确保显式 UNKNOWN，不从遗漏的写入推断不存在保护 |
| 权限检查后权限状态更新或外部调用 | 初始测试复现 UNKNOWN 被误判 SUPPORTED；绑定器将失效检查保留为 UNKNOWN |
| 同映射不同动态索引可能别名 | 初始测试复现 UNKNOWN 被误判 CONTRADICTED；现保留别名不确定性 |
| 重复条件配对消耗额外上下文 | 初始测试期望 2 条得到 4 条；现跳过不增加条件覆盖的配对 |
| 候选池可能用于另一份源码 | pool.sourceHash 与目标事实摘要严格一致；导出要求目标属于非 knowledge 审核划分 |
| 无候选时缺少逐条件未知解释 | 证据包保存全部候选 evaluations，不仅保存选中案例 |
| 事实响应缺少顺序字段 | 严格 Jackson 原始类型/构造字段校验拒绝，加入特性测试；此路径原有严格校验也能拒绝，不声称它曾通过生产校验 |

### 2026-09-22 独立复审闭环

| 复现问题（P1） | 修复与回归证据 |
|---|---|
| 短路表达式内写入可能被旁路，却标记 COMPLETE | 含 `&&/||` 的作用域降级 PARTIAL；`control-flow-red.log` 保留失败，最终 11 项事实测试通过 |
| 多维映射写入漏提取却标记 COMPLETE | 未支持的多维索引降级 PARTIAL，禁止从漏提取推断不存在写入 |
| 下标参数重赋值或下标状态变量变化后沿用旧资源绑定 | 未识别赋值、自增、单语句多重赋值及下标变量写入降级；`index-mutation-red.log` 与 `index-mutation-green.log` |
| 检查后的同根权限映射写入可能别名，却未使检查失效 | 按根状态槽保守失效为 UNKNOWN；`authority-alias-red.log` 与 `authority-alias-green.log` |
| 反向等值检查遗漏动态别名不确定性 | 先统一等式两侧的主体与资源，再匹配别名；`reverse-alias-red.log` 与 `reverse-alias-green.log` |

失败日志也保留测试编写过程中一处 subTest 变量名错误；该错误已修正，最终全量日志无失败或错误。上述缺陷均另有明确的预期/实际断言失败，不以测试框架错误作为缺陷复现依据。

独立复核：Python 事实测试 11 项、Java RetrievalTest 12 项通过；四策略、来源绑定、预算、配对、子进程和召回接口无新增可复现阻断。主会话随后重新执行 Maven 35 项、Python 52 项和四策略 CLI 对照，全部通过。本地 Milvus 2.6.4 的 09-21 合成向量冒烟证据保留，本次无需重启容器。完整证据见 VERIFICATION。

当前工程范围已完成验证和独立复审，可标记 READY_TO_SHIP；未获发布授权，也未执行发布。工程测试通过不替代真实开发配对、编译/语义审核、同 token 预算下游实验或论文创新结论。

<a id="s3-first-batch-evidence-review"></a>

## 首批真实案例原件复核与正式快照准入

更新：2026-10-04。结论：**知识 2、开发检测 4、验证 2 的项目级划分维持；正式知识快照仍不得激活。**八项固定源码的摘要与分组门禁通过，新增原始报告四份、修复版本两份。当前五项有逐事件报告，三项有修复源码或修复版本；但八项均没有符合 S3 契约的独立逐事件标签，重入知识候选还缺可回读的修复源码。报告与修复版本的存在不自动证明修复充分，也不产生安全负例。

### 划分与原件

| ID | 划分 | 原始报告 | 修复证据 | 当前结论 |
|---|---|---|---|---|
| `AC-ASE-040` PoolTogether H-04 | 知识候选 | [原始 finding #396](https://github.com/code-423n4/2023-07-pooltogether-findings/issues/396) | [维护者 PR #7](https://github.com/GenerationSoftware/pt-v5-vault/pull/7)、固定修复提交 `50bd158` | 报告指向 `Vault.sol:394` 的任意接收方参数；修复版本移除该参数并改用 `_yieldFeeRecipient`。修复是否覆盖完整攻击路径仍需独立审核。 |
| `RE-POP-077` AI Arena H-08 | 知识候选 | [原始 finding #37](https://github.com/code-423n4/2024-02-ai-arena-findings/issues/37) | [Code4rena 修复审查范围](https://github.com/code-423n4/2024-04-ai-arena-mitigation/blob/ac5b626ddb3e8005ec452e61b4fee8390438e118/README.md)引用维护者 PR #6，但维护者仓库返回 404 | 重入报告可固定；修复源码不可回读，不能构成真实正反补丁对。 |
| `AC-ASE-006` Basin H-01 | 开发检测 | [原始 finding #52](https://github.com/code-423n4/2024-07-basin-findings/issues/52) | [后续修复审查固定源码](https://github.com/code-423n4/2024-08-basin/blob/7e08ff591df0a2ade7d5618113dda2621cd899bc/src/WellUpgradeable.sol) | 原版 `_authorizeUpgrade` 无 `onlyOwner`，审查版加入该限制；审查版是修复状态证据，尚未定位精确引入提交。 |
| `AC-ASE-009` Gondi H-03 | 开发检测 | [原始 finding #64](https://github.com/code-423n4/2024-04-gondi-findings/issues/64) | [修复审查范围](https://github.com/code-423n4/2024-05-gondi-mitigation/blob/195e6122474a3b9f5abb7fa9d02ffc79181c0b7f/README.md)列出 `fix/64`，维护者源码仓库当前不可取得 | 报告明确 `distribute()` 缺调用者限制；缺可固定的修复源码。 |
| `RE-SCRUBD-001` DexBlue、`RE-SCRUBD-002` MonkeyScam | 开发检测 | 无逐事件原始报告 | 无真实修复 | SCRUBD 标签行与固定源码匹配，仅作待审索引，不当作已证实漏洞。 |
| `AC-ASE-030` Maia H-01 | 验证 | [原始 finding #885](https://github.com/code-423n4/2023-09-maia-findings/issues/885) | [维护者修复提交 `2209d6e`](https://github.com/Maia-DAO/2023-09-maia-remediations/commit/2209d6e96af986fa0960aacc356ba2be070fdc85) | 原版 `payableCall` 缺 `requiresApprovedCaller`；修复提交增加该修饰器。验证集不用于调参。 |
| `RE-SCRUBD-003` ViVICO | 验证 | 无逐事件原始报告 | 无真实修复 | 仅保留待审索引，验证集不用于调参。 |

`AC-ASE-003` 和 `RE-POP-048` 仍因原始报告与预定类别不符而剔除。没有建立锁定测试集，也没有把任何补丁版本自动标为“安全”。本次新增报告与修复文件均位于 Git 忽略的 `.local/first-batch/`；URL、固定版本、SHA-256 和组 ID 的引用见[分配清单](evidence/S3/first-batch-assignment.json)与[泄漏报告](evidence/S3/first-batch-leakage-report.json)。

### 可重放的原件获取与门禁

以下命令只获取已经登记的六份新增原件；首次运行前需有 `curl` 和 Python 3。任何上游正文变化都会导致后续摘要校验失败，应核对版本，不得静默改写清单。

```bash
mkdir -p .local/first-batch/reports .local/first-batch/patches
python3 - <<'PY'
import json
import subprocess
from pathlib import Path

reports = {
    'AC-ASE-006': ('2024-07-basin-findings', 52),
    'AC-ASE-009': ('2024-04-gondi-findings', 64),
    'AC-ASE-030': ('2023-09-maia-findings', 885),
    'RE-POP-077': ('2024-02-ai-arena-findings', 37),
}
for identifier, (repo, issue) in reports.items():
    url = f'https://api.github.com/repos/code-423n4/{repo}/issues/{issue}'
    data = json.loads(subprocess.run(['curl', '-fsSL', '--max-time', '30', url],
                                     check=True, capture_output=True).stdout)
    raw = (data['body'].rstrip() + '\n').encode('utf-8')
    path = Path('.local/first-batch/reports') / f'{identifier}.md'
    if path.exists() and path.read_bytes() != raw:
        raise ValueError(f'{identifier} 已有报告与上游不同')
    if not path.exists():
        path.write_bytes(raw)

patches = {
    'AC-ASE-006': 'https://raw.githubusercontent.com/code-423n4/2024-08-basin/7e08ff591df0a2ade7d5618113dda2621cd899bc/src/WellUpgradeable.sol',
    'AC-ASE-030': 'https://raw.githubusercontent.com/Maia-DAO/2023-09-maia-remediations/2209d6e96af986fa0960aacc356ba2be070fdc85/src/VirtualAccount.sol',
}
for identifier, url in patches.items():
    raw = subprocess.run(['curl', '-fsSL', '--max-time', '30', url],
                         check=True, capture_output=True).stdout
    path = Path('.local/first-batch/patches') / f'{identifier}.sol'
    if path.exists() and path.read_bytes() != raw:
        raise ValueError(f'{identifier} 已有修复源码与固定版本不同')
    if not path.exists():
        path.write_bytes(raw)
PY
PYTHONPATH=tools/experiment python3 tools/experiment/first_batch.py audit \
  --intake docs/vibe/releases/R1/evidence/S3/first-batch-intake.json \
  --assignment docs/vibe/releases/R1/evidence/S3/first-batch-assignment.json --root .
```

PoolTogether 两份原件的获取命令仍见[原分组说明](research/S3_FIRST_BATCH_SPLIT.md)。当前门禁输出为 `ok=true`、跨划分错误 0、近克隆候选 0、`pendingSamples=8`、`readyForFormalSnapshot=false`。`ok` 仅表示**已登记材料的谱系隔离正确**，并非八项已准入。

### 正式快照阻塞

S3 门禁要求来源、报告、补丁、漏洞位置和独立审核标签形成闭环。当前知识侧只有 PoolTogether 具备可核对的原始漏洞与修复源码，AI Arena 没有可回读修复源码；两者都缺独立逐事件标签与目标—案例适用性判断。Milvus 中现有的两个 `mvp_` 集合均是三条词法哈希演示片段，`researchEligible=false`；第二个是原件清单更新后重建的当前工程快照，旧集合作为历史保留。**本次没有创建或激活 `s1b_` 正式集合，正式激活指针不存在。**待补齐真实修复对和独立标签、复核两个方向的知识案例后，才能按 S1b 原子构建、完整读回并切换正式指针。

<a id="s9-review"></a>

## R1-S9 独立评审与修复记录

2026-10-10。评审范围为本轮源码、八项验收条件及真实运行边界。采用独立代理执行 review、deslop-shared-libs 和 cso 的适用检查；受限辅助器不满足只读精确范围时使用原生追踪与本地反例。所有已确认的阻断已修复并复核，随后主执行者重新运行完整 Java/Python 和 Chromium 验收。

| 已确认问题 | 最终修复 | 证据 |
|---|---|---|
| 大小写相近的函数可能绑定到首个声明；合约伪声明影响校验 | 精确声明优先，大小写容错仅唯一候选；名称匹配读取屏蔽注释/字符串的源码 | Java 假设服务 23 项回归；独立 Java 探针通过 |
| 临时权限接管随后被同资源写入覆盖仍称可达 | 按展开执行顺序检查覆盖，保留 UNKNOWN 和覆盖事实引用 | 本函数、修饰器后置覆盖与有效接管红绿 |
| 权限消费入口重置权限、附加检查或不可公开到达仍支持攻击 | 只证明完整公开的同 authority CHECK→敏感 WRITE/CALL 两步直线路径；其他入口保留 UNKNOWN | D2 新七项回归；独立原否例 UNKNOWN、正例 SUPPORTED，引用可解析 |
| 模型等待期间修改配置会改变工具消费；Python/Java 属性解析或空白凭证可绕过冻结 | 捕获文本与环境、严格语法准入、重序列化、删除环境回退；模型和工具使用权限 600 的临时快照并清理 | [根因调查](investigations/S9_CONFIG_DEBUG.md)、三项配置回归、实际 Java 消费独立复核与 loopback 整链 |
| 同一行多合约/函数的其他假设可替代所选目标 | FUNCTION 严格绑定声明、类别、摘要和片段；FULL 允许全文真实声明 | 同行、重载、错类别、FULL 其他函数/合约与批量回归 |
| 拒绝假设或校验问题漏出反驳汇总 | 拒绝项使“全部反驳/无发现”保持未决，已有确证漏洞和原模型用量保留 | 单样本及批量聚合回归 |
| 工作台 HTML 可被其他页面嵌入 | HTTP CSP `frame-ancestors 'none'`、`X-Frame-Options: DENY` | 新 HTTP 响应红绿；安全复核关闭；8771 实际头验证 |
| Java D1 EvidenceBundle 没有执行 status，实际页面运行中断 | 身份校验后的策略适配统一补 COMPLETED；失败历史保留 | 实际浏览器发现、专门回归、重启后两条完整流程 |

消肿结论：单样本、既有审计入口和批量统一复用 `assess`/`final_conclusion`；保留模型统计与流水线统计的不同职责。复用原 BenchmarkRuntime、Ollama 和 Milvus 快照，不另建附件提到但仓库不存在的 `vector_cache.py`。未发现需要新增共享库或并行重复缓存的理由。

安全结论限于本轮本机接口与配置：输入/模型只作为文本节点，来源、字段、大小、并发、一次性票据和历史摘要均有验证；不会把工具异常映射为安全。不以本次限定评审宣称全仓库安全或 D2 完整形式化证明。

最终新鲜验证：Java 75、Python 245 项，无失败和跳过；Chromium 控制台零错误；完整矩阵与原始证据见 [VERIFICATION](VERIFICATION.md#s9-verification)。
