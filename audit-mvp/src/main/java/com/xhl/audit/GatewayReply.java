package com.xhl.audit;

/** 缺失用量保留 null，不能用零代替未知。 */
public record GatewayReply(String content, String provider, String model, Integer inputTokens, Integer outputTokens, long durationMs) {}
