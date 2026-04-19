package com.xhl.xhlaiagent.config;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.time.Duration;

/**
 * 百炼 Coding Plan OpenAI 兼容接口配置
 * <p>
 * 激活 coding-plan profile 时，使用 OpenAI 兼容接口创建 ChatModel Bean。
 * 此 Bean 名称为 dashscopeChatModel，与原有 Dashscope Bean 名称一致，实现无侵入替换。
 * </p>
 *
 * <p>使用方式：</p>
 * <ul>
 *   <li>启动时指定 profile: java -jar app.jar --spring.profiles.active=coding-plan</li>
 *   <li>或在配置文件中设置: spring.profiles.active=coding-plan</li>
 * </ul>
 *
 * <p>注意：</p>
 * <ul>
 *   <li>Chat 模型使用 Coding Plan (包月计费)</li>
 *   <li>Embedding 模型继续使用 Dashscope 按量计费</li>
 * </ul>
 */
@Configuration
@Profile("coding-plan")
@EnableAutoConfiguration(excludeName = {
        "com.alibaba.cloud.ai.autoconfigure.dashscope.DashScopeAutoConfiguration",
        "org.springframework.ai.autoconfigure.openai.OpenAiAutoConfiguration"
})
public class CodingPlanConfig {

    @Value("${spring.ai.openai.base-url}")
    private String baseUrl;

    @Value("${spring.ai.openai.api-key}")
    private String apiKey;

    @Value("${spring.ai.openai.chat.options.model}")
    private String model;

    /** 连接超时时间（毫秒） */
    @Value("${spring.ai.openai.connect-timeout:60000}")
    private int connectTimeout;

    /** 读取超时时间（毫秒） */
    @Value("${spring.ai.openai.read-timeout:300000}")
    private int readTimeout;

    /**
     * 创建名为 dashscopeChatModel 的 OpenAI 兼容 ChatModel Bean
     * <p>
     * 此 Bean 名称与原 Dashscope Bean 名称一致，实现无侵入替换。
     * 业务代码通过参数名 dashscopeChatModel 注入时，将自动使用此 Bean。
     * </p>
     *
     * @return OpenAI 兼容的 ChatModel 实例
     */
    @Bean("dashscopeChatModel")
    public ChatModel dashscopeChatModel() {
        // 创建带有超时配置的 RestClient
        ClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        ((SimpleClientHttpRequestFactory) requestFactory).setConnectTimeout(Duration.ofMillis(connectTimeout));
        ((SimpleClientHttpRequestFactory) requestFactory).setReadTimeout(Duration.ofMillis(readTimeout));

        RestClient.Builder restClientBuilder = RestClient.builder()
                .requestFactory(requestFactory);

        OpenAiApi openAiApi = OpenAiApi.builder()
                .baseUrl(baseUrl)
                .apiKey(apiKey)
                .restClientBuilder(restClientBuilder)
                .build();

        OpenAiChatOptions options = OpenAiChatOptions.builder()
                .model(model)
                .build();

        return OpenAiChatModel.builder()
                .openAiApi(openAiApi)
                .defaultOptions(options)
                .build();
    }
}