package com.xhl.xhlaiagent.app;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.xhl.xhlaiagent.advisor.JsonNormalizationAdvisor;
import com.xhl.xhlaiagent.advisor.MyLoggerAdvisor;
import com.xhl.xhlaiagent.app.model.ContractAuditHypothesis;
import com.xhl.xhlaiagent.chatmemory.FileBasedChatMemory;
import com.xhl.xhlaiagent.constant.FileConstant;
import com.xhl.xhlaiagent.rag.SafeQuestionAnswerAdvisor;
import com.xhl.xhlaiagent.rag.model.SmartContractAnalysisResult;
import com.xhl.xhlaiagent.tools.MythrilTool;
import com.xhl.xhlaiagent.tools.SlitherTool;

import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

@Component
@Slf4j

public class SmartContractDetect {

    private final ChatClient chatClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    // 系统提示词
    // 简单的 System Prompt (用于 Baseline )
    private static final String BASIC_SYSTEM_PROMPT = """
            你是一名智能合约安全专家。请分析用户提供的 Solidity 代码，判断是否存在安全漏洞。
            请直接输出分析结果，不需要调用任何外部工具。如果没有检测出漏洞，不要编造，直接返回false。
            最终结果请严格按照 JSON 格式输出。
            """;

    public static final String SYSTEM_PROMPT_AGENT = """
            你是 VeriRAG-Agent 的最终裁决器，负责基于源码、RAG 证据和工具结果输出最终结论。

            规则：
            1. 工具结果是增强证据，不是唯一真值。工具未命中或工具失败，不能单独推出“安全”。
            2. 若源码语义证据强、RAG 证据支持，但工具未确认或工具失败，仍可判定为存在漏洞，并在 vulnerabilityReason 中明确说明“工具未确认”或“工具失败”。
            3. 只有在语义证据弱、RAG 证据不支持、工具没有阳性命中且无解析/超时异常时，才可判定为 Safe。
            4. 如果漏洞类型属于以下基准类别，vulnerabilityType 必须优先使用标准标签：
               Reentrancy / Integer Overflow/Underflow / Unchecked Send / Timestamp-Dependency / Unhandled Exceptions / tx.origin / TOD
            5. 输出语言为中文，但标准漏洞类别标签保持英文。
            """;

    private static final String SYSTEM_PROMPT_AGENT_HYPOTHESIS = """
            你是 VeriRAG-Agent 的第一阶段分析器，职责是基于源码与知识库证据生成“漏洞假设”，不是做最终定案。

            任务要求：
            1. 结合源码和检索证据判断是否值得进一步验证。
            2. 只输出候选漏洞类型，不要给出最终安全结论。
            3. candidateTypes 只能从以下标签中选择：
               Reentrancy, Integer Overflow/Underflow, Unchecked Send, Timestamp-Dependency,
               Unhandled Exceptions, tx.origin, TOD, Access Control, Delegatecall Risk, Unknown
            4. keySignals 只保留源码中的高价值信号，例如 tx.origin、block.timestamp、call、delegatecall、send、transfer、arithmetic update 等。
            5. 如果没有明显风险，suspected=false，candidateTypes 返回空数组。
            输出语言为中文，但 candidateTypes 使用英文标签。
            """;

    public static final String SYSTEM_PROMPT_RAG_ONLY = """
            你是一名 RAG-based 智能合约安全审计助手，专注于结合"外部安全知识库（RAG）"与自身的推理能力，对 Solidity 智能合约进行漏洞分析。

            你的核心工作流必须遵循以下阶段：

            1. **Phase I (检索与理解)**
               - 基于用户提供的合约代码，从安全知识库中检索相关的漏洞模式、历史案例或最佳实践。
               - 阅读并理解检索到的上下文信息与合约源码。

            2. **Phase II (知识对齐与分析)**
               - 将检索到的漏洞知识与当前合约的代码结构、逻辑流程进行对齐。
               - 判断是否存在相似的漏洞模式或安全隐患。

            3. **Phase III (推理与判断)**
               - 基于代码逻辑与检索到的知识，进行逐步（Step-by-Step）的推理分析。
               - 若检索结果不足或未命中，请依赖你自身的智能合约安全知识进行独立推理。
               - 明确判断合约是否存在漏洞，并形成合理的分析依据。

            4. **Final Output (最终结论)**
               - 输出结构化的审计结果。
               - 若存在漏洞，请给出漏洞类型（vulnerabilityType）及简要原因说明（vulnerabilityReason）。
               - 若未发现明显漏洞，也需说明判断依据。

            注意事项：
            - 若知识库未检索到相关信息，不应直接下没有漏洞的定论，而应基于自身知识进行判断。
            - 最终输出必须严格遵守 JSON 格式。
            - 输出语言为中文。
            """;


