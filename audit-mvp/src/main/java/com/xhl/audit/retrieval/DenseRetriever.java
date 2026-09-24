package com.xhl.audit.retrieval;

import java.util.*;
import static com.xhl.audit.retrieval.RetrievalData.*;

/** 不按条件过滤的向量相似度对照。 */
public class DenseRetriever implements RetrievalStrategy {
    protected boolean hybrid() {return false;}
    protected String name() {return "DENSE";}
    @Override public EvidenceBundle retrieve(ProgramFacts facts, Target target, CandidatePool pool, Budget budget) {
        RetrievalSupport.validate(facts, target, pool, budget);
        var selected = new ArrayList<Selection>();
        var cases = new HashSet<String>();
        int used = 0;
        for (Candidate candidate : pool.candidates().stream().sorted(RetrievalSupport.ranking(hybrid())).toList()) {
            if (cases.contains(candidate.caseId())) continue;
            var row = new Selection(candidate, "RETRIEVED", new ConditionBinder().bind(facts, target, candidate));
            if (selected.size() < budget.maxCases() && used + RetrievalSupport.bytes(row) <= budget.maxBytes()) {
                selected.add(row); cases.add(candidate.caseId()); used += RetrievalSupport.bytes(row);
            }
        }
        return RetrievalSupport.bundle(name(), facts, target, pool, budget, selected, selected.isEmpty() ? List.of("候选为空或预算不足") : List.of());
    }
}
