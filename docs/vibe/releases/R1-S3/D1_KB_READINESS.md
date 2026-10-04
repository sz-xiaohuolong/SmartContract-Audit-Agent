# D1 首版正式知识快照与数据划分

更新：2026-10-04。首版正式知识快照已在本机 Milvus 激活。它包含两个独立项目的真实漏洞—修复对，共四条语义向量：访问控制 Maia `VirtualAccount.payableCall`、重入 Atomic Loans `Loans.pull`。PoolTogether `Vault.mintYieldFee` 仅列入独立验证侧，不进入知识库。这个结果证明数据准入、向量入库、全量读回和召回链路可用；**尚无独立审核的目标—案例适用性标签，不报告 D1 效果提升**。

## 为什么这样选

| 用途 | 项目与事件 | 原始证据 | 固定修复 | 准入判断 |
|---|---|---|---|---|
| 知识：访问控制 | `AC-ASE-030`，Maia H-01 | [Code4rena finding #885](https://github.com/code-423n4/2023-09-maia-findings/issues/885)，包含复现和项目方确认 | [维护者修复提交](https://github.com/Maia-DAO/2023-09-maia-remediations/commit/2209d6e96af986fa0960aacc356ba2be070fdc85)在 `payableCall` 加入 `requiresApprovedCaller` | 原版第 85 行无该修饰器；修复版第 89 行加入。条件字段 `CHECK_BEFORE` 可由两版源码直接核对。 |
| 知识：重入 | `RE-ATOMIC-001`，Atomic Loans 审计第 6.6 节 | [ConsenSys Diligence 原报告](https://github.com/ConsenSysDiligence/atomic-loans-audit-report-2019-07#66-reentrancy-attack-on-loanspull-can-lead-to-draining-funds) | [已合并 PR #23](https://github.com/AtomicLoans/atomicloans-eth-contracts/pull/23)将 `bools[loan].off = true` 移到外部转账之前 | 报告审计范围 `Loans.sol` 的 SHA-1 `72400480e986cbf206ef249bd14aca6c28833df3`，与上游提交 `3632e622e0b3fedf468866db0b878b7b74dd757e` 的文件**完全一致**；从该提交到 PR 基线 `697f12d3eb0772a059a165ec50f02c265bd3dd43`，`pull` 中只增加 ERC20 返回值检查，风险顺序未变；PR 头提交 `17adcc19c977c77273f07be3bd73123bf46e18a0` 修正顺序。 |
| 验证候选：访问控制 | `AC-ASE-040`，PoolTogether H-04 | [Code4rena finding #396](https://github.com/code-423n4/2023-07-pooltogether-findings/issues/396)，包含项目方确认 | [维护者 PR #7](https://github.com/GenerationSoftware/pt-v5-vault/pull/7)将任意指定接收方改为固定 `_yieldFeeRecipient` | 它的防护机理是**固定接收方**，不是加入调用权限修饰器。现有 D1 `CHECK_BEFORE` 字段不能诚实描述其防御侧，因此不作该条件的知识对；仅保留为隔离的目标候选。 |

[准入裁决](evidence/d1-kb-v1-decisions.json)固定源码摘要、漏洞位置、原始报告正文摘要、MIT 许可证原件和修复配对行号；Atomic 的[审计版—修复版版本链](evidence/d1-kb-v1-atomic-version-chain.json)单独保留；[准入清单](evidence/d1-kb-v1-ledger.json)与[知识配对](evidence/d1-kb-v1-pairs.json)由脚本生成。`INDEPENDENT` 在本版指**相对于本项目的外部原始审计裁决**，不是声称外部审计方重新审核了本项目的 D1 字段或目标—案例相关性。对 PoolTogether 与 Maia，源码文件声明 MIT；Atomic Loans 使用固定提交的仓库 MIT 许可证。报告正文保留来源引用，不把修复片段当作“整份合约安全”负例。

原始 11 项候选排除 3 项；余下 8 项中仅上述 3 项满足首版原件与标签准入。Basin、Gondi 和 3 个 SCRUBD 案例继续待审，**没有为凑数量制造标签**。首版 [泄漏报告](evidence/d1-kb-v1-leakage-report.json)为知识 2、验证 1、开发 0、锁定测试 0，跨划分冲突 0、已发现近克隆候选 0、首版待审 0。`pendingSamples=0` 仅针对这 3 个准入项；其余 5 项的待审状态见原[候选泄漏报告](evidence/d1-kb-leakage-report.json)。近克隆扫描不能证明不存在未发现的语义克隆。

## 向量、Milvus 与当前结果

使用 [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) 的固定提交 `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`，384 维，本地离线编码。文件从 [BAAI ModelScope 镜像](https://modelscope.cn/models/BAAI/bge-small-en-v1.5)获取，十个文件逐一按[模型摘要清单](../../../../tools/experiment/d1-embedding-model.json)校验；权重 `model.safetensors` 的 SHA-256 为 `3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad`。依赖版本见 [`d1-embedding-requirements.lock`](../../../../tools/experiment/d1-embedding-requirements.lock)。不使用此前工程演示库的词法哈希向量，也没有调用付费模型 API。

[快照收据](evidence/d1-kb-v1-snapshot-receipt.json)记录快照 `9fc63d0e8828a8caa78145e133b8f954f9fedaf79469ea0927434d7dbef725c8`，本机 Milvus 集合 `s1b_612ad26b068c4b64842463a633d6d1ba`，四条文档。S1b 原子激活先构建新集合、强一致性读回每个 ID／正文／向量，再更新 `.local/d1-kb-snapshots/active.json`。四条向量的自检索均命中自身；对 PoolTogether 验证目标的本地和 Milvus 召回排序完全一致。这只是**技术链路冒烟检查**，排序不代表适用性或漏洞检测准确率。Attu 在本机 `http://127.0.0.1:3000`，可查看该集合；原 `mvp_` 工程演示集合没有被覆盖。

D1 检索契约已允许访问控制风险操作为对外调用，Maia 案例的元数据据实标为 `CALL`。但现有轻量事实提取器对 Maia 的继承、分支和修饰器返回 `PARTIAL`，其 `payableCall` 条件绑定仍应为 `UNKNOWN`；**不能因为补丁中出现修饰器字样，就报告自动事实证明或 D1 适用性成功**。早期试建的 `s1b_2f8522116d6b43e693092c303947be6a` 集合未被修改，但已退出激活指针；在 Attu 中以本节收据所列集合为准。

## 重放

从项目根目录执行。首批固定源码、报告、补丁的获取与摘要见[原件复核](FIRST_BATCH_EVIDENCE_REVIEW.md)；缺少这些原件时，应先按该文档下载并验证。所有生成文件写入 Git 忽略的 `.local/`。首版决策与候选清单摘要绑定；若重取源码后摘要不一致，准入会拒绝。

```bash
PYTHONPATH=tools/experiment python3 tools/experiment/first_batch.py audit \
  --intake docs/vibe/releases/R1-S3/evidence/d1-kb-intake.json \
  --assignment docs/vibe/releases/R1-S3/evidence/d1-kb-assignment.json \
  --root . --output-dir .local/d1-kb-candidates

PYTHONPATH=tools/experiment python3 tools/experiment/d1_admission.py \
  --candidate-ledger .local/d1-kb-candidates/ledger.json \
  --decisions docs/vibe/releases/R1-S3/evidence/d1-kb-v1-decisions.json \
  --root . --output-dir .local/d1-kb-v1

uv venv .local/d1-embed-venv --python 3.12
uv pip install --python .local/d1-embed-venv/bin/python -r tools/experiment/d1-embedding-requirements.lock
PYTHONPATH=tools/experiment python3 tools/experiment/d1_model.py --model-dir .local/d1-embedding-model
PYTHONPATH=tools/experiment HF_HUB_OFFLINE=1 .local/d1-embed-venv/bin/python tools/experiment/d1_embed.py \
  --ledger .local/d1-kb-v1/ledger.json --pairs .local/d1-kb-v1/pairs.json \
  --root . --output-dir .local/d1-kb-v1 --model-dir .local/d1-embedding-model

PYTHONPATH=tools/experiment python3 tools/experiment/d1_kb.py \
  --ledger .local/d1-kb-v1/ledger.json --pairs .local/d1-kb-v1/pairs.json \
  --vector-bundle .local/d1-kb-v1/candidate-vectors.json \
  --root . --snapshot-root .local/d1-kb-snapshots

PYTHONPATH=tools/experiment python3 tools/experiment/s1b.py snapshot-verify \
  --root .local/d1-kb-snapshots \
  --id 9fc63d0e8828a8caa78145e133b8f954f9fedaf79469ea0927434d7dbef725c8
```

在**新环境首次**构建并激活本机 Milvus 集合时，调用 `snapshots.activate_snapshot(root, id, MilvusRestIndex('http://127.0.0.1:29531'))`；已有集合用 `active_snapshot(root, index)` 只读校验，避免重复建立新集合。`recall.py` 通过 `--milvus-url http://127.0.0.1:29531` 从已激活集合生成同一候选池；目标向量必须由上述同一模型编码。完整命令、输出摘要和测试见 [验证记录](VERIFICATION.md)。

Atomic 版本链可在独立上游克隆中核对：`git show 3632e622e0b3fedf468866db0b878b7b74dd757e:contracts/Loans.sol | shasum -a 1` 应返回报告所列 SHA-1；`git diff 3632e622e0b3fedf468866db0b878b7b74dd757e 697f12d3eb0772a059a165ec50f02c265bd3dd43 -- contracts/Loans.sol` 可核对 PR 前风险顺序未变。

## 下一步研究边界

需要让独立审核员逐一标注**目标—案例适用性、支持与反证价值及 UNKNOWN**，并补充其他项目的真实开发目标；目前首版开发准入为 0。只有这些标签齐备、固定真实 tokenizer 与完整提示预算后，才能在相同快照和候选池下运行 D1 与简单条件字段过滤等强基线并解释差异。不得用这次自检索排序或 PoolTogether 的单个冒烟目标推断 D1 科研效果；锁定测试集未打开。
