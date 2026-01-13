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
import java.util.stream.Collectors;

public class SafeQuestionAnswerAdvisor implements CallAroundAdvisor {

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
        //不再使用 PromptTemplate —— 直接把用户输入当作普通字符串
        String query = request.userText();

        // 向量检索
        SearchRequest searchRequestToUse = SearchRequest.from(this.searchRequest)
                .query(query)
                .topK(3)
                .similarityThreshold(0.5)
                .filterExpression(doGetFilterExpression(request.adviseContext()))
                .build();

        List<Document> documents = this.vectorStore.similaritySearch(searchRequestToUse);

        // 拼接上下文，把检索结果“注入”到 Prompt 里
        String contextText = documents.stream()
                .map(Document::getText)
                .collect(Collectors.joining("\n\n"));

        // 把上下文附加在用户问题后
        String userText = query + "\n\n--- 以下是知识库相关信息 ---\n" + contextText;

        // 构造新的请求
        AdvisedRequest advisedRequest = AdvisedRequest.from(request)
                .userText(userText)
                .adviseContext(Map.of("qa_retrieved_documents", documents))
                .build();

        // 调用下一个 advisor
        AdvisedResponse response = chain.nextAroundCall(advisedRequest);

        // 保留检索文档信息
        ChatResponse chatResponse = ChatResponse.builder()
                .from(response.response())
                .metadata("qa_retrieved_documents", documents)
                .build();

        return new AdvisedResponse(chatResponse, advisedRequest.adviseContext());
    }

    private Filter.Expression doGetFilterExpression(Map<String, Object> context) {
        if (context.containsKey("qa_filter_expression") &&
                StringUtils.hasText(context.get("qa_filter_expression").toString())) {
            return new FilterExpressionTextParser().parse(context.get("qa_filter_expression").toString());
        }
        return this.searchRequest.getFilterExpression();
    }
}
