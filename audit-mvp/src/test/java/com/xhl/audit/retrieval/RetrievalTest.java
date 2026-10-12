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

    @Test void accessControlCanBindGuardBeforeExternalCall() {
        var call = new Fact("risk", scope.id(), "CALL", "target", "", 1, 4);
        var check = new Fact("check", scope.id(), "CHECK", "msg.sender", "owner", 0, 2);
        var query = new Target("ACCESS_CONTROL", "risk", Map.of("actor", "msg.sender", "authority", "owner"));
        var defense = new Candidate("safe", "safe-chunk", "p", "DEFENSE", "ACCESS_CONTROL", "CALL", "案例",
            List.of(new Condition("CHECK_BEFORE", "$actor", "$authority", true)), true, "fixture", 1, 1);
        assertEquals("SUPPORTED", new ConditionBinder().bind(facts(List.of(check, call), true), query, defense).applicability());
    }

    @Test void exploratoryPoolAcceptsOnlyUnreviewedCandidatesAndFormalStillRejectsThem() {
        var original = candidate("bad", "pair", "VULNERABLE", .9);
        var provisional = new Candidate(original.caseId(), original.chunkId(), original.pairId(),
            original.role(), original.mechanism(), original.riskKind(), original.text(),
            original.conditions(), false, original.provenance(), original.denseScore(), original.lexicalScore());
        var facts = facts(List.of(write), true);
        assertThrows(IllegalArgumentException.class, () -> new DenseRetriever().retrieve(facts, target(),
            pool(provisional), new Budget(1000, 2)));
        var exploratory = new CandidatePool("exploratory-1", HASH, HASH, List.of(provisional));
        assertEquals("DENSE", new DenseRetriever().retrieve(facts, target(), exploratory, new Budget(1000, 2)).strategy());
        assertThrows(IllegalArgumentException.class, () -> new DenseRetriever().retrieve(facts, target(),
            new CandidatePool("exploratory-1", HASH, HASH, List.of(original)), new Budget(1000, 2)));
    }

    @Test void reentrancyModifierBindingIsSyntacticAndIncompleteScopeIsUnknown() {
        var call = new Fact("risk-call", scope.id(), "CALL", "msg.sender", "", 1, 4);
        var query = new Target("REENTRANCY", "risk-call", Map.of("actor", "msg.sender", "resource", "balance"));
        var provisional = new Candidate("patched", "patched-chunk", "pair", "DEFENSE", "REENTRANCY", "CALL", "修饰器对照",
            List.of(new Condition("NON_REENTRANT", "$actor", "$resource", true)), false, "pending", .9, .1);
        var withModifier = new ProgramFacts("1", HASH, "COMPLETE", List.of(),
            List.of(new Scope(scope.id(), scope.contract(), scope.name(), List.of("nonReentrant"), true)), List.of(call), List.of());
        assertEquals("SUPPORTED", new ConditionBinder().bind(withModifier, query, provisional).applicability());
        assertEquals("CONTRADICTED", new ConditionBinder().bind(facts(List.of(call), true), query, provisional).applicability());
        assertEquals("UNKNOWN", new ConditionBinder().bind(facts(List.of(call), false), query, provisional).applicability());
    }

    @Test void exploratoryReferenceCanBeRecalledButCannotFormD1Pair() {
        var reference = new Candidate("report", "report-chunk", "unpaired", "REFERENCE", "ACCESS_CONTROL", "WRITE", "待审报告",
            List.of(), false, "pending", .9, .1);
        var exploratory = new CandidatePool("exploratory-1", HASH, HASH, List.of(reference));
        assertEquals(1, new DenseRetriever().retrieve(facts(List.of(write), true), target(), exploratory, new Budget(1000, 2)).selected().size());
        assertEquals(0, new D1Retriever().retrieve(facts(List.of(write), true), target(), exploratory, new Budget(1000, 2)).selected().size());
        assertThrows(IllegalArgumentException.class, () -> new DenseRetriever().retrieve(facts(List.of(write), true), target(),
            pool(reference), new Budget(1000, 2)));
    }

    @Test void autoLabeledPoolUsesSoftPairWhenNoStrictConditionMatches() {
        var original = new Candidate("before", "before", "patch-1", "VULNERABLE", "ACCESS_CONTROL", "WRITE", "value = next;",
            List.of(), false, "auto", .91, 0);
        var patched = new Candidate("after", "after", "patch-1", "DEFENSE", "ACCESS_CONTROL", "WRITE", "require(msg.sender == admin); value = next;",
            List.of(), false, "auto", .83, 0);
        var auto = new CandidatePool("auto-1", HASH, HASH, List.of(original, patched));
        var output = new D1Retriever().retrieve(facts(List.of(write), true), target(), auto, new Budget(1000, 2));
        assertEquals(List.of("before", "after"), output.selected().stream().map(s -> s.candidate().chunkId()).toList());
        assertTrue(output.gaps().stream().anyMatch(value -> value.contains("自动标注软配对")));
        assertEquals("DENSE", new DenseRetriever().retrieve(facts(List.of(write), true), target(), auto,
            new Budget(1000, 2)).strategy());
    }

    @Test void 自动软配对拒绝只有文字标签差异的片段() {
        assertFalse(AutomaticContrast.changed("改动前", "改动后", "ACCESS_CONTROL"));
        assertFalse(AutomaticContrast.changed("旧代码", "新代码", "REENTRANCY"));
    }

    @Test void explicitOwnerModifierCanBindEvenWhenBodyIsPartial() {
        var modifier = new Candidate("patched", "patched", "p", "DEFENSE", "ACCESS_CONTROL", "WRITE", "onlyOwner",
            List.of(new Condition("ONLY_OWNER", "$actor", "$authority", true)), false, "auto", .9, 0);
        var partial = new ProgramFacts("1", HASH, "PARTIAL", List.of(),
            List.of(new Scope(scope.id(), "C", "f", List.of("onlyOwner"), false)), List.of(write), List.of());
        assertEquals("SUPPORTED", new ConditionBinder().bind(partial, target(), modifier).applicability());
        assertEquals("UNKNOWN", new ConditionBinder().bind(facts(List.of(write), false), target(), modifier).applicability());
    }

    @Test void 自动软配对拒绝接口重命名而保留两组实际保护改动() {
        var rows = new java.util.ArrayList<Candidate>();
        for (int i = 0; i < 3; i++) {
            String before = i == 0 ? "-ERC20I(token).transfer(msg.sender, amount);\n delete credit[msg.sender];" : "value" + i + " = next;";
            String after = i == 0 ? "+ERC20(token).transfer(msg.sender, amount);\n delete credit[msg.sender];"
                : "require(msg.sender == " + (i == 1 ? "admin" : "manager") + ");\n" + before;
            String mechanism = i == 0 ? "REENTRANCY" : "ACCESS_CONTROL";
            String kind = i == 0 ? "CALL" : "WRITE";
            for (int side = 0; side < 2; side++) rows.add(new Candidate("case-" + i + "-" + side,
                "chunk-" + i + "-" + side, "pair-" + i, side == 0 ? "VULNERABLE" : "DEFENSE", mechanism,
                kind, side == 0 ? before : after, List.of(), false, "auto", 1.0 - i * .1, 0));
        }
        var auto = new CandidatePool("auto-1", HASH, HASH, rows);
        var output = new D1Retriever().retrieve(facts(List.of(write), true), target(), auto, new Budget(4096, 4));
        assertEquals(4, output.selected().size());
        assertTrue(output.selected().stream().allMatch(row -> row.binding().applicability().equals("UNKNOWN")));
        assertTrue(output.context().contains("改动后"));
        assertFalse(output.context().contains("|DEFENSE]"));
        var call = new Fact("risk-call", scope.id(), "CALL", "msg.sender", "", 1, 4);
        var query = new Target("REENTRANCY", "risk-call", Map.of("actor", "msg.sender"));
        assertTrue(new D1Retriever().retrieve(facts(List.of(call), true), query, auto, new Budget(4096, 4)).selected().isEmpty());
    }

    @Test void 自动条件即使能够匹配也不能冒充已审核补丁适用性() {
        var before = new Candidate("before", "before", "pair", "VULNERABLE", "ACCESS_CONTROL", "WRITE", "value = next;",
            List.of(new Condition("CHECK_BEFORE", "$actor", "$authority", false)), false, "auto", .9, 0);
        var after = new Candidate("after", "after", "pair", "DEFENSE", "ACCESS_CONTROL", "WRITE", "require(msg.sender == admin); value = next;",
            List.of(new Condition("CHECK_BEFORE", "$actor", "$authority", true)), false, "auto", .8, 0);
        var output = new D1Retriever().retrieve(facts(List.of(write), true), target(),
            new CandidatePool("auto-1", HASH, HASH, List.of(before, after)), new Budget(4096, 4));
        assertEquals(List.of("SOFT_SUPPORT", "SOFT_CONTRAST"), output.selected().stream().map(Selection::use).toList());
        assertTrue(output.evaluations().values().stream().allMatch(binding -> binding.applicability().equals("UNKNOWN")));
    }

    @Test void 自动机制规则忽略注释字符串不完整条件和权限主体改名() {
        assertFalse(AutomaticContrast.changed("value = next;", "value = next; // require(msg.sender == admin);\n"
            + "string s = \"onlyOwner require(msg.sender == admin);\";", "ACCESS_CONTROL"));
        assertFalse(AutomaticContrast.changed("value = next;", "require(msg.sender == admin", "ACCESS_CONTROL"));
        assertFalse(AutomaticContrast.changed("require(msg.sender == owner);", "require(msg.sender == admin);", "ACCESS_CONTROL"));
        assertTrue(AutomaticContrast.changed("msg.sender.call(\"\"); credit[msg.sender] = 0;",
            "credit[msg.sender] = 0; msg.sender.call(\"\");", "REENTRANCY"));
    }

    @Test void 自动完整配对预算包含中文未审核标题() {
        var before = new Candidate("改动前", "前", "配对", "VULNERABLE", "ACCESS_CONTROL", "WRITE", "value = next;",
            List.of(), false, "auto", .9, 0);
        var after = new Candidate("改动后", "后", "配对", "DEFENSE", "ACCESS_CONTROL", "WRITE", "require(msg.sender == admin); value = next;",
            List.of(), false, "auto", .8, 0);
        var auto = new CandidatePool("auto-1", HASH, HASH, List.of(before, after));
        var full = new D1Retriever().retrieve(facts(List.of(write), true), target(), auto, new Budget(4096, 4));
        assertEquals(full.context().getBytes(java.nio.charset.StandardCharsets.UTF_8).length, full.usedBytes());
        assertEquals(2, new D1Retriever().retrieve(facts(List.of(write), true), target(), auto,
            new Budget(full.usedBytes(), 4)).selected().size());
        assertTrue(new D1Retriever().retrieve(facts(List.of(write), true), target(), auto,
            new Budget(full.usedBytes() - 1, 4)).selected().isEmpty());
    }

    @Test void 自动配对不能跨越风险类型或者复用相同文本() {
        var rows = new java.util.ArrayList<Candidate>();
        for (int i = 0; i < 2; i++) {
            rows.add(new Candidate("前" + i, "前" + i, "对" + i, "VULNERABLE", "ACCESS_CONTROL", "WRITE", "value = next;",
                List.of(), false, "auto", .9 - i * .1, 0));
            rows.add(new Candidate("后" + i, "后" + i, "对" + i, "DEFENSE", "ACCESS_CONTROL", "WRITE", "require(msg.sender == admin); value = next;",
                List.of(), false, "auto", .8 - i * .1, 0));
        }
        assertEquals(2, new D1Retriever().retrieve(facts(List.of(write), true), target(),
            new CandidatePool("auto-1", HASH, HASH, rows), new Budget(4096, 4)).selected().size());
        var mismatched = new Candidate("后", "后", "对0", "DEFENSE", "ACCESS_CONTROL", "CALL", "require(msg.sender == admin); value = next;",
            List.of(), false, "auto", .8, 0);
        assertTrue(new D1Retriever().retrieve(facts(List.of(write), true), target(),
            new CandidatePool("auto-1", HASH, HASH, List.of(rows.getFirst(), mismatched)), new Budget(4096, 4)).selected().isEmpty());
    }

    @Test void 自动Dense与Hybrid入选绑定和评估均保留未知() {
        var before = new Candidate("前", "前", "对", "VULNERABLE", "ACCESS_CONTROL", "WRITE", "value = next;",
            List.of(new Condition("CHECK_BEFORE", "$actor", "$authority", false)), false, "auto", .9, .1);
        var after = new Candidate("后", "后", "对", "DEFENSE", "ACCESS_CONTROL", "WRITE", "require(msg.sender == owner); value = next;",
            List.of(new Condition("CHECK_BEFORE", "$actor", "$authority", true)), false, "auto", .8, .1);
        var guarded = facts(List.of(new Fact("guard", scope.id(), "CHECK", "msg.sender", "owner", 0, 2), write), true);
        var auto = new CandidatePool("auto-1", HASH, HASH, List.of(before, after));
        for (RetrievalStrategy strategy : List.of(new DenseRetriever(), new HybridRetriever())) {
            var output = strategy.retrieve(guarded, target(), auto, new Budget(4096, 4));
            assertEquals(List.of("前", "后"), output.selected().stream().map(row -> row.candidate().chunkId()).toList());
            assertTrue(output.selected().stream().allMatch(row -> row.binding().applicability().equals("UNKNOWN")));
            assertTrue(output.evaluations().values().stream().allMatch(binding -> binding.applicability().equals("UNKNOWN")));
        }
    }

    @Test void 自动软配对拒绝多义登记及多义标识() {
        var before = new Candidate("前", "前", "对", "VULNERABLE", "ACCESS_CONTROL", "WRITE", "value = next;",
            List.of(), false, "auto", .9, 0);
        var other = new Candidate("另一前", "另一前", "对", "VULNERABLE", "ACCESS_CONTROL", "WRITE", "otherValue = next;",
            List.of(), false, "auto", .99, 0);
        var after = new Candidate("后", "后", "对", "DEFENSE", "ACCESS_CONTROL", "WRITE", "require(msg.sender == owner); value = next;",
            List.of(), false, "auto", .8, 0);
        assertTrue(new D1Retriever().retrieve(facts(List.of(write), true), target(),
            new CandidatePool("auto-1", HASH, HASH, List.of(before, other, after)), new Budget(4096, 4)).selected().isEmpty());
        assertFalse(AutomaticContrast.changed("【配对关系不唯一，禁止软配对】\nvalue = next;",
            "【配对关系不唯一，禁止软配对】\nrequire(msg.sender == owner); value = next;", "ACCESS_CONTROL"));
    }
}
