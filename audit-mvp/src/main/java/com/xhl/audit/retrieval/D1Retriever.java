package com.xhl.audit.retrieval;

import java.util.*;
import static com.xhl.audit.retrieval.RetrievalData.*;

/** 基于明确条件适用性与审核差异选择完整配对；不裁决目标是否安全。 */
public final class D1Retriever implements RetrievalStrategy {
    private record Pair(Selection support, Selection contrast, int coverage, double score) {}
    @Override public EvidenceBundle retrieve(ProgramFacts facts, Target target, CandidatePool pool, Budget budget) {
        RetrievalSupport.validate(facts, target, pool, budget);
        var bound = new LinkedHashMap<String, Binding>();
        for (Candidate candidate : pool.candidates()) bound.put(candidate.chunkId(), new ConditionBinder().bind(facts, target, candidate));
        var pairs = new ArrayList<Pair>();
        for (Candidate a : pool.candidates()) for (Candidate b : pool.candidates()) {
            if (!a.role().equals("VULNERABLE") || !b.role().equals("DEFENSE") || !isPair(a, b)) continue;
            Binding left = bound.get(a.chunkId()), right = bound.get(b.chunkId());
            if (left.applicability().equals("SUPPORTED") && right.applicability().equals("CONTRADICTED"))
                pairs.add(new Pair(new Selection(a, "SUPPORT", left), new Selection(b, "CONTRAST", right), a.conditions().size(), a.denseScore() + b.denseScore()));
            else if (right.applicability().equals("SUPPORTED") && left.applicability().equals("CONTRADICTED"))
                pairs.add(new Pair(new Selection(b, "SUPPORT", right), new Selection(a, "CONTRAST", left), b.conditions().size(), a.denseScore() + b.denseScore()));
        }
        pairs.sort(Comparator.comparingInt(Pair::coverage).reversed().thenComparing(Comparator.comparingDouble(Pair::score).reversed())
            .thenComparing(p -> p.support().candidate().chunkId()).thenComparing(p -> p.contrast().candidate().chunkId()));
        var selected = new ArrayList<Selection>();
        var cases = new HashSet<String>();
        var texts = new HashSet<String>();
        var covered = new HashSet<String>();
        int used = 0;
        for (Pair pair : pairs) {
            Candidate a = pair.support().candidate(), b = pair.contrast().candidate();
            int cost = RetrievalSupport.bytes(pair.support()) + RetrievalSupport.bytes(pair.contrast());
            var signatures = pair.support().binding().conditions().stream()
                .map(c -> c.condition().predicate() + ":" + c.subject() + ":" + c.resource()).toList();
            if (covered.containsAll(signatures)) continue;
            if (cases.contains(a.caseId()) || cases.contains(b.caseId()) || texts.contains(a.text()) || texts.contains(b.text()) || a.text().equals(b.text())) continue;
            if (selected.size() + 2 > budget.maxCases() || used + cost > budget.maxBytes()) continue;
            selected.add(pair.support()); selected.add(pair.contrast()); used += cost;
            covered.addAll(signatures);
            cases.add(a.caseId()); cases.add(b.caseId()); texts.add(a.text()); texts.add(b.text());
        }
        var gaps = new ArrayList<String>();
        if (selected.isEmpty()) gaps.add(pairs.isEmpty() ? "没有经审核且条件适用的完整对比配对" : "完整配对超过预算或重复内容限制");
        for (var entry : bound.entrySet()) if (entry.getValue().applicability().equals("UNKNOWN")) gaps.add("条件未知：" + entry.getKey());
        return RetrievalSupport.bundle("D1", facts, target, pool, budget, selected, gaps);
    }
    private boolean isPair(Candidate a, Candidate b) {
        if (a.caseId().equals(b.caseId()) || !a.pairId().equals(b.pairId()) || !a.mechanism().equals(b.mechanism())
            || !a.riskKind().equals(b.riskKind()) || a.conditions().size() != b.conditions().size()) return false;
        var right = new HashMap<String, Boolean>();
        for (Condition c : b.conditions()) right.put(c.predicate() + ":" + c.subject() + ":" + c.resource(), c.expected());
        boolean difference = false;
        for (Condition c : a.conditions()) {
            Boolean expected = right.get(c.predicate() + ":" + c.subject() + ":" + c.resource());
            if (expected == null) return false;
            difference |= !expected.equals(c.expected());
        }
        return difference;
    }
}
