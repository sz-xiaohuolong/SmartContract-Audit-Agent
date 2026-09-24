package com.xhl.audit.retrieval;

import java.util.List;
import java.util.Map;

/** D1 与检索对照共享的纯数据契约；不含目标真值。 */
public final class RetrievalData {
    private RetrievalData() {}
    public record StateVariable(String contract, String name, int line) {}
    public record Scope(String id, String contract, String name, List<String> modifiers, boolean complete) {}
    public record Fact(String id, String scope, String kind, String subject, String resource, int order, int line) {}
    public record ProgramFacts(String schemaVersion, String sourceHash, String status, List<StateVariable> stateVariables,
                               List<Scope> scopes, List<Fact> facts, List<String> limitations) {}
    public record Target(String mechanism, String riskFactId, Map<String, String> bindings) {}
    public record Condition(String predicate, String subject, String resource, Boolean expected) {}
    public record Candidate(String caseId, String chunkId, String pairId, String role, String mechanism, String riskKind,
                            String text, List<Condition> conditions, boolean reviewed, String provenance,
                            double denseScore, double lexicalScore) {}
    public record CandidatePool(String schemaVersion, String snapshotId, String sourceHash, List<Candidate> candidates) {}
    public record Budget(int maxBytes, int maxCases) {}
    public record BoundCondition(Condition condition, String subject, String resource, String state,
                                 List<String> evidenceIds, String reason) {}
    public record Binding(String applicability, List<BoundCondition> conditions) {}
    public record Selection(Candidate candidate, String use, Binding binding) {}
    public record EvidenceBundle(String strategy, String sourceHash, String snapshotId, String poolHash, Budget budget,
                                 String budgetVersion, int usedBytes, String context,
                                 List<Selection> selected, List<String> gaps, Target target, Map<String, Binding> evaluations) {}
}
