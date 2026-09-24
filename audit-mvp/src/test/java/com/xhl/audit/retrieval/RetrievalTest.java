package com.xhl.audit.retrieval;

import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static com.xhl.audit.retrieval.RetrievalData.*;

class RetrievalTest {
    private static final String HASH = "a".repeat(64);
    private final Scope scope = new Scope("C.f@1", "C", "f", List.of(), true);
    private Fact write = new Fact("risk", "C.f@1", "WRITE", "msg.sender", "balance", 1, 4);
    private ProgramFacts facts(List<Fact> rows, boolean complete) {
        return new ProgramFacts("1", HASH, complete ? "COMPLETE" : "PARTIAL",
            List.of(new StateVariable("C", "owner", 1), new StateVariable("C", "balance", 1)),
            List.of(new Scope(scope.id(), scope.contract(), scope.name(), List.of(), complete)), rows, List.of());
    }
    private Target target() {return new Target("ACCESS_CONTROL", "risk", Map.of("actor", "msg.sender", "resource", "balance", "authority", "owner"));}
    private Candidate candidate(String id, String pair, String role, double score) {
        return new Candidate(id, id + "-chunk", pair, role, "ACCESS_CONTROL", "WRITE", "案例" + id,
            List.of(new Condition("CHECK_BEFORE", "$actor", "$authority", role.equals("DEFENSE"))),
            true, "fixture-reviewed", score, score);
    }
    private CandidatePool pool(Candidate... rows) {return new CandidatePool("1", HASH, HASH, List.of(rows));}

    @Test void bindsCorrectWrongSubjectWrongResourceLateAndUnknown() {
        var defense = candidate("safe", "p", "DEFENSE", .8);
        var binder = new ConditionBinder();
        for (var check : List.of(new Fact("check", scope.id(), "CHECK", "msg.sender", "owner", 0, 2),
                                new Fact("check", scope.id(), "CHECK", "tx.origin", "owner", 0, 2),
                                new Fact("check", scope.id(), "CHECK", "msg.sender", "balance", 0, 2),
                                new Fact("check", scope.id(), "CHECK", "msg.sender", "owner", 2, 5))) {
            var bound = binder.bind(facts(List.of(check, write), true), target(), defense);
            assertEquals(check.subject().equals("msg.sender") && check.resource().equals("owner") && check.order() == 0
                ? "SUPPORTED" : "CONTRADICTED", bound.applicability());
            assertFalse(bound.conditions().getFirst().reason().isBlank());
        }
        assertEquals("UNKNOWN", binder.bind(facts(List.of(write), false), target(), defense).applicability());
    }

    @Test void d1SelectsReviewedContrastPairAndDoesNotUseContradictionAsSupport() {
        var candidates = pool(candidate("bad", "p", "VULNERABLE", .99), candidate("safe", "p", "DEFENSE", .5));
        var check = new Fact("check", scope.id(), "CHECK", "msg.sender", "owner", 0, 2);
        var output = new D1Retriever().retrieve(facts(List.of(check, write), true), target(), candidates, new Budget(1000, 2));
        assertEquals(2, output.selected().size());
        assertEquals("safe", output.selected().getFirst().candidate().caseId());
        assertEquals("SUPPORT", output.selected().getFirst().use());
        assertEquals("CONTRAST", output.selected().getLast().use());
        assertEquals("CONTRADICTED", output.selected().getLast().binding().applicability());
        assertEquals(output.context().getBytes(java.nio.charset.StandardCharsets.UTF_8).length, output.usedBytes());
    }

    @Test void refusesWrongPairUnknownAndInsufficientBudget() {
        var facts = facts(List.of(write), true);
        var d1 = new D1Retriever();
        var wrong = d1.retrieve(facts, target(), pool(candidate("bad", "p", "VULNERABLE", 1), candidate("safe", "q", "DEFENSE", .9)), new Budget(1000, 2));
        assertTrue(wrong.selected().isEmpty());
        assertFalse(wrong.gaps().isEmpty());
        var valid = pool(candidate("bad", "p", "VULNERABLE", 1), candidate("safe", "p", "DEFENSE", .9));
        var unknown = d1.retrieve(facts(List.of(write), false), target(), valid, new Budget(1000, 2));
        assertTrue(unknown.selected().isEmpty());
        assertEquals("UNKNOWN", unknown.evaluations().get("safe-chunk").conditions().getFirst().state());
        assertTrue(d1.retrieve(facts, target(), valid, new Budget(1, 2)).selected().isEmpty());
    }

    @Test void strategiesSharePoolBudgetAndDeduplicateCaseChunks() {
        var a = candidate("bad", "p", "VULNERABLE", 1);
        var duplicate = new Candidate(a.caseId(), "another", a.pairId(), a.role(), a.mechanism(), a.riskKind(), a.text(), a.conditions(), true, a.provenance(), .8, .8);
        var candidates = pool(a, duplicate, candidate("safe", "p", "DEFENSE", .9));
        String hash = null;
        for (RetrievalStrategy strategy : List.of(new DenseRetriever(), new HybridRetriever(), new ContrastiveRetriever(), new D1Retriever())) {
            var output = strategy.retrieve(facts(List.of(write), true), target(), candidates, new Budget(1000, 2));
            if (hash == null) hash = output.poolHash();
            assertEquals(hash, output.poolHash());
            assertTrue(output.usedBytes() <= 1000);
            assertEquals(output.selected().size(), output.selected().stream().map(s -> s.candidate().caseId()).distinct().count());
            assertEquals(output, strategy.retrieve(facts(List.of(write), true), target(), candidates, new Budget(1000, 2)));
        }
    }

