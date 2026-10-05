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
        return completeWithSchema(provider, system, user, false);
    }
    public GatewayReply completeHypotheses(String provider, String system, String user) {
        return completeWithSchema(provider, system, user, true);
    }
    private GatewayReply completeWithSchema(String provider, String system, String user, boolean hypotheses) {
        var p = registry.resolve(provider);
        // 显式管理 SDK 客户端，使成功和异常路径都释放连接资源。
        var client = OpenAiSetup.setupSyncClient(p.baseUrl(), p.apiKey(), null, null, null, null,
            false, false, p.model(), p.timeout(), 0, null, null, ObservationRegistry.NOOP, null, List.of());
        try {
        var options = OpenAiChatOptions.builder().baseUrl(p.baseUrl()).apiKey(p.apiKey()).model(p.model())
            .timeout(p.timeout()).maxRetries(0);
        boolean deepseekV4 = p.name().equals("ark") && p.model().startsWith("deepseek-v4");
        // 此类模型的推理 token 也需纳入请求上限。
        if (deepseekV4) options.maxCompletionTokens(p.maxOutputTokens());
        else options.maxTokens(p.maxOutputTokens());
        if (p.responseFormat().equals("json_schema")) {
            if (!deepseekV4) throw new IllegalArgumentException("当前模型未启用严格结构化输出");
            options.responseFormat(OpenAiChatModel.ResponseFormat.builder()
                .type(OpenAiChatModel.ResponseFormat.Type.JSON_SCHEMA)
                .jsonSchema(hypotheses ? """
                    {"type":"object","properties":{
                    "schemaVersion":{"type":"string","enum":["2"]},
                    "hypotheses":{"type":"array","maxItems":3,"items":{"type":"object","properties":{
                    "vulnerabilityType":{"type":"string","enum":["REENTRANCY","ACCESS_CONTROL"]},
                    "contract":{"type":"string"},"function":{"type":"string"},
                    "riskLine":{"type":"integer"},"riskOperation":{"type":"string"},
                    "reason":{"type":"string"},"evidenceIds":{"type":"array","items":{"type":"string"}}},
                    "required":["vulnerabilityType","contract","function","riskLine","riskOperation","reason","evidenceIds"],
                    "additionalProperties":false}}},
                    "required":["schemaVersion","hypotheses"],"additionalProperties":false}
                    """ : """
                    {"type":"object","properties":{
                    "hasVulnerability":{"type":"boolean"},
                    "vulnerabilityType":{"type":"string"},
                    "vulnerabilityReason":{"type":"string"}},
                    "required":["hasVulnerability","vulnerabilityType","vulnerabilityReason"],
                    "additionalProperties":false}
                    """).strict(true).build());
        }
        if (p.thinking().equals("disabled")) {
            if (!deepseekV4) throw new IllegalArgumentException("当前模型未启用思考开关");
            // 工程试跑关闭显式思考，避免推理阶段独占总输出预算。
            options.extraBody(java.util.Map.of("thinking", java.util.Map.of("type", "disabled")));
        }
        var model = OpenAiChatModel.builder().openAiClient(client).openAiClientAsync(client.async()).options(options.build()).build();
        long start = System.nanoTime();
        var response = model.call(new Prompt(List.of(new SystemMessage(system), new UserMessage(user))));
        if (response == null || response.getResult() == null || response.getResult().getOutput() == null)
            throw new IllegalStateException("模型未返回消息");
        var usage = response.getMetadata().getUsage();
        Integer input = usage == null || usage instanceof EmptyUsage ? null : usage.getPromptTokens();
        Integer output = usage == null || usage instanceof EmptyUsage ? null : usage.getCompletionTokens();
        var metadata = response.getResult().getMetadata();
        return new GatewayReply(response.getResult().getOutput().getText(), p.name(), p.model(), input, output,
            (System.nanoTime()-start)/1_000_000, metadata == null ? null : metadata.getFinishReason());
        } finally { client.close(); }
    }
}
