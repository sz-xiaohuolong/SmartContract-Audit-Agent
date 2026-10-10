# 访问控制与重入真实案例先导盘点

更新：2026-10-10。对应 R2-09 与 R2-11，仅记录当前取得的原件、既有审核和编译依赖缺口。本轮已取得两组真实项目依赖并核对原锁；编译与程序证据仍在单独核验。新增模型请求为0，正式划分未调整。

## 结论与事实源

已定位十个独立项目的原始漏洞事件：六项已有正式准入记录，四项仍待审。十项不是十组已经独立审核的真实正反对，也不证明 D1 或 D2 的研究效果。当前最适合先实现的是知识侧 RabbitHole 访问控制与 Atomic Loans 重入两组；它们各有原报告和真实维护者修复，且差异可以绑定到明确的函数与资源。

现行划分读取本机 [formal-v2 账本](../../../../../.local/r1-s5/formal-v2/ledger.json)，并与跟踪的 [formal-v2 镜像](../../../../../data/audit/r1/formal-expansion/formal-v2-ledger.json)核对。原报告、补丁对应范围及许可的具体说明以 [S3 准入记录](../../R1/attachments/D1_KB_READINESS.md)、[Atomic 版本链](../../../../../data/audit/r1/first-batch/d1-kb-v1-atomic-version-chain.json)、[S5 原件审核](../../../../../.evidence/R1/S5/source-review.json)为准。

本轮重新计算六个正式事件的 18 份源码／报告／补丁 SHA-256，均与账本匹配；S5 九份 Git 原件镜像也全部匹配。机器盘点记录位于被忽略的 [本机清单](../../../../../.local/r2/real-case-inventory.json)，逐件保留实际摘要、登记摘要、匹配状态与依赖检查。这里的摘要匹配只证明原件一致，不产生新的漏洞审核或安全负例。

`.local/` 原件和机器清单仅在本机；文档能定位它们，不代表另一台机器已经具备全部原件。S5 九份原件有 Git 镜像；其他原件取得方式见上述来源文档。

## 六项既有正式事件

### 1. Maia：AC-ASE-030／H-01／VirtualAccount.payableCall