    @Test void candidatePoolCannotBeReusedForDifferentTargetSource() {
        var candidates = new CandidatePool("1", HASH, "b".repeat(64), List.of(candidate("a", "p", "VULNERABLE", 1)));
        assertThrows(IllegalArgumentException.class, () -> new DenseRetriever().retrieve(facts(List.of(write), true), target(), candidates, new Budget(1000, 2)));
    }

    @Test void interveningAuthorityChangeOrExternalCallInvalidatesGuardBinding() {
        var check = new Fact("check", scope.id(), "CHECK", "msg.sender", "owner", 0, 2);
        var risk = new Fact("risk", scope.id(), "WRITE", "msg.sender", "balance", 2, 5);
        for (Fact intervening : List.of(new Fact("change", scope.id(), "WRITE", "msg.sender", "owner", 1, 3),
                                       new Fact("call", scope.id(), "CALL", "other", "", 1, 3))) {
            assertEquals("UNKNOWN", new ConditionBinder().bind(facts(List.of(check, intervening, risk), true), target(), candidate("safe", "p", "DEFENSE", 1)).applicability());
        }
    }

    @Test void potentiallyAliasedAuthorityWriteInvalidatesEarlierCheck() {
        var check = new Fact("check", scope.id(), "CHECK", "msg.sender", "owner[a]", 0, 2);
        var change = new Fact("change", scope.id(), "WRITE", "msg.sender", "owner[b]", 1, 3);
        var risk = new Fact("risk", scope.id(), "WRITE", "msg.sender", "balance", 2, 5);
        var query = new Target("ACCESS_CONTROL", "risk", Map.of("actor", "msg.sender", "resource", "balance", "authority", "owner[a]"));
        assertEquals("UNKNOWN", new ConditionBinder().bind(facts(List.of(check, change, risk), true), query,
            candidate("safe", "p", "DEFENSE", 1)).applicability());
    }

    @Test void malformedEvidenceAndScoresAreRejected() {
        var invalid = new Candidate("bad", "chunk", "p", "VULNERABLE", "ACCESS_CONTROL", "WRITE", "内容",
            List.of(new Condition("CHECK_BEFORE", "$actor", "$authority", false)), true, "fixture", Double.NaN, 0);
        assertThrows(IllegalArgumentException.class, () -> new D1Retriever().retrieve(facts(List.of(write), true), target(), pool(invalid), new Budget(1000, 2)));
        var missing = new Target("ACCESS_CONTROL", "absent", target().bindings());
        assertThrows(IllegalArgumentException.class, () -> new DenseRetriever().retrieve(facts(List.of(write), true), missing, pool(candidate("bad", "p", "VULNERABLE", 1)), new Budget(1000, 2)));
    }

    @Test void dynamicIndexMismatchIsUnknownRatherThanProvenDifferentResource() {
        var call = new Fact("risk", scope.id(), "CALL", "msg.sender", "", 1, 4);
        var write = new Fact("w", scope.id(), "WRITE", "msg.sender", "balance[other]", 0, 2);
        var safe = new Candidate("safe", "chunk", "p", "DEFENSE", "REENTRANCY", "CALL", "案例",
            List.of(new Condition("STATE_WRITE_BEFORE", "$actor", "$resource", true)), true, "fixture", 1, 1);
        var query = new Target("REENTRANCY", "risk", Map.of("actor", "msg.sender", "resource", "balance[msg.sender]"));
        assertEquals("UNKNOWN", new ConditionBinder().bind(facts(List.of(write, call), true), query, safe).applicability());
    }

    @Test void reversedEqualityRetainsDynamicAuthorityAliasUncertainty() {
        var check = new Fact("check", scope.id(), "CHECK", "owner[b]", "msg.sender", 0, 2);
        var query = new Target("ACCESS_CONTROL", "risk", Map.of("actor", "msg.sender", "resource", "balance", "authority", "owner[a]"));
        for (String role : List.of("VULNERABLE", "DEFENSE")) {
            assertEquals("UNKNOWN", new ConditionBinder().bind(facts(List.of(check, write), true), query,
                candidate("case", "p", role, 1)).applicability());
        }
    }

    @Test void duplicateConditionPairsDoNotConsumeExtraContextBudget() {
        var candidates = pool(candidate("a", "one", "VULNERABLE", 1), candidate("b", "one", "DEFENSE", .9),
                              candidate("c", "two", "VULNERABLE", .8), candidate("d", "two", "DEFENSE", .7));
        var output = new D1Retriever().retrieve(facts(List.of(write), true), target(), candidates, new Budget(2000, 4));
        assertEquals(2, output.selected().size());
    }

    @Test void stateWriteBeforeCallMatchesOnlySameResource() {
        var call = new Fact("risk", scope.id(), "CALL", "msg.sender", "", 1, 4);
        var safe = new Candidate("safe", "chunk", "p", "DEFENSE", "REENTRANCY", "CALL", "先更新状态",
            List.of(new Condition("STATE_WRITE_BEFORE", "$actor", "$resource", true)), true, "fixture", 1, 1);
        var query = new Target("REENTRANCY", "risk", Map.of("actor", "msg.sender", "resource", "balance"));
        assertEquals("SUPPORTED", new ConditionBinder().bind(facts(List.of(new Fact("w", scope.id(), "WRITE", "msg.sender", "balance", 0, 2), call), true), query, safe).applicability());
        assertEquals("CONTRADICTED", new ConditionBinder().bind(facts(List.of(new Fact("w", scope.id(), "WRITE", "msg.sender", "owner", 0, 2), call), true), query, safe).applicability());
    }
}
