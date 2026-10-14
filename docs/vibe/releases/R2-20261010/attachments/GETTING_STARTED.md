# 快速上手：先看演示，再核验真实合约

从项目根目录运行下面三条命令，可以构建命令行程序并启动本机工作台。第一次体验建议使用合成演示；它无需模型账号或 Solidity 工具。

## 环境要求

| 环境 | 用途 | 入门演示是否需要 |
|---|---|---|
| Java 21、Maven | 构建 Java 网关和执行 CLI | 下面的构建与帮助命令需要 |
| Python 3 | 启动本机 HTTP 服务、执行分析与统计 | 需要；近期工程分别有 Python 3.12 和 3.14 的验证记录 |
| solc | 把 Solidity 编译成 AST、ABI 和字节码 | 合成演示不需要；真实核验按源码版本固定编译器 |
| Slither | 提供程序分析和风险告警 | 合成演示不需要；真实静态核验需要 |
| Anvil、cast | 执行可选的本机 EVM 业务见证 | 仅显式启用有限执行提供器时需要 |
| Nomic 快照、Ollama、Milvus | 提供本机知识检索 | 合成演示不需要；完整检索流程需要恢复并配置 |

根构建使用 Spring Boot 4.1.1、Spring AI 2.0.1，仅构建 `audit-mvp`。Maven 首次运行可能需要下载依赖。

运行前确认 `java -version` 与 `mvn -version` 都显示 Java 21。两者可能使用不同的 Java 安装位置；若 Maven 版本输出中的 Java 不符，需要把 `JAVA_HOME` 指向 JDK 21。

## 三条命令启动演示

```bash
mvn clean verify
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help
PYTHONPATH=tools/experiment python3 tools/experiment/local_ui.py --port 8765
```

第一条运行 Java 检查并生成 JAR；第二条显示参数帮助；第三条持续运行本机服务。打开 [工作台](http://127.0.0.1:8765/agent.html)，在输入区选择“粘贴源码”，点击“合成演示”。页面会读取仓库中的合成案例，展示源码、三策略资料和报告布局。此演示不执行 D2，六项检查保持未知。

关闭服务时，在启动它的终端按 `Ctrl+C`。端口已占用可换成 `--port 8766`，浏览器地址也相应更改。

## 在本机核验 SimpleDAO

确认 `config/tools.local.properties` 已配置固定 solc 与 Slither。字段格式见 [工具配置示例](../../../../../config/tools.example.properties)，不同 Solidity 版本的编译器要与源码 `pragma`（版本约束）一致。

在同一页面选择“重入 · SimpleDAO · 公开学术基准”，点击“离线演练”。这条路径会真实执行本机编译、Slither 与 D2，复用登记候选；知识服务暂不可用时，仍可进行登记候选的核验。工具齐备且输入一致时，既有本机记录中的候选结果是“支持”。

如果结果仍是未知或运行失败，展开工具诊断，先检查编译器版本、Slither 路径和代码依赖。缺工具时得到未知是预期的失败处理，不能拿合成演示代替真实核验。

JSON 下载应包含候选、六项检查、源码位置及实际编译清单。真实模型模式需要单独配置；离线演示和离线演练均可在没有模型凭证时执行。

## 开发者检查与研究恢复

Python 离线检查命令为：

```bash
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
```

测试使用本地 HTTP 和子进程夹具，不依赖真实 API、Milvus 或外部工具。真实实验的历史响应、编译收据和固定工具有部分只保存在本机；仅克隆 Git 仓库可以启动合成演示，尚不能恢复全部历史实验身份。恢复入口见 [原件说明](../../../../../research-artifacts/README.md)，逐步核验方法见 [运行审计附录](OPERATIONS_AND_REPRODUCIBILITY.md)。

更多参数见 [工具说明](../../../../../tools/experiment/README.md)。返回 [唯一文档地图](../../../PROJECT.md)。
