package com.xhl.xhlaiagent.rag;

import org.springframework.ai.chat.client.advisor.api.AdvisedRequest;
import org.springframework.ai.chat.client.advisor.api.AdvisedResponse;
import org.springframework.ai.chat.client.advisor.api.CallAroundAdvisor;
import org.springframework.ai.chat.client.advisor.api.CallAroundAdvisorChain;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.util.Assert;
import org.springframework.util.StringUtils;
import org.springframework.ai.vectorstore.filter.Filter;
import org.springframework.ai.vectorstore.filter.FilterExpressionTextParser;

import java.util.*;
import java.util.regex.Pattern;

public class SafeQuestionAnswerAdvisor implements CallAroundAdvisor {

    private static final String DEFAULT_DATASET_FILTER = "dataset == 'smartbugs-curated'";
    private static final int DEFAULT_TOP_K = 3;
    private static final double DEFAULT_SIMILARITY_THRESHOLD = 0.5;
    private static final int SNIPPET_LIMIT = 700;

    private final VectorStore vectorStore;
    private final SearchRequest searchRequest;

    public SafeQuestionAnswerAdvisor(VectorStore vectorStore) {
        Assert.notNull(vectorStore, "vectorStore must not be null");
        this.vectorStore = vectorStore;
        this.searchRequest = SearchRequest.builder().build();
    }

    @Override
    public String getName() {
        return "SafeQuestionAnswerAdvisor";
    }

    @Override
    public int getOrder() {
        return 0;
    }

    @Override
    public AdvisedResponse aroundCall(AdvisedRequest request, CallAroundAdvisorChain chain) {
        RetrievalContext retrievalContext = retrieveContext(request.userText(), request.adviseContext());
        String userText = request.userText()
                + "\n\n--- 以下是知识库相关信息 ---\n"
                + retrievalContext.formattedEvidence();

        // 构造新的请求
        AdvisedRequest advisedRequest = AdvisedRequest.from(request)
                .userText(userText)
                .adviseContext(Map.of(
                        "qa_retrieved_documents", retrievalContext.documents(),
                        "qa_retrieval_query", retrievalContext.query(),
                        "qa_formatted_evidence", retrievalContext.formattedEvidence()))
                .build();

        // 调用下一个 advisor
        AdvisedResponse response = chain.nextAroundCall(advisedRequest);

        // 保留检索文档信息
        ChatResponse chatResponse = ChatResponse.builder()
                .from(response.response())
                .metadata("qa_retrieved_documents", retrievalContext.documents())
                .metadata("qa_retrieval_query", retrievalContext.query())
                .build();

        return new AdvisedResponse(chatResponse, advisedRequest.adviseContext());
    }

    public RetrievalContext retrieveContext(String sourceCode) {
        return retrieveContext(sourceCode, Collections.emptyMap());
    }

    public RetrievalContext retrieveContext(String sourceCode, Map<String, Object> context) {
        String query = buildRetrievalQuery(sourceCode);

        SearchRequest searchRequestToUse = SearchRequest.from(this.searchRequest)
                .query(query)
                .topK(DEFAULT_TOP_K)
                .similarityThreshold(DEFAULT_SIMILARITY_THRESHOLD)
                .filterExpression(doGetFilterExpression(context))
                .build();

        List<Document> documents = Optional.ofNullable(this.vectorStore.similaritySearch(searchRequestToUse))
                .orElseGet(List::of);

        return new RetrievalContext(query, documents, formatEvidence(documents));
    }

    private Filter.Expression doGetFilterExpression(Map<String, Object> context) {
        if (context.containsKey("qa_filter_expression") &&
                StringUtils.hasText(context.get("qa_filter_expression").toString())) {
            return new FilterExpressionTextParser().parse(context.get("qa_filter_expression").toString());
        }
        if (this.searchRequest.getFilterExpression() != null) {
            return this.searchRequest.getFilterExpression();
        }
        return new FilterExpressionTextParser().parse(DEFAULT_DATASET_FILTER);
    }

    private String buildRetrievalQuery(String sourceCode) {
        String code = Optional.ofNullable(sourceCode).orElse("");
        Set<String> terms = new LinkedHashSet<>();
        terms.add("solidity smart contract security");

        if (containsAny(code, "tx.origin")) {
            terms.add("tx.origin authentication vulnerability");
        }
        if (containsAny(code, "block.timestamp", "now", "block.number")) {
            terms.add("timestamp dependency transaction order dependence");
        }
        if (containsAny(code, ".call(", ".delegatecall(", ".staticcall(", "call{")) {
            terms.add("external call reentrancy unchecked low level call");
        }
        if (containsAny(code, ".send(", ".transfer(")) {
            terms.add("unchecked send ether transfer external call");
        }
        if (containsArithmeticSignal(code)) {
            terms.add("integer overflow underflow arithmetic vulnerability");
        }
        if (containsAny(code, "require(", "assert(", "revert(")) {
            terms.add("unhandled exception revert handling");
        }
        if (containsAny(code, "onlyOwner", "owner", "AccessControl", "delegatecall")) {
            terms.add("authorization access control privilege escalation");
        }

        return String.join(" | ", terms);
    }

    private boolean containsArithmeticSignal(String code) {
        return containsAny(code, "+", "-", "*", "/")
                && (containsAny(code, "uint", "int", "SafeMath") || Pattern.compile("\\b[a-zA-Z_][a-zA-Z0-9_]*\\s*[+\\-*/]=").matcher(code).find());
    }

    private boolean containsAny(String text, String... needles) {
        for (String needle : needles) {
            if (text.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private String formatEvidence(List<Document> documents) {
        if (documents == null || documents.isEmpty()) {
            return "未检索到高相关知识库证据。";
        }

        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < documents.size(); i++) {
            Document doc = documents.get(i);
            Map<String, Object> metadata = doc.getMetadata() == null ? Collections.emptyMap() : doc.getMetadata();
            String sourceFile = String.valueOf(metadata.getOrDefault("source_file", "unknown"));
            String category = String.valueOf(metadata.getOrDefault("category", "unknown"));
            String swcId = String.valueOf(metadata.getOrDefault("swc_id", "unknown"));
            String snippet = abbreviate(doc.getText(), SNIPPET_LIMIT);
            sb.append("[").append(i + 1).append("] ")
                    .append("source=").append(sourceFile)
                    .append(", category=").append(category)
                    .append(", swc=").append(swcId)
                    .append("\n")
                    .append(snippet)
                    .append("\n\n");
        }
        return sb.toString().trim();
    }

    private String abbreviate(String text, int limit) {
        String normalized = Optional.ofNullable(text)
                .orElse("")
                .replaceAll("\\s+", " ")
                .trim();
        if (normalized.length() <= limit) {
            return normalized;
        }
        return normalized.substring(0, limit) + "...";
    }

    public record RetrievalContext(String query, List<Document> documents, String formattedEvidence) {}
}
