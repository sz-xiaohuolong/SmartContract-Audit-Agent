# S1 数据与实验基础实施计划

使用 `superpowers:executing-plans` 在当前主目录逐项执行；保留已有未提交文件。

目标：落实 [SPEC](SPEC.md) 的 S1a/S1b 工程范围。技术栈为 Python 标准库和已有 Java CLI，不引入服务依赖，不迁移旧集合。用户 2026-09-21 明确授权 S1b 实现；以下为内部实现选择。

## 已完成 S1a

只读 inventory、严格 evaluate 及 7 项离线测试，保留原验证记录。

## S1b 执行顺序

- [x] T1 分组隔离：新增 `isolation.py` 与 `tests/test_isolation.py`。接受人工审核的来源、项目组、克隆组、字节组和 split；对全部样本统一验证，同组不得跨划分；knowledge 文档必须继承原样本谱系。先用同字节、同项目、近似克隆和缺审核信息的夹具证明拒绝，再实现。
- [x] T2 知识快照：新增 `snapshots.py` 与 `tests/test_snapshots.py`。快照绑定完整清单、文档内容、分块参数、embedding 模型与维度；逐条验证向量、ID、数量和哈希。先写半构建、内容损坏、索引缺项测试，再实现临时目录构建、完整验证后原子发布和激活指针替换。索引通过可注入适配接口读回核对，离线文件索引用于确定性验收；旧集合不修改。
- [x] T3 批处理：新增 `batch.py` 与 `tests/test_batch.py`。计划绑定源码、规范类型映射、配置、执行产物和知识快照；单写者锁内每个 START/RESULT 事件 fsync 到 JSONL。先验证中断、尾部残行、配置变化、重复记录、失败负例，再实现 run/resume/replay。完成和失败记录默认跳过；有 START 无 RESULT 的调用保留为不确定，不自动付费重试。显式指定样本方可重试失败/不确定项。Replay 只读日志，复用 evaluate。
- [x] T4 命令与文档：提供离线快照及隔离命令、显式 Java 批处理入口、子进程夹具端到端测试，更新工具 README、PROJECT/PROGRESS 与 VERIFICATION。
- [x] T5 验证与复审：运行 Python 全套、`mvn clean verify`、CLI 帮助和 diff 检查；按 `requesting-code-review` 进行独立复审，修复重要问题并记录证据。

## 重点检查

1. 调用已发出但结果未持久化：默认不得盲目重发，无法保证跨外部 API 的 exactly-once。
2. JSONL 只有末尾非完整行可恢复，完整行损坏必须拒绝；重放不修改原日志。
3. 恢复前校验全部源码、配置和产物；不得到批处理中途才发现输入漂移。
4. 半成品、重复 ID、非有限向量和索引读回不符不能更新 active；失败保持旧快照。
5. 划分校验不能只比较 sample ID；项目/克隆/源码关联与知识衍生文档同样参与。

## 验证命令

```bash
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
mvn clean verify
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
git diff --check
```

不自动提交、推送或发布；不运行真实模型、embedding 或 Milvus。真实部署适配的连通性不计入离线验证结论。

## 本轮执行记录（2026-09-21）

- T1/T2/T3 首次运行分别因新模块尚不存在而失败；随后各自离线测试通过。T4 命令闭环首次因入口尚不存在而失败，实现后通过。
- 补充未映射类型 usage 测试明确复现 `12 != None`，定位为类型映射失败统一丢弃结果；修复后保留原始响应和实际 usage，仍计 FAILED。
- 独立复审及增量复核未发现阻断问题；另外补齐 RESULT 落盘中断、多页索引读回、冻结 JAR/配置三项边界测试。最终 35 项 Python 与 19 项 Java 测试通过。
- 实现选择：JSONL 本身作为 checkpoint；in-flight 调用保守记录为 UNRESOLVED，显式重试才重新调用。知识块由调用方提供，避免在本轮隐式运行 embedding 或改动旧集合。
- 本轮保持未提交状态，未执行外部发布。证据见 [VERIFICATION](VERIFICATION.md)。
