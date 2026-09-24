package com.xhl.audit;

import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import java.util.List;
import org.springframework.ai.openai.setup.OpenAiSetup;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ai.chat.metadata.EmptyUsage;

/** 使用 Spring AI 2 的 OpenAI 兼容适配，不依赖全局供应商单例。 */
public final class SpringAiGateway implements ModelGateway {
    private final ProviderRegistry registry;
    public SpringAiGateway(ProviderRegistry registry) {this.registry = registry;}
    @Override public GatewayReply complete(String provider, String system, String user) {
        var p = registry.resolve(provider);
        // 显式管理 SDK 客户端，使成功和异常路径都释放连接资源。
        var client = OpenAiSetup.setupSyncClient(p.baseUrl(), p.apiKey(), null, null, null, null,
            false, false, p.model(), p.timeout(), 0, null, null, ObservationRegistry.NOOP, null, List.of());
        try {
        var model = OpenAiChatModel.builder().openAiClient(client).openAiClientAsync(client.async()).options(OpenAiChatOptions.builder()
            .baseUrl(p.baseUrl()).apiKey(p.apiKey()).model(p.model())
            .timeout(p.timeout()).maxRetries(0).maxTokens(p.maxOutputTokens()).build()).build();
        long start = System.nanoTime();
        var response = model.call(new Prompt(List.of(new SystemMessage(system), new UserMessage(user))));
        if (response == null || response.getResult() == null || response.getResult().getOutput() == null)
            throw new IllegalStateException("模型未返回消息");
        var usage = response.getMetadata().getUsage();
        Integer input = usage == null || usage instanceof EmptyUsage ? null : usage.getPromptTokens();
        Integer output = usage == null || usage instanceof EmptyUsage ? null : usage.getCompletionTokens();
        return new GatewayReply(response.getResult().getOutput().getText(), p.name(), p.model(), input, output,
            (System.nanoTime()-start)/1_000_000);
        } finally { client.close(); }
    }
}
