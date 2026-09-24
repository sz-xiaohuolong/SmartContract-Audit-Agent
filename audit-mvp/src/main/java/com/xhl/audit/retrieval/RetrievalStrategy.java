package com.xhl.audit.retrieval;

import static com.xhl.audit.retrieval.RetrievalData.*;

/** 四种策略替换点：相同程序事实、候选池、目标与上下文预算。 */
public interface RetrievalStrategy {
    EvidenceBundle retrieve(ProgramFacts facts, Target target, CandidatePool pool, Budget budget);
}
