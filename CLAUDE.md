# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
