# 研究原件与可复核产物

本目录保存真实实验响应、固定候选、检索快照、编译与工具收据。人类阅读的实验报告仍位于 `docs/vibe/releases/R2-20261010/experiments/`；原始产物按运行编号组织，与源码、本机环境及可读报告分开。

```text
research-artifacts/
├── runs/benchmarks/             原始模型批次、计划、事件和逐样本结果
├── runs/derived/                保存候选的零模型派生重放
├── runs/audits/、workbench/     单合约与工作台历史
├── snapshots/                  BGE、Nomic 与历史知识快照
├── inputs/                     固定历史输入及基线编译原件
├── receipts/                   Slither、EVM 与编译双收据
├── diagnostics/                模型解析失败的原始响应
├── archives/                   历史大型原件的无损归档
└── migrations/                 本机迁移、原件摘要与压缩清单
```

## 一键整理

在项目根目录执行：

```bash
python3 tools/experiment/organize_storage.py --apply --restart-ui
```

省略 `--apply` 只预览目录映射。重复执行不会复制数据或覆盖冲突目录；活动实验或持有写锁的批次会阻止整理。`--restart-ui` 仅短暂停止并恢复本项目的本机页面，使其加载归档读取支持；不调用模型、向量服务或工具后端。未完成批次保留可续写的原始 JSONL。

目录重命名前后核对文件字节及链接。历史清单、计划、事件、候选、来源标签和原始摘要不改写；旧 `.local/` 与 `.evidence/` 入口保留相对兼容链接，指向本目录中的同一份内容。新写入入口直接使用规范目录。虚拟环境入口和历史绝对路径仍需要这些链接，不应手工删除。

## 历史归档与新输出

已完成批次的大型 JSONL、重复汇总和 CSV，以及大型工具 JSON，使用 gzip 无损压缩。程序通过 `storage.read_artifact()` 按逻辑文件名读取原始字节，重放与页面下载继续核对解压后的原始摘要。归档损坏、超限或来源冲突时报错，不能映射成安全或空成功。

新模型批次的 `summary.json` 只保存统计、计划及 `samples.jsonl` 指针；完整样本只存一份，CSV 按下载请求生成。历史汇总保持原始字节，仅改变压缩编码；即使两批内容近似，也不合并付费响应或改写历史候选。

本目录原件默认不提交 Git，README、生成工具、来源登记和可读报告继续版本控制。它们仍需与正式论文一起备份到用户选择的长期存储；当前没有配置远程原件归档，Git 同步不包含这些文件。跨机器恢复需要复制原件目录、按本机重新生成兼容入口，再核对迁移清单中的摘要。

本机环境位于 `.local/envs/`、`.local/models/`、`.local/services/` 和 `.local/solidity/`；唯一恢复材料位于 `.local/recovery/`。下载的外部仓库位于 `data/external/`，正式数据入口与来源登记见 [数据说明](../data/README.md)。
