package com.xhl.audit;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class HypothesisServiceTest {
    private static final String SOURCE = "contract Vault { function withdraw() public { msg.sender.call(\"\"); } }";
    private HypothesisService.Request request() {
        return new HypothesisService.Request(SOURCE, SOURCE, null, "FULL", 1, 1,
            "REENTRANCY", "withdraw", "[案例]", List.of("evidence-1"));
    }
    private HypothesisService service(String body, Integer input, Integer output, String finish) {
        return new HypothesisService((provider, system, user) ->
            new GatewayReply(body, "fixture", "fixture", input, output, 1, finish));
    }

    @Test void validEmptyAndReportedHypothesesRemainPreliminary() {
        var empty = service("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", null, null, "stop")
            .analyze(request(), "fixture");
        assertEquals("COMPLETED", empty.status());
        assertEquals("NO_CONFIRMED_FINDINGS", empty.conclusion());
        assertNull(empty.inputTokens());
        var body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Vault","function":"withdraw","riskLine":1,"riskOperation":"CALL",
            "reason":"调用前状态未更新","evidenceIds":["evidence-1"]}]}
            """;
        var reported = service(body, 15, 20, "stop").analyze(request(), "fixture");
        assertEquals("COMPLETED", reported.status());
        assertEquals("VULNERABILITY_REPORTED", reported.conclusion());
        assertEquals(1, reported.hypotheses().size());
        assertEquals(20, reported.outputTokens());
    }

    @Test void badStructureLineAndEvidenceNeverBecomeSafe() {
        var valid = "{\"schemaVersion\":\"2\",\"hypotheses\":[{\"vulnerabilityType\":\"REENTRANCY\",\"contract\":\"Vault\",\"function\":\"withdraw\",\"riskLine\":1,\"riskOperation\":\"CALL\",\"reason\":\"x\",\"evidenceIds\":[\"evidence-1\"]}]}";
        for (String body : List.of("", "{}", valid.replace("\"riskLine\":1", "\"riskLine\":2"),
                                   valid.replace("evidence-1", "unknown"),
                                   valid.replace("\"reason\":\"x\"", "\"reason\":\"x\",\"extra\":1"),
                                   valid.replace("\"reason\":\"x\"", "\"reason\":\"x\",\"reason\":\"y\""),
                                   valid + "{}",
                                   valid.replace("REENTRANCY", "ACCESS_CONTROL"))) {
            var result = service(body, null, null, "stop").analyze(request(), "fixture");
            assertEquals("FAILED", result.status(), body);
            assertEquals("UNRESOLVED", result.conclusion());
            assertEquals("MODEL_OUTPUT_INVALID", result.errorCategory());
        }
    }

    @Test void truncationAndCallErrorPreserveUnknown() {
        var truncated = service("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", 10, 2048, "length")
            .analyze(request(), "fixture");
        assertEquals("FAILED", truncated.status());
        assertEquals("MODEL_OUTPUT_TRUNCATED", truncated.errorCategory());
        assertEquals(2048, truncated.outputTokens());
        var failed = new HypothesisService((p, s, u) -> {throw new RuntimeException("secret");})
            .analyze(request(), "fixture");
        assertEquals("FAILED", failed.status());
        assertEquals("MODEL_CALL_ERROR", failed.errorCategory());
        assertFalse(failed.toString().contains("secret"));
    }
    @Test void sourceDigestAndScopeMustMatchBeforeCallingModel() {
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        var service = new HypothesisService((p, s, u) -> {
            calls.incrementAndGet();
            return new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", "fixture", "fixture", null, null, 1);
        });
        var badHash = new HypothesisService.Request(SOURCE, SOURCE, "0".repeat(64), "FULL", 1, 1,
            "REENTRANCY", "withdraw", "", List.of());
        assertEquals("FAILED", service.analyze(badHash, "fixture").status());
        var badExcerpt = new HypothesisService.Request(SOURCE, "contract Other {}", null, "FULL", 1, 1,
            "REENTRANCY", "withdraw", "", List.of());
        assertEquals("FAILED", service.analyze(badExcerpt, "fixture").status());
        assertEquals(0, calls.get());
    }
}