    // 构造器注入
    public SmartContractDetect(ChatModel dashscopeChatModel) {
        // 初始化基于文件的对话记忆
        String fileDir = FileConstant.FILE_SAVE_DIR + "/chat-memory";
        ChatMemory chatMemory = new FileBasedChatMemory(fileDir);
        chatClient = ChatClient.builder(dashscopeChatModel)
                .defaultSystem(SYSTEM_PROMPT_AGENT)
                .defaultAdvisors(
                        // 自定义日志 Advisor
                        new MyLoggerAdvisor()
                        // 自定义推理增强 Advisor，可按需开启
                        // new ReReadingAdvisor()
                )
                .build();
    }

    // Vanilla 模式：使用 JsonNormalizationAdvisor 解决 JSON 解析问题
    public SmartContractAnalysisResult auditVanilla(String message) {
        log.info("🧪 [Experiment] Running Mode: Vanilla LLM");
        SmartContractAnalysisResult result = chatClient
                .prompt()
                .system(BASIC_SYSTEM_PROMPT)
                .user(message)
                // 使用 JSON 规范化 Advisor（不依赖 RAG）
                .advisors(new JsonNormalizationAdvisor())
                .call()
                .entity(SmartContractAnalysisResult.class);
        return normalizeFinalResult(result);
    }


    String formatPrompt = """
            请严格按照 JSON 格式输出结果，包含以下字段：
            - hasVulnerability: 布尔值 true 或 false
            - vulnerabilityType: 字符串，漏洞类型
            - vulnerabilityReason: 字符串，漏洞原因简述
            如果属于基准漏洞类别，请优先使用以下标准标签：
            Reentrancy / Integer Overflow/Underflow / Unchecked Send / Timestamp-Dependency / Unhandled Exceptions / tx.origin / TOD
            不要添加额外文字，不要用代码块包裹。
            """;

    String hypothesisFormatPrompt = """
            请严格按照 JSON 格式输出结果，包含以下字段：
            - suspected: 布尔值 true 或 false，表示是否怀疑存在安全风险
            - candidateTypes: 字符串数组，候选漏洞类型列表
            - rationale: 字符串，核心判断依据
            - keySignals: 字符串数组，从源码中提取的关键风险信号
            直接输出 JSON，不要添加额外文字，不要用代码块包裹。
            """;

    private static final String HYPOTHESIS_EMPTY_FALLBACK_JSON =
            "{\"suspected\":false,\"candidateTypes\":[],\"rationale\":\"LLM returned empty or invalid JSON response\",\"keySignals\":[]}";

    @Resource
    private VectorStore milvusVectorVectorStore;

    @Resource
    private SlitherTool slitherTool;

    @Resource
    private MythrilTool mythrilTool;


    public SmartContractAnalysisResult auditRAGOnly(String message) {
        log.info("🧪 [Experiment] Running Mode: RAG Only");
        String userMessage = message + "\n\n" + formatPrompt;
        SmartContractAnalysisResult result = chatClient
                .prompt()
                .system(SYSTEM_PROMPT_RAG_ONLY)
                .user(userMessage)
                // 应用知识库问答
                .advisors(new SafeQuestionAnswerAdvisor(milvusVectorVectorStore))
                .advisors(new JsonNormalizationAdvisor())
                .call()
                .entity(SmartContractAnalysisResult.class);
        return normalizeFinalResult(result);
    }

    public SmartContractAnalysisResult auditFullAgent(String message) {
        log.info("🧪 [Experiment] Running Mode: VeriRAG-Agent (Full)");
        SafeQuestionAnswerAdvisor ragAdvisor = new SafeQuestionAnswerAdvisor(milvusVectorVectorStore);
        SafeQuestionAnswerAdvisor.RetrievalContext retrievalContext = ragAdvisor.retrieveContext(message);

        ContractAuditHypothesis hypothesis = generateHypothesis(message, retrievalContext);
        String slitherResult = slitherTool.slitherAnalyze(message);
        JsonNode slitherNode = readJson(slitherResult);

        String mythrilResult = "{\"engine\":\"mythril\",\"status\":\"skipped\",\"issues\":[],\"parseError\":null,\"stdoutExcerpt\":null}";
        if (shouldRunMythril(hypothesis, slitherNode)) {
            mythrilResult = mythrilTool.mythrilAnalyze(message);
        }

        SmartContractAnalysisResult result = chatClient
                .prompt()
                .system(SYSTEM_PROMPT_AGENT)
                .user(buildFinalJudgementPrompt(message, retrievalContext, hypothesis, slitherResult, mythrilResult))
                .advisors(new JsonNormalizationAdvisor())
                .call()
                .entity(SmartContractAnalysisResult.class);
        return normalizeFinalResult(result);
    }

