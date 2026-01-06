package com.xhl.xhlaiagent.rag;

import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.document.DocumentTransformer;
import org.springframework.ai.transformer.splitter.TextSplitter;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
@Slf4j
public class MilvusVectorStoreConfig {

    @Resource
    private ContractAppDocumentLoader contractAppDocumentLoader;

    @Resource
    VectorStore vectorStore; // 内置了 text-embedding-v3 模型的 Milvus 客户端对象。

    @Bean
    public VectorStore milvusVectorVectorStore() {
        // 判断是否已有数据
        List<Document> exitDocuments = vectorStore.
                similaritySearch(SearchRequest.builder().query("合约").topK(1).build());
        if (exitDocuments != null && !exitDocuments.isEmpty()) return vectorStore;

        //todo ETL优化切分数据方式
        log.info("Milvus 向量库为空，开始加载文档...");

        // 加载文档
        List<Document> documents = contractAppDocumentLoader.loadMarkdowns();
        vectorStore.add(documents);
        return vectorStore;
    }
}
