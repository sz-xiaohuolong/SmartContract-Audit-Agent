package com.xhl.audit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

/** 本地目录接口夹具，只验证绑定行为，不作为真实编译或漏洞证据。 */
final class RiskCatalogFixture {
    static final ObjectMapper MAPPER = new ObjectMapper();
    static String digest(byte[] value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
        catch (Exception error) { throw new AssertionError(error); }
    }
    static ObjectNode catalog(String source) {
        var catalog = MAPPER.createObjectNode();
        catalog.put("schemaVersion", "compiler-risk-1").put("provider", "solc-standard-json")
            .put("verificationStatus", "RECOMPILED_MATCH").put("sourceHash", digest(source.getBytes(StandardCharsets.UTF_8)))
            .put("targetSourceUnit", "Contract.sol").put("environmentHash", "1".repeat(64))
            .put("receiptDigest", "2".repeat(64)).put("sourceClosureSha256", "3".repeat(64)).put("status", "PARTIAL");
        catalog.putArray("contracts");
        catalog.putArray("operations");
        catalog.putArray("sourceUnits").addObject().put("sourceUnit", "Contract.sol").put("sourceUnitId", 0)
            .put("sha256", catalog.path("sourceHash").asText());
        return catalog;
    }
    static ObjectNode guidance(ObjectNode catalog, String text) {
        var result = MAPPER.createObjectNode().put("schemaVersion", "permission-guidance-1")
            .put("text", text).put("textSha256", digest(text.getBytes(StandardCharsets.UTF_8)))
            .put("textBytes", text.getBytes(StandardCharsets.UTF_8).length)
            .put("indexSha256", "a".repeat(64)).put("complete", false).put("indexOmittedRelationCount", 0);
        for (String key : java.util.List.of("sourceHash", "receiptDigest", "environmentHash", "sourceClosureSha256"))
            result.set(key, catalog.get(key));
        result.putArray("includedRelationIds");
        result.putArray("omittedRelationIds");
        return result;
    }
    static ObjectNode operation(ObjectNode catalog, String source, String contract, String function,
                                String expression, String operation, String factId) {
        int offset = source.indexOf(expression);
        int start = source.substring(0, offset).getBytes(StandardCharsets.UTF_8).length;
        int line = 1 + (int) source.substring(0, offset).chars().filter(c -> c == '\n').count();
        var declarations = catalog.withArray("contracts");
        ObjectNode declaration = null;
        for (var item : declarations)
            if (contract.equals(item.path("contract").asText())) declaration = (ObjectNode) item;
        if (declaration == null) {
            declaration = declarations.addObject();
            declaration.put("contract", contract).put("declarationId", declarations.size())
                .put("sourceUnit", "Contract.sol").put("sourceUnitHash", catalog.path("sourceHash").asText());
            declaration.putArray("entries");
        }
        var entry = declaration.withArray("entries").addObject();
        entry.put("signature", function + "()").put("function", function).put("kind", "function")
            .put("matched", true).put("declarationId", 100 + declarations.size());
        var row = catalog.withArray("operations").addObject();
        row.put("contract", contract).put("contractDeclarationId", declaration.path("declarationId").asInt())
            .put("function", function).put("entrySignature", function + "()")
            .put("entryDeclarationId", entry.path("declarationId").asInt()).put("riskOperation", operation)
            .put("factId", factId).put("line", line).put("sourceUnit", "Contract.sol")
            .put("sourceUnitHash", catalog.path("sourceHash").asText()).put("candidateEligible", true);
        row.putObject("span").put("start", start).put("length", expression.getBytes(StandardCharsets.UTF_8).length)
            .put("sourceUnitId", 0).put("sourceUnit", "Contract.sol").put("line", line)
            .put("contentSha256", digest(expression.getBytes(StandardCharsets.UTF_8)));
        row.putObject("capability").put("status", "MECHANISM_UNSUPPORTED").putArray("gaps");
        return row;
    }
    private RiskCatalogFixture() {}
}
