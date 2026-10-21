package com.xhl.audit.service;

import com.xhl.audit.exception.ModelCallException;

import com.xhl.audit.dto.GatewayReply;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/** 消费回执必须绑定传给网关的实际消息，而非另一份估算提示。 */
class HypothesisConsumptionTest {
    @Test void 调用失败后服务与消费回执保留实际次数且不泄露异常正文() throws Exception {
        String source = "contract C { function f() public {} }";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "f", "", List.of());
        var result = new HypothesisService((name, system, user) -> {
            throw new ModelCallException(new IllegalStateException("敏感供应商正文"), 2);
        }).analyze(request, "fixture");
        var json = new ObjectMapper().valueToTree(result);
        assertEquals("FAILED", result.status());
        assertEquals("UNRESOLVED", result.conclusion());
        assertEquals("MODEL_CALL_ERROR", result.errorCategory());
        assertEquals(2, result.requestAttempts());
        assertEquals(2, json.path("requestConsumptionReceipt").path("requestAttempts").asInt());
        assertNull(result.inputTokens());
        assertNull(result.outputTokens());
        assertFalse(json.toString().contains("敏感供应商正文"));
    }

    private static String sha(String value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
            .digest(value.getBytes(StandardCharsets.UTF_8)));
    }
    @Test void 实际消息与源码上下文逐项绑定且用量缺失保持空() throws Exception {
        String source = "contract C { function f() public {} }";
        String context = "中文配对上下文\n包含原片段";
        String[] captured = new String[2];
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "f", context, List.of("案例甲"));
        var result = new HypothesisService((name, system, user) -> {
            captured[0] = system; captured[1] = user;
            return new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}",
                "fixture", "fixture", null, null, 1, "stop", 1);
        }).analyze(request, "fixture");
        var receipt = new ObjectMapper().valueToTree(result).path("requestConsumptionReceipt");
        assertEquals("request-consumption-1", receipt.path("schemaVersion").asText());
        assertEquals(sha(source), receipt.path("sourceHash").asText());
        assertEquals(sha(source), receipt.path("modelSourceHash").asText());
        assertEquals(sha(context), receipt.path("contextSha256").asText());
        assertEquals(sha(captured[0]), receipt.path("systemPromptSha256").asText());
        assertEquals(sha(captured[1]), receipt.path("userPromptSha256").asText());
        assertEquals(captured[1].getBytes(StandardCharsets.UTF_8).length,
            receipt.path("userPromptBytes").asInt());
        assertEquals("案例甲", receipt.path("evidenceIds").get(0).asText());
        assertTrue(receipt.path("inputTokens").isNull());
        assertTrue(receipt.path("tokenizer").isNull());
        assertEquals("diff-guidance-1", receipt.path("diffGuidanceVersion").asText());
        assertTrue(captured[0].contains("差分引导"));
        assertTrue(captured[0].contains("变化窗口"));
        assertTrue(captured[0].contains("UNKNOWN"));
        assertTrue(receipt.path("promptBudgetComponents").has("system"));
        assertTrue(receipt.path("promptBudgetComponents").has("source"));
        assertTrue(receipt.path("promptBudgetComponents").has("context"));
        assertTrue(receipt.path("promptBudgetComponents").has("output"));
        assertEquals(List.of("system", "user"), new ObjectMapper().convertValue(
            receipt.path("messageOrder"), List.class));
    }

    @Test void 输出解析失败仍保留真实请求用量与消费身份() {
        String source = "contract C { function f() public {} }";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "f", "", List.of());
        var result = new HypothesisService((name, system, user) ->
            new GatewayReply("不是JSON", "fixture", "fixture", 23, 5, 1, "stop", 1))
            .analyze(request, "fixture");
        assertEquals("FAILED", result.status());
        var receipt = new ObjectMapper().valueToTree(result).path("requestConsumptionReceipt");
        assertEquals(23, receipt.path("inputTokens").asInt());
        assertEquals(5, receipt.path("outputTokens").asInt());
        assertEquals(64, receipt.path("requestSha256").asText().length());
    }
}
