# 当前重构开发约定（2026-09-19）

所有新增说明、注释和文档使用简体中文。

用户已明确要求直接在当前本地项目目录开发，不使用隔离工作树；保留已有未提交修改。
每完成一个小版本并通过相应验证后，先检查待提交内容与凭证，再在当前主目录提交并同步至远程 `origin/main`；若远程已有新提交，先整合并重新验证。未完成的小版本不得以完成名义同步。

- Python 离线工具验证：`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`；实现位于 `tools/experiment/`。
- 文档恢复：先读 `docs/vibe/PROJECT.md` 的唯一文档地图和 `docs/vibe/PROGRESS.md` 首屏，再按当前任务读取地图中的规格、架构、计划或验证入口。
- Slice 组织：同一 Release 内的切片记录在统一实施计划的 Slice Map 和进度表中，不新增切片独立目录或整套规格／计划／验证文件；存量目录按地图标明职责，移动前核对代码与证据引用。
- 文档结构：`docs/vibe/` 根目录只维护 PROJECT、PROGRESS、TECH_DESIGN；各 Release 的基线、规格、目标方案、计划和验收放在 `docs/vibe/releases/<release-id>/`。Slice 只进入统一计划与当前进度。
- 原始证据：新增日志、运行 dump 和截图放 `.evidence/<release-id>/<task-id>/`，默认 Git 忽略；已有长期证据继续跟踪。配置、来源登记、源码和测试夹具分别放数据或工具目录，不当作原始日志归档。
- R1 历史基线：`docs/vibe/releases/R1/PROJECT_BRIEF.md`；当前 R2 的有效文档通过唯一地图定位。
- 根构建使用 Java 21、Spring Boot 4.1.1、Spring AI 2.0.1；默认模块 `audit-mvp`。
- 默认验证：`mvn clean verify`；命令行：`java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help`。
- 测试不得依赖真实 API、Milvus 或工具环境；使用本地 HTTP 与子进程夹具。
- 不将调用异常、解析错误、超时或缺失工具结果映射为安全；usage 缺失必须保留 null。
- 凭证可来自环境变量或被 Git 忽略的 `config/providers.local.properties`；不得提交真实密钥。真实模型调用须显式选择配置，不自动批量实验或更换计费端点。
- 数据入口：`data/README.md`；公开知识文档位于 `data/benchmarks/smartbugs-curated/`，历史合约基准位于 `data/benchmarks/legacy-testset/`。迁移保留原件字节与标签。
- 旧应用已退役；当前构建仅使用 `audit-mvp`，旧 Java、测试、配置与独立构建不再维护。历史代码通过 Git 恢复，当前架构以 TECH_DESIGN 为准。
