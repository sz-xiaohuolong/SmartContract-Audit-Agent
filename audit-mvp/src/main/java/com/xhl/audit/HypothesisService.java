package com.xhl.audit;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

/** 将模型输出限制为可追溯的初步假设，任何异常都保持未决。 */
public final class HypothesisService {
    public record Request(String fullSource, String modelSource, String sourceHash, String scope,
                          int lineStart, int lineEnd, String mechanism, String function,
                          String context, List<String> evidenceIds) {}
    public record Hypothesis(String vulnerabilityType, String contract, String function,
                             int riskLine, String riskOperation, String reason, List<String> evidenceIds) {}
    public record Result(String schemaVersion, String status, String conclusion, List<Hypothesis> hypotheses,
                         String errorCategory, Integer inputTokens, Integer outputTokens, long durationMs) {}
    private final ModelGateway gateway;
    private final ObjectMapper mapper = new ObjectMapper()
        .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    public HypothesisService(ModelGateway gateway) { this.gateway = gateway; }

    public Result analyze(Request request, String provider) {
        GatewayReply reply;
        try {
            validateRequest(request);
            String system = "你是智能合约审计员。仅输出符合指定 JSON schema 的初步漏洞假设。证据不足时返回空数组；不得编造行号或证据 ID。最多 3 条。";
            String user = "机制：" + request.mechanism() + "\n函数：" + request.function() + "\n范围：" + request.scope()
                + "，原始行号 " + request.lineStart() + "-" + request.lineEnd()
                + "\n可引用证据 ID：" + request.evidenceIds() + "\n检索上下文：" + request.context()
                + "\n待审源码：\n" + request.modelSource();
            reply = gateway.complete(provider, system, user);
        } catch (IllegalArgumentException e) { return failed("INPUT_INVALID", null); }
          catch (Exception e) { return failed("MODEL_CALL_ERROR", null); }
        if (reply == null) return failed("MODEL_CALL_ERROR", null);
        if ("length".equalsIgnoreCase(reply.finishReason())) return failed("MODEL_OUTPUT_TRUNCATED", reply);
        try {
            JsonNode root = mapper.readTree(reply.content());
            exact(root, Set.of("schemaVersion", "hypotheses"));
            if (!"2".equals(text(root, "schemaVersion"))) throw new IllegalArgumentException();
            JsonNode entries = root.get("hypotheses");
            if (!entries.isArray() || entries.size() > 3) throw new IllegalArgumentException();
            List<Hypothesis> hypotheses = new ArrayList<>();
            for (JsonNode item : entries) {
                exact(item, Set.of("vulnerabilityType", "contract", "function", "riskLine", "riskOperation", "reason", "evidenceIds"));
                String type = text(item, "vulnerabilityType");
                if (!type.equals(request.mechanism())) throw new IllegalArgumentException();
                String contract = text(item, "contract");
                if (!contract.matches("[A-Za-z_$][A-Za-z0-9_$]*") ||
                    !java.util.regex.Pattern.compile("\\b(?:contract|library|interface)\\s+" +
                        java.util.regex.Pattern.quote(contract) + "\\b").matcher(request.fullSource()).find())
                    throw new IllegalArgumentException();
                String function = text(item, "function");
                if (!function.equals(request.function())) throw new IllegalArgumentException();
                JsonNode line = item.get("riskLine");
                if (!line.isIntegralNumber() || line.intValue() < request.lineStart() || line.intValue() > request.lineEnd())
                    throw new IllegalArgumentException();
                String operation = text(item, "riskOperation");
                String reason = text(item, "reason");
                JsonNode ids = item.get("evidenceIds");
                if (!ids.isArray()) throw new IllegalArgumentException();
                List<String> used = new ArrayList<>();
                for (JsonNode id : ids) {
                    if (!id.isTextual() || !request.evidenceIds().contains(id.textValue()) || used.contains(id.textValue()))
                        throw new IllegalArgumentException();
                    used.add(id.textValue());
                }
                hypotheses.add(new Hypothesis(type, contract, function, line.intValue(), operation, reason, List.copyOf(used)));
            }
            return new Result("2", "COMPLETED", hypotheses.isEmpty() ? "NO_CONFIRMED_FINDINGS" : "VULNERABILITY_REPORTED",
                List.copyOf(hypotheses), null, reply.inputTokens(), reply.outputTokens(), reply.durationMs());
        } catch (Exception e) { return failed("MODEL_OUTPUT_INVALID", reply); }
    }
    private static void validateRequest(Request request) {
        if (request == null || request.fullSource() == null || request.fullSource().isBlank()
            || request.modelSource() == null || request.modelSource().isBlank()
            || !Set.of("FULL", "FUNCTION").contains(request.scope())
            || request.lineStart() < 1 || request.lineEnd() < request.lineStart()
            || request.mechanism() == null || !Set.of("REENTRANCY", "ACCESS_CONTROL").contains(request.mechanism())
            || request.function() == null || request.function().isBlank()
            || request.context() == null || request.evidenceIds() == null) throw new IllegalArgumentException();
        String[] sourceLines = request.fullSource().split("\\R", -1);
        int lines = sourceLines.length;
        if (request.lineEnd() > lines) throw new IllegalArgumentException();
        String expected = request.scope().equals("FULL") ? request.fullSource()
            : String.join("\n", java.util.Arrays.copyOfRange(sourceLines, request.lineStart() - 1, request.lineEnd()));
        if (!expected.equals(request.modelSource())) throw new IllegalArgumentException();
        if (request.sourceHash() != null) {
            try {
                String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(request.fullSource().getBytes(StandardCharsets.UTF_8)));
                if (!actual.equals(request.sourceHash())) throw new IllegalArgumentException();
            } catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
        }
    }
    private static void exact(JsonNode node, Set<String> keys) {
        if (node == null || !node.isObject() || node.size() != keys.size()) throw new IllegalArgumentException();
        for (String key : keys) if (!node.has(key)) throw new IllegalArgumentException();
    }
    private static String text(JsonNode node, String key) {
        JsonNode value = node.get(key);
        if (value == null || !value.isTextual() || value.textValue().isBlank() || value.textValue().length() > 2000)
            throw new IllegalArgumentException();
        return value.textValue();
    }
    private static Result failed(String category, GatewayReply reply) {
        return new Result("2", "FAILED", "UNRESOLVED", List.of(), category,
            reply == null ? null : reply.inputTokens(), reply == null ? null : reply.outputTokens(),
            reply == null ? 0 : reply.durationMs());
    }
}
