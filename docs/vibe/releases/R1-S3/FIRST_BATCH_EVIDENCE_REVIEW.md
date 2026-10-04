# 首批真实案例原件复核与正式快照准入

更新：2026-10-04。结论：**知识 2、开发检测 4、验证 2 的项目级划分维持；正式知识快照仍不得激活。**八项固定源码的摘要与分组门禁通过，新增原始报告四份、修复版本两份。当前五项有逐事件报告，三项有修复源码或修复版本；但八项均没有符合 S3 契约的独立逐事件标签，重入知识候选还缺可回读的修复源码。报告与修复版本的存在不自动证明修复充分，也不产生安全负例。

## 划分与原件

| ID | 划分 | 原始报告 | 修复证据 | 当前结论 |
|---|---|---|---|---|
| `AC-ASE-040` PoolTogether H-04 | 知识候选 | [原始 finding #396](https://github.com/code-423n4/2023-07-pooltogether-findings/issues/396) | [维护者 PR #7](https://github.com/GenerationSoftware/pt-v5-vault/pull/7)、固定修复提交 `50bd158` | 报告指向 `Vault.sol:394` 的任意接收方参数；修复版本移除该参数并改用 `_yieldFeeRecipient`。修复是否覆盖完整攻击路径仍需独立审核。 |
| `RE-POP-077` AI Arena H-08 | 知识候选 | [原始 finding #37](https://github.com/code-423n4/2024-02-ai-arena-findings/issues/37) | [Code4rena 修复审查范围](https://github.com/code-423n4/2024-04-ai-arena-mitigation/blob/ac5b626ddb3e8005ec452e61b4fee8390438e118/README.md)引用维护者 PR #6，但维护者仓库返回 404 | 重入报告可固定；修复源码不可回读，不能构成真实正反补丁对。 |
| `AC-ASE-006` Basin H-01 | 开发检测 | [原始 finding #52](https://github.com/code-423n4/2024-07-basin-findings/issues/52) | [后续修复审查固定源码](https://github.com/code-423n4/2024-08-basin/blob/7e08ff591df0a2ade7d5618113dda2621cd899bc/src/WellUpgradeable.sol) | 原版 `_authorizeUpgrade` 无 `onlyOwner`，审查版加入该限制；审查版是修复状态证据，尚未定位精确引入提交。 |
| `AC-ASE-009` Gondi H-03 | 开发检测 | [原始 finding #64](https://github.com/code-423n4/2024-04-gondi-findings/issues/64) | [修复审查范围](https://github.com/code-423n4/2024-05-gondi-mitigation/blob/195e6122474a3b9f5abb7fa9d02ffc79181c0b7f/README.md)列出 `fix/64`，维护者源码仓库当前不可取得 | 报告明确 `distribute()` 缺调用者限制；缺可固定的修复源码。 |
| `RE-SCRUBD-001` DexBlue、`RE-SCRUBD-002` MonkeyScam | 开发检测 | 无逐事件原始报告 | 无真实修复 | SCRUBD 标签行与固定源码匹配，仅作待审索引，不当作已证实漏洞。 |
| `AC-ASE-030` Maia H-01 | 验证 | [原始 finding #885](https://github.com/code-423n4/2023-09-maia-findings/issues/885) | [维护者修复提交 `2209d6e`](https://github.com/Maia-DAO/2023-09-maia-remediations/commit/2209d6e96af986fa0960aacc356ba2be070fdc85) | 原版 `payableCall` 缺 `requiresApprovedCaller`；修复提交增加该修饰器。验证集不用于调参。 |
| `RE-SCRUBD-003` ViVICO | 验证 | 无逐事件原始报告 | 无真实修复 | 仅保留待审索引，验证集不用于调参。 |

`AC-ASE-003` 和 `RE-POP-048` 仍因原始报告与预定类别不符而剔除。没有建立锁定测试集，也没有把任何补丁版本自动标为“安全”。本次新增报告与修复文件均位于 Git 忽略的 `.local/first-batch/`；URL、固定版本、SHA-256 和组 ID 的引用见[分配清单](evidence/first-batch-assignment.json)与[泄漏报告](evidence/first-batch-leakage-report.json)。

## 可重放的原件获取与门禁

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
  --intake docs/vibe/releases/R1-S3/evidence/first-batch-intake.json \
  --assignment docs/vibe/releases/R1-S3/evidence/first-batch-assignment.json --root .
```

PoolTogether 两份原件的获取命令仍见[原分组说明](FIRST_BATCH_SPLIT.md)。当前门禁输出为 `ok=true`、跨划分错误 0、近克隆候选 0、`pendingSamples=8`、`readyForFormalSnapshot=false`。`ok` 仅表示**已登记材料的谱系隔离正确**，并非八项已准入。

## 正式快照阻塞

S3 门禁要求来源、报告、补丁、漏洞位置和独立审核标签形成闭环。当前知识侧只有 PoolTogether 具备可核对的原始漏洞与修复源码，AI Arena 没有可回读修复源码；两者都缺独立逐事件标签与目标—案例适用性判断。Milvus 中现有的两个 `mvp_` 集合均是三条词法哈希演示片段，`researchEligible=false`；第二个是原件清单更新后重建的当前工程快照，旧集合作为历史保留。**本次没有创建或激活 `s1b_` 正式集合，正式激活指针不存在。**待补齐真实修复对和独立标签、复核两个方向的知识案例后，才能按 S1b 原子构建、完整读回并切换正式指针。