- 源码：[漏洞原件](../../../../../.local/first-batch/sources/AC-ASE-030.sol)，168 行，Solidity `^0.8.0`。
- 报告：[原件正文](../../../../../.local/first-batch/reports/AC-ASE-030.md)，原始 Code4rena finding [#885](https://github.com/code-423n4/2023-09-maia-findings/issues/885)。
- 修复：[维护者修复源码](../../../../../.local/first-batch/patches/AC-ASE-030.sol)；漏洞版本 `f5ba4de628836b2a29f9b5fff59499690008c463`，修复版本 `2209d6e96af986fa0960aacc356ba2be070fdc85`。
- 许可：源码文件 MIT；该文件声明不是整个来源集合的再分发许可结论。
- 划分／审核：`knowledge`，账本 `REVIEWED`／`REAL_PATCH`。真实修复在目标函数加入 `requiresApprovedCaller`。
- 缺口：权限包含外部 `IRootPort.isRouterApproved` 与 owner 两条分支；现有轻量事实提取不等于完整权限覆盖。需要 Solady、Solmate、OpenZeppelin、两个项目接口及相关外部权限语义。不能凭修饰器名称声称 D2 已证实。

### 2. Atomic Loans：RE-ATOMIC-001／审计第 6.6 节／Loans.pull

- 源码：[补丁前原件](../../../../../.local/first-batch/sources/RE-ATOMIC-001.sol)，343 行，Solidity `^0.5.8`；[本地上游 Git 仓库](../../../../../.local/atomicloans-upstream)保留历史对象。
- 报告：[原报告正文](../../../../../.local/first-batch/reports/RE-ATOMIC-001.md)，ConsenSys Diligence [原始审计第 6.6 节](https://github.com/ConsenSysDiligence/atomic-loans-audit-report-2019-07#66-reentrancy-attack-on-loanspull-can-lead-to-draining-funds)。
- 修复：[维护者修复源码](../../../../../.local/first-batch/patches/RE-ATOMIC-001.sol)，已合并 [PR #23](https://github.com/AtomicLoans/atomicloans-eth-contracts/pull/23)。审计版本 `3632e622e0b3fedf468866db0b878b7b74dd757e`，补丁基线 `697f12d3eb0772a059a165ec50f02c265bd3dd43`，补丁版本 `17adcc19c977c77273f07be3bd73123bf46e18a0`。
- 许可：[固定仓库 MIT 原件](../../../../../.local/first-batch/licenses/RE-ATOMIC-001.md)。
- 划分／审核：`knowledge`，账本 `REVIEWED`／`REAL_PATCH`。修复将 `bools[loan].off = true` 移到全部分支的外部转账之前；入口 `off(loan)` 读取同一资源。
- 缺口：三版本项目七文件及对应 OpenZeppelin Solidity 2.2.0／2.3.0 已固定导出，包摘要与原锁匹配；本机 solc 0.5.8 可执行。依赖取得不等于真实编译或路径核验已完成。

### 3. RabbitHole：AC-RABBIT-001／H-01／RabbitHoleReceipt.mint

- 源码：[漏洞原件](../../../../../.local/r1-s5/sources/AC-RABBIT-001.sol)，195 行，Solidity `^0.8.15`；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/sources/AC-RABBIT-001.sol)。
- 报告：[原件正文](../../../../../.local/r1-s5/reports/AC-RABBIT-001.md)；Code4rena finding [#608](https://github.com/code-423n4/2023-01-rabbithole-findings/issues/608)；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/reports/AC-RABBIT-001.md)。
- 修复：[真实补丁原件](../../../../../.local/r1-s5/patches/AC-RABBIT-001.sol)；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/patches/AC-RABBIT-001.sol)；已合并 [PR #86](https://github.com/rabbitholegg/quest-protocol/pull/86)。审计版本 `8c4c1f71221570b14a0479c216583342bd652d8d`，补丁父版本 `93fd452ecf0bf0725d73d5ed0d7640e3ee6f4299`，修复版本 `8e1bc90f619dfafba1fbfbac39c9249b8885e64a`。审计文件与补丁父版本目标文件字节相同。
- 许可：文件 MIT，来源审核记录仓库 GPL-3.0；两种声明不一致，保留来源归属与冲突事实。
- 划分／审核：`knowledge`，账本 `REVIEWED`／`REAL_PATCH`。第 59 行裸地址比较改为 `require`，第 98 行 `mint` 消费 `onlyMinter`。
- 缺口：三个固定版本的四份项目源码、原锁和构建配置已取得；真实闭包分别含24／28／28源码单元，缺失导入为0。原报告复现需要代理初始化，不能直接实例化被 `_disableInitializers` 锁定的实现合约后假定路径有效。

### 4. PoolTogether：AC-ASE-040／H-04／Vault.mintYieldFee

- 源码：[漏洞原件](../../../../../.local/first-batch/sources/AC-ASE-040.sol)，1232 行，Solidity `0.8.17`。
- 报告：[原报告正文](../../../../../.local/first-batch/reports/AC-ASE-040.md)，Code4rena finding [#396](https://github.com/code-423n4/2023-07-pooltogether-findings/issues/396)。
- 修复：[维护者修复源码](../../../../../.local/first-batch/patches/AC-ASE-040.sol)，[PR #7](https://github.com/GenerationSoftware/pt-v5-vault/pull/7)。漏洞版本 `b1deb5d494c25f885c34c83f014c8a855c5e2749`，修复版本 `50bd158089d890eb759da67282bf5b5238a3a22a`。
- 许可：目标源码 MIT。
- 划分／审核：`validation`，账本 `REVIEWED`／`REAL_PATCH`。补丁移除任意接收方参数，改为 `_mint(_yieldFeeRecipient, _shares)`。
- 缺口：这是固定收益接收方机理，不能描述为增加调用者权限。源码依赖 ERC4626、TwabController、PrizePool、LiquidationPair 等多个项目；补丁还有编译版本和依赖别名变化。验证侧保留，不用作先导调参。

### 5. JPEG’d：RE-JPEGD-001／YVault.deposit

- 源码：[漏洞原件](../../../../../.local/r1-s5/sources/RE-JPEGD-001.sol)，203 行，Solidity `^0.8.0`；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/sources/RE-JPEGD-001.sol)。
- 报告：[原报告正文](../../../../../.local/r1-s5/reports/RE-JPEGD-001.md)，Code4rena finding [#81](https://github.com/code-423n4/2022-04-jpegd-findings/issues/81)；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/reports/RE-JPEGD-001.md)。
- 修复：[真实补丁原件](../../../../../.local/r1-s5/patches/RE-JPEGD-001.sol)；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/patches/RE-JPEGD-001.sol)；已合并 [PR #19](https://github.com/jpegd/core/pull/19)。审计版本 `e72861a9ccb707ced9015166fbded5c97c6991b6`，补丁父版本 `641ecd6247636fb5d1402b115a074bf71ac8c0f4`，修复版本 `5eb2e19e71c949503664017183d65f19c72ed2f9`。
- 许可：文件 GPL-3.0；独立仓库许可尚未核实。
- 划分／审核：`validation`，账本 `REVIEWED`／`REAL_PATCH`。审计版与补丁父版仅目标函数正文逐行相同，整文件不同。
- 缺口：修复将 `safeTransferFrom` 移到总供应量读取与份额计算之后，`_mint` 仍在转账之后；不能使用泛化“所有状态写必须早于调用”规则判断该修复。攻击还依赖代币回调、非零初始池状态、`noContract` 白名单或构造期路径。验证侧保留，不用作先导调参。

### 6. Infinity：RE-INFINITY-001／InfinityExchange.matchOneToManyOrders

- 源码：[漏洞原件](../../../../../.local/r1-s5/sources/RE-INFINITY-001.sol)，1270 行，Solidity `0.8.14`；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/sources/RE-INFINITY-001.sol)。
- 报告：[原报告正文](../../../../../.local/r1-s5/reports/RE-INFINITY-001.md)，Code4rena finding [#184](https://github.com/code-423n4/2022-06-infinity-findings/issues/184)；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/reports/RE-INFINITY-001.md)。
- 修复：[项目方修复源码](../../../../../.local/r1-s5/patches/RE-INFINITY-001.sol)；[Git 镜像](../../../../../data/audit/r1/formal-expansion/originals/patches/RE-INFINITY-001.sol)；项目方指定 [修复提交](https://github.com/infinitydotxyz/exchange-contracts-v2/commit/b90e746fa7af13037e7300b58df46457a026c1ac)。审计版本 `bb8d35a07051204cb0d4b77fd30e60ec186c9e24`，补丁父版本 `5a3f81b82a9bee2de7517b3a5f18953cb5ec3684`，修复版本 `b90e746fa7af13037e7300b58df46457a026c1ac`。
- 许可：文件 MIT；独立仓库许可尚未核实。
- 划分／审核：`validation`，账本 `REVIEWED`／`REAL_PATCH`。目标入口加入 `nonReentrant`，整文件还有其他变化。
- 缺口：攻击从订单匹配内部转账路径回调至 `takeOrders`，需要相关内部调用、订单 nonce 资源、两个入口共享锁和回调能力证据。不能把函数中的内部 helper 当作已证明的直接外部调用。验证侧保留，不用作先导调参。

## 四项仍待审事件

### 7. Basin：AC-ASE-006／H-01／WellUpgradeable._authorizeUpgrade

- 源码：[漏洞原件](../../../../../.local/first-batch/sources/AC-ASE-006.sol)，133 行，Solidity `^0.8.20`；版本 `7d5aacbb144d0ba0bc358dfde6e0cc913d25310e`。
- 报告：[原报告正文](../../../../../.local/first-batch/reports/AC-ASE-006.md)，finding [#52](https://github.com/code-423n4/2024-07-basin-findings/issues/52)。
- 修复：[后续修复审查源码](../../../../../.local/first-batch/patches/AC-ASE-006.sol)，版本 `7e08ff591df0a2ade7d5618113dda2621cd899bc`。目标加入 `onlyOwner`，同时还有代理条件和 token 校验变化。
- 许可／划分／审核：文件 MIT；历史候选 `development`，尚未正式准入。
- 缺口：精确引入修复提交、完整版本链及独立标签未完成。升级路径依赖 Well、Aquifer、UUPS 和 Ownable；修复审查状态证据不自动证明任意升级入口均受保护。

### 8. Gondi：AC-ASE-009／H-03／LiquidationDistributor.distribute

- 源码：[漏洞原件](../../../../../.local/first-batch/sources/AC-ASE-009.sol)，123 行，Solidity `^0.8.21`；版本 `b9863d73c08fcdd2337dc80a8b5e0917e18b036c`。
- 报告：[原报告正文](../../../../../.local/first-batch/reports/AC-ASE-009.md)，finding [#64](https://github.com/code-423n4/2024-04-gondi-findings/issues/64)。
- 修复：本地没有可核对修复源码。修复审查范围 `195e6122474a3b9f5abb7fa9d02ffc79181c0b7f` 的 README 引用 `fix/64`，该引用不能代替源码。
- 许可／划分／审核：文件 AGPL-3.0；历史候选 `development`，尚未正式准入。
- 缺口：维护者真实修复原件、精确版本、修复覆盖和独立标签均缺；漏洞涉及伪造 ERC20、LoanManager 回调与 Pool 记账，不能只看 distribute 的签名。

### 9. AI Arena：RE-POP-077／Proof-of-Patch 077／H-08／MergingPool.claimRewards

- 源码：[首批原件](../../../../../.local/first-batch/sources/RE-POP-077.sol)；[完整原版仓库中的目标文件](../../../../../.local/dataset-candidates/proof-of-patch/findings/077/2024-02-ai-arena/src/MergingPool.sol)，212 行；固定版本 `b05b54a9eb5b0964bde9825f75305caa2d943155`。
- 报告：[原始报告正文](../../../../../.local/first-batch/reports/RE-POP-077.md)，finding [#37](https://github.com/code-423n4/2024-02-ai-arena-findings/issues/37)。
- 修复：[数据集保留的补丁源码](../../../../../.local/dataset-candidates/proof-of-patch/patches/077/2024-02-ai-arena/src/MergingPool.sol)，加入 ReentrancyGuard 与 nonReentrant；元数据指向维护者 [PR #6](https://github.com/ArenaX-Labs/2024-02-ai-arena-mitigation/pull/6)。
- 许可／划分／审核：目标文件 MIT，Proof-of-Patch 仓库未声明许可；历史正式候选被排除，S8 将数据集材料作为待审线索保留，未取得新正式划分。
- 缺口：尚未固定维护者补丁原样版本及版本链。Foundry 配置 solc 0.8.13，forge-std 本地有源码，OpenZeppelin 子模块没有 Solidity 源码；目标还通过 FighterFarm 的 NFT 铸造产生回调。不能把历史被替换的正式槽自动恢复。

### 10. Cooler：Proof-of-Patch 049／rollLoan

- 源码：[审计仓库中的目标文件](../../../../../.local/dataset-candidates/proof-of-patch/findings/049/2023-08-cooler/Cooler/src/Cooler.sol)，428 行，Solidity `^0.8.15`；外层审计仓库固定版本 `6d34cd12a2a15d2c92307d44782d6eae1474ab25`。
- 报告：原事件主问题 [#243](https://github.com/sherlock-audit/2023-08-cooler-judging/issues/243)，重复报告 [#200](https://github.com/sherlock-audit/2023-08-cooler-judging/issues/200)。本地只有 [数据集摘录](../../../../../.local/dataset-candidates/proof-of-patch/annotations/049.txt)和 [S8 来源核对](../../R1/VERIFICATION.md#r1-model-comparison)，没有这两项原始 issue 的固定正文；数据集元数据还指向 #26。
- 修复：[数据集补丁文件](../../../../../.local/dataset-candidates/proof-of-patch/patches/049/2023-08-cooler/Cooler/src/Cooler.sol)给 rollLoan 加调用者检查。维护者 [PR #54](https://github.com/ohmzeus/Cooler/pull/54)实际整体更换贷款延期流程，不能把数据集单行检查叫作该 PR 原样修复。
- 许可／划分／审核：目标文件 MIT；尚无正式划分，未正式准入。
- 缺口：主原报告正文、真实维护者修复源码及版本、完整攻击与修复覆盖和独立标签均缺。源码涉及 immutable-args clone、贷款条款与所有者；本地 lib 子模块目录存在但依赖源码未取得。

## 两组优先先导的完整编译依赖检查

### Atomic Loans

原审计 `3632e622…`、补丁前 `697f12d…` 与补丁后 `17adcc19…` 均从固定 Git 对象导出七份原项目文件：Loans、Funds、Sales、DSMath、Medianizer、Currency、Vars。补丁前后除 Loans 的状态写入移动外，其他项目源码与构建锁一致；原审计版的 Loans、Funds、Sales 与依赖锁另有差异，三版分别保留。

| 项目 | 固定事实与收据 |
|---|---|
| 编译器 | 原 truffle.js 为 solc **0.5.8**；本机相应二进制已探测成功 |
| 编译设置 | optimizer disabled，runs 200，evmVersion byzantium |
| 补丁前／后依赖 | 原 yarn.lock 锁 OpenZeppelin Solidity **2.3.0**；真实包已取得并核完整性 |
| 审计版依赖 | 原 package-lock.json 锁 **2.2.0**；真实包已取得；同提交旧 yarn.lock 的1.12.0冲突保留 |
| 环境目录 | `.local/r2/environments/atomic-{audited,before,after}/` |
| 导出与包收据 | `.local/r2/dependencies/atomic-export.json`、`openzeppelin-receipt.json` |

未使用当前仓库 HEAD 或替身依赖。依赖取得与 AST 编译属于不同证据；攻击／修复复现还需要实际部署、外部代币回调和状态前提的证据。

### RabbitHole

已取得审计 `8c4c1f7…`、补丁父 `93fd452…`、修复 `8e1bc90…` 三版原仓库归档。188份仓库文件及652份包文件逐件摘要回读通过；目标文件三版均匹配正式原件。原项目闭包为 RabbitHoleReceipt、ReceiptRenderer、IQuestFactory、IQuest；其余来源为对应原锁的真实 OpenZeppelin 包。

| 项目 | 固定事实与收据 |
|---|---|
| 编译器 | 原 Hardhat 配置锁 **0.8.15**；package 中的 JS solc 0.6.11不是项目编译器 |
| 编译设置 | optimizer enabled，runs 5000；未设置 viaIR／EVM版本 |
| 依赖 | 原 yarn.lock 锁 `@openzeppelin/contracts` 与 `contracts-upgradeable` **4.8.0**；SHA-512 integrity和SHA-1匹配 |
| 递归闭包 | 审计／父版／修复版24／28／28源码单元，missingImports均为0 |
| 环境目录 | `.local/r2/environments/rabbit-{audited,before,after}/`；各有标准JSON输入及环境收据 |
| 获取收据 | `.local/r2/dependencies/rabbit-acquisition.json`、`openzeppelin-rabbit-receipt.json` |
| 编译器取得 | `.local/r2/compilers/download-receipt.json`；0.8.15官方SHA-256核验并实际执行版本命令成功 |

审计版与补丁父版的目标文件相同，其他项目文件不同，因此不合并环境身份。三版仓库LICENSE为GPLv3，目标文件MIT声明冲突保留。编译不安装完整JavaScript测试依赖，也不省略Solidity源码依赖；攻击路径还须核对原代理初始化，不能由闭包无缺失推断权限漏洞或修复已经复现。

## 其他线索与历史裁决

- **Caviar RE-POP-048**：本地原版／PoP 补丁均存在，版本 `5c87f7d69c6fac29eb253b5c7b2fb4a9f23f8750`，文件 MIT，Foundry 0.8.19。但 [d1-kb-assignment](../../../../../data/audit/r1/first-batch/d1-kb-assignment.json)明确排除其作为重入补丁对。注释涉及回调期间改变版税，与历史类别裁决存在解释差异；应重新核原始 finding 与维护者 PR12，不自动恢复。本机依赖子模块目录为空。
- **MileVerse AutoMESC**：`automesc-selected.json` 中 `am_3ddefa391e5cd90c84eb563d3d581de38bed6d41` 指向开发者提交 `2c62075324a28437e763b9e83c1071e8f764d7ce`，将 transferWithLockUp 加 onlyOwner。当前只有局部 CSV 差异，完整两版、原报告、许可、父版本和独立安全审核均缺；它是调查线索，不计入十项原始事件或正式真实对。
- **OMarket AutoMESC**：`b6839bdea865704264e30a9ccc6612367f704950` 被自动提示为 AC，但旧版已经通过 helper 检查 admin；直接 mapping 检查和移除只读函数限制不自动证明安全修复。
- **TraitForge AC-ASE-003、SCRUBD 索引、Cally PoP054／098**：已有类别不符或原始报告／修复缺口，不能为扩大数量转正。

旧 first-batch 分配曾记录 Maia 为 validation、PoolTogether 为 knowledge；现行 formal-v2 为 Maia knowledge、PoolTogether validation。旧记录代表当时划分，本轮不改写；AI Arena 正式重入槽已由 Atomic 替换，也不恢复。正式知识、独立验证、待审候选和自动标注层继续隔离。

`REVIEWED`／`INDEPENDENT` 表示已有外部漏洞裁决与原件／修复准入记录，不表示本项目 D2 条件、目标—案例适用性、全路径覆盖或修复后整份合约已获独立审核。后续先导应固定条件、源码版本和基线契约，并分别记录 TRUE、FALSE、UNKNOWN；真实编译、路径核验和方法效果以统一验收矩阵的独立证据为准，不由本盘点转正。
