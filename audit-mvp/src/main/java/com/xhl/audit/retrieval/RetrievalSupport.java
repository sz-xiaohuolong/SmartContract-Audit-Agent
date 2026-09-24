package com.xhl.audit.retrieval;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import static com.xhl.audit.retrieval.RetrievalData.*;

final class RetrievalSupport {
    private RetrievalSupport() {}
    static void require(boolean condition) {if (!condition) throw new IllegalArgumentException("检索输入契约无效");}
    static boolean text(String value) {return value != null && !value.isBlank();}
    static boolean hash(String value) {return value != null && value.matches("[0-9a-f]{64}");}
    static void validateFacts(ProgramFacts facts, Target target) {
        require(facts != null && "1".equals(facts.schemaVersion()) && hash(facts.sourceHash())
            && Set.of("COMPLETE", "PARTIAL", "FAILED").contains(facts.status()));
        require(target != null && Set.of("REENTRANCY", "ACCESS_CONTROL").contains(target.mechanism())
            && text(target.riskFactId()) && target.bindings() != null && "msg.sender".equals(target.bindings().get("actor")));
        require(target.bindings().entrySet().stream().allMatch(e -> Set.of("actor", "resource", "authority").contains(e.getKey()) && text(e.getValue())));
        require(facts.scopes() != null && facts.facts() != null && facts.stateVariables() != null && facts.limitations() != null);
        var scopes = new HashMap<String, Scope>();
        for (Scope scope : facts.scopes()) {
            require(scope != null && text(scope.id()) && text(scope.contract()) && text(scope.name()) && scope.modifiers() != null);
            require(scopes.putIfAbsent(scope.id(), scope) == null);
            if (facts.status().equals("COMPLETE")) require(scope.complete());
        }
        var ids = new HashSet<String>();
        var orders = new HashSet<String>();
        for (Fact fact : facts.facts()) {
            require(fact != null && text(fact.id()) && scopes.containsKey(fact.scope()) && fact.line() > 0 && fact.order() >= 0
                && Set.of("CALL", "WRITE", "CHECK").contains(fact.kind()) && fact.subject() != null && fact.resource() != null);
            require(ids.add(fact.id()) && orders.add(fact.scope() + ":" + fact.order()));
        }
        for (StateVariable variable : facts.stateVariables()) require(variable != null && text(variable.contract()) && text(variable.name()) && variable.line() > 0);
        Fact risk = facts.facts().stream().filter(f -> f.id().equals(target.riskFactId())).findFirst().orElseThrow(() -> new IllegalArgumentException("风险位置不存在"));
        require(risk.kind().equals(target.mechanism().equals("REENTRANCY") ? "CALL" : "WRITE"));
        if (risk.kind().equals("WRITE")) require(risk.resource().equals(target.bindings().get("resource")));
    }
    static void validateCandidate(Candidate candidate) {
        require(candidate != null && text(candidate.caseId()) && text(candidate.chunkId()) && text(candidate.pairId())
            && Set.of("VULNERABLE", "DEFENSE").contains(candidate.role())
            && Set.of("REENTRANCY", "ACCESS_CONTROL").contains(candidate.mechanism())
            && candidate.riskKind().equals(candidate.mechanism().equals("REENTRANCY") ? "CALL" : "WRITE")
            && text(candidate.text()) && text(candidate.provenance()) && candidate.reviewed()
            && Double.isFinite(candidate.denseScore()) && Double.isFinite(candidate.lexicalScore())
            && candidate.conditions() != null && !candidate.conditions().isEmpty());
        var conditions = new HashSet<String>();
        for (Condition condition : candidate.conditions()) {
            require(condition != null && Set.of("CHECK_BEFORE", "STATE_WRITE_BEFORE").contains(condition.predicate())
                && text(condition.subject()) && text(condition.resource()) && condition.expected() != null);
            require(conditions.add(condition.predicate() + ":" + condition.subject() + ":" + condition.resource()));
        }
    }
    static void validate(ProgramFacts facts, Target target, CandidatePool pool, Budget budget) {
        validateFacts(facts, target);
        require(pool != null && "1".equals(pool.schemaVersion()) && hash(pool.snapshotId()) && facts.sourceHash().equals(pool.sourceHash()) && pool.candidates() != null && pool.candidates().size() <= 1000);
        require(budget != null && budget.maxBytes() > 0 && budget.maxBytes() <= 1_048_576 && budget.maxCases() > 0 && budget.maxCases() <= 1000);
        var ids = new HashSet<String>();
        var cases = new HashMap<String, Candidate>();
        for (Candidate candidate : pool.candidates()) {
            validateCandidate(candidate);
            require(ids.add(candidate.chunkId()));
            Candidate previous = cases.putIfAbsent(candidate.caseId(), candidate);
            if (previous != null) require(previous.pairId().equals(candidate.pairId()) && previous.role().equals(candidate.role())
                && previous.mechanism().equals(candidate.mechanism()) && previous.riskKind().equals(candidate.riskKind())
                && previous.conditions().equals(candidate.conditions()) && previous.provenance().equals(candidate.provenance()));
        }
    }
    static String hashObject(Object value) {
        try {return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(new ObjectMapper().writeValueAsBytes(value)));}
        catch (Exception error) {throw new IllegalArgumentException("无法计算候选池摘要", error);}
    }
    static Comparator<Candidate> ranking(boolean hybrid) {
        return Comparator.<Candidate>comparingDouble(c -> hybrid ? c.denseScore() + c.lexicalScore() : c.denseScore())
            .reversed().thenComparing(Candidate::caseId).thenComparing(Candidate::chunkId);
    }
    static String context(Selection selection) {
        Candidate candidate = selection.candidate();
        return "[" + candidate.caseId() + "/" + candidate.chunkId() + "|" + candidate.role() + "]\n" + candidate.text() + "\n";
    }
    static int bytes(Selection selection) {return context(selection).getBytes(StandardCharsets.UTF_8).length;}
    static EvidenceBundle bundle(String name, ProgramFacts facts, Target target, CandidatePool pool, Budget budget, List<Selection> rows, List<String> gaps) {
        String context = rows.stream().map(RetrievalSupport::context).collect(java.util.stream.Collectors.joining());
        var evaluations = new TreeMap<String, Binding>();
        for (Candidate candidate : pool.candidates()) evaluations.put(candidate.chunkId(), new ConditionBinder().bind(facts, target, candidate));
        return new EvidenceBundle(name, facts.sourceHash(), pool.snapshotId(), hashObject(pool), budget, "utf8-context-bytes-v1",
            context.getBytes(StandardCharsets.UTF_8).length, context, List.copyOf(rows), List.copyOf(gaps), target, Collections.unmodifiableMap(evaluations));
    }
}
