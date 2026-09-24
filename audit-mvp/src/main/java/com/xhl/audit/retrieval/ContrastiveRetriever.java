package com.xhl.audit.retrieval;

import java.util.*;
import static com.xhl.audit.retrieval.RetrievalData.*;

/** 普通正反例对照：同机制取高分两类，不检查条件差异或审核配对 ID。 */
public final class ContrastiveRetriever implements RetrievalStrategy {
    @Override public EvidenceBundle retrieve(ProgramFacts facts, Target target, CandidatePool pool, Budget budget) {
        RetrievalSupport.validate(facts, target, pool, budget);
        var selected = new ArrayList<Selection>();
        var roles = new HashSet<String>();
        int used = 0;
        for (Candidate candidate : pool.candidates().stream().sorted(RetrievalSupport.ranking(false)).toList()) {
            if (!candidate.mechanism().equals(target.mechanism()) || roles.contains(candidate.role())) continue;
            var row = new Selection(candidate, "RETRIEVED", new ConditionBinder().bind(facts, target, candidate));
            if (selected.size() < budget.maxCases() && used + RetrievalSupport.bytes(row) <= budget.maxBytes()) {
                selected.add(row); roles.add(candidate.role()); used += RetrievalSupport.bytes(row);
            }
        }
        return RetrievalSupport.bundle("CONTRASTIVE", facts, target, pool, budget, selected,
            roles.size() < 2 ? List.of("普通正反例未覆盖两种角色") : List.of());
    }
}