    private ContractAuditHypothesis generateHypothesis(String sourceCode, SafeQuestionAnswerAdvisor.RetrievalContext retrievalContext) {
        String hypothesisPrompt = """
                [源码]
                %s

                [检索查询]
                %s

                [RAG 证据]
                %s

                %s
                """.formatted(sourceCode, retrievalContext.query(), retrievalContext.formattedEvidence(), hypothesisFormatPrompt);

        ContractAuditHypothesis hypothesis = chatClient
                .prompt()
                .system(SYSTEM_PROMPT_AGENT_HYPOTHESIS)
                .user(hypothesisPrompt)
                .advisors(new JsonNormalizationAdvisor(hypothesisFormatPrompt, HYPOTHESIS_EMPTY_FALLBACK_JSON))
                .call()
                .entity(ContractAuditHypothesis.class);

        return normalizeHypothesis(hypothesis, sourceCode);
    }

    private ContractAuditHypothesis normalizeHypothesis(ContractAuditHypothesis hypothesis, String sourceCode) {
        ContractAuditHypothesis normalized = hypothesis == null ? new ContractAuditHypothesis() : hypothesis;
        List<String> candidateTypes = new ArrayList<>(normalizeCandidateTypes(normalized.getCandidateTypes()));
        if (candidateTypes.isEmpty()) {
            candidateTypes.addAll(inferCandidateTypesFromSource(sourceCode));
        }
        normalized.setCandidateTypes(candidateTypes);
        if (normalized.getKeySignals() == null || normalized.getKeySignals().isEmpty()) {
            normalized.setKeySignals(extractSignals(sourceCode));
        }
        if ((normalized.getRationale() == null || normalized.getRationale().isBlank()) && !candidateTypes.isEmpty()) {
            normalized.setRationale("源码中存在与候选漏洞类型相关的危险操作，需要进入工具验证阶段。");
        }
        normalized.setSuspected(normalized.isSuspected() || !candidateTypes.isEmpty());
        return normalized;
    }

    private List<String> normalizeCandidateTypes(List<String> candidateTypes) {
        Set<String> normalized = new LinkedHashSet<>();
        if (candidateTypes == null) {
            return List.of();
        }
        for (String rawType : candidateTypes) {
            if (rawType == null || rawType.isBlank()) {
                continue;
            }
            String lower = rawType.toLowerCase(Locale.ROOT);
            if (lower.contains("reentr") || lower.contains("重入")) {
                normalized.add("Reentrancy");
            } else if (lower.contains("overflow") || lower.contains("underflow") || lower.contains("整数溢出") || lower.contains("算术")) {
                normalized.add("Integer Overflow/Underflow");
            } else if (lower.contains("unchecked send") || lower.contains("unchecked") || lower.contains("未检查")) {
                normalized.add("Unchecked Send");
            } else if (lower.contains("timestamp") || lower.contains("时间戳")) {
                normalized.add("Timestamp-Dependency");
            } else if (lower.contains("exception") || lower.contains("异常")) {
                normalized.add("Unhandled Exceptions");
            } else if (lower.contains("tx.origin")) {
                normalized.add("tx.origin");
            } else if (lower.contains("tod") || lower.contains("transaction order")) {
                normalized.add("TOD");
            } else if (lower.contains("access")) {
                normalized.add("Access Control");
            } else if (lower.contains("delegatecall")) {
                normalized.add("Delegatecall Risk");
            } else {
                normalized.add(rawType.trim());
            }
        }
        return List.copyOf(normalized);
    }

