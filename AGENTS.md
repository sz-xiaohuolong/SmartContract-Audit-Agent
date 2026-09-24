# 当前重构开发约定（2026-09-19）

所有新增说明、注释和文档使用简体中文。

用户已明确要求直接在当前本地项目目录开发，不使用隔离工作树；保留已有未提交修改。
每完成一个小版本并通过相应验证后，先检查待提交内容与凭证，再在当前主目录提交并同步至远程 `origin/main`；若远程已有新提交，先整合并重新验证。未完成的小版本不得以完成名义同步。

- Python 离线工具验证：`PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v`；实现位于 `tools/experiment/`。
- S0 基础切片：`docs/vibe/releases/R1-S0/SPEC.md`，执行计划位于同目录。
- 根构建使用 Java 21、Spring Boot 4.1.1、Spring AI 2.0.1；默认模块 `audit-mvp`。
- 默认验证：`mvn clean verify`；命令行：`java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --help`。
- 测试不得依赖真实 API、Milvus 或工具环境；使用本地 HTTP 与子进程夹具。
- 不将调用异常、解析错误、超时或缺失工具结果映射为安全；usage 缺失必须保留 null。
- 凭证仅环境变量；真实模型调用须显式选择配置，不自动批量实验或更换计费端点。
- 旧 `src/` 通过 `legacy/pom.xml` 单独构建；以下旧架构说明仅适用于该历史代码，不是新模块规范。

---

# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Build
mvn clean install -DskipTests

# Run all tests
mvn test

# Run specific test class
mvn test -Dtest=SmartContractDetectTest

# Run single test method
mvn test -Dtest=SmartContractDetectTest#doChatWithRag

# Run experiment with specific mode
mvn test -Dtest=VeriRAGExperimentTest#runFullExperiment -Dmode=Vanilla
mvn test -Dtest=VeriRAGExperimentTest#runFullExperiment -Dmode=RAG-Only
mvn test -Dtest=VeriRAGExperimentTest#runFullExperiment -Dmode=VeriRAG-Full

# Start application (requires Milvus running)
mvn spring-boot:run
```

## Prerequisites

- **Java 21** (required by Spring Boot 3.4.10)
- **Python venv** at `venv/` with Slither and Mythril installed (tools invoke via `venv/bin/myth` and system `slither`)
- **Milvus** running at localhost:19530 (vector database for RAG)
- **Dashscope API keys** configured in `application-coding-plan.yml`

## Architecture

### Core Service: SmartContractDetect (src/main/java/com/xhl/xhlaiagent/app/)

Three audit modes with different capabilities:

| Mode | LLM | RAG | Tools | Method |
|------|-----|-----|-------|--------|
| Vanilla | ✓ | ✗ | ✗ | `auditVanilla()` |
| RAG-Only | ✓ | ✓ | ✗ | `auditRAGOnly()` |
| VeriRAG-Full | ✓ | ✓ | Slither/Mythril | `auditFullAgent()` |

### Tool Engine Integration

- **SlitherTool**: Static analysis, 30s timeout, filters High/Medium severity issues
- **MythrilTool**: Symbolic execution, 60s execution timeout + 90s process timeout, higher precision for complex logic bugs
- Both tools: create temp directory → write `.sol` → execute → parse JSON output → cleanup

### RAG Pipeline (src/main/java/com/xhl/xhlaiagent/rag/)

- **ContractAppDocumentLoader**: Loads SmartBugs Curated markdown docs with YAML front matter
- **MilvusVectorStoreConfig**: Checks if dataset exists, chunks documents (6000 chars, 400 overlap), batch inserts
- **SafeQuestionAnswerAdvisor**: Custom advisor that injects retrieved documents into prompt (topK=3, threshold=0.5)

### Configuration Profile

Profile `coding-plan` activates OpenAI-compatible interface to Alibaba Dashscope Coding Plan:
- **ChatModel bean**: `dashscopeChatModel` (created by `CodingPlanConfig`, NOT standard Dashscope auto-config)
- **HTTP timeouts**: connect=60s, read=300s (critical for long LLM responses)
- **Embedding**: Dashscope text-embedding-v3, dimension=1024

### Key Design Decisions

1. **Spring AI Tool Calling**: `.tools(allTools)` only registers tools; LLM decides whether to call. To force tool usage, modify the system prompt or manually invoke before LLM call.

2. **API Rate Limiting**: `VeriRAGExperimentTest` implements exponential backoff retry (MAX_RETRIES=3, INITIAL_DELAY=1s, MAX_DELAY=30s) plus inter-request delay (1s) to avoid QPS/RPM limits.

3. **RAG Knowledge Base**: Only documents with `metadata.dataset='smartbugs-curated'` are imported. Use `filterExpression("dataset == 'smartbugs-curated'")` to scope searches.

### Test Dataset Structure

```
src/main/resources/testset/
├── buggy_contracts/         ← SolidiFI-benchmark (GT=true)
│   ├── Re-entrancy/
│   ├── Overflow-Underflow/
│   └── ...
└── safe_contracts/          ← Clean contracts (GT=false)
```

Experiment samples MAX_SAMPLES_PER_CATEGORY=3 per vulnerability type, uses fixed seed (42L) for reproducibility.

### Output Format

All modes return `SmartContractAnalysisResult`:
```json
{
  "hasVulnerability": true|false,
  "vulnerabilityType": "漏洞类型",
  "vulnerabilityReason": "原因简述"
}
```
