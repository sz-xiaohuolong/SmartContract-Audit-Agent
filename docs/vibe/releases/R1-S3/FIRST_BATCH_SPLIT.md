# 首批案例的知识与检测分配

更新：2026-09-26。用户确认首批范围用于非商业毕业设计实验。本文件给出**项目级预分配和已执行的源码隔离结果**；`knowledge` 表示知识候选，不等于已激活正式知识快照。真实防御补丁、逐事件报告与独立标签未齐备前，正式 Milvus 集合保持未激活。

## 数据集分别做什么

数据集名称只表示发现案例的入口。实际划分按项目、漏洞事件、补丁对和近克隆组进行；同一项目的源码、报告、修复前后代码和知识文档必须留在同一侧。

| 来源 | 本轮用途 | 限制 |
|---|---|---|
| ASE 2025 访问控制基准 | 从中选 PoolTogether 作知识候选；Basin、Gondi 作开发检测目标；Maia 作验证目标 | 不按“整个 ASE 数据集”统一放一侧，逐项目隔离；TraitForge H-06 暂剔除 |
| SCRUBD V6.0 重入索引 | DexBlue、MonkeyScam 作开发检测目标；ViVICO 作验证目标 | 仅能确认固定源码与数据集标签行，尚无逐事件原始报告或真实修复；不产生安全负例 |
| Proof-of-Patch 修复线索 | AI Arena H-08 作重入知识候选；用于寻找真实修复对 | 不是独立真值来源；AI Arena 修复原件仍不可取得，Caviar H-01 不按重入使用 |
| SmartBugs Curated | 后续知识案例的补充来源 | 本次十项先导中未导入；先核对原项目和与检测侧的重复/近克隆，再选择少量案例，不整库灌入 |
| ACFix | 本轮不用 | 模型生成修复不作为真实防御补丁 |

## 十项候选的去向

| 位置 | 访问控制 | 重入 | 数量 |
|---|---|---|---:|
| 知识候选 | PoolTogether `AC-ASE-040` | AI Arena `RE-POP-077` | 2 |
| 开发检测 | Basin `AC-ASE-006`、Gondi `AC-ASE-009` | DexBlue `RE-SCRUBD-001`、MonkeyScam `RE-SCRUBD-002` | 4 |
| 独立验证 | Maia `AC-ASE-030` | ViVICO `RE-SCRUBD-003` | 2 |
| 本轮剔除 | TraitForge `AC-ASE-003` | Caviar `RE-POP-048` | 2 |

TraitForge [H-06 原始报告](https://code4rena.com/reports/2024-07-traitforge)描述错误修饰器导致铸造／锻造失败，暂不按未经授权访问案例使用。Caviar [H-01 原始报告](https://code4rena.com/reports/2023-04-caviar)是版税接收方抽干池子，关联的[维护者 PR 12](https://github.com/outdoteth/caviar-private-pools/pull/12)修正版税计算，不是可核实的重入补丁对。PoolTogether [H-04 报告](https://code4rena.com/reports/2023-07-pooltogether)与[PR 7](https://github.com/GenerationSoftware/pt-v5-vault/pull/7)在 `mintYieldFee` 处对应：修复移除任意接收方参数，改用预设接收方。本机已固定[原始 finding 396](https://github.com/code-423n4/2023-07-pooltogether-findings/issues/396)正文和[修复提交 50bd158](https://github.com/GenerationSoftware/pt-v5-vault/commit/50bd158089d890eb759da67282bf5b5238a3a22a)源码，两份原件摘要与知识候选事件组绑定；独立标签仍待审。AI Arena [H-08 报告](https://code4rena.com/reports/2024-02-ai-arena)明确写出 `claimRewards()` 的重入路径，但名单所指修复仓库仍无法取回。

十份固定版本源码已重新下载到本机 `.local/first-batch/sources/`，逐项 SHA-256 与[原名单](evidence/first-batch-intake.json)一致。八个未剔除项目的[分组报告](evidence/first-batch-leakage-report.json)显示知识 2、开发 4、验证 2，当前项目/事件/字节/已发现近克隆跨划分冲突 0；两个剔除项与入选项也没有达到当前近克隆阈值。该检查不能证明不存在其他语义克隆，且补丁与报告原件尚未加入关联图。八项均保持待审；安全负例 0，锁定测试集 0，正式知识快照和 Milvus 激活数 0。

## 重放与进入正式知识库的条件

在仓库根目录运行：

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/first_batch.py fetch \
  --intake docs/vibe/releases/R1-S3/evidence/first-batch-intake.json \
  --assignment docs/vibe/releases/R1-S3/evidence/first-batch-assignment.json --root .
mkdir -p .local/first-batch/reports .local/first-batch/patches
curl -fsSL 'https://api.github.com/repos/code-423n4/2023-07-pooltogether-findings/issues/396' \
  | python3 -c 'import json,sys;from pathlib import Path;Path(".local/first-batch/reports/AC-ASE-040.md").write_text(json.load(sys.stdin)["body"],encoding="utf-8")'
curl -fsSL 'https://raw.githubusercontent.com/GenerationSoftware/pt-v5-vault/50bd158089d890eb759da67282bf5b5238a3a22a/src/Vault.sol' \
  -o .local/first-batch/patches/AC-ASE-040.sol
PYTHONPATH=tools/experiment python3 tools/experiment/first_batch.py audit \
  --intake docs/vibe/releases/R1-S3/evidence/first-batch-intake.json \
  --assignment docs/vibe/releases/R1-S3/evidence/first-batch-assignment.json --root .
```

最后一条命令完全离线，生成 `.local/first-batch/ledger.json` 和 `leakage-report.json`，并核对两份 PoolTogether 原件摘要。若上游原始 finding 正文后来改变，摘要会不符，须人工比对并更新证据版本；不能悄悄替换。待取得其余真实报告、修复前后代码与审核标签后，把所有原件及知识文档绑定到相同事件组，再运行 S3 谱系门禁，准备 embedding 向量和快照完整性读回；只有检验成功才切换正式 Milvus 激活指针。当前两条知识候选都还不能作为完整的经独立审核的漏洞／防御正反例对，因此不构造“安全”代码、不制造向量，也不发布冒充正式库的集合。
