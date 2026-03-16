package com.xhl.xhlaiagent.config;

import com.alibaba.cloud.ai.dashscope.api.DashScopeApi;
import com.alibaba.cloud.ai.dashscope.embedding.DashScopeEmbeddingModel;
import com.alibaba.cloud.ai.dashscope.embedding.DashScopeEmbeddingOptions;
import org.springframework.ai.document.MetadataMode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Profile;

/**
 * Dashscope Embedding 配置
 * <p>
 * Coding Plan 不支持 Embedding 模型，因此 Embedding 继续使用 Dashscope 按量计费。
 * 此配置类在 coding-plan profile 激活时生效。
 * </p>
 *
 * <p>说明：</p>
 * <ul>
 *   <li>Chat 模型使用 Coding Plan (OpenAI 兼容接口，包月计费)</li>
 *   <li>Embedding 模型使用 Dashscope (按量计费)</li>
 * </ul>
 */
@Configuration
@Profile("coding-plan")
public class DashscopeEmbeddingConfig {

    @Value("${spring.ai.dashscope.api-key}")
    private String apiKey;

    @Value("${spring.ai.dashscope.embedding.options.model:text-embedding-v3}")
    private String embeddingModel;

    /**
     * 创建 Dashscope Embedding Model Bean
     * <p>
     * 用于向量数据库嵌入功能，继续使用 Dashscope API。
     * 使用 @Primary 标记为首选 Bean，确保 Milvus 使用此 Embedding。
     * Bean 名称设为 embeddingModel，覆盖其他自动配置的同名 Bean。
     * </p>
     *
     * @return DashScopeEmbeddingModel 实例
     */
    @Bean("embeddingModel")
    @Primary
    public DashScopeEmbeddingModel embeddingModel() {
        DashScopeApi dashScopeApi = new DashScopeApi(apiKey);
        DashScopeEmbeddingOptions options = DashScopeEmbeddingOptions.builder()
                .withModel(embeddingModel)
                .build();
        return new DashScopeEmbeddingModel(dashScopeApi, MetadataMode.EMBED, options);
    }
}