# 项目数据

原始公开数据集使用仓库根目录已保留的 `smartbugs-curated/` 与 `SolidiFI-benchmark/`。本目录维护来源登记、固定实验输入、额外对照和示例，避免再复制一整套公开数据。

```text
data/
├── datasets.json               原始数据集版本与内容校验登记
├── controls/openzeppelin/      50 份额外展平对照
├── audit/
│   ├── r1/                     来源审核、配对、划分和已登记原件
│   └── r2/                     固定编译输入清单与路径候选
├── examples/contracts/         3 份未重复的历史示例
└── reference/                  漏洞参考资料
```

## 原始数据来源

| 数据 | 原始入口 | 当前用途 |
|---|---|---|
| SmartBugs Curated | `../smartbugs-curated/dataset/` 与 `../smartbugs-curated/vulnerabilities.json` | 直接读取 Solidity 字节与类别、来源、漏洞行；当前筛选访问控制和重入案例，另做知识侧重复检查 |
| SolidiFI benchmark | `../SolidiFI-benchmark/buggy_contracts/` | 350 份注入漏洞源码和 350 份 CSV；可生成离线清单，未自动加入当前批量目标 |
| OpenZeppelin 对照 | `controls/openzeppelin/` | 额外来源；当前加载器选择其中 4 份作探索性阴性对照 |

两个原始仓库继续由 Git 忽略，版本、上游地址和输入内容摘要记录在 [datasets.json](datasets.json)。缺少本机原始仓库时，应按登记的地址与 `revision` 恢复；实验工具不自动下载或回退到旧副本。SolidiFI 的旧工具运行结果目录不属于本次登记的输入范围。

校验摘要按相对路径排序，将每个输入文件的 `{path, sha256}` 列表编码为 UTF-8 紧凑 JSON 后取 SHA-256；SmartBugs 的 JSON 标注单独登记摘要。离线测试使用最小原始数据集夹具，不要求下载这两个仓库。

## 对照、固定输入与示例

OpenZeppelin 展平文件保留原字节与旧样本编号，源码带有来源和许可证说明；完整生成版本尚未登记，不能把文件头的更新时间当作完整依赖版本。其历史“安全”标签只属于来源标签，不构成安全证明，研究准入仍为 `false`。

`audit/r1/`、`audit/r2/` 是机器读取的固定输入与登记包，目录标识属于已保存实验的身份；整理公开数据副本不改变其内容、路径或历史划分。历史运行原件按 [研究原件说明](../research-artifacts/README.md) 保存到 `research-artifacts/`，关键日志和核对记录放 `.evidence/`；历史登记的旧路径通过兼容入口读取同一份原件。

剩余示例与参考资料用于历史演示和阅读，不自动进入评测。重复的 `Overflow15.sol` 已移除，原件位于 `../SolidiFI-benchmark/buggy_contracts/Overflow-Underflow/buggy_15.sol`。

## 2026-10-12 去重记录

删除 143 份可从 SmartBugs 重建的 Markdown、700 份与 SolidiFI 完全相同的副本及 1 份重复示例，共 844 份文件。50 份额外对照移至 `controls/openzeppelin/`，内容不变。旧加工文件可通过提交 `56ebdf5` 复核。

原 53 个批量目标的编号、漏洞类型、标签值和漏洞行保持一致。新加载器保留原始空白与行号，不再经过 Markdown 代码块提取；其中 29 个目标的输入摘要仅因空白恢复而改变。新目标记录源码路径、标注路径及标注摘要，`documentHash` 不再代表已删除的 Markdown；已保存实验与历史摘要保持原记录，不可直接以新输入续写旧计划。
