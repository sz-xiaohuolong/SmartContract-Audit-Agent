# D1 正式知识库候选与准入状态

更新：2026-10-04。**已形成访问控制与重入各一组真实漏洞—修复知识候选，正式知识快照和 `s1b_` Milvus 集合尚未激活。**本轮把 AI Arena 从正式重入知识位置移出，换入经用户批准的 Atomic Loans；原有 AI Arena 工程演示资料保持原样。正式候选清单为 11 项，排除 3 项，剩余知识 2、开发检测 4、验证 2。谱系检查发现跨划分冲突 0、近克隆候选 0；八项仍为待审，不能据此报告 D1 效果。

## 知识配对和原件

| 方向 | 漏洞案例 | 原始报告 | 修复对 | 待复核事项 |
|---|---|---|---|---|
| 访问控制 | `AC-ASE-040` PoolTogether `Vault.mintYieldFee`，原版第 394–402 行 | [Code4rena H-04 finding #396](https://github.com/code-423n4/2023-07-pooltogether-findings/issues/396)，含项目方确认标签 | [维护者 PR #7](https://github.com/GenerationSoftware/pt-v5-vault/pull/7)，修复版删除调用者可控接收方，改用 `_yieldFeeRecipient` | 原始报告有建议代码笔误；必须以真实修复源码判断这条路径的覆盖，不把整份合约视为安全。 |
| 重入 | `RE-ATOMIC-001` Atomic Loans `Loans.pull`，原版第 298–316 行 | [ConsenSys Diligence 审计报告 6.6](https://github.com/ConsenSysDiligence/atomic-loans-audit-report-2019-07#66-reentrancy-attack-on-loanspull-can-lead-to-draining-funds) | [维护者 PR #23](https://github.com/AtomicLoans/atomicloans-eth-contracts/pull/23)，把 `bools[loan].off = true` 移到外部转账之前 | 报告列出的审计范围文件 SHA-1 为 `72400480e986cbf206ef249bd14aca6c28833df3`，PR 修复前固定版本为 `433dafd38f49abef191e0defc00420c83e0621c1`。两版整文件不同，报告所述关键函数顺序与修复前版本一致；逐行版本对应仍须独立审核。 |

Atomic Loans 的源码、补丁、报告和仓库 MIT 许可证均固定在 Git 提交，分别由[候选清单](evidence/d1-kb-intake.json)、[划分清单](evidence/d1-kb-assignment.json)及本机 `.local/first-batch/` 原件保存 SHA-256。报告仓库没有可核对的独立许可声明；仅保留来源引用并用于非商业论文内部核验。修复后的片段只表示该报告所述风险路径获得相应防护，不构造“整份合约安全”的负例。

[成对片段审查表](evidence/d1-kb-pairs-review.json)记录指定函数、源码和补丁行号、条件字段与证据 ID，`reviewed=false`。这些条件是供复核的提议，尚未成为 D1 正式案例元数据。开发与验证中的 Gondi 和 SCRUBD 项仍缺真实补丁或逐事件原始报告；Basin 只有后续修复审查版，并非精确修复提交。[泄漏报告](evidence/d1-kb-leakage-report.json)的 `pendingSamples` 完整列出八项。

## 建库机制与阻塞

新增 `tools/experiment/d1_kb.py` 复用 S3 谱系审计与 S1b 原子快照：仅当**所有参与样本**的来源、补丁、报告、独立标签均审核通过，且知识配对审查表精确覆盖知识样本时，生成每组漏洞／修复两个文档、S1b 全量清单和 D1 条件 catalog。文档继承同一 `sample_id`、项目组和补丁对 ID。向量必须逐文档提供，写入后通过原有快照校验；此命令只构建，不激活。激活仍需 Milvus 全量读回完全一致。

当前不可运行正式构建的原因有两个：八项独立标签未完成，其中部分原始报告或补丁缺失；尚未冻结并生成**真实语义向量**。本机工程演示用的 128 维词法哈希向量不能转成正式向量。可选的本地模型为 [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)，官方模型卡声明 MIT，2026-10-04 查询的模型提交为 `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`；这只是待验证的选型，尚未安装、跑向量或冻结 token 化／依赖版本。

## 本机重放

原有八份源码及六份报告／补丁的获取方式见[首批复核记录](FIRST_BATCH_EVIDENCE_REVIEW.md)。Atomic Loans 固定原件可用以下命令下载，随后运行隔离审计；所有原件写入 Git 忽略目录，任何已存在文件应先核对摘要，不可覆盖不一致版本。

```bash
mkdir -p .local/first-batch/{sources,reports,patches,licenses}
curl -fsSL https://raw.githubusercontent.com/AtomicLoans/atomicloans-eth-contracts/697f12d3eb0772a059a165ec50f02c265bd3dd43/contracts/Loans.sol -o .local/first-batch/sources/RE-ATOMIC-001.sol
curl -fsSL https://raw.githubusercontent.com/AtomicLoans/atomicloans-eth-contracts/17adcc19c977c77273f07be3bd73123bf46e18a0/contracts/Loans.sol -o .local/first-batch/patches/RE-ATOMIC-001.sol
curl -fsSL https://raw.githubusercontent.com/ConsenSysDiligence/atomic-loans-audit-report-2019-07/987823cd198eef4119e57b12e42385e8799a7142/README.md -o .local/first-batch/reports/RE-ATOMIC-001.md
curl -fsSL https://raw.githubusercontent.com/AtomicLoans/atomicloans-eth-contracts/697f12d3eb0772a059a165ec50f02c265bd3dd43/LICENSE.md -o .local/first-batch/licenses/RE-ATOMIC-001.md
PYTHONPATH=tools/experiment python3 tools/experiment/first_batch.py audit --intake docs/vibe/releases/R1-S3/evidence/d1-kb-intake.json --assignment docs/vibe/releases/R1-S3/evidence/d1-kb-assignment.json --root . --output-dir .local/d1-kb-candidates
```

`d1_kb.py` 的 `--ledger` 指向上述审计生成的清单；`--pairs` 指向审查完成后的配对表，`--vectors` 与 `--embedding` 必须来自同一固定真实模型，`--snapshot-root` 为专用本机目录。**当前命令会因待审标签拒绝构建；不得把 `reviewed` 改成 `true` 作为运行捷径。**

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/d1_kb.py \
  --ledger .local/d1-kb-candidates/ledger.json \
  --pairs docs/vibe/releases/R1-S3/evidence/d1-kb-pairs-review.json \
  --vectors /经核验的向量文件.json --embedding /固定模型元数据.json \
  --root . --snapshot-root .local/d1-kb-snapshots
```

下一步先补齐独立逐事件复核与缺失原件，剔除仍无法确认的检测项；再锁定本地 embedding 运行环境，计算文档和目标同模型向量，通过完整读回后才激活 `s1b_` 集合。D1 真实对照应复用同一快照、候选池和完整提示 token 预算；不打开锁定测试集调参。
