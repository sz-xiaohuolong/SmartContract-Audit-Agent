package com.xhl.audit;

public record AuditResult(String schemaVersion, String sourceHash, Status status, Conclusion conclusion,
    String vulnerabilityType, String reason, String provider, String model,
    Integer inputTokens, Integer outputTokens, long durationMs, String errorCategory) {
    public enum Status { COMPLETED, FAILED }
    public enum Conclusion { VULNERABILITY_REPORTED, NO_CONFIRMED_FINDINGS, UNRESOLVED }
}
