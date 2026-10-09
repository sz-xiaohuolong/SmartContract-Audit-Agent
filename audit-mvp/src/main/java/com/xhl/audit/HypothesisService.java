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
    public record RejectedHypothesis(int index, String issue) {}
    public record Result(String schemaVersion, String status, String conclusion, List<Hypothesis> hypotheses,
                         String errorCategory, String validationIssue, Integer inputTokens, Integer outputTokens, long durationMs, Integer requestAttempts, List<RejectedHypothesis> rejectedHypotheses) {}
    private final ModelGateway gateway;
    private final ObjectMapper mapper = new ObjectMapper()
        .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    public HypothesisService(ModelGateway gateway) { this.gateway = gateway; }

    public Result analyze(Request request, String provider) {
        GatewayReply reply;
        try {
            validateRequest(request);
            String system = "你是智能合约审计员。只输出一个 JSON 对象，不要 Markdown、代码围栏、解释文字或顶层数组。"
                + "对象必须且只能有 schemaVersion 和 hypotheses 两个字段；schemaVersion 固定为字符串 2。"
                + "hypotheses 最多 3 项，每项必须且只能有 vulnerabilityType、contract、function、riskLine、riskOperation、reason、evidenceIds。"
                + "riskLine 是源码左侧标注的绝对整数行号，不是范围或字符串。证据不足时只返回 {\"schemaVersion\":\"2\",\"hypotheses\":[]}。"
                + "不得编造合约、函数、行号和证据 ID。";
            String user = "机制：" + request.mechanism() + "\n函数：" + request.function() + "\n范围：" + request.scope()
                + "，原始行号 " + request.lineStart() + "-" + request.lineEnd()
                + "\n目标所属合约：" + contractHint(request)
                + "\n可引用证据 ID：" + request.evidenceIds() + "\n检索上下文：" + request.context()
                + "\n每条假设的 vulnerabilityType 必须等于上述机制；"
                + (request.scope().equals("FULL")
                    ? "完整合约可以报告真实声明的不同函数，function 用其声明名称；无名回退函数写 fallback，构造函数写 constructor；"
                    : "函数片段的 function 必须等于上述函数；无名回退函数写 fallback，构造函数写 constructor；")
                + "若给出目标所属合约，contract 必须等于该名称；evidenceIds 只能从可引用 ID 中选择，也可以为空数组。"
                + "\n待审源码（左侧为原始行号）：\n" + numberedSource(request);
            reply = gateway.complete(provider, system, user);
        } catch (IllegalArgumentException e) { return failed("INPUT_INVALID", null); }
          catch (Exception e) {
              int attempts = e instanceof SpringAiGateway.CallFailure failure ? failure.attempts : 1;
              return new Result("2", "FAILED", "UNRESOLVED", List.of(), "MODEL_CALL_ERROR", null,
                  null, null, 0, attempts, List.of());
          }
        if (reply == null) return failed("MODEL_CALL_ERROR", null);
        if ("length".equalsIgnoreCase(reply.finishReason())) return failed("MODEL_OUTPUT_TRUNCATED", reply);
        try {
            JsonNode root = mapper.readTree(extractObject(reply.content()));
            required(root, Set.of("schemaVersion", "hypotheses"));
            if (!"2".equals(text(root, "schemaVersion"))) throw invalid("SCHEMA_VERSION");
            JsonNode entries = root.get("hypotheses");
            if (!entries.isArray() || entries.size() > 3) throw invalid("HYPOTHESIS_COUNT");
            List<Hypothesis> hypotheses = new ArrayList<>();
            List<RejectedHypothesis> rejected = new ArrayList<>();
            int entryIndex = 0;
            for (JsonNode item : entries) {
                try {
                    required(item, Set.of("vulnerabilityType", "contract", "function", "riskLine", "riskOperation", "reason"));
                    String type = text(item, "vulnerabilityType");
                    if (!type.equals(request.mechanism())) throw invalid("MECHANISM_MISMATCH");
                    String contract = canonicalContract(text(item, "contract"), request.fullSource());
                    JsonNode functionNode = item.get("function");
                    if (!functionNode.isTextual() || functionNode.textValue().length() > 2000) throw invalid("SCHEMA_TEXT");
                    int riskLine = riskLine(item.get("riskLine"));
                    if (riskLine < request.lineStart() || riskLine > request.lineEnd()) throw invalid("RISK_LINE_INVALID");
                    String function = canonicalFunction(functionNode.textValue(), contract, riskLine, request);
                    String operation = text(item, "riskOperation");
                    String reason = text(item, "reason");
                    JsonNode ids = item.get("evidenceIds");
                    if (ids != null && !ids.isNull() && !ids.isArray()) throw invalid("EVIDENCE_IDS_INVALID");
                    List<String> used = new ArrayList<>();
                    for (JsonNode id : ids == null || ids.isNull() ? mapper.createArrayNode() : ids) {
                        if (!id.isTextual() || !request.evidenceIds().contains(id.textValue()) || used.contains(id.textValue()))
                            throw invalid("EVIDENCE_IDS_INVALID");
                        used.add(id.textValue());
                    }
                    hypotheses.add(new Hypothesis(type, contract, function, riskLine, operation, reason, List.copyOf(used)));
                } catch (OutputIssue issue) {
                    rejected.add(new RejectedHypothesis(entryIndex, issue.code));
                }
                entryIndex++;
            }
            // 只保留经过位置与引用校验的发现；全部被拒绝时不能生成阴性结论。
            if (hypotheses.isEmpty() && !rejected.isEmpty())
                return failed("MODEL_OUTPUT_INVALID", rejected.getFirst().issue(), reply, rejected);
            return new Result("2", "COMPLETED", hypotheses.isEmpty() ? "NO_CONFIRMED_FINDINGS" : "VULNERABILITY_REPORTED",
                List.copyOf(hypotheses), null, rejected.isEmpty() ? null : "PARTIAL_HYPOTHESES_REJECTED", reply.inputTokens(), reply.outputTokens(), reply.durationMs(), reply.requestAttempts(), List.copyOf(rejected));
        } catch (OutputIssue e) { return failed("MODEL_OUTPUT_INVALID", e.code, reply); }
          catch (Exception e) { return failed("MODEL_OUTPUT_INVALID", "JSON_OR_TYPE_INVALID", reply); }
    }
    private static String numberedSource(Request request) {
        String[] lines = request.modelSource().split("\\n", -1);
        StringBuilder result = new StringBuilder();
        int start = request.scope().equals("FUNCTION") ? request.lineStart() : 1;
        for (int i = 0; i < lines.length; i++) {
            if (i > 0) result.append('\n');
            result.append(start + i).append(" | ").append(lines[i]);
        }
        return result.toString();
    }
    private static String contractHint(Request request) {
        String[] lines = request.fullSource().split("\\R", -1);
        var declaration = java.util.regex.Pattern.compile("^\\s*(?:abstract\\s+)?(?:contract|library|interface)\\s+([A-Za-z_$][A-Za-z0-9_$]*)\\b");
        var targetFunction = java.util.regex.Pattern.compile("^\\s*function\\s+" +
            java.util.regex.Pattern.quote(normalizeFunction(request.function())) + "\\b");
        String current = null;
        for (int i = 0; i < lines.length; i++) {
            var matcher = declaration.matcher(lines[i]);
            if (matcher.find()) current = matcher.group(1);
            if ((request.scope().equals("FUNCTION") && i + 1 == request.lineStart())
                || (request.scope().equals("FULL") && targetFunction.matcher(lines[i]).find()))
                return current == null ? "请从完整源码中的真实声明判断" : current;
        }
        return "请从完整源码中的真实声明判断";
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
    private static void required(JsonNode node, Set<String> keys) {
        if (node == null || !node.isObject()) throw invalid("SCHEMA_FIELDS");
        for (String key : keys) if (!node.has(key)) throw invalid("SCHEMA_FIELDS");
    }
    // 只清理呈现形式；重复键、多对象和缺失字段仍由严格 JSON 校验拒绝。
    private static String extractObject(String content) {
        if (content == null) throw invalid("JSON_OR_TYPE_INVALID");
        int start = content.indexOf('{'), end = content.lastIndexOf('}');
        if (start < 0 || end < start) throw invalid("JSON_OR_TYPE_INVALID");
        return content.substring(start, end + 1);
    }
    private static int riskLine(JsonNode line) {
        try {
            if (line != null && line.isIntegralNumber() && line.canConvertToInt()) return line.intValue();
            if (line != null && line.isTextual() && line.textValue().trim().matches("[0-9]+"))
                return Integer.parseInt(line.textValue().trim());
        } catch (NumberFormatException ignored) { }
        throw invalid("RISK_LINE_INVALID");
    }
    private static String normalizeFunction(String value) {
        return value.trim().replaceFirst("\\s*\\(\\s*\\)\\s*$", "");
    }
    private record FunctionScope(String contract, String name, int start, int end) {}
    private static String canonicalFunction(String name, String contract, int line, Request request) {
        String value = normalizeFunction(name);
        if (value.isEmpty() || value.equals("(") || value.equals("function")) value = "fallback";
        String target = normalizeFunction(request.function());
        if (target.equals("(")) target = "fallback";
        for (FunctionScope declared : functionScopes(request.fullSource())) {
            boolean matchesName = declared.name().equalsIgnoreCase(value)
                || declared.name().equals("constructor") && value.equalsIgnoreCase(contract);
            boolean matchesTarget = declared.name().equalsIgnoreCase(target)
                || declared.name().equals("constructor") && target.equalsIgnoreCase(contract);
            if (declared.contract().equals(contract) && matchesName
                && (!request.scope().equals("FUNCTION") || matchesTarget)
                && declared.start() <= line && line <= declared.end()) return declared.name();
        }
        throw invalid("FUNCTION_MISMATCH");
    }
    // 去掉注释和字符串内容但保留换行，避免伪声明参与源码位置校验。
    private static String maskedSource(String source) {
        var matcher = java.util.regex.Pattern.compile(
            "(?s)/\\*.*?\\*/|//[^\\r\\n]*|\"(?:\\\\.|[^\"\\\\])*\"|'(?:\\\\.|[^'\\\\])*'").matcher(source);
        return matcher.replaceAll(match -> match.group().replaceAll("[^\\r\\n]", " "));
    }
    private static int closeBrace(String source, int start) {
        int depth = 0;
        for (int i = start; i < source.length(); i++) {
            if (source.charAt(i) == '{') depth++;
            else if (source.charAt(i) == '}' && --depth == 0) return i;
        }
        return -1;
    }
    private static int lineAt(String source, int offset) {
        return 1 + (int) source.substring(0, offset).chars().filter(c -> c == '\n').count();
    }
    private static List<FunctionScope> functionScopes(String original) {
        String source = maskedSource(original);
        List<FunctionScope> scopes = new ArrayList<>();
        var contracts = java.util.regex.Pattern.compile(
            "\\b(?:contract|library|interface)\\s+([A-Za-z_$][A-Za-z0-9_$]*)[^{};]*\\{").matcher(source);
        var pattern = java.util.regex.Pattern.compile(
            "\\b(function|constructor|fallback|receive)\\s*([A-Za-z_$][A-Za-z0-9_$]*)?\\s*\\(");
        while (contracts.find()) {
            int contractEnd = closeBrace(source, contracts.end() - 1);
            if (contractEnd < 0) continue;
            var functions = pattern.matcher(source).region(contracts.end(), contractEnd);
            while (functions.find()) {
                String name = functions.group(1).equals("function")
                    ? functions.group(2) == null ? "fallback" : functions.group(2) : functions.group(1);
                if (name.equals(contracts.group(1))) name = "constructor";
                int opening = source.indexOf('{', functions.end());
                int semicolon = source.indexOf(';', functions.end());
                if (opening < 0 || opening >= contractEnd || semicolon >= 0 && semicolon < opening) continue;
                int ending = closeBrace(source, opening);
                if (ending < 0 || ending > contractEnd) continue;
                scopes.add(new FunctionScope(contracts.group(1), name, lineAt(source, functions.start()), lineAt(source, ending)));
            }
        }
        return scopes;
    }
    private static String canonicalContract(String value, String source) {
        String name = value.trim();
        var matcher = java.util.regex.Pattern.compile(
            "\\b(?:contract|library|interface)\\s+([A-Za-z_$][A-Za-z0-9_$]*)\\b").matcher(source);
        String result = null;
        while (matcher.find()) {
            String declared = matcher.group(1);
            if (declared.equalsIgnoreCase(name)) {
                if (result != null && !result.equals(declared)) throw invalid("CONTRACT_MISMATCH");
                result = declared;
            }
        }
        if (result == null) throw invalid("CONTRACT_MISMATCH");
        return result;
    }
    private static String text(JsonNode node, String key) {
        JsonNode value = node.get(key);
        if (value == null || !value.isTextual() || value.textValue().isBlank() || value.textValue().length() > 2000)
            throw invalid("SCHEMA_TEXT");
        return value.textValue();
    }
    private static OutputIssue invalid(String code) { return new OutputIssue(code); }
    private static final class OutputIssue extends IllegalArgumentException {
        final String code;
        OutputIssue(String code) { this.code = code; }
    }
    private static Result failed(String category, GatewayReply reply) {
        return failed(category, null, reply);
    }
    private static Result failed(String category, String issue, GatewayReply reply) {
        return failed(category, issue, reply, List.of());
    }
    private static Result failed(String category, String issue, GatewayReply reply, List<RejectedHypothesis> rejected) {
        return new Result("2", "FAILED", "UNRESOLVED", List.of(), category, issue,
            reply == null ? null : reply.inputTokens(), reply == null ? null : reply.outputTokens(),
            reply == null ? 0 : reply.durationMs(), reply == null ? null : reply.requestAttempts(), List.copyOf(rejected));
    }
}
