package com.xhl.audit;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AuditServiceTest {
    private AuditService service(String content) {
        return new AuditService((provider, system, user) -> new GatewayReply(content, "fixture", "fixture", 10, 5, 1));
    }
    @Test void malformedResponsesNeverBecomeSafe() {
        for (String text : new String[]{"", "{}", "not json", "{\"hasVulnerability\":false}",
            "{\"hasVulnerability\":\"false\",\"vulnerabilityType\":\"none\",\"vulnerabilityReason\":\"x\"}",
            "{\"hasVulnerability\":false,\"vulnerabilityType\":\"none\",\"vulnerabilityReason\":\"x\"} {}"}) {
            var result = service(text).audit("contract C {}", null);
            assertEquals(AuditResult.Status.FAILED, result.status(), text);
            assertEquals(AuditResult.Conclusion.UNRESOLVED, result.conclusion());
        }
    }
    @Test void negativeMeansNoConfirmedFindingsNotProvenSafety() {
        var result = service("{\"hasVulnerability\":false,\"vulnerabilityType\":\"none\",\"vulnerabilityReason\":\"未发现\"}").audit("contract C {}", null);
        assertEquals(AuditResult.Status.COMPLETED, result.status());
        assertEquals(AuditResult.Conclusion.NO_CONFIRMED_FINDINGS, result.conclusion());
        assertEquals(64, result.sourceHash().length());assertEquals(10, result.inputTokens());
    }
    @Test void transportFailureIsSeparateAndSanitized() {
        var s = new AuditService((p, system, u) -> { throw new IllegalStateException("secret-key-sensitive"); });
        var result = s.audit("contract C {}", null);
        assertEquals(AuditResult.Status.FAILED, result.status());
        assertFalse(result.toString().contains("secret-key-sensitive"));
    }
}