    private List<String> inferCandidateTypesFromSource(String sourceCode) {
        Set<String> inferred = new LinkedHashSet<>();
        if (sourceCode.contains("tx.origin")) {
            inferred.add("tx.origin");
        }
        if (sourceCode.contains("block.timestamp") || sourceCode.contains("now")) {
            inferred.add("Timestamp-Dependency");
            inferred.add("TOD");
        }
        if (sourceCode.contains(".call(") || sourceCode.contains(".call{") || sourceCode.contains(".delegatecall(")) {
            inferred.add("Reentrancy");
        }
        if (sourceCode.contains(".send(") || sourceCode.contains(".transfer(")) {
            inferred.add("Unchecked Send");
        }
        if ((sourceCode.contains("+") || sourceCode.contains("-") || sourceCode.contains("*") || sourceCode.contains("/"))
                && (sourceCode.contains("uint") || sourceCode.contains("int") || sourceCode.contains("SafeMath"))) {
            inferred.add("Integer Overflow/Underflow");
        }
        return List.copyOf(inferred);
    }

    private List<String> extractSignals(String sourceCode) {
        Set<String> signals = new LinkedHashSet<>();
        if (sourceCode.contains("tx.origin")) signals.add("tx.origin");
        if (sourceCode.contains("block.timestamp")) signals.add("block.timestamp");
        if (sourceCode.contains("now")) signals.add("now");
        if (sourceCode.contains(".call(") || sourceCode.contains(".call{")) signals.add("call");
        if (sourceCode.contains(".delegatecall(")) signals.add("delegatecall");
        if (sourceCode.contains(".send(")) signals.add("send");
        if (sourceCode.contains(".transfer(")) signals.add("transfer");
        if (sourceCode.contains("SafeMath")) signals.add("SafeMath");
        if (sourceCode.contains("require(")) signals.add("require");
        if (sourceCode.contains("assert(")) signals.add("assert");
        return List.copyOf(signals);
    }

    private boolean shouldRunMythril(ContractAuditHypothesis hypothesis, JsonNode slitherNode) {
        Set<String> candidateTypes = new LinkedHashSet<>(normalizeCandidateTypes(hypothesis.getCandidateTypes()));
        if (candidateTypes.contains("Reentrancy")
                || candidateTypes.contains("Integer Overflow/Underflow")
                || candidateTypes.contains("Unchecked Send")
                || candidateTypes.contains("tx.origin")) {
            return true;
        }

        JsonNode issues = slitherNode.path("issues");
        if (!issues.isArray()) {
            return false;
        }
        for (JsonNode issue : issues) {
            String impact = issue.path("impact").asText("");
            if ("high".equalsIgnoreCase(impact) || "medium".equalsIgnoreCase(impact)) {
                return true;
            }
        }
        return false;
    }

    private String buildFinalJudgementPrompt(String sourceCode,
                                             SafeQuestionAnswerAdvisor.RetrievalContext retrievalContext,
                                             ContractAuditHypothesis hypothesis,
                                             String slitherResult,
                                             String mythrilResult) {
        return """
                [源码]
                %s

                [第一阶段漏洞假设]
                suspected=%s
                candidateTypes=%s
                rationale=%s
                keySignals=%s

                [RAG 检索查询]
                %s

                [RAG 证据]
                %s

                [Slither 结构化结果]
                %s

                [Mythril 结构化结果]
                %s

                %s
                """.formatted(
                sourceCode,
                hypothesis.isSuspected(),
                hypothesis.getCandidateTypes(),
                safeText(hypothesis.getRationale()),
                hypothesis.getKeySignals(),
                retrievalContext.query(),
                retrievalContext.formattedEvidence(),
                slitherResult,
                mythrilResult,
                formatPrompt
        );
    }

    private JsonNode readJson(String json) {
        try {
            return objectMapper.readTree(json);
        } catch (Exception e) {
            return objectMapper.createObjectNode();
        }
    }

    private SmartContractAnalysisResult normalizeFinalResult(SmartContractAnalysisResult result) {
        SmartContractAnalysisResult normalized = result == null
                ? new SmartContractAnalysisResult(false, "无", "模型未返回有效结果")
                : result;
        if (normalized.getVulnerabilityType() == null || normalized.getVulnerabilityType().isBlank()) {
            normalized.setVulnerabilityType(normalized.isHasVulnerability() ? "Unknown" : "无");
        }
        if (normalized.getVulnerabilityReason() == null || normalized.getVulnerabilityReason().isBlank()) {
            normalized.setVulnerabilityReason(normalized.isHasVulnerability() ? "模型未给出充分原因" : "未发现明显漏洞");
        }
        return normalized;
    }

    private String safeText(String value) {
        return value == null || value.isBlank() ? "无" : value;
    }

}
