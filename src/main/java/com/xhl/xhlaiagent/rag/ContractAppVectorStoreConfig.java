package com.xhl.xhlaiagent.rag;

import jakarta.annotation.Resource;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
public class ContractAppVectorStoreConfig {

    @Resource
    private ContractAppDocumentLoader contractAppDocumentLoader;

    /**
     * 初始化向量数据库并且保存文档
     * 基于内存的
     * @param dashscopeEmbeddingModel
     */
    @Bean
    VectorStore contractAppVectorStore(EmbeddingModel dashscopeEmbeddingModel) {
        //构建一个向量存储器对象
        SimpleVectorStore simpleVectorStore = SimpleVectorStore.builder(dashscopeEmbeddingModel)
                .build();
        // 加载文档
        List<Document> documents = contractAppDocumentLoader.loadMarkdowns();
        // 转换为向量并保存文档
        simpleVectorStore.add(documents);
        return simpleVectorStore;
    }
}
