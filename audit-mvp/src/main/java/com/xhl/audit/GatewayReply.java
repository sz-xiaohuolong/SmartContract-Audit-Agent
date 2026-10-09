package com.xhl.audit;

/** 缺失用量保留 null，不能用零代替未知。 */
public record GatewayReply(String content, String provider, String model, Integer inputTokens, Integer outputTokens,
                           long durationMs, String finishReason, int requestAttempts) {
    public GatewayReply(String content, String provider, String model, Integer inputTokens, Integer outputTokens,
                        long durationMs, String finishReason) {
        this(content, provider, model, inputTokens, outputTokens, durationMs, finishReason, 1);
    }
    public GatewayReply(String content, String provider, String model, Integer inputTokens, Integer outputTokens, long durationMs) {
        this(content, provider, model, inputTokens, outputTokens, durationMs, null);
    }
}
